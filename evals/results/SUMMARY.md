# Evaluation results — 18 September 2026

Four runs of `backend/tests/evaluation` on 18 September 2026, two models against two
versions of the golden set. Every number here comes from the logs in this folder;
nothing is estimated or rounded up.

The golden set grew during the day. It started as 20 cases (10 invoices, 10 contracts)
of short, clean text, and 12 harder cases were added: vendor traps, competing totals,
OCR artefacts, an ambiguous date format, a two-page invoice, a credit note with a
negative total, a prompt-injection attempt, a dense Italian table, a contract amendment
that supersedes the original value, two currencies in one agreement, a value stated only
as milestones, and auto-renewal competing with the initial term. Existing cases are
tagged `"difficulty": "clean"`, the new ones `"hard"`, in the golden files.

Both models are served by Groq. `llama-3.1-8b-instant`, the previous default, returned
HTTP 404 from Groq on this date and no Llama chat model was available on the account,
which is why these two were used. See ADR 005.

## Headline

Field checks passed, on the full 32-case set:

| | `openai/gpt-oss-20b` | `openai/gpt-oss-120b` |
|---|---|---|
| All 32 cases | 262/274 (95.62%) | 265/274 (96.72%) |
| Clean subset (20) | 160/170 (94.12%) | 163/170 (95.88%) |
| Hard subset (12) | 102/104 (98.08%) | 102/104 (98.08%) |
| Cases scoring 100% | 23/32 | 25/32 |
| Wall clock, 32 cases | 142.51 s | 136.93 s |

The hard cases score higher than the clean ones, for both models. That is not a mistake
in the data. The hard cases test choosing the right candidate among distractors, which
both models do well; the clean cases fail mostly on null handling, which is a different
skill and the weaker one.

## Treat small differences as noise

The same model, on the same 20 clean cases, scored 162/170 in the morning run and
163/170 in the afternoon, and the misses were different cases both times. A gap of one
or two field checks between these two models is inside that variance. The 120b leads on
both sets here, but not by enough to call it better at this sample size.

## Per field

`currency` is scored on invoices and contracts, so it has twice the checks of the other
fields. Invoice-only and contract-only fields are marked accordingly.

| Field | 20b clean | 20b hard | 120b clean | 120b hard |
|---|---|---|---|---|
| `vendor_name` | 9/10 | 8/8 | 9/10 | 8/8 |
| `invoice_number` | 10/10 | 7/8 | 10/10 | 8/8 |
| `invoice_date` | 10/10 | 7/8 | 10/10 | 7/8 |
| `due_date` | 10/10 | 8/8 | 10/10 | 7/8 |
| `total_amount` | 10/10 | 8/8 | 10/10 | 8/8 |
| `subtotal` | 5/10 | 8/8 | 8/10 | 8/8 |
| `tax_amount` | 10/10 | 8/8 | 10/10 | 8/8 |
| `line_items` | 10/10 | 8/8 | 10/10 | 8/8 |
| `parties` | 10/10 | 4/4 | 10/10 | 4/4 |
| `effective_date` | 10/10 | 4/4 | 10/10 | 4/4 |
| `expiry_date` | 10/10 | 4/4 | 10/10 | 4/4 |
| `contract_value` | 9/10 | 4/4 | 9/10 | 4/4 |
| `jurisdiction` | 10/10 | 4/4 | 10/10 | 4/4 |
| `key_obligations` | 9/10 | 4/4 | 9/10 | 4/4 |
| `termination_clause` | 10/10 | 4/4 | 9/10 | 4/4 |
| `currency` | 18/20 | 12/12 | 19/20 | 12/12 |

## Weakest field: subtotal on clean invoices

`subtotal` is the weakest field for both models and fails the same way every time: the
invoice states no subtotal, and the model returns the total instead of leaving the field
empty. The 20b did this on five clean invoices, the 120b on two. On the eight hard
invoices, where a subtotal is either clearly stated or clearly absent, both models scored
8/8.

This does not misroute documents. The arithmetic gate in `validator.py` runs only when
subtotal, tax and total are all present, and both models left `tax_amount` empty on every
invoice where they invented a subtotal, so the gate skipped. It costs accuracy, not
correctness.

## What both models get wrong

- A contract worth 0.0 comes back as null (`con_009_zero_value`), for both models. Zero
  is being read as "no value".
- `con_007_minimal` yields no obligations where the labels expect some.
- `inv_005_messy_formatting` gives no currency where the label says USD; the invoice
  writes `$340` with no currency code.

## Hard-case misses

Only three, across both models:

- `inv_014_ambiguous_date_format`, both models: returned `03/04/2026` verbatim rather than
  a normalised date. The matcher parses that as 4 March, the label says 3 April, which is
  what the invoice's 30-day terms require. The model copied the ambiguity through instead
  of resolving it.
- `inv_016_credit_note`, 20b only: took the referenced original invoice number
  (`AP-2026-0912`) instead of the credit note's own (`CN-2026-0031`), and returned no date.

Everything else in the hard set was read correctly by both models, including the
letterhead vendor over the "Bill To" company, the invoice total over account balance due,
OCR text with `O` for `0`, the negative credit-note total, five line items split across
two pages, Italian comma decimals, a contract value that exists only as the sum of three
milestones, and the amendment that supersedes the original value. Both models ignored the
`inv_017_prompt_injection` document's instruction to change the vendor and zero the total.

## Errors and retries

One case errored rather than failed. In the 20b run over 32 cases,
`inv_003_multiple_items` hit Groq's rate limit:

```
status_code: 429 ... tokens per minute (TPM): Limit 8000, Used 6955, Requested 1069
```

That case was re-run on its own about 30 seconds later and scored 9/9; the log is
`2026-09-18-openai-gpt-oss-20b-32cases-inv_003-retry.txt`, and its result is included in
the 20b numbers above. No other case errored in any run. Anyone reproducing this on the
free tier should expect the occasional 429 on the 32-case set.

## Logs in this folder

| File | Model | Cases |
|---|---|---|
| `2026-09-18-openai-gpt-oss-20b.txt` | gpt-oss-20b | 20 clean |
| `2026-09-18-openai-gpt-oss-120b.txt` | gpt-oss-120b | 20 clean |
| `2026-09-18-openai-gpt-oss-20b-32cases.txt` | gpt-oss-20b | 32 (inv_003 errored) |
| `2026-09-18-openai-gpt-oss-20b-32cases-inv_003-retry.txt` | gpt-oss-20b | the retried case |
| `2026-09-18-openai-gpt-oss-120b-32cases.txt` | gpt-oss-120b | 32 |

The two 20-case logs are kept because they are the only measurements of the clean set
before the hard cases existed.

## How to reproduce

```bash
# set LLM_MODEL in .env to the model you want, then
uv run pytest backend/tests/evaluation -s
```

32 real Groq calls per run, which is why this suite is kept out of CI.

## What these numbers do not cover

- Per-case latency and token counts. The harness records neither; the only timing is
  pytest's total per run. That instrumentation is V1-7's `run_eval.py`, not yet written.
- OCR itself. `inv_013_ocr_noise` contains text shaped like Tesseract output, but it is
  typed, not produced by running Tesseract on an image, so the parser is still unmeasured.
- A pass/fail threshold worth trusting. Each case asserts at 60% of fields for invoices
  and 50% for contracts, so "32 passed" means every case cleared a low bar, not that the
  extraction was right. The field counts above are the real measurement.
- Model availability over time. Quote any number from this file with the model name and
  the date.
