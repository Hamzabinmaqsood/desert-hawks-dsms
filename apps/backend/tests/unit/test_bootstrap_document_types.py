import pytest
from django.core.management import call_command

from dsms.documents.models import DocumentType

pytestmark = pytest.mark.django_db


def test_document_type_bootstrap_is_idempotent() -> None:
    call_command("bootstrap_document_types")
    call_command("bootstrap_document_types")
    assert DocumentType.objects.filter(company=None, is_system=True).count() == 13
    cnic = DocumentType.objects.get(code="CNIC", company=None)
    assert cnic.is_sensitive
    assert cnic.requires_document_number
    assert not cnic.allow_multiple
