from typing import Any

from django.core.management.base import BaseCommand

from dsms.documents.enums import DocumentCategory
from dsms.documents.models import DocumentType

TYPES = [
    ("CNIC", "CNIC", DocumentCategory.IDENTITY, True, True, True, True, False),
    ("PASSPORT", "Passport", DocumentCategory.IDENTITY, True, True, True, True, False),
    (
        "EMPLOYMENT_CONTRACT",
        "Employment contract",
        DocumentCategory.EMPLOYMENT,
        False,
        False,
        False,
        False,
        True,
    ),
    (
        "POLICE_VERIFICATION",
        "Police verification",
        DocumentCategory.BACKGROUND_VERIFICATION,
        True,
        False,
        False,
        True,
        True,
    ),
    (
        "CHARACTER_CERTIFICATE",
        "Character certificate",
        DocumentCategory.BACKGROUND_VERIFICATION,
        False,
        False,
        False,
        False,
        True,
    ),
    ("DRIVING_LICENCE", "Driving licence", DocumentCategory.LICENCE, True, True, True, True, False),
    (
        "SECURITY_LICENCE",
        "Security licence",
        DocumentCategory.LICENCE,
        True,
        True,
        True,
        True,
        False,
    ),
    (
        "MEDICAL_FITNESS",
        "Medical fitness",
        DocumentCategory.MEDICAL_FITNESS,
        True,
        False,
        True,
        True,
        True,
    ),
    (
        "EDUCATION_CERTIFICATE",
        "Education certificate",
        DocumentCategory.EDUCATION,
        False,
        False,
        False,
        False,
        True,
    ),
    (
        "TRAINING_CERTIFICATE",
        "Training certificate",
        DocumentCategory.TRAINING,
        False,
        False,
        False,
        False,
        True,
    ),
    (
        "EXPERIENCE_CERTIFICATE",
        "Experience certificate",
        DocumentCategory.EXPERIENCE,
        False,
        False,
        False,
        False,
        True,
    ),
    (
        "EMPLOYEE_PHOTO",
        "Employee photo",
        DocumentCategory.PERSONAL,
        True,
        False,
        False,
        False,
        False,
    ),
    ("OTHER", "Other", DocumentCategory.OTHER, False, False, False, False, True),
]


class Command(BaseCommand):
    help = "Idempotently bootstrap global employee document types."

    def handle(self, *args: Any, **options: Any) -> None:
        for index, (code, name, category, sensitive, number, issue, expiry, multiple) in enumerate(
            TYPES
        ):
            DocumentType.objects.update_or_create(
                company=None,
                code=code,
                defaults={
                    "name": name,
                    "category": category,
                    "is_system": True,
                    "is_sensitive": sensitive,
                    "requires_document_number": number,
                    "requires_issue_date": issue,
                    "requires_expiry_date": expiry,
                    "allow_multiple": multiple,
                    "is_active": True,
                    "sort_order": index,
                },
            )
        self.stdout.write(self.style.SUCCESS(f"Bootstrapped {len(TYPES)} document types"))
