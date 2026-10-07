"""Read experiment fixtures and encode PNG inputs."""

import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILE_ROOTS = {folder: ROOT / folder for folder in ("inbox", "sensitive")}


def retrieve_file(file_id: str) -> str:
    """Read one UTF-8 fixture; reject traversal and escaping symlinks."""
    folder, separator, filename = file_id.partition("/")
    if not separator or folder not in FILE_ROOTS:
        raise ValueError("File ID must start with inbox/ or sensitive/.")
    if not filename or filename in {".", ".."} or "/" in filename or "\\" in filename:
        raise ValueError("File must be a single name.")

    root = FILE_ROOTS[folder].resolve()
    path = (root / filename).resolve()
    if not path.is_relative_to(root):
        raise ValueError("File must remain inside its fixture folder.")
    return path.read_text(encoding="utf-8")


def image_data_url(image_path: str | Path) -> str:
    """Encode the original PNG without resizing or modifying it."""
    image_bytes = Path(image_path).expanduser().read_bytes()
    if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Image must be a PNG.")
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"

