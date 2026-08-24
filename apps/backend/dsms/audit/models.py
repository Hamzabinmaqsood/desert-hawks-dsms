from collections.abc import Iterable
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from dsms.common.models import UUIDModel


class AuditCategory(models.TextChoices):
    AUTHENTICATION = "AUTHENTICATION", "Authentication"
    AUTHORIZATION = "AUTHORIZATION", "Authorization"
    IDENTITY = "IDENTITY", "Identity"
    WORKFORCE = "WORKFORCE", "Workforce"
    DOCUMENTS = "DOCUMENTS", "Documents"
    FINANCE = "FINANCE", "Finance"
    BILLING = "BILLING", "Billing"
    PAYMENTS = "PAYMENTS", "Payments"
    RECRUITMENT = "RECRUITMENT", "Recruitment"
    TRAINING = "TRAINING", "Training"
    CONTRACTS = "CONTRACTS", "Contracts"
    DEPLOYMENT = "DEPLOYMENT", "Deployment"
    ATTENDANCE = "ATTENDANCE", "Attendance"
    SUPERVISION = "SUPERVISION", "Supervision"
    PATROL = "PATROL", "Patrol"
    INCIDENT = "INCIDENT", "Incident"
    CLIENT_PORTAL = "CLIENT_PORTAL", "Client portal"
    NOTIFICATION = "NOTIFICATION", "Notification"
    LEAVE = "LEAVE", "Leave"
    ASSETS = "ASSETS", "Assets"
    HR_CASE = "HR_CASE", "HR case"
    PERFORMANCE = "PERFORMANCE", "Performance"
    ANALYTICS = "ANALYTICS", "Analytics"
    SYSTEM = "SYSTEM", "System"
    OTHER = "OTHER", "Other"


class AuditSeverity(models.TextChoices):
    INFO = "INFO", "Info"
    WARNING = "WARNING", "Warning"
    HIGH = "HIGH", "High"
    CRITICAL = "CRITICAL", "Critical"


class AuditEventQuerySet(models.QuerySet["AuditEvent"]):
    def update(self, **kwargs: Any) -> int:
        raise ValidationError("Audit events are immutable.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Audit events cannot be deleted.")

    def bulk_update(
        self,
        objs: Iterable["AuditEvent"],
        fields: Iterable[str],
        batch_size: int | None = None,
    ) -> int:
        raise ValidationError("Audit events are immutable.")


class AuditEvent(UUIDModel):
    """Privacy-minimized, append-only record of a security or business action."""

    event_id = models.UUIDField(null=True, blank=True, db_index=True)
    correlation_id = models.CharField(max_length=100, blank=True, db_index=True)
    occurred_at = models.DateTimeField(db_index=True)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    actor_employee = models.ForeignKey(
        "workforce.Employee",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    actor_type = models.CharField(max_length=30, default="USER")
    action = models.CharField(max_length=100, db_index=True)
    category = models.CharField(max_length=30, choices=AuditCategory.choices, db_index=True)
    severity = models.CharField(
        max_length=10, choices=AuditSeverity.choices, default=AuditSeverity.INFO, db_index=True
    )
    company = models.ForeignKey(
        "organization.Company",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="audit_events",
    )
    region = models.ForeignKey(
        "organization.Region",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="audit_events",
    )
    branch = models.ForeignKey(
        "organization.Branch",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="audit_events",
    )
    source_app = models.CharField(max_length=100, db_index=True)
    source_model = models.CharField(max_length=100, blank=True)
    source_object_id = models.CharField(max_length=100, blank=True, db_index=True)
    object_reference = models.CharField(max_length=255, blank=True)
    request_id = models.CharField(max_length=100, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent_summary = models.CharField(max_length=255, blank=True)
    success = models.BooleanField(default=True, db_index=True)
    reason_code = models.CharField(max_length=100, blank=True)
    summary = models.CharField(max_length=500)
    metadata_safe = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = AuditEventQuerySet.as_manager()

    class Meta:
        ordering = ["-occurred_at", "-created_at"]
        permissions = [
            ("view_sensitive_audit_metadata", "Can view sensitive audit metadata"),
            ("export_audit", "Can export audit events"),
            ("view_audit_dashboard", "Can view the audit dashboard"),
        ]
        indexes = [
            models.Index(fields=["company", "occurred_at"], name="audit_company_time_idx"),
            models.Index(fields=["branch", "occurred_at"], name="audit_branch_time_idx"),
            models.Index(fields=["category", "action"], name="audit_category_action_idx"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("Audit events are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError("Audit events cannot be deleted.")
