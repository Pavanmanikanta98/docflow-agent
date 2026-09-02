"""
LangGraph pipeline: Parser → Extractor → Route.

State flows through nodes. Each node reads the current state dict,
does its work, and returns an updated copy. LangGraph wires the routing.

Graph shape:
    START → parse → [conditional] → extract → [conditional] → completed
                                             → awaiting_review
                  → failed                  → END
"""

from typing import TypedDict, Optional

from langgraph.graph import StateGraph, START, END

from backend.agents.parser import extract_text_from_pdf
from backend.agents.validator import validate_fields
from backend.core.config import settings
from backend.core.llm import llm_client


# ---------------------------------------------------------------------------
# State — the single dict that travels through every node
# ---------------------------------------------------------------------------

class DocFlowState(TypedDict):
    """All data the pipeline needs and produces."""
    document_id: int
    tenant_id: str                # Needed for BYOK key lookup
    document_type: str
    file_bytes: bytes             # Raw PDF bytes read from Redis
    raw_text: str                 # Filled by parse_node
    extraction_results: Optional[dict]    # Filled by extract_node
    confidence_score: Optional[float]     # Filled by validate_node (overall)
    field_confidences: Optional[dict]     # Filled by validate_node (per-field)
    human_review_required: Optional[bool]  # Set by awaiting_review_node
    status: str                   # "processing" → "completed" | "awaiting_review" | "failed"
    error: Optional[str]          # Only populated on failure


# ---------------------------------------------------------------------------
# Nodes — each is a pure async function: state → updated state
# ---------------------------------------------------------------------------

async def parse_node(state: DocFlowState) -> DocFlowState:
    """
    Node 1: Extract raw text from PDF bytes.
    If the PDF is scanned (0 chars extracted), marks state as failed.
    """
    raw_text = extract_text_from_pdf(state["file_bytes"])
    if not raw_text.strip():
        return {**state, "status": "failed", "error": "Parser returned empty text — scanned PDF?"}
    return {**state, "raw_text": raw_text}


def _resolve_model(document_id: int):
    """Resolve the LLM model for this extraction request.

    Priority order:
      1. Temp key in Redis (user provided X-LLM-Key header at upload time)
      2. Global fallback (.env GROQ_API_KEY)

    The key is read but NOT deleted here — both extract_node and validate_node
    call this function and need the same key. The worker deletes it once the
    pipeline finishes (success or failure paths in worker.py). The 1h Redis
    TTL is the safety net if cleanup is missed.
    """
    from backend.core.db import redis_client

    # Check for user-provided key (stored temporarily during upload)
    temp_key = redis_client.get(f"llm_key:{document_id}")
    if temp_key:
        raw_key = temp_key.decode() if isinstance(temp_key, bytes) else temp_key
        return llm_client.get_model(api_key=raw_key)

    # No user key — use global .env defaults
    return llm_client.get_model()


async def extract_node(state: DocFlowState) -> DocFlowState:
    """
    Node 2: Send raw text to LLM via pydantic-ai.
    Resolves tenant's BYOK key if available, otherwise falls back to .env.
    """

    from backend.plugins import get_plugin
    from backend.agents.extractor import extract_fields

    plugin = get_plugin(state["document_type"])
    model = _resolve_model(state["document_id"])

    fields = await extract_fields(state["raw_text"], plugin, model=model)
    return {
        **state,
        "extraction_results": fields.model_dump(exclude={"confidence_score"}),
    }


async def validate_node(state: DocFlowState) -> DocFlowState:
    """
    Node 3: Independent per-field confidence scoring.
    Uses tenant's BYOK key if available, otherwise falls back to .env.
    """
    model = _resolve_model(state["document_id"])
    validation = await validate_fields(
        raw_text=state["raw_text"],
        extracted_fields=state["extraction_results"],
        model=model,
    )
    return {
        **state,
        "confidence_score": validation.overall_confidence,
        "field_confidences": validation.field_scores,
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
    """After validation: route by the validator's overall_confidence score."""
    score = state.get("confidence_score") or 0.0
    if score >= settings.confidence_threshold:
        return "completed"
    return "awaiting_review"


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
