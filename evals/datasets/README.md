# OCR evaluation datasets (ADR 007)

Two sets, used by `backend/tests/evaluation/run_ocr_eval.py`. Neither is
scored the same way as the deterministic golden-text evaluation
(`backend/tests/evaluation/golden/`) — these measure what OCR costs versus
a clean text layer, not overall extraction accuracy.

## Set A — synthetic degraded scans

**Source.** The 20 existing golden invoice/contract texts
(`backend/tests/evaluation/golden/invoices.json`,
`backend/tests/evaluation/golden/contracts.json`), rendered to images with
`backend/core/ocr_synthetic.py` and degraded with a fixed seed (42) across
8 variants: 300/200/150 DPI, ±1.5° rotation, Gaussian blur, sensor noise,
JPEG quality 40, and one combined "phone-like" variant.

**License.** N/A — these are this project's own golden texts, rendered to
images by this project's own code. No third-party data, nothing to
redistribute under a license.

**Ground truth.** The existing golden `expected` blocks — every field
`InvoiceFields`/`ContractFields` define, including `vendor_name`,
`invoice_number`, `invoice_date`, `due_date`.

**Not committed as files.** Set A is generated at eval-run time from the
golden JSON already in the repo — there is nothing to download or store
under `evals/datasets/`.

## Set B — CORD-v2 (real scanned receipts)

**Source.** [naver-clova-ix/cord-v2](https://huggingface.co/datasets/naver-clova-ix/cord-v2)
on Hugging Face — a mirror of CLOVA AI Research's
[CORD](https://github.com/clovaai/cord) (Consolidated Receipt Dataset),
verified live on 2026-09-24 (license tag `cc-by-4.0` on the dataset card).

**License.** CC BY 4.0. Full text and attribution: `cord-v2/LICENSE.md`.

**Subset.** The **first 50 rows of the `test` split** (rows 0–49 of 100),
selected by index for reproducibility, not cherry-picked. Images are the
original PNG bytes, committed as-is with no re-compression
(`cord-v2/images/cord_test_000.png` … `cord_test_049.png`).
Total size of `evals/datasets/`: **109 MB**.

**Label mapping.** CORD's `ground_truth.gt_parse` maps onto this project's
`InvoiceFields` as follows (`cord-v2/labels.json`):

| CORD field | `InvoiceFields` field | Notes |
|---|---|---|
| `sub_total.subtotal_price` | `subtotal` | Parsed to float; currency symbols/commas stripped |
| `sub_total.tax_price` | `tax_amount` | Same parsing |
| `total.total_price` | `total_amount` | Same parsing |
| `menu.nm` (one or many) | `line_items` | Item name(s); `menu` is a single object or a list in CORD, normalized to a list of names |
| — | `vendor_name` | **Not scored on Set B** — CORD does not label a vendor/merchant name field |
| — | `invoice_date` | **Not scored on Set B** — CORD does not label a date field |
| — | `invoice_number` | **Not scored on Set B** — CORD does not label a reference-number field |

A field CORD does not label is left `null` in `labels.json` and excluded
from scoring entirely — never guessed or drafted from reading the image.

**Date and invoice-number coverage.** A 20-minute search (2026-09-24) for a
clearly CC-BY/CC0 scanned receipt or invoice dataset that also labels a
date field found nothing that met the bar — candidates were either
unlicensed/unclear (most Hugging Face invoice-OCR datasets found) or under
a different license (e.g. ODbL). SROIE was considered for Set B originally
and dropped for the same reason: its original license cannot be verified.
**`invoice_date` and `invoice_number` are therefore scored on Set A only** —
`run_ocr_eval.py` and the README report this scope limit next to those
numbers, not silently.

## Golden vs. OCR-eval ground truth

Both sets score against the fields their source actually provides. Set A's
ground truth is this project's own hand-written golden data (full field
coverage). Set B's is CORD's own human-labeled `gt_parse` (partial field
coverage, per the table above) — never re-derived or drafted by reading a
CORD image, per this project's rule that only a source's own labels count
as ground truth.
