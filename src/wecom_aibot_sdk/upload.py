"""Upload helper utilities for WeCom media upload protocol"""

import re
from pathlib import Path

WECOM_UPLOAD_MAX_BYTES = 200 * 1024 * 1024  # 200MB
WECOM_UPLOAD_CHUNK_SIZE = 512 * 1024  # 512KB (before base64)

_UNSAFE_FILENAME_RE = re.compile(r"[^\w.\-]")


def _sanitize_filename(name: str) -> str:
    """Extract safe filename from a path string."""
    return _UNSAFE_FILENAME_RE.sub("_", Path(name).name)


def _guess_wecom_media_type(filename: str) -> str:
    """Guess WeCom media type from file extension."""
    ext = Path(filename).suffix.lower()
    if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
        return "image"
    if ext in (".mp4", ".avi", ".mov"):
        return "video"
    if ext in (".amr", ".mp3", ".wav", ".ogg"):
        return "voice"
    return "file"


def _validate_upload_file(file_path: str) -> tuple[str, str, int]:
    """
    Validate a file for upload.

    Returns:
        Tuple of (sanitized_name, media_type, file_size)

    Raises:
        FileNotFoundError: If file does not exist
        ValueError: If file exceeds size limit
    """
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    size = p.stat().st_size
    if size > WECOM_UPLOAD_MAX_BYTES:
        raise ValueError(
            f"File too large: {size} bytes (max {WECOM_UPLOAD_MAX_BYTES} bytes)"
        )

    name = _sanitize_filename(p.name)
    media_type = _guess_wecom_media_type(p.name)
    return name, media_type, size


def _chunk_data(data: bytes, chunk_size: int = WECOM_UPLOAD_CHUNK_SIZE) -> list[bytes]:
    """Split data into chunks using memoryview for zero-copy slicing."""
    mv = memoryview(data)
    return [bytes(mv[i : i + chunk_size]) for i in range(0, len(mv), chunk_size)]


def _read_and_validate(file_path: str) -> tuple[str, str, int, bytes]:
    """
    Validate file, read its contents, and compute MD5 in a single thread call.

    Returns:
        Tuple of (sanitized_name, media_type, size, data)

    Raises:
        FileNotFoundError: If file does not exist
        ValueError: If file exceeds size limit
    """
    name, media_type, size = _validate_upload_file(file_path)
    data = Path(file_path).read_bytes()
    return name, media_type, size, data
