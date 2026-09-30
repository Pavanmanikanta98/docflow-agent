"""ADR 007 — synthetic degradation is deterministic given a seed, and each
variant actually changes the image (otherwise it isn't testing anything)."""

from PIL import ImageChops

from backend.core.ocr_synthetic import (
    VARIANTS,
    make_variant,
    preprocess_grayscale_otsu_deskew,
    render_text_as_image,
)

SAMPLE_TEXT = "INVOICE #INV-1\nTotal: $100.00"


def test_render_produces_the_expected_page_size():
    image = render_text_as_image(SAMPLE_TEXT)
    assert image.size == (2550, 3300)


def test_same_seed_produces_identical_images():
    first = make_variant(SAMPLE_TEXT, "noisy", seed=7)
    second = make_variant(SAMPLE_TEXT, "noisy", seed=7)
    assert list(first.getdata()) == list(second.getdata())


def test_different_seeds_produce_different_noisy_images():
    first = make_variant(SAMPLE_TEXT, "noisy", seed=1)
    second = make_variant(SAMPLE_TEXT, "noisy", seed=2)
    assert list(first.getdata()) != list(second.getdata())


def test_every_degrading_variant_changes_the_base_image():
    """dpi_300 is deliberately the no-degradation control (see the test
    below) — every other variant must actually alter the image."""
    base = render_text_as_image(SAMPLE_TEXT)
    for variant_name in VARIANTS:
        if variant_name == "dpi_300":
            continue
        degraded = make_variant(SAMPLE_TEXT, variant_name)
        diff = ImageChops.difference(base.convert("RGB"), degraded.convert("RGB"))
        assert diff.getbbox() is not None, f"{variant_name} did not change the image"


def test_dpi_300_variant_is_the_least_altered():
    """dpi_300 applies no resampling — it should be identical to the
    unmodified render (it exists as the "no degradation" control)."""
    base = render_text_as_image(SAMPLE_TEXT)
    variant = make_variant(SAMPLE_TEXT, "dpi_300")
    assert list(base.getdata()) == list(variant.getdata())


def test_preprocessing_returns_a_black_and_white_image():
    image = make_variant(SAMPLE_TEXT, "noisy")
    processed = preprocess_grayscale_otsu_deskew(image)
    values = set(processed.convert("L").getdata())
    assert values <= {0, 255}
