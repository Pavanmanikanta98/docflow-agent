"""ADR 007 — the OCR eval's checkpoint must survive a crash mid-run:
this session's container has restarted mid-evaluation more than once, and a
process that had been running for hours lost all its progress each time
until this checkpoint was added."""

import json

import backend.tests.evaluation.run_ocr_eval as run_ocr_eval


def test_missing_checkpoint_file_starts_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(run_ocr_eval, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    checkpoint = run_ocr_eval.load_checkpoint("openai/gpt-oss-20b")
    assert checkpoint == {"model": "openai/gpt-oss-20b", "set_a": {}, "set_b": {}}


def test_save_then_load_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(run_ocr_eval, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    saved = {
        "model": "openai/gpt-oss-20b",
        "set_a": {"inv_001:text_layer": {"vendor_name": "Acme"}},
        "set_b": {},
    }
    run_ocr_eval.save_checkpoint(saved)
    loaded = run_ocr_eval.load_checkpoint("openai/gpt-oss-20b")
    assert loaded == saved


def test_checkpoint_from_a_different_model_is_discarded(tmp_path, monkeypatch):
    monkeypatch.setattr(run_ocr_eval, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    run_ocr_eval.save_checkpoint(
        {"model": "openai/gpt-oss-20b", "set_a": {"x": {"a": 1}}, "set_b": {}}
    )
    loaded = run_ocr_eval.load_checkpoint("openai/gpt-oss-120b")
    assert loaded == {"model": "openai/gpt-oss-120b", "set_a": {}, "set_b": {}}


def test_corrupt_checkpoint_file_starts_empty_instead_of_crashing(
    tmp_path, monkeypatch
):
    path = tmp_path / "checkpoint.json"
    path.write_text("{not valid json")
    monkeypatch.setattr(run_ocr_eval, "CHECKPOINT_PATH", path)
    checkpoint = run_ocr_eval.load_checkpoint("openai/gpt-oss-20b")
    assert checkpoint == {"model": "openai/gpt-oss-20b", "set_a": {}, "set_b": {}}


def test_save_is_atomic_and_leaves_no_tmp_file_behind(tmp_path, monkeypatch):
    path = tmp_path / "checkpoint.json"
    monkeypatch.setattr(run_ocr_eval, "CHECKPOINT_PATH", path)
    run_ocr_eval.save_checkpoint({"model": "m", "set_a": {}, "set_b": {}})
    assert path.exists()
    assert not path.with_suffix(".tmp").exists()
    assert json.loads(path.read_text())["model"] == "m"


def test_clear_checkpoint_removes_the_file(tmp_path, monkeypatch):
    path = tmp_path / "checkpoint.json"
    monkeypatch.setattr(run_ocr_eval, "CHECKPOINT_PATH", path)
    run_ocr_eval.save_checkpoint({"model": "m", "set_a": {}, "set_b": {}})
    run_ocr_eval.clear_checkpoint()
    assert not path.exists()


def test_clear_checkpoint_is_a_no_op_when_nothing_to_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(run_ocr_eval, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    run_ocr_eval.clear_checkpoint()  # must not raise
