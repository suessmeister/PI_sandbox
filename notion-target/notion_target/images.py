"""Validate uploaded image bytes before sending them to the model."""

import io
import warnings

from fastapi import HTTPException
from PIL import Image

MAX_BYTES = 10 * 1024 * 1024


def validate_image(data, mime):
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Image exceeds 10 MiB")
    if mime not in ("image/png", "image/jpeg"):
        raise HTTPException(415, "Image must be PNG or JPEG")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format != {"image/png": "PNG", "image/jpeg": "JPEG"}[mime]:
                    raise ValueError("MIME mismatch")
                if image.width * image.height > 20000000:
                    raise ValueError("Too many pixels")
                image.verify()
    except Exception:
        raise HTTPException(
            400, "Invalid image or image exceeds 20 megapixels"
        ) from None
