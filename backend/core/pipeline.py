"""
LangGraph pipeline: Parser → Extractor → Route.

State flows through nodes. Each node reads the current state dict,
does its work, and returns an updated copy. LangGraph wires the routing.

Graph shape:
    START → parse → [conditional] → extract → [conditional] → completed
                                             → awaiting_review
                  → failed                  → END
"""

from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.agents.parser import extract_text
from backend.agents.validator import validate_fields
from backend.core.config import settings
from backend.core.db import redis_client
from backend.core.llm import llm_client

# ---------------------------------------------------------------------------
# State — the single dict that travels through every node
# ---------------------------------------------------------------------------

class DocFlowState(TypedDict):
    """All data the pipeline needs and produces."""
    document_id: int
    tenant_id: str                # Carried for the DB row; unused by the nodes
    document_type: str
    mime_type: str                # "application/pdf" | "image/png" | "image/jpeg"
    file_bytes: bytes             # Raw upload bytes read from Redis
    raw_text: str                 # Filled by parse_node
    extraction_results: Optional[dict]    # Filled by extract_node
    confidence_score: Optional[float]     # Filled by validate_node (overall)
    field_confidences: Optional[dict]     # Filled by validate_node (per-field)
    review_reasons: Optional[list[str]]   # Why a human is needed (validate_node)
    human_review_required: Optional[bool]  # Set by awaiting_review_node
    # "processing" → "completed" | "awaiting_review" | "failed"
    status: str
    error: Optional[str]          # Only populated on failure


# ---------------------------------------------------------------------------
# Nodes — each is a pure async function: state → updated state
# ---------------------------------------------------------------------------

async def parse_node(state: DocFlowState) -> DocFlowState:
    """
    Node 1: Extract raw text from the uploaded PDF or image.
    If no text can be extracted (text layer and OCR both empty), marks state as failed.

    If `raw_text` is already populated (the worker pre-parses every document
    once — ADR 006 — to decide whether it needs chunking), this is a no-op:
    parsing never runs twice.
    """
    if state.get("raw_text"):
        return state
    try:
        raw_text = extract_text(state["file_bytes"], state["mime_type"])
    except ValueError as exc:
        return {**state, "status": "failed", "error": str(exc)}
    if not raw_text.strip():
        return {
            **state,
            "status": "failed",
            "error": "No text could be extracted (text layer and OCR both empty)",
        }
    return {**state, "raw_text": raw_text}


def _resolve_model():
    """Return the model every node uses: the server key from .env."""
    return llm_client.get_model()


async def extract_node(state: DocFlowState) -> DocFlowState:
    """
    Node 2: Send raw text to LLM via pydantic-ai.
    """

    from backend.agents.extractor import extract_fields
    from backend.plugins import get_plugin

    plugin = get_plugin(state["document_type"])
    model = _resolve_model()

    fields = await extract_fields(
        state["raw_text"], plugin, model=model, redis_client=redis_client
    )
    return {
        **state,
        "extraction_results": fields.model_dump(exclude={"confidence_score"}),
    }


def resolve_validation_outcome(
    validation, confidence_threshold: float, extra_reasons: Optional[list[str]] = None
) -> tuple[str, list[str]]:
    """The single place that turns a ValidatorOutput into (status, reasons).

    Shared by the normal (LangGraph) path and the chunked path
    (`backend.queue.worker`) so a chunked document is routed by exactly the
    same rules as a single-request one — a math-mismatch or low-confidence
    gate does not mean something different depending on how the document
    was split.
    """
    reasons = list(validation.review_reasons) + list(extra_reasons or [])
    if validation.status != "human_review" and (
        validation.overall_confidence < confidence_threshold
    ):
        reasons.append(f"low_confidence:{validation.overall_confidence:.2f}")

    if validation.status == "human_review" or reasons:
        status = "awaiting_review"
    elif validation.overall_confidence >= confidence_threshold:
        status = "completed"
    else:
        status = "awaiting_review"

    return status, reasons


async def validate_node(state: DocFlowState) -> DocFlowState:
    """
    Node 3: Independent per-field confidence scoring.
    """
    model = _resolve_model()
    validation = await validate_fields(
        raw_text=state["raw_text"],
        extracted_fields=state["extraction_results"],
        model=model,
        redis_client=redis_client,
    )
    status, reasons = resolve_validation_outcome(
        validation, settings.confidence_threshold
    )

    return {
        **state,
        "confidence_score": validation.overall_confidence,
        "field_confidences": validation.field_scores,
        "review_reasons": reasons,
        "status": status,
    }


async def completed_node(state: DocFlowState) -> DocFlowState:
    """Terminal node: confidence was high enough."""
    return {**state, "status": "completed"}


async def awaiting_review_node(state: DocFlowState) -> DocFlowState:
    """Terminal node: confidence too low — flag for human review."""
    return {**state, "status": "awaiting_review", "human_review_required": True}


async def failed_node(state: DocFlowState) -> DocFlowState:
    """Terminal node: something went wrong upstream."""
    return {**state, "status": "failed"}


# ---------------------------------------------------------------------------
# Conditional routing functions — return the NAME of the next node
# ---------------------------------------------------------------------------

def route_after_parse(state: DocFlowState) -> str:
    """After parsing: if failed (scanned PDF), skip extraction."""
    if state.get("status") == "failed":
        return "failed"
    return "extract"


def route_after_validate(state: DocFlowState) -> str:
    """After validation: use the status `resolve_validation_outcome` already
    decided in validate_node — the single source of truth for this decision
    (shared with the chunked path in backend.queue.worker)."""
    return state.get("status") or "awaiting_review"


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

_builder = StateGraph(DocFlowState)

# Register nodes
_builder.add_node("parse", parse_node)
_builder.add_node("extract", extract_node)
_builder.add_node("validate", validate_node)   # Agent 3 — new
_builder.add_node("completed", completed_node)
_builder.add_node("awaiting_review", awaiting_review_node)
_builder.add_node("failed", failed_node)

# Wire edges
_builder.add_edge(START, "parse")
_builder.add_conditional_edges("parse", route_after_parse, {
    "extract": "extract",
    "failed": "failed",
})
_builder.add_edge("extract", "validate")   # always validate after extract
_builder.add_conditional_edges("validate", route_after_validate, {
    "completed": "completed",
    "awaiting_review": "awaiting_review",
})
_builder.add_edge("completed", END)
_builder.add_edge("awaiting_review", END)
_builder.add_edge("failed", END)

# Compile — this is what worker.py imports and calls
pipeline = _builder.compile()
