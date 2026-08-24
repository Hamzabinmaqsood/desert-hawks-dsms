from django.db import models

from dsms.common.models import ActiveModel, TimeStampedModel, UUIDModel
from dsms.common.validators import CODE_VALIDATOR, normalize_code

__all__ = [
    "CODE_VALIDATOR",
    "TimeStampedModel",
    "UUIDModel",
    "WorkforceBaseModel",
    "WorkforceLogModel",
    "normalize_code",
]


class WorkforceBaseModel(UUIDModel, TimeStampedModel, ActiveModel):
    """Shared fields for mutable workforce master-data entities."""

    class Meta:
        abstract = True


class WorkforceLogModel(UUIDModel):
    """Shared fields for immutable workforce history/log entries.

    Log rows are created once by a service and never updated, so they carry
    only a creation timestamp -- no ``updated_at``/``is_active``.
    """

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created at")

    class Meta:
        abstract = True
