# mypy: disable-error-code="no-untyped-def"
import uuid
from pathlib import Path

from dsms.documents.storage import private_document_storage


def field_evidence_upload_to(instance, filename: str) -> str:
    return (
        f"supervision-evidence/{uuid.uuid4().hex[:2]}/{uuid.uuid4()}{Path(filename).suffix.lower()}"
    )


private_evidence_storage = private_document_storage
