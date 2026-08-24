from dsms.common.models import ActiveModel, TimeStampedModel, UUIDModel
from dsms.common.validators import CODE_VALIDATOR, normalize_code

__all__ = ["CODE_VALIDATOR", "IdentityBaseModel", "normalize_code"]


class IdentityBaseModel(UUIDModel, TimeStampedModel, ActiveModel):
    """Shared fields for identity/RBAC master-data entities."""

    class Meta:
        abstract = True
