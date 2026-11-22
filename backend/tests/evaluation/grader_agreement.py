"""Grader agreement (issue #43; 17 Nov plan delta R4 item 1b).

ADR 008's GEval judge scores contract free text. It passed hand-written
controls, but nobody had checked it against a human on real extractions.
This module does that in three steps:

1. export  — sample real extractions from a run_eval result file into a
             blind CSV: no judge score, no fuzzy verdict. A human fills
             `human_label` with `correct` or `wrong`.
2. judge   — the GEval judge scores the same items (real API calls;
             needs the `eval` extra). Written to a separate file so the
             labeller never sees it.
3. report  — agreement %, Cohen's kappa and the disagreements, written to
             evals/results/. `check_gate --agreement <file>` enforces
             `grader_agreement_min` from evals/thresholds.toml.

Usage:
    uv run python -m backend.tests.evaluation.grader_agreement export <result.json>
    # ... fill human_label in evals/blind_labels.csv by hand ...
    uv run --extra eval python -m backend.tests.evaluation.grader_agreement judge
    uv run python -m backend.tests.evaluation.grader_agreement report
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import random
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.tests.evaluation.judge_calibration import JUDGE_THRESHOLD

EVALS_DIR = Path(__file__).resolve().parents[3] / "evals"
BLIND_CSV = EVALS_DIR / "blind_labels.csv"
JUDGE_CSV = EVALS_DIR / "blind_labels_judge.csv"
JUDGED_FIELDS = ("termination_clause", "key_obligations")
BLIND_COLUMNS = (
    "item_id", "case_id", "run", "field", "extracted", "reference", "human_label",
)
LABELS = {"correct": True, "wrong": False}
DEFAULT_SAMPLE_SIZE = 30
DEFAULT_SEED = 20261118

ScoreFn = Callable[[str, str, str], Awaitable[float]]


def export_items(result: dict[str, Any], n: int, seed: int) -> list[dict[str, str]]:
    """Up to `n` judgeable items, sampled with a fixed seed. An item is
    judgeable when both the extraction and the reference have text (the
    judge eval scores nothing else). Identical text from repeated runs of
    the same case is kept once."""
    seen: set[tuple[str, str, str]] = set()
    pool: list[dict[str, str]] = []
    for case in result["cases"]:
        for fr in case["field_results"]:
            if fr["field_name"] not in JUDGED_FIELDS:
                continue
            extracted, reference = _as_text(fr["actual"]), _as_text(fr["expected"])
            key = (case["case_id"], fr["field_name"], extracted)
            if not extracted or not reference or key in seen:
                continue
            seen.add(key)
            pool.append({
                "case_id": case["case_id"], "run": str(case.get("run", 1)),
                "field": fr["field_name"], "extracted": extracted,
                "reference": reference,
            })
    sample = random.Random(seed).sample(pool, min(n, len(pool)))
    return [{"item_id": f"item_{i:02d}", **item} for i, item in enumerate(sample, 1)]


def _as_text(value: Any) -> str:
    """Lists are joined the way run_judge_eval.py joins them for the judge."""
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return "" if value is None else str(value)


def write_blind_csv(items: list[dict[str, str]], path: Path) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=BLIND_COLUMNS)
        writer.writeheader()
        for item in items:
            writer.writerow({**item, "human_label": ""})


def load_labels(path: Path) -> dict[str, bool]:
    """Human labels by item id. Every row must be labelled `correct` or
    `wrong`: a partial set would make the agreement figure meaningless."""
    rows = list(csv.DictReader(path.open()))
    bad = [r["item_id"] for r in rows if r["human_label"].strip().lower() not in LABELS]
    if bad:
        raise ValueError(
            f"{len(bad)} item(s) not labelled correct/wrong: {', '.join(bad)}"
        )
    return {r["item_id"]: LABELS[r["human_label"].strip().lower()] for r in rows}


async def judge_items(
    items: list[dict[str, str]], score_fn: ScoreFn
) -> dict[str, dict[str, Any]]:
    """Judge score and verdict (score >= JUDGE_THRESHOLD) for each item."""
    verdicts = {}
    for item in items:
        score = await score_fn(item["field"], item["extracted"], item["reference"])
        correct = score >= JUDGE_THRESHOLD
        verdicts[item["item_id"]] = {"score": score, "correct": correct}
    return verdicts


def compute_agreement(human: dict[str, bool], judge: dict[str, bool]) -> dict[str, Any]:
    """Raw agreement and Cohen's kappa (agreement corrected for chance)."""
    ids = sorted(set(human) & set(judge))
    n = len(ids)
    if n == 0:
        raise ValueError("No item has both a human label and a judge verdict")
    agree = sum(human[i] == judge[i] for i in ids) / n
    p_human = sum(human[i] for i in ids) / n
    p_judge = sum(judge[i] for i in ids) / n
    chance = p_human * p_judge + (1 - p_human) * (1 - p_judge)
    kappa = 1.0 if chance == 1 else (agree - chance) / (1 - chance)
    return {
        "n": n,
        "agreement": agree,
        "cohens_kappa": kappa,
        "disagreements": [i for i in ids if human[i] != judge[i]],
    }


async def _live_score_fn() -> ScoreFn:
    """The same GEval judges and judge model as run_judge_eval.py."""
    from deepeval.test_case import LLMTestCase

    from backend.core.db import redis_client
    from backend.core.deepeval_judge import LLMClientBasedJudge
    from backend.tests.evaluation.judge_calibration import (
        build_key_obligations_judge,
        build_termination_clause_judge,
    )
    from backend.tests.evaluation.retry import with_capacity_retry

    wrapper = LLMClientBasedJudge(
        model_name="openai/gpt-oss-120b", redis_client=redis_client
    )
    judges = {
        "termination_clause": build_termination_clause_judge(wrapper, JUDGE_THRESHOLD),
        "key_obligations": build_key_obligations_judge(wrapper, JUDGE_THRESHOLD),
    }

    async def score(field: str, extracted: str, reference: str) -> float:
        case = LLMTestCase(input="", actual_output=extracted, expected_output=reference)
        return await with_capacity_retry(lambda: judges[field].a_measure(case))

    return score


def _cmd_export(args: argparse.Namespace) -> None:
    result = json.loads(Path(args.result_file).read_text())
    items = export_items(result, n=args.n, seed=args.seed)
    write_blind_csv(items, args.out)
    if len(items) < args.n:
        print(f"WARNING: only {len(items)} judgeable items (asked for {args.n}). "
              "Use a result file with more runs (--runs 3) before labelling.")
    print(f"Wrote {len(items)} blind items to {args.out}. Label each row "
          "correct/wrong without looking at any judge or fuzzy score.")


def _cmd_judge(args: argparse.Namespace) -> None:
    items = list(csv.DictReader(args.labels.open()))
    verdicts = asyncio.run(_judge_live(items))
    with args.out.open("w", newline="") as f:
        columns = ("item_id", "judge_score", "judge_correct")
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for item_id, v in verdicts.items():
            writer.writerow({"item_id": item_id, "judge_score": v["score"],
                             "judge_correct": v["correct"]})
    print(f"Wrote judge verdicts for {len(verdicts)} items to {args.out}")


async def _judge_live(items: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    return await judge_items(items, await _live_score_fn())


def _cmd_report(args: argparse.Namespace) -> None:
    human = load_labels(args.labels)
    judge = {r["item_id"]: r["judge_correct"] == "True"
             for r in csv.DictReader(args.judge.open())}
    report = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "judge_threshold": JUDGE_THRESHOLD,
        **compute_agreement(human, judge),
    }
    out = args.out or EVALS_DIR / "results" / f"{report['date']}-grader-agreement.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"Agreement {report['agreement']:.1%}, kappa {report['cohens_kappa']:.2f}, "
          f"n={report['n']} -> {out}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Judge vs human agreement")
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("result_file")
    export.add_argument("--n", type=int, default=DEFAULT_SAMPLE_SIZE)
    export.add_argument("--seed", type=int, default=DEFAULT_SEED)
    export.add_argument("--out", type=Path, default=BLIND_CSV)
    judge = sub.add_parser("judge")
    judge.add_argument("--labels", type=Path, default=BLIND_CSV)
    judge.add_argument("--out", type=Path, default=JUDGE_CSV)
    report = sub.add_parser("report")
    report.add_argument("--labels", type=Path, default=BLIND_CSV)
    report.add_argument("--judge", type=Path, default=JUDGE_CSV)
    report.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    {"export": _cmd_export, "judge": _cmd_judge, "report": _cmd_report}[
        args.command
    ](args)


if __name__ == "__main__":
    main()
