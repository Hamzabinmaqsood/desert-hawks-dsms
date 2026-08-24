# mypy: disable-error-code="no-untyped-def"
import uuid
from pathlib import Path

from dsms.documents.storage import private_document_storage

private_portal_storage = private_document_storage


def portal_attachment_upload_to(instance, filename):
    return f"client-portal/{instance.client_id}/{uuid.uuid4()}{Path(filename).suffix.lower()}"
