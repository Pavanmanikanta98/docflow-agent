"""ADR 006 — cost per document, from measured tokens only.

Reads every evals/results/*.json file, pulls out any "cases" with measured
input_tokens/output_tokens (see backend/core/cost_aggregation.py for the
expected shape), aggregates per document type, and prices it against
backend/core/pricing.py. A document type or model with no measured cases
prints "not measured yet" rather than a guess — CLAUDE.md's hard rule
against invented numbers applies to a cost figure exactly as much as an
accuracy figure.

Usage:
    uv run python scripts/cost_report.py

Writes evals/results/<date>-cost.json and prints a markdown table.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.core.config import settings  # noqa: E402
from backend.core.cost_aggregation import (  # noqa: E402
    aggregate_by_document_type,
    load_cases_from_result,
)
from backend.core.pricing import (  # noqa: E402
    MODEL_PRICING,
    PRICING_CHECKED_DATE,
    PRICING_SOURCE_URL,
)

RESULTS_DIR = REPO_ROOT / "evals" / "results"
NOT_MEASURED = "not measured yet"


def _load_all_cases() -> list:
    cases = []
    for path in sorted(RESULTS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            cases.extend(load_cases_from_result(data))
    return cases


def _throughput_tier(tpm: int, rpm: int, tpd: int, rpd: int) -> dict | str:
    if not any([tpm, rpm, tpd, rpd]):
        return NOT_MEASURED
    return {
        "requests_per_minute": rpm,
        "tokens_per_minute": tpm,
        "requests_per_day": rpd,
        "tokens_per_day": tpd,
    }


def build_report() -> dict:
    cases = _load_all_cases()
    stats_by_type = aggregate_by_document_type(cases)

    per_model: dict[str, dict | str] = {}
    for model_name, pricing in MODEL_PRICING.items():
        per_type: dict[str, dict] = {}
        for document_type, stats in stats_by_type.items():
            standard_cost = pricing.cost(
                stats.median_input, stats.median_output, batch=False
            )
            batch_cost = pricing.cost(
                stats.median_input, stats.median_output, batch=True
            )
            per_type[document_type] = {
                "measured_cases": stats.count,
                "median_input_tokens": stats.median_input,
                "median_output_tokens": stats.median_output,
                "p95_input_tokens": stats.p95_input,
                "p95_output_tokens": stats.p95_output,
                "cost_per_document_standard_usd": round(standard_cost, 6),
                "cost_per_document_batch_usd": round(batch_cost, 6),
                "cost_per_1000_documents_standard_usd": round(standard_cost * 1000, 2),
                "cost_per_1000_documents_batch_usd": round(batch_cost * 1000, 2),
            }
        per_model[model_name] = per_type or (
            f"{NOT_MEASURED} — no evals/results/*.json file has per-case "
            "token usage yet (see SPRINT.md V1-7)"
        )

    return {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pricing_source": PRICING_SOURCE_URL,
        "pricing_checked_date": PRICING_CHECKED_DATE,
        "per_model": per_model,
        "throughput": {
            "free_tier": _throughput_tier(
                settings.llm_tpm, settings.llm_rpm, settings.llm_tpd, settings.llm_rpd
            ),
            "developer_tier": _throughput_tier(
                settings.llm_developer_tpm,
                settings.llm_developer_rpm,
                settings.llm_developer_tpd,
                settings.llm_developer_rpd,
            ),
        },
    }


def _format_tier(tier: dict | str) -> str:
    if isinstance(tier, str):
        return tier
    return (
        f"{tier['requests_per_minute']} RPM, {tier['tokens_per_minute']} TPM, "
        f"{tier['requests_per_day']} RPD, {tier['tokens_per_day']} TPD"
    )


def render_markdown(report: dict) -> str:
    lines = [f"# Cost report — {report['date']}", ""]
    lines.append(
        f"Pricing verified against `{report['pricing_source']}` on "
        f"{report['pricing_checked_date']}."
    )
    lines.append("")

    for model, per_type in report["per_model"].items():
        lines.append(f"## {model}")
        if isinstance(per_type, str):
            lines.append(per_type)
            lines.append("")
            continue
        lines.append(
            "| Document type | Measured cases | Median tokens (in/out) | "
            "$/doc (standard) | $/doc (batch) | $/1,000 docs (standard) | "
            "$/1,000 docs (batch) |"
        )
        lines.append("|---|---|---|---|---|---|---|")
        for document_type, row in per_type.items():
            lines.append(
                f"| {document_type} | {row['measured_cases']} | "
                f"{row['median_input_tokens']:.0f}/{row['median_output_tokens']:.0f} | "
                f"${row['cost_per_document_standard_usd']:.6f} | "
                f"${row['cost_per_document_batch_usd']:.6f} | "
                f"${row['cost_per_1000_documents_standard_usd']:.2f} | "
                f"${row['cost_per_1000_documents_batch_usd']:.2f} |"
            )
        lines.append("")

    lines.append("## Throughput")
    lines.append(f"- Free tier: {_format_tier(report['throughput']['free_tier'])}")
    lines.append(
        f"- Developer tier: {_format_tier(report['throughput']['developer_tier'])}"
    )
    lines.append("- Batch: built and tested, not run live (needs the Developer tier)")
    return "\n".join(lines)


def main() -> None:
    report = build_report()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{report['date']}-cost.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n")

    print(render_markdown(report))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
