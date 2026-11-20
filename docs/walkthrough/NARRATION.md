# DocFlow walkthrough: timed narration

Video: `docflow-walkthrough.mp4`, 78 seconds, 1280x720, captions burned in.
Record your own voice over it (phone or Loom), reading the lines below at the times shown.
Speak a little slower than feels natural; the pauses are long enough for it.

| Time | Say |
|---|---|
| 0:01 | Look at this invoice. The total says one thousand four hundred thirty-nine dollars twenty. The line items add up to one thousand three hundred thirty-nine twenty. Would your system notice? |
| 0:06 | I upload a photo of it to DocFlow. OCR reads the image, and a queue, a worker and a language model extract the fields in the background. |
| 0:13 | It is not approved silently. The totals check fails, so the document is held for review. |
| 0:18 | The reason is written right on the screen. |
| 0:21 | While it waits for review, the original file stays next to the extracted values, so checking takes seconds. |
| 0:26 | I reject it with a reason, and the list shows it as rejected. |
| 0:36 | Now a regular PDF from another vendor. The same checks run, the numbers add up, and it completes without review. |
| 0:49 | Completed documents export as JSON or CSV. |
| 1:00 | First-time visitors get a guided tour of every screen. |
| 1:11 | On my 32 hand-labelled test documents, one run of a small open model got 262 of 274 field checks right. The code is open source, and the live demo link is on screen. |

## What is real and what is edited
- Everything on screen is the real app running locally with the real `openai/gpt-oss-20b` model, a real queue and a real database.
- The two waits for the model (about 9 to 25 seconds each) are sped up 8x, and the caption says "sped up". Nothing else is cut.
- The closing numbers (262 of 274, 32 documents, one run, 18 Sep 2026) come from `evals/results/` and the README. One run is not a rate; say "one run".
- Do not say "production", "customers" or "users": the demo has none.
