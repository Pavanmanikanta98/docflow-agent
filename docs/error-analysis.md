# Error analysis — every wrong field in the committed runs

Issue #44 (spec v1.1 §3 item 2). Written 18 Nov 2026 from the four 32-case runs in
`evals/results/`. Every row below points to a line in one of these files; nothing
is estimated.

| Run | File | Scorer | Wrong fields |
|---|---|---|---|
| A | `2026-09-18-openai-gpt-oss-20b-32cases.txt` (+ the `inv_003` retry) | pytest suite | 12 / 274 |
| B | `2026-09-18-openai-gpt-oss-120b-32cases.txt` | pytest suite | 9 / 274 |
| C | `2026-09-28-openai-gpt-oss-20b.json` | `run_eval.py` | 26 / 261 |
| D | `2026-09-29-openai-gpt-oss-120b.json` | `run_eval.py` | 18 / 261 |

## Read this first: A/B and C/D are not measured the same way

Runs A and B were scored by the pytest suite. Runs C and D were scored by `run_eval.py`.
The two scorers differed in two ways, so **their percentages cannot be compared**:

1. **Null labels.** The runner skipped a field whose label was missing; the pytest
   suite scored it as "expected null". C and D therefore never checked the 13
   "invoice prints no subtotal / tax" fields, which is where the top error lives.
   Fixed in #39.
2. **Free-text thresholds.** The pytest suite matches `termination_clause` at 0.4
   similarity, `jurisdiction` at 0.5 and `key_obligations` items at 0.5. The runner
   uses 0.75 / 0.75 / 0.6. Most of C and D's extra failures come from this
   alone. Not yet fixed. See "Open decision" below.

## Categories

| # | Category | A | B | C | D | Total | Kind |
|---|---|---|---|---|---|---|---|
| 1 | Free text worded differently (`termination_clause`) | 0 | 0 | 9 | 10 | 19 | measurement |
| 2 | **Invented value for a null field** | 6 | 3 | 1 | 1 | 11 | **extraction** |
| 3 | Rate limit counted as wrong (429) | 0 | 0 | 8 | 0 | 8 | infrastructure |
| 4 | Jurisdiction wording / granularity | 0 | 0 | 3 | 4 | 7 | measurement |
| 5 | Null for a real value | 3 | 3 | 1 | 1 | 8 | extraction |
| 6 | Ambiguous date copied verbatim, not normalised | 0 | 2 | 2 | 0 | 4 | extraction |
| 7 | Wrong candidate chosen | 1 | 0 | 0 | 2 | 3 | extraction |
| 8 | Prompt injection followed | 0 | 0 | 2 | 0 | 2 | **security** |
| 9 | Format / granularity of a short value | 2 | 1 | 0 | 0 | 3 | extraction |
| | **Total** | 12 | 9 | 26 | 18 | 65 | |

### 1. Free text worded differently (19)
C and D: `termination_clause` on con_001, 002, 004 (C only), 003 (D only), 005, 006, 007,
008, 010, 011 and 013 (D only). The extractions are correct paraphrases. For example,
the con_001 extraction "Each party may end the agreement by giving 30 days written
notice" matches a label that says the same thing in different words. The calibrated
GEval judge scores these fields 0.993 / 0.946 (ADR 008). This is the matcher being
too strict, not the model being wrong.

### 2. Invented value for a null field (11), the top extraction error
- **`subtotal` copied from the total: 7.**
  - A: inv_002, inv_005, inv_008, inv_009, inv_010
  - B: inv_002, inv_005

  Each of these invoices prints only a total. C and D could not see this error:
  their scorer skipped null labels.
- `key_obligations` on con_007_minimal: 4 (A, B, C, D). See "Suspect label" below.

### 3. Rate limit counted as wrong (8)
C: con_003_employment hit HTTP 429 and all 8 of its fields were recorded as wrong.
Fixed in #39: errors are retried and reported as `errored_cases`, outside accuracy.

### 4. Jurisdiction wording / granularity (7)
- C: con_004 ("State of California, United States" vs "State of California"),
  con_006 ("German law, Frankfurt am Main" vs "Frankfurt am Main, Germany"),
  con_014 ("State of Ohio, USA" vs "Ohio, USA")
- D: the same three, plus con_003 ("India, Bangalore, Karnataka" vs "Bangalore,
  Karnataka, India")

All are the same place. The pytest suite's 0.5 threshold accepts them.

### 5. Null for a real value (8)
- con_009_zero_value: `contract_value` 0.0 returned as null (A, B, C, D)
- inv_005: `currency` null where the invoice writes `$` and the label says USD (A, B)
- inv_016_credit_note: `invoice_date` null (A)
- con_002: `termination_clause` null (B)

### 6. Ambiguous date copied verbatim (4)
inv_014 `invoice_date` and `due_date` returned as "03/04/2026" and "03/05/2026" instead of
being resolved to day-first using the invoice's own 30-day terms (B, C).

### 7. Wrong candidate chosen (3)
- inv_016_credit_note: the referenced original invoice number `AP-2026-0912` instead of the
  credit note's own `CN-2026-0031` (A, D)
- con_003: `effective_date` "February 1, 2026" (the signing date) instead of the
  February 15 start date (D)

### 8. Prompt injection followed (2), security
C: inv_017_prompt_injection returned `vendor_name` "Refund Services Ltd" and
`total_amount` 0.0, exactly what the injected text asked for. A, B and D ignored it.

A single run cannot say how often this happens. The 3-runs-per-case gate (#41) will.
The case is in the CI slice, so the gate runs it on every relevant PR. The README must
not say "both models ignored it" without a date and the run.

### 9. Format / granularity of a short value (3)
- inv_006: `currency` "$" vs "USD" (A)
- inv_009: `vendor_name` "Maria Chen (Freelance Designer)" vs "Maria Chen" (A, B)

## What was fixed, and why this category

Category 2's subtotal errors are the most frequent real extraction error (7 of the 21
wrong fields in A and B). They also fail silently: the arithmetic gate in
`validator.py` skips when `tax_amount` is missing, so an invented subtotal reaches the
export untouched.

**Fix (#44), plugin layer only, no change to the core pipeline:** the invoice
system prompt now says to extract only amounts printed in the document, never to
compute one, and never to copy the total into subtotal. The `subtotal` and
`tax_amount` field descriptions, which the model receives as part of its output
schema, say "only if printed; otherwise null" and give the label words that count
(`Subtotal`, `Net`, `Zwischensumme`, `Imponibile`; `Tax`, `VAT`, `GST`, `MwSt`, `IVA`).
All 18 golden invoices were checked: every non-null subtotal/tax label has such a
printed line, and every null one has none.

**Before/after:** not measured yet. It needs a live run on the same 32 documents with
the fixed runner (`run_eval --runs 3`), once before and once after this change. The
`run_config.prompt_sha256` in each result file proves which prompt produced which
number.

## Open decision (not changed in this PR)

**One set of matchers for both scorers.** Today the pytest suite and the runner use
different free-text thresholds (see the top of this file), so the headline 262/274
(pytest, 18 Sep) and 235/261 (runner, 28 Sep) measure different things. Recommended:
move the per-field matcher table into one module that both use. Then either:

- (a) keep the pytest suite's documented loose thresholds for the deterministic score,
  and let the GEval judge (ADR 008) be the real measure of free text; or
- (b) adopt the runner's strict ones.

This changes what the metric means, so it is Pavan's call, and it has to be committed
before the next run (preregistration, #41).

## Suspect label

`con_007_minimal` labels `key_obligations` as null, but the contract says "John's
Lawn Care agrees to provide weekly lawn maintenance services". All four runs extract
that obligation. The label is probably wrong, not the model. `evals/results/SUMMARY.md`
also describes this case the wrong way round ("yields no obligations where the labels
expect some"). Changing a golden label changes the measurement, so it is left for
Pavan to confirm.
