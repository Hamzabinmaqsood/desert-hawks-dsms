from typing import Any, ClassVar, cast

from django.db import models as django_models
from rest_framework import serializers

from dsms.identity import access

from .. import models


class SensitiveLocationMixin:
    location_fields: ClassVar[tuple[str, ...]] = ()

    def to_representation(self, instance: Any) -> dict[str, Any]:
        data = super().to_representation(instance)  # type: ignore[misc]
        request = self.context.get("request")  # type: ignore[attr-defined]
        if (
            not request
            or "patrol.view_sensitive_patrol_location"
            not in access.get_effective_permissions(request.user)
        ):
            for field_name in self.location_fields:
                data.pop(field_name, None)
        return cast(dict[str, Any], data)


def _serializer(
    model: type[django_models.Model], name: str
) -> type[serializers.ModelSerializer[Any]]:
    meta = type("Meta", (), {"model": model, "fields": "__all__"})
    return type(name, (serializers.ModelSerializer,), {"Meta": meta})


SERIALIZERS: dict[str, type[serializers.ModelSerializer[Any]]] = {
    name: _serializer(getattr(models, name), f"{name}Serializer")
    for name in (
        "PatrolPolicy",
        "PatrolCheckpoint",
        "CheckpointQRCredential",
        "CheckpointNFCCredential",
        "PatrolRoute",
        "PatrolRouteVersion",
        "PatrolRouteCheckpoint",
        "PatrolRequirement",
        "PatrolRequirementDay",
        "PatrolRequirementTime",
        "PatrolTask",
        "PatrolEvent",
        "PatrolEvidence",
        "PatrolObservation",
        "PatrolException",
        "PatrolReview",
    )
}


class PatrolRunSerializer(SensitiveLocationMixin, serializers.ModelSerializer[models.PatrolRun]):
    location_fields = (
        "start_latitude",
        "start_longitude",
        "end_latitude",
        "end_longitude",
        "start_accuracy_meters",
        "end_accuracy_meters",
    )

    class Meta:
        model = models.PatrolRun
        fields = "__all__"


class CheckpointVisitSerializer(
    SensitiveLocationMixin, serializers.ModelSerializer[models.CheckpointVisit]
):
    location_fields = ("latitude", "longitude", "accuracy_meters")

    class Meta:
        model = models.CheckpointVisit
        fields = "__all__"


SERIALIZERS["PatrolRun"] = PatrolRunSerializer
SERIALIZERS["CheckpointVisit"] = CheckpointVisitSerializer
