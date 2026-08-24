# mypy: disable-error-code="no-untyped-def"
import uuid
from pathlib import Path

from dsms.documents.storage import private_document_storage

private_incident_storage = private_document_storage


def incident_evidence_upload_to(instance, filename):
    suffix = Path(filename).suffix.lower()
    return f"{instance.company_id}/{instance.incident_id}/{uuid.uuid4()}{suffix}"
