"""ADR 007 — OCR evaluation: synthetic degraded scans (Set A) + CORD-v2 (Set B).

Real LLM calls (extraction only) — this lives in backend/tests/evaluation/
per the project's rule that real API calls only happen here or in scripts/.

For each Set A case: extract from the clean golden text (the baseline) and
from each degraded variant's OCR output, then score both against the same
golden `expected` fields with the existing deterministic matchers
(backend/tests/evaluation/conftest.py). The GAP between the two — not
CER/WER alone — is "the cost of OCR" in the unit that actually matters.

Set B (CORD-v2) has no clean-text baseline (there is no digital text layer
for a photographed receipt): field accuracy is measured against CORD's own
labels for the fields it provides (see evals/datasets/README.md).

Usage (needs GROQ_API_KEY):
    uv run python -m backend.tests.evaluation.run_ocr_eval

This is a long run (~230 real calls; the free tier's 8000 TPM ceiling makes
it take hours, not minutes) with its own checkpoint/resume (see
CHECKPOINT_PATH below), so it tolerates being killed and re-run. To also
auto-restart on a crash instead of needing a manual re-run:
    scripts/run_eval_resilient.sh backend.tests.evaluation.run_ocr_eval

Writes evals/results/<date>-ocr-<model>.json and prints a markdown table.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import jiwer
import pytesseract
from PIL import Image
from pydantic_ai.exceptions import ModelHTTPError

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from backend.agents.extractor import extract_fields  # noqa: E402
from backend.core.config import settings  # noqa: E402
from backend.core.llm import llm_client  # noqa: E402
from backend.core.ocr_synthetic import (  # noqa: E402
    VARIANTS,
    make_variant,
    preprocess_grayscale_otsu_deskew,
)
from backend.plugins.contract import ContractPlugin  # noqa: E402
from backend.plugins.invoice import InvoicePlugin  # noqa: E402
from backend.tests.evaluation.conftest import (  # noqa: E402
    date_match,
    exact_match_number,
    fuzzy_match,
    list_overlap_score,
    load_golden,
)

RESULTS_DIR = REPO_ROOT / "evals" / "results"
DATASET_DIR = REPO_ROOT / "evals" / "datasets" / "cord-v2"

# A full run is ~230 real LLM calls and can take hours on the free tier —
# long enough to outlive a container restart. Every successful extraction is
# flushed here immediately, so resuming after a crash replays only the calls
# that hadn't succeeded yet, not the whole run.
CHECKPOINT_PATH = RESULTS_DIR / ".ocr_eval_checkpoint.json"
MAX_FULL_PASSES = 3  # self-heal transient failures (dropped connections,
# not just 429s) by re-running only what's still missing, up to this many
# times in one invocation, before leaving the rest for a resumed run.


def load_checkpoint(model_name: str) -> dict:
    """A checkpoint from a different model is discarded rather than reused,
    so switching models never silently mixes cached extractions."""
    if CHECKPOINT_PATH.exists():
        try:
            data = json.loads(CHECKPOINT_PATH.read_text())
        except json.JSONDecodeError:
            data = {}
        if data.get("model") == model_name:
            return data
    return {"model": model_name, "set_a": {}, "set_b": {}}


def save_checkpoint(checkpoint: dict) -> None:
    """Atomic write (temp file + rename) so a crash mid-save can't leave a
    truncated, unreadable checkpoint behind."""
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CHECKPOINT_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(checkpoint))
    tmp_path.replace(CHECKPOINT_PATH)


def clear_checkpoint() -> None:
    """Called once a run's results are written, so the next invocation
    starts a fresh evaluation instead of replaying a finished one."""
    CHECKPOINT_PATH.unlink(missing_ok=True)

RATE_LIMIT_DELAY_SECONDS = 2.2  # sequential calls, comfortably under 30 RPM
MAX_RETRIES = 8
RATE_LIMIT_MAX_BACKOFF_SECONDS = 90.0

_DURATION_RE = re.compile(
    r"^(?:(?P<hours>\d+)h)?(?:(?P<minutes>\d+)m)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)s)?(?:(?P<millis>\d+)ms)?$"
)


def _parse_duration_seconds(value: str) -> float | None:
    """Parse Groq's rate-limit reset duration strings, e.g. "1m26.4s", "585ms"
    (verified live: this is NOT plain seconds)."""
    match = _DURATION_RE.match(value.strip())
    if not match or not any(match.groups()):
        return None
    parts = match.groupdict()
    total = 0.0
    if parts["hours"]:
        total += int(parts["hours"]) * 3600
    if parts["minutes"]:
        total += int(parts["minutes"]) * 60
    if parts["seconds"]:
        total += float(parts["seconds"])
    if parts["millis"]:
        total += int(parts["millis"]) / 1000
    return total


def _rate_limit_wait_seconds(exc: Exception, fallback: float) -> float:
    """Prefer the server's own signal for how long to wait over a guess: the
    standard `Retry-After` header first, then Groq's `x-ratelimit-reset-*`
    duration headers (the actual binding constraint here is TPM, not RPM —
    a fixed backoff schedule gives up long before an 8000 TPM free-tier
    window actually clears)."""
    if isinstance(exc, ModelHTTPError) and exc.status_code == 429:
        if exc.retry_after is not None:
            return exc.retry_after + 1.0
        if exc.headers:
            candidates = [
                _parse_duration_seconds(exc.headers[key])
                for key in ("x-ratelimit-reset-tokens", "x-ratelimit-reset-requests")
                if key in exc.headers
            ]
            candidates = [c for c in candidates if c is not None]
            if candidates:
                return max(candidates) + 1.0
    return fallback

DATE_FIELDS = {"invoice_date", "due_date", "effective_date", "expiry_date"}
NUMBER_FIELDS = {"subtotal", "tax_amount", "total_amount", "contract_value"}
LIST_FIELDS = {"line_items", "key_obligations", "parties"}

SET_A_INVOICE_FIELDS = [
    "vendor_name",
    "invoice_number",
    "invoice_date",
    "due_date",
    "subtotal",
    "tax_amount",
    "total_amount",
    "line_items",
]
SET_A_CONTRACT_FIELDS = [
    "parties",
    "effective_date",
    "expiry_date",
    "contract_value",
    "termination_clause",
    "key_obligations",
]
SET_B_FIELDS = ["subtotal", "tax_amount", "total_amount", "line_items"]


def field_passes(field_name: str, actual: Any, expected: Any) -> bool:
    if expected is None:
        return actual is None
    if field_name in DATE_FIELDS:
        return date_match(actual, expected)
    if field_name in NUMBER_FIELDS:
        return exact_match_number(actual, expected)
    if field_name in LIST_FIELDS:
        return list_overlap_score(actual, expected) >= 0.6
    return fuzzy_match(actual, expected)


async def extract_with_backoff(raw_text: str, plugin) -> Any:
    """Resolve a fresh model (and httpx client) on every call — the
    production pipeline never reuses one model instance across LLM calls.

    Backoff is driven by the server's own rate-limit signal
    (`_rate_limit_wait_seconds`), not a fixed schedule: the binding
    constraint on the free tier is 8000 TPM, and a handful of sequential
    calls can exhaust a whole window, so waiting a guessed 2-35s and then
    giving up (the original bug here) fails almost every case in a long
    run even though the quota recovers within a minute."""
    delay = RATE_LIMIT_DELAY_SECONDS
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            model = llm_client.get_model()
            result = await extract_fields(raw_text, plugin, model=model)
            await asyncio.sleep(RATE_LIMIT_DELAY_SECONDS)
            return result
        except Exception as exc:  # noqa: BLE001 - real API errors, various shapes
            message = str(exc).lower()
            is_rate_limit = (
                (isinstance(exc, ModelHTTPError) and exc.status_code == 429)
                or "429" in message
                or "rate_limit" in message
                or "rate limit" in message
            )
            if not is_rate_limit:
                raise
            last_exc = exc
            wait = _rate_limit_wait_seconds(exc, fallback=delay)
            wait = min(wait, RATE_LIMIT_MAX_BACKOFF_SECONDS)
            await asyncio.sleep(wait)
            delay = min(delay * 2, RATE_LIMIT_MAX_BACKOFF_SECONDS)
    raise RuntimeError(f"Exceeded {MAX_RETRIES} retries for extraction") from last_exc


def ocr_image(image: Image.Image, preprocess: bool = False) -> str:
    if preprocess:
        image = preprocess_grayscale_otsu_deskew(image)
    return pytesseract.image_to_string(image)


def score_case(
    fields_dict: dict, expected: dict, field_names: list[str]
) -> tuple[int, int]:
    passed = 0
    for field_name in field_names:
        actual_value = fields_dict.get(field_name)
        expected_value = expected.get(field_name)
        if field_passes(field_name, actual_value, expected_value):
            passed += 1
    return passed, len(field_names)


def _clean_cases(filename: str) -> list[dict]:
    return [c for c in load_golden(filename) if c.get("difficulty") == "clean"]


async def run_set_a(preprocess: bool, checkpoint: dict) -> dict:
    invoices = _clean_cases("invoices.json")
    contracts = _clean_cases("contracts.json")

    invoice_plugin = InvoicePlugin()
    contract_plugin = ContractPlugin()

    variant_results: dict[str, dict] = {
        name: {"cer": [], "wer": [], "field_accuracy": []} for name in VARIANTS
    }
    text_layer_accuracy: list[float] = []
    extraction_failures: list[str] = []

    for case, plugin, field_names in (
        [(c, invoice_plugin, SET_A_INVOICE_FIELDS) for c in invoices]
        + [(c, contract_plugin, SET_A_CONTRACT_FIELDS) for c in contracts]
    ):
        golden_text = case["input"]
        expected = case["expected"]
        case_id = case["case_id"]

        baseline_key = f"{case_id}:text_layer"
        baseline_dict = checkpoint["set_a"].get(baseline_key)
        if baseline_dict is None:
            try:
                baseline_fields = await extract_with_backoff(golden_text, plugin)
            except Exception as exc:  # noqa: BLE001 - a real API error, various shapes
                extraction_failures.append(baseline_key)
                print(f"  [Set A] extraction failed for {case_id} (text layer): {exc}")
                continue
            baseline_dict = baseline_fields.model_dump(exclude={"confidence_score"})
            checkpoint["set_a"][baseline_key] = baseline_dict
            save_checkpoint(checkpoint)
        passed, total = score_case(baseline_dict, expected, field_names)
        text_layer_accuracy.append(passed / total)

        for variant_name in VARIANTS:
            image = make_variant(golden_text, variant_name)
            ocr_text = ocr_image(image, preprocess=preprocess)

            cer = jiwer.cer(golden_text, ocr_text) if ocr_text.strip() else 1.0
            wer = jiwer.wer(golden_text, ocr_text) if ocr_text.strip() else 1.0
            variant_results[variant_name]["cer"].append(cer)
            variant_results[variant_name]["wer"].append(wer)

            variant_key = f"{case_id}:{variant_name}"
            variant_dict = checkpoint["set_a"].get(variant_key)
            if variant_dict is None:
                try:
                    variant_fields = await extract_with_backoff(ocr_text, plugin)
                except Exception as exc:  # noqa: BLE001
                    extraction_failures.append(variant_key)
                    msg = f"{case_id}/{variant_name}: {exc}"
                    print(f"  [Set A] extraction failed for {msg}")
                    continue
                variant_dict = variant_fields.model_dump(exclude={"confidence_score"})
                checkpoint["set_a"][variant_key] = variant_dict
                save_checkpoint(checkpoint)
            v_passed, v_total = score_case(variant_dict, expected, field_names)
            variant_results[variant_name]["field_accuracy"].append(v_passed / v_total)

    text_layer_avg = sum(text_layer_accuracy) / len(text_layer_accuracy)

    summary = {
        "text_layer_field_accuracy": text_layer_avg,
        "extraction_failures": extraction_failures,
        "variants": {},
    }
    for variant_name, data in variant_results.items():
        if not data["field_accuracy"]:
            summary["variants"][variant_name] = {
                "cer": sum(data["cer"]) / len(data["cer"]),
                "wer": sum(data["wer"]) / len(data["wer"]),
                "field_accuracy": None,
                "accuracy_gap_vs_text_layer": None,
            }
            continue
        avg_cer = sum(data["cer"]) / len(data["cer"])
        avg_wer = sum(data["wer"]) / len(data["wer"])
        avg_field_accuracy = sum(data["field_accuracy"]) / len(data["field_accuracy"])
        summary["variants"][variant_name] = {
            "cer": avg_cer,
            "wer": avg_wer,
            "field_accuracy": avg_field_accuracy,
            "accuracy_gap_vs_text_layer": text_layer_avg - avg_field_accuracy,
        }
    return summary


async def run_set_b(preprocess: bool, checkpoint: dict) -> dict:
    labels = json.loads((DATASET_DIR / "labels.json").read_text())
    plugin = InvoicePlugin()

    per_case_accuracy: list[float] = []
    extraction_failures: list[str] = []
    for record in labels:
        image_path = DATASET_DIR / "images" / record["image_file"]
        image = Image.open(image_path)
        ocr_text = ocr_image(image, preprocess=preprocess)

        record_id = record["id"]
        fields_dict = checkpoint["set_b"].get(record_id)
        if fields_dict is None:
            try:
                fields = await extract_with_backoff(ocr_text, plugin)
            except Exception as exc:  # noqa: BLE001 - a real scan's OCR text can be
                # garbled enough that the model refuses structured output
                # entirely; one bad case must not crash the whole eval run.
                extraction_failures.append(record_id)
                print(f"  [Set B] extraction failed for {record_id}: {exc}")
                continue
            fields_dict = fields.model_dump(exclude={"confidence_score"})
            checkpoint["set_b"][record_id] = fields_dict
            save_checkpoint(checkpoint)

        expected = record["labels"]
        passed, total = score_case(fields_dict, expected, SET_B_FIELDS)
        per_case_accuracy.append(passed / total)

    return {
        "extraction_failures": extraction_failures,
        "cases": len(labels),
        "cases_scored": len(per_case_accuracy),
        "field_accuracy": (
            sum(per_case_accuracy) / len(per_case_accuracy)
            if per_case_accuracy
            else None
        ),
        "fields_scored": SET_B_FIELDS,
    }


def render_markdown(report: dict) -> str:
    lines = [f"# OCR evaluation — {report['date']} ({report['model']})", ""]
    tesseract_line = (
        f"Tesseract {report['tesseract_version']}, PSM {report['tesseract_psm']}."
    )
    lines.append(tesseract_line)
    exp = report["preprocessing_experiment"]
    cer_none = exp["avg_cer_no_preprocessing"]
    cer_pre = exp["avg_cer_with_preprocessing"]
    lines.append(
        f"Preprocessing (grayscale+Otsu+deskew): CER {cer_none:.3f} (none) vs "
        f"{cer_pre:.3f} (preprocessed), improvement {exp['improvement']:+.3f} — "
        f"**kept: {report['preprocessing_kept']}**"
    )
    lines.append("")
    lines.append("## Set A — synthetic degraded scans")
    lines.append(
        f"Text-layer baseline field accuracy: "
        f"{report['set_a']['text_layer_field_accuracy']:.1%}"
    )
    lines.append("")
    if report["set_a"].get("extraction_failures"):
        lines.append(
            f"Extraction failures (excluded from the averages below): "
            f"{', '.join(report['set_a']['extraction_failures'])}"
        )
    lines.append("| Variant | CER | WER | Field accuracy | Gap vs text layer |")
    lines.append("|---|---|---|---|---|")
    for variant, row in report["set_a"]["variants"].items():
        field_acc = row["field_accuracy"]
        accuracy = "n/a" if field_acc is None else f"{field_acc:.1%}"
        gap = (
            "n/a"
            if row["accuracy_gap_vs_text_layer"] is None
            else f"{row['accuracy_gap_vs_text_layer']:.1%}"
        )
        lines.append(
            f"| {variant} | {row['cer']:.3f} | {row['wer']:.3f} | {accuracy} | {gap} |"
        )
    lines.append("")
    lines.append("## Set B — CORD-v2 (real scans)")
    lines.append(
        f"{report['set_b']['cases']} cases ({report['set_b']['cases_scored']} scored), "
        f"fields scored: {', '.join(report['set_b']['fields_scored'])}"
    )
    if report["set_b"].get("extraction_failures"):
        lines.append(
            f"Extraction failures (excluded): "
            f"{', '.join(report['set_b']['extraction_failures'])}"
        )
    set_b_accuracy = report["set_b"]["field_accuracy"]
    accuracy_text = "n/a" if set_b_accuracy is None else f"{set_b_accuracy:.1%}"
    lines.append(f"Field accuracy: {accuracy_text}")
    return "\n".join(lines)


def run_preprocessing_experiment() -> dict:
    """CER/WER only — no LLM calls needed to compare OCR quality, so this
    runs cheaply as its own step rather than doubling the real API cost of
    the full field-accuracy run below. Decides `preprocess` for run_set_a/b.
    """
    invoices = _clean_cases("invoices.json")
    contracts = _clean_cases("contracts.json")
    texts = [c["input"] for c in invoices + contracts]

    def average_cer(preprocess: bool) -> float:
        scores = []
        for text in texts:
            for variant_name in VARIANTS:
                image = make_variant(text, variant_name)
                ocr_text = ocr_image(image, preprocess=preprocess)
                scores.append(jiwer.cer(text, ocr_text) if ocr_text.strip() else 1.0)
        return sum(scores) / len(scores)

    cer_none = average_cer(preprocess=False)
    cer_preprocessed = average_cer(preprocess=True)
    improvement = cer_none - cer_preprocessed

    return {
        "avg_cer_no_preprocessing": cer_none,
        "avg_cer_with_preprocessing": cer_preprocessed,
        "improvement": improvement,
        # Keep it only if it measurably helps — an improvement inside noise
        # is not a reason to add a permanent preprocessing step.
        "kept": improvement > 0.01,
    }


async def main() -> None:
    model_name = getattr(llm_client.get_model(), "model_name", settings.llm_model)
    tesseract_version = str(pytesseract.get_tesseract_version())
    tesseract_psm = "default (PSM 3, fully automatic page segmentation)"

    preprocessing_experiment = run_preprocessing_experiment()
    use_preprocessing = preprocessing_experiment["kept"]

    checkpoint = load_checkpoint(model_name)

    started = time.time()
    set_a: dict = {}
    set_b: dict = {}
    for pass_num in range(1, MAX_FULL_PASSES + 1):
        set_a = await run_set_a(preprocess=use_preprocessing, checkpoint=checkpoint)
        set_b = await run_set_b(preprocess=use_preprocessing, checkpoint=checkpoint)
        remaining = len(set_a["extraction_failures"]) + len(
            set_b["extraction_failures"]
        )
        if remaining == 0:
            break
        print(
            f"Pass {pass_num}/{MAX_FULL_PASSES}: {remaining} extraction failures "
            "remain (already-succeeded cases were not re-spent); retrying just "
            "those..."
        )
    elapsed = time.time() - started

    report = {
        "date": time.strftime("%Y-%m-%d"),
        "model": model_name,
        "tesseract_version": tesseract_version,
        "tesseract_psm": tesseract_psm,
        "preprocessing_experiment": preprocessing_experiment,
        "preprocessing_kept": use_preprocessing,
        "set_a": set_a,
        "set_b": set_b,
        "elapsed_seconds": elapsed,
        "against": "real Groq API",
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    model_slug = model_name.replace("/", "-")
    out_path = RESULTS_DIR / f"{report['date']}-ocr-{model_slug}.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n")

    print(render_markdown(report))
    print(f"\nWrote {out_path}")

    # Only clear on a fully clean run: if failures remain after
    # MAX_FULL_PASSES, keep the checkpoint so a later invocation resumes
    # from these successes instead of re-spending quota on all of them.
    if not set_a["extraction_failures"] and not set_b["extraction_failures"]:
        clear_checkpoint()


if __name__ == "__main__":
    asyncio.run(main())
