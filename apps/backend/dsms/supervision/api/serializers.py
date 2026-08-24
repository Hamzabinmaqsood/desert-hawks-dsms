# mypy: disable-error-code="no-untyped-def,type-arg,no-untyped-call,valid-type,misc,name-defined"
from rest_framework import serializers

from dsms.identity import access

from .. import models

MODEL_NAMES = [
    "SupervisionAssignment",
    "VisitFrequencyRequirement",
    "SupervisorVisitPlan",
    "SiteVisit",
    "InspectionTemplate",
    "InspectionTemplateSection",
    "InspectionTemplateItem",
    "InspectionTemplateItemOption",
    "SiteInspection",
    "InspectionResponse",
    "FieldEvidence",
    "GuardObservation",
    "InspectionFinding",
    "CorrectiveAction",
    "SiteObservation",
    "SiteVisitClientFeedback",
    "SupervisorDailyReport",
]


def serializer_for(model_class):
    class Serializer(serializers.ModelSerializer):
        class Meta:
            model = model_class
            fields = "__all__"
            read_only_fields = ("id", "created_at", "updated_at")

    Serializer.__name__ = f"{model_class.__name__}Serializer"
    Serializer.__qualname__ = Serializer.__name__
    return Serializer


SERIALIZERS = {name: serializer_for(getattr(models, name)) for name in MODEL_NAMES}


class SiteVisitSerializer(SERIALIZERS["SiteVisit"]):
    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if (
            not request
            or "supervision.view_sensitive_visit_location"
            not in access.get_effective_permissions(request.user)
        ):
            for field in (
                "arrival_latitude",
                "arrival_longitude",
                "departure_latitude",
                "departure_longitude",
                "arrival_accuracy_meters",
                "departure_accuracy_meters",
            ):
                data.pop(field, None)
        return data

    class Meta(SERIALIZERS["SiteVisit"].Meta):
        read_only_fields = SERIALIZERS["SiteVisit"].Meta.read_only_fields + (
            "verification_result",
            "arrival_distance_from_site_meters",
        )


SERIALIZERS["SiteVisit"] = SiteVisitSerializer
