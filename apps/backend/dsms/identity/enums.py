from django.db import models


class AccessScopeType(models.TextChoices):
    """The organizational level at which a role assignment grants access."""

    GLOBAL = "GLOBAL", "Global"
    COMPANY = "COMPANY", "Company"
    REGION = "REGION", "Region"
    BRANCH = "BRANCH", "Branch"
    DEPARTMENT = "DEPARTMENT", "Department"
    OPERATIONAL_ZONE = "OPERATIONAL_ZONE", "Operational zone"
