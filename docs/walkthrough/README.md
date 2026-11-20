# Walkthrough video

A 78-second screen recording of the real app, with captions burned in. It is
recorded by a script, so it can be redone after any UI change.

## What it shows (in order)
1. Hook: an invoice whose total does not equal its line items. "Would your system notice?"
2. A scanned photo of that invoice is uploaded. OCR, queue, worker and model run.
3. The document is **held for review**, and the reason is written on the screen.
   The original file stays beside the values while it waits (issue #56).
4. Reject with a reason; the list shows REJECTED (issue #57).
5. A regular PDF from another vendor completes without review.
6. Export as JSON; a guided-tour clip (issue #59).
7. Closing card with the committed eval numbers and the links.

## What is real and what is edited
- The app, queue, database and model (`openai/gpt-oss-20b` through Groq) are real.
  Only the two waits for the model are sped up 8x, with a "sped up" caption.
- The closing numbers (262 of 274 field checks, 32 labelled documents, one run,
  18 Sep 2026) come from `evals/results/` and the README. One run is not a rate.
- The sample invoices are invented (`scripts/walkthrough/make_samples.py`).
- The recording was made on a local branch that merges the fixes for #55 to #59,
  #65 and #70, because the video shows those fixes working. Re-record after they merge.

## Redo it
Needs the stack running locally (API, worker, frontend, Redis, Postgres, a Groq
key), Playwright for Node, `ffmpeg`, and Tesseract. None of these are project
dependencies; this folder is a helper, not part of the product.

```bash
uv run python scripts/walkthrough/make_samples.py /tmp/demo-samples
node scripts/walkthrough/record_demo.js /tmp/demo-video /tmp/demo-samples
python3 scripts/walkthrough/post_demo.py /tmp/demo-video /tmp/demo-final
```

The last step writes the MP4, an SRT, a thumbnail and `NARRATION.md` (timed
lines to read in your own voice). Set the per-session limit to 10 first
(`RATE_LIMIT_PER_SESSION=10`) so the usage badge matches the live site.

## Why it opens the way it does
Advice from video-marketing blogs (practitioner advice, not research) agrees on
a few points, which this cut follows: open on the problem instead of a logo or a
greeting, show the product doing the thing quickly, and finish with proof and a
link.
- https://flowjam.com/blog/startup-product-demo-video
- https://www.yansmedia.com/blog/explainer-video-hook-techniques
- https://dev.to/pickuma/how-to-build-a-portfolio-project-that-survives-a-2026-recruiter-screen-49kp

The video file itself is not in git. Upload it to Loom or YouTube and link it
from the README ("Walkthrough video: not recorded yet" is there today).
