# mypy: disable-error-code="type-arg"
from rest_framework import serializers

from .. import models


def serializer_for(model: type) -> type[serializers.ModelSerializer]:
    class ContractSerializer(serializers.ModelSerializer):
        class Meta:
            fields = "__all__"

    ContractSerializer.Meta.model = model
    ContractSerializer.__name__ = f"{model.__name__}Serializer"
    return ContractSerializer


SERIALIZERS = {
    model.__name__: serializer_for(model)
    for model in (
        models.ClientIndustry,
        models.Client,
        models.ClientContact,
        models.ServiceContract,
        models.ContractService,
        models.ContractAmendment,
        models.ContractCommercialTerms,
        models.SiteType,
        models.SecuritySite,
        models.SiteContact,
        models.SiteOperationalProfile,
        models.SiteEscalationContact,
        models.SiteCalendarException,
        models.PostType,
        models.SecurityPost,
        models.PostQualificationRequirement,
        models.PostCredentialRequirement,
        models.StaffingRequirement,
        models.ServiceLevelAgreement,
    )
}
