from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PIL import Image


@dataclass
class PreprocessedImage:
    image_bytes: bytes
    original_width: int
    original_height: int
    processed_width: int
    processed_height: int
    crop_applied: bool
    crop_box: tuple[int, int, int, int] | None
    resize_applied: bool
    compressed: bool

    def metadata(self) -> dict[str, int | bool]:
        return {
            'original_width': self.original_width,
            'original_height': self.original_height,
            'processed_width': self.processed_width,
            'processed_height': self.processed_height,
            'crop_applied': self.crop_applied,
            'crop_box': list(self.crop_box) if self.crop_box else None,
            'resize_applied': self.resize_applied,
            'compressed': self.compressed,
        }


def _pil() -> tuple[Any, Any]:
    try:
        from PIL import Image, ImageOps

        return Image, ImageOps
    except ModuleNotFoundError as exc:
        raise RuntimeError('Pillow is required for screenshot preprocessing.') from exc


def _content_bbox(image: 'Image.Image', threshold: int = 252) -> tuple[int, int, int, int] | None:
    _, image_ops = _pil()
    grayscale = image_ops.grayscale(image)
    mask = grayscale.point(lambda px: 255 if px < threshold else 0)
    return mask.getbbox()


def detect_slip_region(image: 'Image.Image') -> tuple[int, int, int, int]:
    width, height = image.size
    bbox = _content_bbox(image)
    if not bbox:
        return (0, 0, width, height)

    left, top, right, bottom = bbox
    pad = max(24, int(min(width, height) * 0.02))
    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(width, right + pad)
    bottom = min(height, bottom + pad)

    cropped_width = right - left
    cropped_height = bottom - top
    if cropped_width < int(width * 0.35) or cropped_height < int(height * 0.35):
        return (0, 0, width, height)
    return (left, top, right, bottom)


def resize_for_vision(image: 'Image.Image', max_width: int = 1000) -> tuple['Image.Image', bool]:
    image_mod, _ = _pil()
    width, height = image.size
    if width <= max_width:
        return image, False
    ratio = max_width / float(width)
    resized = image.resize((max_width, max(1, int(height * ratio))), image_mod.Resampling.LANCZOS)
    return resized, True


def preprocess_screenshot(image_bytes: bytes) -> PreprocessedImage:
    image_mod, _ = _pil()
    with image_mod.open(BytesIO(image_bytes)) as opened:
        image = opened.convert('RGB')

    original_width, original_height = image.size
    box = detect_slip_region(image)
    crop_applied = box != (0, 0, original_width, original_height)
    if crop_applied:
        image = image.crop(box)

    image, resize_applied = resize_for_vision(image, max_width=1000)

    out = BytesIO()
    image.save(out, format='PNG', optimize=True)
    processed = out.getvalue()
    compressed = False

    if len(processed) > 3_000_000:
        jpg = BytesIO()
        image.save(jpg, format='JPEG', quality=88, optimize=True)
        jpg_bytes = jpg.getvalue()
        if len(jpg_bytes) < len(processed):
            processed = jpg_bytes
            compressed = True

    return PreprocessedImage(
        image_bytes=processed,
        original_width=original_width,
        original_height=original_height,
        processed_width=image.size[0],
        processed_height=image.size[1],
        crop_applied=crop_applied,
        crop_box=box if crop_applied else None,
        resize_applied=resize_applied,
        compressed=compressed,
    )
