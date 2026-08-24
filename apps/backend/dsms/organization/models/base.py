from dsms.common.models import ActiveModel, TimeStampedModel, UUIDModel
from dsms.common.validators import CODE_VALIDATOR, normalize_code

__all__ = ["CODE_VALIDATOR", "OrganizationBaseModel", "normalize_code"]


class OrganizationBaseModel(UUIDModel, TimeStampedModel, ActiveModel):
    """Shared fields for organization master-data entities."""

    class Meta:
        abstract = True
