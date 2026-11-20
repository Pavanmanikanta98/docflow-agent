"""Turn the raw recording into the final MP4 + subtitles + a timed narration script.

Usage: python3 post_demo.py <video_dir> <out_dir>
Reads  <video_dir>/raw.webm and events.json (written by record_demo.js).
Writes <out_dir>/docflow-walkthrough.mp4, .srt, thumbnail.png, NARRATION.md
Only the two waiting-for-the-model stretches are sped up (8x); they carry an
on-screen "sped up" caption, so nothing is hidden.
"""
import json
import subprocess
import sys
from pathlib import Path

video_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
out_dir.mkdir(parents=True, exist_ok=True)
events = json.loads((video_dir / "events.json").read_text())
SPEED = 8.0
end_ms = next(e["t"] for e in events if e["type"] == "end")
marks = {e["name"]: e["t"] for e in events if e["type"] == "mark"}

# (start_ms, end_ms, speed)
fast = [(marks["fast-start"], marks["fast-end"]), (marks["fast2-start"], marks["fast2-end"])]
segments, cursor = [], 0
for a, b in fast:
    if a > cursor:
        segments.append((cursor, a, 1.0))
    segments.append((a, b, SPEED))
    cursor = b
segments.append((cursor, end_ms, 1.0))


def out_time(t_ms: float) -> float:
    """Map a raw-recording time to the time in the edited video, in seconds."""
    total = 0.0
    for a, b, f in segments:
        if t_ms >= b:
            total += (b - a) / f / 1000
        else:
            return total + max(t_ms - a, 0) / f / 1000
    return total


parts = []
for i, (a, b, f) in enumerate(segments):
    parts.append(
        f"[0:v]trim=start={a/1000:.3f}:end={b/1000:.3f},setpts=(PTS-STARTPTS)/{f},fps=30[v{i}]"
    )
concat = "".join(f"[v{i}]" for i in range(len(segments)))
graph = ";".join(parts) + f";{concat}concat=n={len(segments)}:v=1:a=0[out]"
mp4 = out_dir / "docflow-walkthrough.mp4"
subprocess.run(
    ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video_dir / "raw.webm"),
     "-filter_complex", graph, "-map", "[out]", "-c:v", "libx264", "-crf", "20",
     "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)],
    check=True,
)
duration = float(subprocess.check_output(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)]
).decode().strip())
subprocess.run(
    ["ffmpeg", "-y", "-loglevel", "error", "-ss", "2.0", "-i", str(mp4), "-frames:v", "1",
     str(out_dir / "thumbnail.png")], check=True)


def srt_time(s: float) -> str:
    ms = int(round(s * 1000))
    return f"{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}"


# captions -> SRT (a caption lasts until the next caption/clear/card event)
timeline = [e for e in events if e["type"] in ("caption", "card", "end")]
cues = []
for i, e in enumerate(timeline):
    if e["type"] != "caption" or not e["text"]:
        continue
    nxt = timeline[i + 1]["t"] if i + 1 < len(timeline) else end_ms
    cues.append((out_time(e["t"]), out_time(nxt), e["text"]))
(out_dir / "docflow-walkthrough.srt").write_text(
    "\n".join(f"{n}\n{srt_time(a)} --> {srt_time(b)}\n{t}\n" for n, (a, b, t) in enumerate(cues, 1))
)

# narration: suggested spoken lines, timed to the first on-screen event of each scene
NARRATION = [
    ("This invoice says the total is", "Look at this invoice. The total says one thousand four hundred thirty-nine dollars twenty. The line items add up to one thousand three hundred thirty-nine twenty. Would your system notice?"),
    ("DocFlow: upload the invoice.", "I upload a photo of it to DocFlow. OCR reads the image, and a queue, a worker and a language model extract the fields in the background."),
    ("Held for review.", "It is not approved silently. The totals check fails, so the document is held for review."),
    ("The reason is written", "The reason is written right on the screen."),
    ("While it waits for review", "While it waits for review, the original file stays next to the extracted values, so checking takes seconds."),
    ("Reject it, with a reason.", "I reject it with a reason, and the list shows it as rejected."),
    ("Now a regular PDF", "Now a regular PDF from another vendor. The same checks run, the numbers add up, and it completes without review."),
    ("Completed documents export", "Completed documents export as JSON or CSV."),
    ("A guided tour walks", "First-time visitors get a guided tour of every screen."),
    ("262 of 274", "On my 32 hand-labelled test documents, one run of a small open model got 262 of 274 field checks right. The code is open source, and the live demo link is on screen."),
]
rows = []
for needle, spoken in NARRATION:
    ev = next((e for e in events if e["type"] in ("caption", "card") and needle in e["text"]), None)
    if ev:
        s = out_time(ev["t"])
        rows.append((s, spoken))
md = [
    "# DocFlow walkthrough: timed narration",
    "",
    f"Video: `docflow-walkthrough.mp4`, {duration:.0f} seconds, 1280x720, captions burned in.",
    "Record your own voice over it (phone or Loom), reading the lines below at the times shown.",
    "Speak a little slower than feels natural; the pauses are long enough for it.",
    "",
    "| Time | Say |",
    "|---|---|",
] + [f"| {int(t//60)}:{int(t%60):02} | {line} |" for t, line in rows] + [
    "",
    "## What is real and what is edited",
    "- Everything on screen is the real app running locally with the real `openai/gpt-oss-20b` model, a real queue and a real database.",
    "- The two waits for the model (about 9 to 25 seconds each) are sped up 8x, and the caption says \"sped up\". Nothing else is cut.",
    "- The closing numbers (262 of 274, 32 documents, one run, 18 Sep 2026) come from `evals/results/` and the README. One run is not a rate; say \"one run\".",
    "- Do not say \"production\", \"customers\" or \"users\": the demo has none.",
]
(out_dir / "NARRATION.md").write_text("\n".join(md) + "\n")
print(f"{mp4.name}: {duration:.1f}s (raw {end_ms/1000:.1f}s); {len(cues)} captions; {len(rows)} narration lines")
