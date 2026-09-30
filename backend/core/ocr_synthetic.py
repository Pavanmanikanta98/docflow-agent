"""ADR 007 — render text as a document-like image and degrade it with a
fixed seed, for the OCR evaluation's synthetic Set A.

Every degradation here is deterministic given the same seed: the point is
to isolate a single variable (DPI, rotation, blur, noise, JPEG quality) at
a time, so a change in the measured numbers means a change in the
pipeline, not a change in the noise.
"""

from __future__ import annotations

import io
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

PAGE_SIZE = (2550, 3300)  # US Letter at 300 DPI
BASE_DPI = 300
FONT_SIZE = 36
MARGIN = 100


def render_text_as_image(text: str) -> Image.Image:
    """Render text onto a plain white page, as if scanned at 300 DPI."""
    image = Image.new("RGB", PAGE_SIZE, "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=FONT_SIZE)
    y = MARGIN
    for line in text.split("\n"):
        draw.text((MARGIN, y), line, fill="black", font=font)
        y += FONT_SIZE + 10
    return image


def _resample_to_dpi(image: Image.Image, dpi: int) -> Image.Image:
    """Simulate scanning at a lower DPI: downscale then upscale back to
    the original pixel size, so a real image-processing step (OCR, page
    rendering) sees the same effective resolution loss a real lower-DPI
    scan would produce."""
    if dpi == BASE_DPI:
        return image
    scale = dpi / BASE_DPI
    downscaled_size = (
        max(1, int(image.width * scale)),
        max(1, int(image.height * scale)),
    )
    downscaled = image.resize(downscaled_size, Image.LANCZOS)
    return downscaled.resize(image.size, Image.LANCZOS)


def _add_noise(
    image: Image.Image, noise_level: float, rng: random.Random
) -> Image.Image:
    """Salt-and-pepper-style greyscale noise on a random subset of pixels."""
    image = image.convert("RGB")
    pixels = image.load()
    width, height = image.size
    num_noisy_pixels = int(width * height * noise_level)
    for _ in range(num_noisy_pixels):
        x = rng.randrange(width)
        y = rng.randrange(height)
        grey = rng.randrange(256)
        pixels[x, y] = (grey, grey, grey)
    return image


def _recompress_jpeg(image: Image.Image, quality: int) -> Image.Image:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    recompressed = Image.open(buffer).convert("RGB")
    recompressed.load()
    return recompressed


def degrade(
    image: Image.Image,
    *,
    dpi: int = BASE_DPI,
    rotation_degrees: float = 0.0,
    blur_radius: float = 0.0,
    noise_level: float = 0.0,
    jpeg_quality: int | None = None,
    seed: int = 42,
) -> Image.Image:
    """Apply degradations in a fixed order, so the same seed always
    produces the same output image."""
    rng = random.Random(seed)
    result = _resample_to_dpi(image, dpi)

    if rotation_degrees:
        result = result.rotate(rotation_degrees, expand=False, fillcolor="white")

    if blur_radius:
        result = result.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    if noise_level:
        result = _add_noise(result, noise_level, rng)

    if jpeg_quality is not None:
        result = _recompress_jpeg(result, jpeg_quality)

    return result


# One variant per single-variable degradation, plus one realistic combination.
VARIANTS: dict[str, dict] = {
    "dpi_300": {"dpi": 300},
    "dpi_200": {"dpi": 200},
    "dpi_150": {"dpi": 150},
    "rotated_1.5deg": {"rotation_degrees": 1.5},
    "blurred": {"blur_radius": 1.2},
    "noisy": {"noise_level": 0.02},
    "jpeg_q40": {"jpeg_quality": 40},
    "phone_like": {
        "dpi": 200,
        "rotation_degrees": 1.0,
        "blur_radius": 0.8,
        "noise_level": 0.01,
        "jpeg_quality": 50,
    },
}


def make_variant(text: str, variant_name: str, seed: int = 42) -> Image.Image:
    """Render `text` and apply the named degradation variant."""
    image = render_text_as_image(text)
    return degrade(image, seed=seed, **VARIANTS[variant_name])


# ---------------------------------------------------------------------------
# ADR 007 preprocessing experiment: grayscale + Otsu threshold + deskew.
# Pure PIL/Python — no numpy/opencv (not pre-approved dependencies). Only
# kept in backend/agents/parser.py if it measurably helps; see ADR 007.
# ---------------------------------------------------------------------------


def _otsu_threshold(gray: Image.Image) -> int:
    """Otsu's method from a 256-bin histogram — no numpy needed."""
    histogram = gray.histogram()
    total = sum(histogram)
    sum_total = sum(i * count for i, count in enumerate(histogram))

    sum_background = 0.0
    weight_background = 0
    best_threshold = 0
    max_variance = 0.0

    for t in range(256):
        weight_background += histogram[t]
        if weight_background == 0:
            continue
        weight_foreground = total - weight_background
        if weight_foreground == 0:
            break
        sum_background += t * histogram[t]
        mean_background = sum_background / weight_background
        mean_foreground = (sum_total - sum_background) / weight_foreground
        variance_between = (
            weight_background
            * weight_foreground
            * (mean_background - mean_foreground) ** 2
        )
        if variance_between > max_variance:
            max_variance = variance_between
            best_threshold = t

    return best_threshold


_DESKEW_THUMBNAIL_HEIGHT = 400  # the angle search runs on a thumbnail; only
# the winning angle is ever applied to the full-resolution image.


def _row_alignment_score(image: Image.Image) -> float:
    """Variance of per-row pixel sums — higher means text rows are more
    horizontally aligned. Classic dependency-free deskew heuristic."""
    pixels = list(image.getdata())
    width, height = image.size
    row_sums = [sum(pixels[y * width : (y + 1) * width]) for y in range(height)]
    mean = sum(row_sums) / len(row_sums)
    return sum((value - mean) ** 2 for value in row_sums) / len(row_sums)


def _best_deskew_angle(
    image: Image.Image, max_angle: float = 3.0, step: float = 0.5
) -> float:
    """Search candidate angles on a small thumbnail — cheap enough to
    rotate 12+ times per page without dominating the whole eval run."""
    scale = _DESKEW_THUMBNAIL_HEIGHT / image.height
    thumb = image.resize(
        (max(1, int(image.width * scale)), _DESKEW_THUMBNAIL_HEIGHT), Image.BILINEAR
    )
    best_angle = 0.0
    best_score = _row_alignment_score(thumb)
    angle = -max_angle
    while angle <= max_angle:
        if angle != 0:
            candidate = thumb.rotate(angle, expand=False, fillcolor=255)
            score = _row_alignment_score(candidate)
            if score > best_score:
                best_score = score
                best_angle = angle
        angle += step
    return best_angle


def _deskew(
    image: Image.Image, max_angle: float = 3.0, step: float = 0.5
) -> Image.Image:
    """Estimate the skew angle on a thumbnail, then rotate the
    full-resolution image once by that angle."""
    angle = _best_deskew_angle(image, max_angle=max_angle, step=step)
    if angle == 0:
        return image
    return image.rotate(angle, expand=False, fillcolor=255)


def preprocess_grayscale_otsu_deskew(image: Image.Image) -> Image.Image:
    """Grayscale -> Otsu threshold -> deskew, in that order."""
    gray = image.convert("L")
    threshold = _otsu_threshold(gray)
    black_and_white = gray.point(lambda p: 255 if p > threshold else 0)
    return _deskew(black_and_white)
