from typing import Any

from django.contrib import admin
from django.db import models as django_models
from django.http import HttpRequest

from . import models


class NoDeleteAdmin(admin.ModelAdmin[django_models.Model]):
    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> tuple[str, ...]:
        controlled = {
            "status",
            "approved_by",
            "approved_at",
            "submitted_by",
            "submitted_at",
            "published_by",
            "published_at",
            "locked_by",
            "locked_at",
            "completed_at",
            "replacement_employee",
            "assigned_by",
            "replaces_assignment",
        }
        return tuple(field.name for field in self.model._meta.fields if field.name in controlled)


for model in (
    models.EmployeeDeployment,
    models.DeploymentPool,
    models.DeploymentPoolMembership,
    models.ShiftTemplate,
    models.SchedulingPolicy,
    models.RosterPeriod,
    models.DutyShift,
    models.DutyAssignment,
    models.EmployeeScheduleBlock,
    models.ReplacementRequest,
    models.RosterChangeEvent,
    models.RosterAvailabilityConflict,
):
    admin.site.register(model, NoDeleteAdmin)
