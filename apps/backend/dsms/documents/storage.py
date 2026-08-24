import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateDocumentStorage(FileSystemStorage):
    """Private local storage with deliberately no public URL."""

    def __init__(self) -> None:
        super().__init__(location=settings.PRIVATE_MEDIA_ROOT, base_url=None)

    def url(self, name: str | None) -> str:
        raise ValueError("Private documents do not have public URLs.")


private_document_storage = PrivateDocumentStorage()


def private_document_upload_to(instance: object, filename: str) -> str:
    extension = Path(filename).suffix.lower()
    return f"employee-documents/{uuid.uuid4().hex[:2]}/{uuid.uuid4()}{extension}"
