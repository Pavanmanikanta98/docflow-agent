"""
Evaluation script for DeepEval GEval judge on contract free-text fields.

This script is NOT run automatically by CI (real LLM calls, costs credits).
Run manually with: `uv run python -m backend.tests.evaluation.run_judge_eval`

It:
1. Loads contract golden cases.
2. Builds calibration controls for both scoped fields (termination_clause,
   key_obligations): a positive control (a faithful, reworded restatement of
   the expected text - not a verbatim copy, since the judge must tolerate
   rewording, not just string equality) and a negative control (a material
   change: a changed notice period / duration, or a dropped obligation).
3. Runs each control through the REAL GEval metric (backend.tests.evaluation
   .judge_calibration.build_termination_clause_judge /
   build_key_obligations_judge) 3 times, to get mean + spread.
4. Checks calibration_passed() (all positives score >= threshold, all
   negatives score < threshold).
5. Runs extraction + the same GEval metrics + the fuzzy matcher on every
   golden contract case, side by side.
6. Writes evals/results/<date>-judge-<model>.json.

headline_metric is "geval" only if calibration passed; otherwise
"fuzzy_fallback" - per ADR 008, this script does not get to declare the
judge trustworthy by assertion.

Checkpoint/resume: every completed step (a calibration run or a scored
case) is flushed to evals/results/.judge_eval_checkpoint.json immediately,
so re-running after an interruption resumes instead of re-spending quota.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from deepeval.test_case import LLMTestCase
from pydantic_ai.exceptions import ModelHTTPError

from backend.agents.extractor import extract_fields
from backend.core.config import settings
from backend.core.db import redis_client
from backend.core.deepeval_judge import LLMClientBasedJudge
from backend.core.llm import llm_client
from backend.core.token_budget import CapacityWaitError
from backend.plugins.contract import ContractPlugin
from backend.tests.evaluation.conftest import fuzzy_match, load_golden
from backend.tests.evaluation.judge_calibration import (
    ControlResult,
    build_key_obligations_judge,
    build_termination_clause_judge,
    calibration_passed,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

RESULTS_DIR = Path(__file__).resolve().parents[3] / "evals" / "results"
CHECKPOINT_FILE = RESULTS_DIR / ".judge_eval_checkpoint.json"

JUDGE_THRESHOLD = 0.5
JUDGE_RUNS_PER_CONTROL = 3
CALIBRATION_CASE_COUNT = 2  # keep the live cost small; see docs/deepeval.md

MAX_CAPACITY_RETRIES = 20
CAPACITY_RETRY_BUFFER_SECONDS = 1.0
CAPACITY_RETRY_MAX_WAIT_SECONDS = 90.0

# A crude, dependency-free "faithful reword": preserves every obligation and
# every number/date, just swaps a few words for synonyms. Not a real
# paraphrase, but changes the wording without touching the content, which is
# exactly what a positive control needs to test (the judge must not require
# near-verbatim phrasing).
_SYNONYMS = {
    "shall": "will",
    "must": "is required to",
    "terminate": "end",
    "termination": "ending",
    "obligation": "responsibility",
    "obligations": "responsibilities",
    "party": "entity",
    "provide": "furnish",
    "agreement": "contract",
}


def _faithful_reword(text: str) -> str:
    reworded = text
    for old, new in _SYNONYMS.items():
        reworded = re.sub(rf"\b{old}\b", new, reworded, flags=re.IGNORECASE)
    return reworded


_DURATION_RE = re.compile(r"\b(\d+)\s*(day|days|month|months|year|years)\b", re.I)


def _material_change(text: str) -> str:
    """A negative control: change a duration if one is found (a changed
    notice period is the canonical material change for a termination
    clause); otherwise drop the back half of the text (likely dropping a
    condition), which is the generic fallback when no duration is present.
    """
    match = _DURATION_RE.search(text)
    if match:
        changed = str(int(match.group(1)) + 1000)
        return text[: match.start(1)] + changed + text[match.end(1) :]
    midpoint = max(1, len(text) // 2)
    return text[:midpoint]


def load_checkpoint() -> dict[str, Any]:
    if not CHECKPOINT_FILE.exists():
        return {}
    try:
        return json.loads(CHECKPOINT_FILE.read_text())
    except json.JSONDecodeError as exc:
        logger.warning(f"Failed to load checkpoint: {exc}, starting fresh")
        return {}


def save_checkpoint(checkpoint: dict[str, Any]) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_file = CHECKPOINT_FILE.with_suffix(".tmp")
    tmp_file.write_text(json.dumps(checkpoint))
    tmp_file.replace(CHECKPOINT_FILE)


async def _with_capacity_retry(coro_fn):
    """Retry a call that hits either the local Redis token bucket
    (CapacityWaitError, ADR 006) or a real Groq 429 (ModelHTTPError),
    sleeping for however long the failure itself says to wait.

    Free-tier capacity waits are routine, not exceptional - letting one
    crash the whole process (relying on scripts/run_eval_resilient.sh to
    restart from checkpoint) works but throws away a full process restart
    for what is often just an 8-second wait.
    """
    for _attempt in range(MAX_CAPACITY_RETRIES):
        try:
            return await coro_fn()
        except CapacityWaitError as exc:
            await asyncio.sleep(
                min(exc.wait_seconds, CAPACITY_RETRY_MAX_WAIT_SECONDS)
                + CAPACITY_RETRY_BUFFER_SECONDS
            )
        except ModelHTTPError as exc:
            if exc.status_code != 429:
                raise
            wait = exc.retry_after or CAPACITY_RETRY_MAX_WAIT_SECONDS
            await asyncio.sleep(
                min(wait, CAPACITY_RETRY_MAX_WAIT_SECONDS)
                + CAPACITY_RETRY_BUFFER_SECONDS
            )
    raise RuntimeError(f"Exceeded {MAX_CAPACITY_RETRIES} capacity retries")


async def _judge_score(metric: Any, actual: str, expected: str) -> float:
    """Run one GEval measurement and return its score (0.0-1.0)."""
    test_case = LLMTestCase(input="", actual_output=actual, expected_output=expected)
    return await _with_capacity_retry(lambda: metric.a_measure(test_case))


async def _run_control(
    metric: Any,
    case_id: str,
    field_name: str,
    is_positive: bool,
    candidate: str,
    expected: str,
    checkpoint: dict[str, Any],
) -> ControlResult:
    step_key = f"calibration_{field_name}_{'pos' if is_positive else 'neg'}_{case_id}"
    cached = checkpoint.get(step_key)
    if cached is not None:
        return ControlResult(
            case_id=case_id,
            is_positive=is_positive,
            candidate=candidate,
            expected=expected,
            scores=cached["scores"],
        )

    scores = []
    for run_num in range(JUDGE_RUNS_PER_CONTROL):
        try:
            scores.append(await _judge_score(metric, candidate, expected))
        except Exception as exc:  # noqa: BLE001 - real API errors, various shapes
            logger.error(f"{step_key} run {run_num}: {exc}")
            raise
    result = ControlResult(
        case_id=case_id,
        is_positive=is_positive,
        candidate=candidate,
        expected=expected,
        scores=scores,
    )
    checkpoint[step_key] = {
        "field": field_name,
        "is_positive": is_positive,
        "scores": scores,
        "mean": result.mean_score,
        "spread": result.spread,
    }
    save_checkpoint(checkpoint)
    return result


async def run_calibration(
    termination_judge: Any,
    obligations_judge: Any,
    checkpoint: dict[str, Any],
) -> list[ControlResult]:
    """Positive + negative controls for both scoped fields, on the first
    CALIBRATION_CASE_COUNT contract golden cases."""
    cases = load_golden("contracts.json")[:CALIBRATION_CASE_COUNT]
    results: list[ControlResult] = []

    for case in cases:
        case_id = case["case_id"]
        expected = case["expected"]

        termination_clause = expected.get("termination_clause")
        if termination_clause:
            results.append(
                await _run_control(
                    termination_judge,
                    case_id,
                    "termination_clause",
                    True,
                    _faithful_reword(termination_clause),
                    termination_clause,
                    checkpoint,
                )
            )
            results.append(
                await _run_control(
                    termination_judge,
                    case_id,
                    "termination_clause",
                    False,
                    _material_change(termination_clause),
                    termination_clause,
                    checkpoint,
                )
            )

        obligations = expected.get("key_obligations")
        if obligations:
            expected_text = "; ".join(obligations)
            positive_text = "; ".join(_faithful_reword(o) for o in obligations)
            results.append(
                await _run_control(
                    obligations_judge,
                    case_id,
                    "key_obligations",
                    True,
                    positive_text,
                    expected_text,
                    checkpoint,
                )
            )
            if len(obligations) >= 2:
                negative_text = "; ".join(obligations[:-1])
                results.append(
                    await _run_control(
                        obligations_judge,
                        case_id,
                        "key_obligations",
                        False,
                        negative_text,
                        expected_text,
                        checkpoint,
                    )
                )

    return results


async def score_case(
    case: dict,
    termination_judge: Any,
    obligations_judge: Any,
    model: Any,
    checkpoint: dict[str, Any],
) -> dict[str, Any]:
    case_id = case["case_id"]
    step_key = f"case_{case_id}"
    cached = checkpoint.get(step_key)
    if cached is not None:
        return cached

    plugin = ContractPlugin()
    extracted = await _with_capacity_retry(
        lambda: extract_fields(
            raw_text=case["input"],
            plugin=plugin,
            model=model,
            redis_client=redis_client,
        )
    )
    expected = case["expected"]

    fuzzy_scores = {
        "termination_clause": fuzzy_match(
            extracted.termination_clause, expected.get("termination_clause")
        ),
    }
    expected_obligations = expected.get("key_obligations") or []
    actual_obligations = extracted.key_obligations or []
    fuzzy_scores["key_obligations_overlap"] = (
        len(set(actual_obligations) & set(expected_obligations))
        / len(expected_obligations)
        if expected_obligations
        else None
    )

    geval_scores: dict[str, float | None] = {
        "termination_clause": None,
        "key_obligations": None,
    }
    if expected.get("termination_clause") and extracted.termination_clause:
        geval_scores["termination_clause"] = await _judge_score(
            termination_judge,
            extracted.termination_clause,
            expected["termination_clause"],
        )
    if expected_obligations and actual_obligations:
        geval_scores["key_obligations"] = await _judge_score(
            obligations_judge,
            "; ".join(actual_obligations),
            "; ".join(expected_obligations),
        )

    result = {
        "case_id": case_id,
        "fuzzy_score": fuzzy_scores,
        "geval_score": geval_scores,
    }
    checkpoint[step_key] = result
    save_checkpoint(checkpoint)
    return result


async def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint = load_checkpoint()

    judge_model_wrapper = LLMClientBasedJudge(
        model_name="openai/gpt-oss-120b", redis_client=redis_client
    )
    termination_judge = build_termination_clause_judge(
        judge_model_wrapper, threshold=JUDGE_THRESHOLD
    )
    obligations_judge = build_key_obligations_judge(
        judge_model_wrapper, threshold=JUDGE_THRESHOLD
    )

    logger.info("Running calibration controls...")
    controls = await run_calibration(termination_judge, obligations_judge, checkpoint)
    calib_passed = calibration_passed(controls, threshold=JUDGE_THRESHOLD)
    logger.info(f"Calibration: {'PASSED' if calib_passed else 'FAILED'}")

    headline_metric = "geval" if calib_passed else "fuzzy_fallback"

    logger.info("Scoring all contract golden cases...")
    extraction_model = llm_client.get_model()
    all_contract_cases = load_golden("contracts.json")
    cases_data = []
    case_failures: list[str] = []
    for case in all_contract_cases:
        try:
            cases_data.append(
                await score_case(
                    case,
                    termination_judge,
                    obligations_judge,
                    extraction_model,
                    checkpoint,
                )
            )
        except Exception as exc:  # noqa: BLE001 - one bad case must not crash the run
            case_failures.append(case["case_id"])
            logger.error(f"Failed to score {case['case_id']}: {exc}")

    results_data = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "extraction_model": settings.llm_model,
        "judge_model": judge_model_wrapper.get_model_name(),
        "calibration": {
            "passed": calib_passed,
            "threshold": JUDGE_THRESHOLD,
            "runs_per_control": JUDGE_RUNS_PER_CONTROL,
            "controls": [
                {
                    "case_id": c.case_id,
                    "is_positive": c.is_positive,
                    "mean_score": c.mean_score,
                    "spread": c.spread,
                    "scores": c.scores,
                }
                for c in controls
            ],
        },
        "headline_metric": headline_metric,
        "cases": cases_data,
        "case_failures": case_failures,
    }

    model_slug = settings.llm_model.replace("/", "-")
    out_path = RESULTS_DIR / f"{results_data['date']}-judge-{model_slug}.json"
    out_path.write_text(json.dumps(results_data, indent=2) + "\n")
    logger.info(f"Wrote {out_path}")
    logger.info(f"Headline metric: {headline_metric}")
    if case_failures:
        logger.warning(f"{len(case_failures)} case(s) failed to score: {case_failures}")

    # Only clear on a fully clean run - calibration passing is not enough if
    # cases are still missing; keep the checkpoint so a re-run resumes
    # instead of re-spending quota on calibration and every already-scored
    # case.
    if not case_failures and len(cases_data) == len(all_contract_cases):
        CHECKPOINT_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())
