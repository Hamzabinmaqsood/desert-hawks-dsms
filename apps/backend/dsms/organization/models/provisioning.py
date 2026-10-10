from django.conf import settings
from django.db import models
from django.db.models import Q

from dsms.common.models import TimeStampedModel, UUIDModel


class TenantProvisioningStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"


class TenantProvisioningRequest(UUIDModel, TimeStampedModel):
    """Durable platform request used to serialize and replay tenant creation."""

    idempotency_key = models.UUIDField(unique=True)
    request_fingerprint = models.CharField(max_length=64, editable=False)
    status = models.CharField(
        max_length=20,
        choices=TenantProvisioningStatus.choices,
        default=TenantProvisioningStatus.PENDING,
    )
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="initiated_tenant_provisioning_requests",
    )
    company = models.OneToOneField(
        "organization.Company",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="provisioning_request",
    )
    initial_admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="tenant_provisioning_results",
    )
    attempt_count = models.PositiveIntegerField(default=0)
    failure_code = models.CharField(max_length=100, blank=True)
    failure_message = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("provision_tenant", "Can provision a tenant Company"),
            ("view_tenant_provisioning", "Can view tenant provisioning status"),
            ("view_platform_tenant_directory", "Can view the platform tenant directory"),
        ]
        indexes = [
            models.Index(fields=["status", "created_at"], name="org_prov_status_time_idx"),
            models.Index(fields=["initiated_by", "created_at"], name="org_prov_actor_time_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    status=TenantProvisioningStatus.SUCCEEDED,
                    company__isnull=False,
                    initial_admin__isnull=False,
                )
                | (
                    ~Q(status=TenantProvisioningStatus.SUCCEEDED)
                    & Q(company__isnull=True, initial_admin__isnull=True)
                ),
                name="org_prov_result_matches_status",
            )
        ]

    def __str__(self) -> str:
        return f"{self.idempotency_key} / {self.status}"
