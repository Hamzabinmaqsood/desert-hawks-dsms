# mypy: disable-error-code="no-untyped-def"
import uuid
from pathlib import Path

from dsms.documents.storage import private_document_storage


def patrol_evidence_upload_to(instance, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return f"patrol-evidence/{uuid.uuid4().hex[:2]}/{uuid.uuid4()}{suffix}"


private_patrol_storage = private_document_storage
