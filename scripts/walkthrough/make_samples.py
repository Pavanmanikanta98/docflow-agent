"""Make the two sample invoices the walkthrough uses.

Usage: uv run python scripts/walkthrough/make_samples.py <out_dir>

- invoice_wrong_total.jpg: a degraded scan (noise, blur, slight rotation) whose
  total does not equal subtotal + tax. The pipeline holds it for review.
- invoice_ok.pdf: a digital PDF whose numbers add up. It completes.
All values are invented; no real vendor or customer data.
"""

import random
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")


def invoice_lines(vendor, number, date, due, items, subtotal, tax, total):
    lines = [
        ("h", vendor), ("t", "123 Harbour Road, Mumbai 400001"), ("s", ""),
        ("b", f"INVOICE {number}"), ("t", f"Date: {date}"), ("t", f"Due: {due}"),
        ("t", "Bill to: Contoso Retail Pvt Ltd"), ("s", ""),
    ]
    for desc, qty, unit, amount in items:
        lines.append(("t", f"{desc:<28}{qty:>3} x {unit:>9}   {amount:>10}"))
    lines += [
        ("s", ""), ("t", f"Subtotal: {subtotal}"), ("t", f"Tax (8%): {tax}"),
        ("b", f"Total: {total}"), ("t", "Currency: USD"),
    ]
    return lines


def make_scan(lines, path: Path) -> None:
    fonts = {
        "h": ImageFont.truetype(str(FONT_DIR / "DejaVuSans-Bold.ttf"), 38),
        "b": ImageFont.truetype(str(FONT_DIR / "DejaVuSans-Bold.ttf"), 30),
        "t": ImageFont.truetype(str(FONT_DIR / "DejaVuSansMono.ttf"), 26),
        "s": ImageFont.truetype(str(FONT_DIR / "DejaVuSans.ttf"), 12),
    }
    img = Image.new("L", (1240, 900), 245)
    draw, y = ImageDraw.Draw(img), 70
    for kind, text in lines:
        draw.text((80, y), text, fill=25, font=fonts[kind])
        y += fonts[kind].size + 16
    random.seed(11)
    pixels = img.load()
    for _ in range(60000):
        x, yy = random.randrange(img.width), random.randrange(img.height)
        pixels[x, yy] = max(0, min(255, pixels[x, yy] + random.randint(-40, 40)))
    img.rotate(-1.0, fillcolor=235).filter(ImageFilter.GaussianBlur(0.8)).save(path, quality=62)


def make_pdf(lines, path: Path) -> None:
    doc = pymupdf.open()
    page, y = doc.new_page(), 72
    for kind, text in lines:
        size = {"h": 20, "b": 14, "t": 11, "s": 6}[kind]
        page.insert_text((60, y), text, fontsize=size,
                         fontname="courier" if kind == "t" else "helv")
        y += size + 7
    doc.save(path)


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    wrong_total = invoice_lines(
        "Northwind Traders", "NT-2026-0417", "2026-04-02", "2026-05-02",
        [("Steel brackets (box of 50)", 4, "$180.00", "$720.00"),
         ("Mounting plates", 8, "$65.00", "$520.00")],
        "$1,240.00", "$99.20", "$1,439.20",  # items add up to $1,339.20
    )
    correct = invoice_lines(
        "Kaveri Office Supplies", "KOS-8841", "2026-03-18", "2026-04-17",
        [("A4 paper (carton)", 5, "$42.00", "$210.00"),
         ("Whiteboard markers", 20, "$6.50", "$130.00"),
         ("Desk organisers", 10, "$52.00", "$520.00")],
        "$860.00", "$68.80", "$928.80",
    )
    make_scan(wrong_total, out / "invoice_wrong_total.jpg")
    make_pdf(correct, out / "invoice_ok.pdf")
    print(f"wrote samples to {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
