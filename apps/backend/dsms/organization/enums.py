from django.db import models


class DepartmentScope(models.TextChoices):
    """Scope at which a department operates within the company hierarchy."""

    COMPANY = "COMPANY", "Company"
    BRANCH = "BRANCH", "Branch"
