# mypy: disable-error-code="assignment"
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
            "actual_check_in_at",
            "actual_check_out_at",
            "approved_check_in_at",
            "approved_check_out_at",
            "approved_worked_minutes",
            "approved_overtime_minutes",
            "reviewed_by",
            "reviewed_at",
            "approved_by",
            "approved_at",
            "locked_by",
            "locked_at",
            "closed_by",
            "closed_at",
        }
        return tuple(field.name for field in self.model._meta.fields if field.name in controlled)


class EvidenceAdmin(NoDeleteAdmin):
    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


for model in (
    models.AttendancePolicy,
    models.AttendanceQRStation,
    models.AttendancePeriod,
    models.AttendanceRecord,
    models.AttendanceException,
    models.AttendanceCorrectionRequest,
    models.AttendancePayrollExport,
):
    admin.site.register(model, NoDeleteAdmin)
for model in (models.AttendanceEvent, models.AttendanceVerification, models.AttendanceChangeEvent):
    admin.site.register(model, EvidenceAdmin)
