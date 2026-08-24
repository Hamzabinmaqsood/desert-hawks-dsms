# mypy: disable-error-code="no-untyped-def"
from django.core.management.base import BaseCommand

from dsms.notifications.models import NotificationRule, NotificationRuleChannel

CATALOG = {
    "SOS_TRIGGERED": ("EMERGENCY", "REQUIRED"),
    "CRITICAL_INCIDENT_CREATED": ("EMERGENCY", "REQUIRED"),
    "ROSTER_PUBLISHED": ("NORMAL", "NONE"),
    "REPLACEMENT_REQUEST_CREATED": ("HIGH", "OPTIONAL"),
    "PATROL_MISSED": ("URGENT", "REQUIRED"),
    "CRITICAL_INSPECTION_FINDING": ("URGENT", "REQUIRED"),
    "CORRECTIVE_ACTION_OVERDUE": ("HIGH", "OPTIONAL"),
    "SITE_ATTENDANCE_GAP": ("URGENT", "REQUIRED"),
    "EMPLOYEE_DOCUMENT_EXPIRING": ("NORMAL", "NONE"),
    "CERTIFICATE_EXPIRING": ("NORMAL", "NONE"),
    "CONTRACT_EXPIRING": ("NORMAL", "NONE"),
    "PAYROLL_APPROVAL_REQUIRED": ("HIGH", "OPTIONAL"),
    "PURCHASE_ORDER_APPROVAL_REQUIRED": ("HIGH", "OPTIONAL"),
    "EXPENSE_APPROVAL_REQUIRED": ("HIGH", "OPTIONAL"),
    "CLIENT_REPORT_PUBLISHED": ("NORMAL", "NONE"),
    "CLIENT_SERVICE_REQUEST_CREATED": ("NORMAL", "NONE"),
}


class Command(BaseCommand):
    help = "Idempotently bootstrap conservative notification rules (in-app only)."

    def handle(self, *args, **options):
        for code, (priority, ack) in CATALOG.items():
            rule, _ = NotificationRule.objects.get_or_create(
                company=None,
                code=code,
                defaults={
                    "event_type": code,
                    "name": code.replace("_", " ").title(),
                    "is_system": True,
                    "priority": priority,
                    "acknowledgement_requirement": ack,
                },
            )
            NotificationRuleChannel.objects.get_or_create(
                rule=rule,
                channel="IN_APP",
                defaults={"required": priority in {"URGENT", "EMERGENCY"}},
            )
        self.stdout.write(self.style.SUCCESS(f"Bootstrapped {len(CATALOG)} notification rules."))
