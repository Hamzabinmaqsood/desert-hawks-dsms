import uuid
from pathlib import Path

from dsms.documents.storage import private_document_storage


def hr_case_evidence_upload_to(instance: object, filename: str) -> str:
    extension = Path(filename).suffix.lower()
    return f"hr-case-evidence/{uuid.uuid4().hex[:2]}/{uuid.uuid4()}{extension}"


__all__ = ["hr_case_evidence_upload_to", "private_document_storage"]
