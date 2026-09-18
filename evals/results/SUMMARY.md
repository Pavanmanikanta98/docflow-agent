# Evaluation results — 18 September 2026

Two runs of `backend/tests/evaluation` against the same 20 golden cases
(10 invoices, 10 contracts), one model each, on 18 September 2026. Both models are
served by Groq. Every number below comes from the two logs in this folder; nothing
is estimated.

All 40 extractions completed. No case errored, and no run hit a rate limit.

| | `openai/gpt-oss-20b` | `openai/gpt-oss-120b` |
|---|---|---|
| Field checks passed | 165 / 170 (97.06%) | 162 / 170 (95.29%) |
| Cases scoring 100% | 15 / 20 | 13 / 20 |
| Wall clock, 20 cases | 64.94 s | 71.15 s |
| Log | `2026-09-18-openai-gpt-oss-20b.txt` | `2026-09-18-openai-gpt-oss-120b.txt` |

The larger model scored lower. Both misread `subtotal` the same way; the 120b added
three misses of its own on contracts and one on currency.

## Per field

Invoices and contracts each contribute 10 cases. `currency` is scored on both, so it
has 20 checks; every other field has 10.

| Field | 20b | 120b |
|---|---|---|
| `vendor_name` | 10/10 | 10/10 |
| `invoice_number` | 10/10 | 10/10 |
| `invoice_date` | 10/10 | 10/10 |
| `due_date` | 10/10 | 10/10 |
| `total_amount` | 10/10 | 10/10 |
| `subtotal` | 7/10 | 7/10 |
| `tax_amount` | 10/10 | 10/10 |
| `line_items` | 10/10 | 10/10 |
| `parties` | 10/10 | 10/10 |
| `effective_date` | 10/10 | 9/10 |
| `expiry_date` | 10/10 | 10/10 |
| `contract_value` | 9/10 | 9/10 |
| `jurisdiction` | 10/10 | 9/10 |
| `key_obligations` | 9/10 | 9/10 |
| `termination_clause` | 10/10 | 10/10 |
| `currency` | 20/20 | 19/20 |

## Weakest field: subtotal

`subtotal` is the weakest field for both models, and it fails the same way each time:
the document states no subtotal, and the model returns the total instead of leaving
the field empty. The 20b did this on `inv_002`, `inv_005` and `inv_009`; the 120b on
`inv_002`, `inv_009` and `inv_010`.

This does not misroute documents. The arithmetic gate in `validator.py` only runs when
subtotal, tax and total are all present, and both models correctly left `tax_amount`
empty on every one of those invoices, so the gate skipped. It costs accuracy, not
correctness.

The four invoices that do state a subtotal (`inv_001`, `inv_003`, `inv_004`,
`inv_007`) were read correctly by both models, including the Indian GST and German
MwSt. formats.

## The other misses

Shared by both models:

- `con_009_zero_value` — a contract worth 0.0 comes back as null. Both models treat a
  zero value as no value.
- `con_007_minimal` — no obligations extracted where the labels expect some.

Only the 120b:

- `inv_005_messy_formatting` — returned no currency where the label says USD. The
  invoice writes amounts as `$340` with no currency code. The 20b answered USD.
- `con_003_employment` — returned February 1 2026 as the effective date where the
  label says February 15. The contract carries both: `Date: February 1, 2026` and
  `Start Date: February 15, 2026`. The label is a judgement call, and this one is
  arguably a disagreement about the label rather than a wrong reading.
- `con_003_employment` — `jurisdiction` came back as "Laws of India, jurisdiction of
  courts in Bangalore, Karnataka" against a label of "Bangalore, Karnataka, India".
  The content is right; the fuzzy matcher scores it below the 0.75 threshold because
  the answer is longer.

## How to reproduce

```bash
# set LLM_MODEL in .env to the model you want, then
uv run pytest backend/tests/evaluation -s
```

The suite makes 20 real Groq calls per run and is kept out of CI for that reason.

## What these numbers do not cover

- Per-case latency and token counts. The harness records neither; the only timing here
  is pytest's total for the run. That instrumentation is V1-7's `run_eval.py`, which
  does not exist yet.
- OCR. The golden inputs are text, so nothing here measures the parser.
- Model availability over time. `llama-3.1-8b-instant`, the previous default, returned
  HTTP 404 from Groq on this date, which is why these two models were used. Any number
  quoted from this file should carry the model name and the date.
