# mypy: disable-error-code="type-arg"
from rest_framework import serializers

from .. import models


def serializer_for(model: type) -> type[serializers.ModelSerializer]:
    class ItemSerializer(serializers.ModelSerializer):
        class Meta:
            fields = "__all__"
            read_only_fields = (
                "status",
                "generated_at",
                "generated_by",
                "submitted_by",
                "submitted_at",
                "approved_by",
                "approved_at",
                "published_by",
                "published_at",
                "locked_by",
                "locked_at",
                "assigned_at",
                "confirmed_at",
                "completed_at",
            )

    ItemSerializer.Meta.model = model
    ItemSerializer.__name__ = f"{model.__name__}Serializer"
    ItemSerializer.__qualname__ = ItemSerializer.__name__
    return ItemSerializer


SERIALIZERS = {
    m.__name__: serializer_for(m)
    for m in (
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
    )
}
