# DeepEval GEval Judge for Contract Free-Text Fields

## What is the judge?

The evaluation harness (CLAUDE.md rule 7) uses deterministic matchers for structured fields like dates, numbers, and names. But contract free-text fields like `termination_clause` and `key_obligations` need a different tool: an LLM judge that understands semantics, not just string overlap.

**DeepEval's GEval metric** is a framework for "LLM-as-judge" scoring. It tells a second LLM (the judge) what to look for in a contract clause, asks it to score the extracted text against the golden text, and returns a score (0.0–1.0). Unlike fuzzy string matching:
- It rewards faithful rewording (same meaning, different words)
- It catches semantic errors (missing conditions, invented obligations)
- It handles the length and complexity of legal text

## Why is the judge a different model?

The extractor uses `openai/gpt-oss-20b` by default. The judge always uses `openai/gpt-oss-120b` — a deliberately larger model.

**Why?** Extracting a field and judging your own extraction is self-grading bias. A model is more likely to mark its own output as correct, especially on ambiguous fields. Using a larger, independent model (trained with different data, at a different scale) breaks that bias.

**Cost:** Judge calls do hit the free-tier token budget (ADR 006). A full calibration + evaluation run costs roughly 2x the extraction calls (one to extract, multiple to judge). Be deliberate about running this.

## How is the judge calibrated?

An uncalibrated judge score is like an invented number — confident but unverified. Calibration is the gate.

For each contract in the calibration set (currently the first 2 golden cases):

**Positive controls:**
- Take the expected `termination_clause` or `key_obligations` from the golden data.
- Reword it faithfully (same meaning, different phrasing).
- Ask the judge to score it against the original.
- **Expect:** score ≥ threshold (e.g., 0.5).

**Negative controls:**
- Same case, but with a material change (e.g., notice period dropped, a party swapped, an obligation removed).
- Ask the judge to score it against the original.
- **Expect:** score < threshold.

Each judgment runs **3 times** (temperature 0 does not guarantee determinism). The report is **mean + spread** (max − min), not a single sample. This reveals variance: a mean of 0.7 with spread 0.1 is more trustworthy than a mean of 0.7 with spread 0.4.

**Calibration passes** only if:
- ALL positive controls have mean ≥ threshold, AND
- ALL negative controls have mean < threshold.

If calibration fails, the results use the fuzzy-matcher score instead and say the judge did not calibrate. The README will report this plainly — "GEval judge attempted but did not calibrate; fuzzy-match scores reported instead."

## How to run the judge evaluation

```bash
# Install the eval extra (includes deepeval and dependencies)
uv sync --extra dev --extra eval

# Run the evaluation (costs API credits; free tier may need retries for large runs)
uv run python backend/tests/evaluation/run_judge_eval.py
```

The script:
1. Loads the contract golden cases.
2. Runs calibration (positive + negative controls, 3 runs each).
3. Runs the judge on all contract cases side-by-side with the fuzzy matcher.
4. Writes `evals/results/<YYYY-MM-DD>-judge-<model>.json`.
5. Writes `evals/judge_calibration.csv` with actual extraction outputs for manual spot-checking.

## How to read the results

### Example `evals/results/2026-09-25-judge-openai-gpt-oss-20b.json`:

```json
{
  "model": "openai/gpt-oss-20b",
  "date": "2026-09-25T14:30:00",
  "judge_model": "openai/gpt-oss-120b",
  "calibration": {
    "passed": true,
    "threshold": 0.5,
    "controls": [
      {
        "case_id": "contract_001",
        "is_positive": true,
        "mean_score": 0.78,
        "spread": 0.05,
        "scores": [0.75, 0.78, 0.82]
      },
      {
        "case_id": "contract_001",
        "is_positive": false,
        "mean_score": 0.32,
        "spread": 0.08,
        "scores": [0.28, 0.32, 0.40]
      }
    ]
  },
  "cases": [
    {
      "case_id": "contract_001",
      "fuzzy_score": {
        "termination_clause": 1.0,
        "key_obligations_overlap": 0.8
      },
      "geval_score": {
        "termination_clause": 0.85,
        "key_obligations": 0.82
      },
      "headline_metric": "geval"
    }
  ]
}
```

**Fields:**
- `calibration.passed`: True if all controls passed, false otherwise.
- `calibration.controls`: The positive and negative control results. Each shows the mean of 3 runs and the spread (variance indicator).
- `cases[].fuzzy_score`: Score from the deterministic fuzzy matcher (0.0–1.0).
- `cases[].geval_score`: Score from the judge LLM (only meaningful if calibration passed).
- `cases[].headline_metric`: Either `"geval"` (if calibration passed) or `"fuzzy_fallback"` (if it didn't). **This is the score to report in the README.**

### `evals/judge_calibration.csv`:

A table with one row per case in the calibration set:
- `case_id`: Which case this is.
- `extracted_termination_clause`: What the extractor returned.
- `expected_termination_clause`: The golden ground truth.
- `extracted_key_obligations`: What the extractor returned.
- `expected_key_obligations`: The golden ground truth.
- `human_verdict`: Empty (for future manual review).

This file helps spot-check: "Did the extractor actually get it right? Is the judge score reasonable?"

## What happens if calibration fails?

If the judge's positive controls don't score well, or its negative controls score too high, the judge is not reliable. In this case:

1. The results file will have `calibration.passed: false`.
2. The `headline_metric` for every case will be `"fuzzy_fallback"`.
3. The README will use the fuzzy-match scores and note: "GEval judge calibration failed; fuzzy-match scores reported."

**Next steps:**
- Examine `evals/judge_calibration.csv` to see if the positive controls were genuinely faithful rewordings (or if they were too similar/different to the golden).
- Check the judge's response text (debug logs would show this) — does it seem to understand the contracts?
- Increase the number of controls or refine the criteria for negative controls (e.g., ensure the "material change" is actually material).
- Consider a different judge model or adjusting the temperature (currently 0).

## Technical notes

- **Token budget:** Judge calls go through ADR 006's shared Redis token bucket, just like extraction. A full calibration + eval run may hit the free-tier 429 if other processes are running; the script includes retry logic with backoff.
- **Determinism:** Even at temperature 0, LLM judge scores vary run-to-run due to sampling in the model itself. That's why we run 3 times and report mean + spread.
- **Cost:** Runs against `gpt-oss-120b`, which is larger than the extractor model. Calibration + evaluation on ~20 cases costs roughly 40–60 API calls (extraction × 2 for judge, × 3 for calibration runs).
- **Pinned version:** `deepeval==4.2.0` is pinned in the `eval` extra to ensure reproducibility. A future DeepEval release changing GEval's internal scoring algorithm would invalidate historical `evals/results/` files; the pin keeps old numbers interpretable.

## For an interview

Describe this:
- "We use a separate, larger LLM as an independent judge to grade free-text contract fields."
- "To avoid self-grading bias, the judge is a different model (120B vs 20B) trained independently."
- "Before trusting the judge's headline number, we calibrate: positive controls (faithful rewording) must score high, negative controls (material changes) must score low. Only if all controls pass do we report the judge's score; otherwise we fall back to a fuzzy matcher."
- "Each judgment runs 3 times; the result is mean + spread, not a single sample, so variance is visible."
- "Calibration passed/failed and raw scores are all in `evals/results/` — the README reports which one is trustworthy."

This demonstrates:
✓ Thoughtful evaluation (bias-aware)
✓ Measured numbers (not invented)
✓ Transparency about uncertainty (spread, fallback)
✓ Reproducibility (pinned versions, checkpoint mechanism)
