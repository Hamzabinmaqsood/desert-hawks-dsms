import re
from pathlib import Path
from typing import BinaryIO

from django.conf import settings

from .exceptions import DocumentValidationError

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
MIME_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}
SIGNATURES = {
    ".pdf": (b"%PDF-",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
}
_SEPARATORS = re.compile(r"[\s-]+")


def normalize_document_number(value: str) -> str:
    normalized = _SEPARATORS.sub("", value.strip().upper())
    if normalized.isdigit() and len(normalized) == 13:
        return f"{normalized[:5]}-{normalized[5:12]}-{normalized[12]}"
    return normalized


def mask_document_number(value: str) -> str:
    if not value:
        return ""
    return "".join(
        char if not char.isalnum() or index == len(value) - 1 else "*"
        for index, char in enumerate(value)
    )


def validate_upload(upload: BinaryIO, filename: str) -> tuple[str, str, int]:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise DocumentValidationError({"file": ["Only PDF, JPG, JPEG, and PNG files are allowed."]})
    size = getattr(upload, "size", None)
    if size is None:
        position = upload.tell()
        upload.seek(0, 2)
        size = upload.tell()
        upload.seek(position)
    if size <= 0 or size > settings.DOCUMENT_MAX_UPLOAD_SIZE:
        raise DocumentValidationError({"file": ["File size is invalid or exceeds the limit."]})
    position = upload.tell()
    upload.seek(0)
    header = upload.read(16)
    upload.seek(position)
    if not any(header.startswith(signature) for signature in SIGNATURES[extension]):
        raise DocumentValidationError({"file": ["File content does not match its extension."]})
    return extension.lstrip("."), MIME_TYPES[extension], int(size)
