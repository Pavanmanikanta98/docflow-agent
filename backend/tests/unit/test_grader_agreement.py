"""Issue #43: the GEval judge is checked against blind human labels.

Pure functions and a fake judge only. The real judge (deepeval) and the
real labels (Pavan's) never appear in unit tests."""

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from backend.tests.evaluation.check_gate import main as gate_main
from backend.tests.evaluation.grader_agreement import (
    BLIND_COLUMNS,
    compute_agreement,
    export_items,
    judge_items,
    load_labels,
    write_blind_csv,
)


def _case(case_id: str, run: int, termination: Any, obligations: Any) -> dict:
    return {
        "case_id": case_id,
        "run": run,
        "field_results": [
            {"field_name": "termination_clause", "actual": termination,
             "expected": "30 days written notice", "passed": False},
            {"field_name": "key_obligations", "actual": obligations,
             "expected": ["Deliver reports", "Keep insurance"], "passed": True},
            {"field_name": "jurisdiction", "actual": "Delaware",
             "expected": "Delaware", "passed": True},
        ],
    }


RESULT: dict[str, Any] = {
    "cases": [
        _case(f"con_{i:03d}", run, f"Notice of {i} days", ["Deliver reports"])
        for i in range(1, 15) for run in (1, 2, 3)
    ] + [_case("con_null", 1, None, None)]
}


def test_export_takes_only_judge_fields_and_skips_nothing_to_judge() -> None:
    items = export_items(RESULT, n=100, seed=7)

    assert {i["field"] for i in items} == {"termination_clause", "key_obligations"}
    assert all(i["case_id"] != "con_null" for i in items)
    # The same text from repeated runs is labelled once.
    assert len(items) == len({(i["case_id"], i["field"], i["extracted"])
                              for i in items})


def test_export_is_deterministic_and_sized() -> None:
    first = export_items(RESULT, n=10, seed=7)
    assert first == export_items(RESULT, n=10, seed=7)
    assert len(first) == 10
    assert len({i["item_id"] for i in first}) == 10


def test_blind_csv_has_no_scores_and_an_empty_label_column(tmp_path: Path) -> None:
    path = tmp_path / "blind.csv"
    write_blind_csv(export_items(RESULT, n=5, seed=7), path)

    rows = list(csv.DictReader(path.open()))
    assert list(rows[0].keys()) == list(BLIND_COLUMNS)
    assert all(row["human_label"] == "" for row in rows)
    assert not any("score" in col or "passed" in col for col in BLIND_COLUMNS)


def test_load_labels_refuses_missing_or_unknown_labels(tmp_path: Path) -> None:
    path = tmp_path / "blind.csv"
    write_blind_csv(export_items(RESULT, n=3, seed=7), path)

    with pytest.raises(ValueError, match="not labelled"):
        load_labels(path)


def test_agreement_and_kappa() -> None:
    human = {"a": True, "b": True, "c": False, "d": False}
    judge = {"a": True, "b": False, "c": False, "d": False}

    report = compute_agreement(human, judge)

    assert report["n"] == 4
    assert report["agreement"] == pytest.approx(0.75)
    assert report["cohens_kappa"] == pytest.approx(0.5)
    assert report["disagreements"] == ["b"]


async def test_judge_items_uses_the_judge_threshold() -> None:
    items = [
        {"item_id": "x", "field": "termination_clause", "extracted": "a",
         "reference": "b"},
        {"item_id": "y", "field": "key_obligations", "extracted": "c",
         "reference": "d"},
    ]
    scores = {"a": 0.9, "c": 0.2}

    async def fake_score(field: str, extracted: str, reference: str) -> float:
        return scores[extracted]

    verdicts = await judge_items(items, fake_score)

    assert verdicts == {
        "x": {"score": 0.9, "correct": True},
        "y": {"score": 0.2, "correct": False},
    }


def test_gate_fails_when_agreement_is_below_the_bar(tmp_path: Path) -> None:
    result = tmp_path / "result.json"
    result.write_text(json.dumps({
        "field_accuracy": {"mean": 1.0, "min": 1.0, "max": 1.0},
        "per_field": {}, "errored_cases": [],
    }))
    agreement = tmp_path / "agreement.json"
    agreement.write_text(json.dumps({"agreement": 0.80, "n": 30}))

    assert gate_main([str(result), "--agreement", str(agreement)]) == 1
