# License — CORD-v2 subset

The 50 images and label mappings in this directory are a subset of
**CORD (Consolidated Receipt Dataset)**, redistributed here under the
**Creative Commons Attribution 4.0 International (CC BY 4.0)** license.

- Full license text: https://creativecommons.org/licenses/by/4.0/legalcode
- Source (Hugging Face mirror, license tag verified 2026-09-24):
  https://huggingface.co/datasets/naver-clova-ix/cord-v2
- Upstream project: CLOVA AI Research (NAVER), https://github.com/clovaai/cord

## Attribution

> Seunghyun Park, Seung Shin, Bado Lee, Junyeop Lee, Jaeheung Surh,
> Minjoon Seo, Hwalsuk Lee. **"CORD: A Consolidated Receipt Dataset for
> Post-OCR Parsing."** Document Intelligence Workshop at NeurIPS 2019.

## What was changed

The 50 images (`images/`) are the original PNG bytes from the dataset's
`test` split, rows 0–49, re-saved verbatim with no re-compression or
re-encoding. `labels.json` maps each image's original CORD ground truth
(`gt_parse`) onto this project's `InvoiceFields` schema — see
`../README.md` for the exact field mapping and which fields are scored.
