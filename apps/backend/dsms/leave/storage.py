# mypy: disable-error-code="no-untyped-def"
import uuid
from pathlib import Path

from dsms.documents.storage import private_document_storage

private_leave_storage = private_document_storage


def leave_attachment_upload_to(instance, filename):
    return (
        f"leave/{instance.leave_request.company_id}/{uuid.uuid4()}{Path(filename).suffix.lower()}"
    )
