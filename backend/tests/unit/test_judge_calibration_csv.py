"""ADR 008 — evals/judge_calibration.csv must hold real calibration outputs
(candidate/expected text, all 3 scores, an empty human_verdict column) for
manual spot-checking, keyed clearly enough (case_id + field_name +
polarity) to tell which control produced which row."""

import csv

from backend.tests.evaluation.judge_calibration import (
    ControlResult,
    write_calibration_csv,
)


def test_writes_one_row_per_control(tmp_path):
    controls = [
        ControlResult(
            case_id="con_001",
            is_positive=True,
            candidate="reworded text",
            expected="original text",
            scores=[1.0, 1.0, 1.0],
            field_name="termination_clause",
        ),
        ControlResult(
            case_id="con_001",
            is_positive=False,
            candidate="changed text",
            expected="original text",
            scores=[0.0, 0.1, 0.0],
            field_name="termination_clause",
        ),
    ]
    path = tmp_path / "judge_calibration.csv"
    write_calibration_csv(controls, path)

    with path.open() as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2
    assert rows[0]["case_id"] == "con_001"
    assert rows[0]["field_name"] == "termination_clause"
    assert rows[0]["candidate"] == "reworded text"
    assert rows[0]["human_verdict"] == ""


def test_human_verdict_column_is_always_empty(tmp_path):
    controls = [
        ControlResult(
            case_id="c1",
            is_positive=True,
            candidate="a",
            expected="b",
            scores=[0.9],
            field_name="key_obligations",
        )
    ]
    path = tmp_path / "judge_calibration.csv"
    write_calibration_csv(controls, path)

    with path.open() as f:
        rows = list(csv.DictReader(f))
    assert all(row["human_verdict"] == "" for row in rows)


def test_creates_parent_directory_if_missing(tmp_path):
    path = tmp_path / "nested" / "judge_calibration.csv"
    write_calibration_csv([], path)
    assert path.exists()


def test_empty_controls_writes_header_only(tmp_path):
    path = tmp_path / "judge_calibration.csv"
    write_calibration_csv([], path)
    with path.open() as f:
        rows = list(csv.DictReader(f))
    assert rows == []
