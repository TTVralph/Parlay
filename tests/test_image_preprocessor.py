from io import BytesIO

import pytest

pytest.importorskip('PIL')
from PIL import Image, ImageDraw

from app.services.image_preprocessor import detect_slip_region, preprocess_screenshot


def _png_bytes(image: Image.Image) -> bytes:
    out = BytesIO()
    image.save(out, format='PNG')
    return out.getvalue()


def test_large_screenshots_get_resized() -> None:
    image = Image.new('RGB', (2200, 1600), 'white')
    ImageDraw.Draw(image).rectangle((150, 200, 2050, 1450), fill='black')

    processed = preprocess_screenshot(_png_bytes(image))

    assert processed.processed_width <= 1000
    assert processed.resize_applied is True


def test_blank_margins_get_trimmed() -> None:
    image = Image.new('RGB', (1200, 900), 'white')
    ImageDraw.Draw(image).rectangle((240, 180, 960, 760), fill='black')

    processed = preprocess_screenshot(_png_bytes(image))

    assert processed.crop_applied is True
    assert processed.processed_width < processed.original_width
    assert processed.processed_height < processed.original_height


def test_detect_slip_region_is_conservative_for_leg_text() -> None:
    image = Image.new('RGB', (1000, 1400), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((200, 210, 820, 260), fill='black')
    draw.rectangle((200, 1180, 820, 1230), fill='black')

    left, top, right, bottom = detect_slip_region(image)

    assert top <= 200
    assert bottom >= 1240
    assert left <= 190
    assert right >= 830


def test_processed_image_smaller_than_original_when_trimmed() -> None:
    image = Image.new('RGB', (1600, 1200), 'white')
    draw = ImageDraw.Draw(image)
    for i in range(8):
        y = 200 + (i * 100)
        draw.rectangle((280, y, 1320, y + 45), fill='black')

    original_bytes = _png_bytes(image)
    processed = preprocess_screenshot(original_bytes)

    assert len(processed.image_bytes) < len(original_bytes)
