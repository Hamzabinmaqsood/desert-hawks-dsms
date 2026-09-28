"""Tenant ownership and historical-relation checks for Contract API resources."""

from __future__ import annotations

from typing import Any

from django.db import models
from django.db.models import F, Q, QuerySet

from dsms.identity import access
from dsms.identity.models import User
from dsms.organization.models import Branch, Company, Designation, OperationalZone
from dsms.training.models import QualificationType
from dsms.workforce.models import Employee

from .. import models as contract_models

COMPANY_PATHS: dict[type[models.Model], str] = {
    contract_models.ClientIndustry: "company_id",
    contract_models.Client: "company_id",
    contract_models.ClientContact: "client__company_id",
    contract_models.ServiceContract: "company_id",
    contract_models.ContractService: "contract__company_id",
    contract_models.ContractAmendment: "contract__company_id",
    contract_models.ContractCommercialTerms: "contract__company_id",
    contract_models.SiteType: "company_id",
    contract_models.SecuritySite: "company_id",
    contract_models.SiteContact: "site__company_id",
    contract_models.SiteOperationalProfile: "site__company_id",
    contract_models.SiteEscalationContact: "site__company_id",
    contract_models.SiteCalendarException: "site__company_id",
    contract_models.PostType: "company_id",
    contract_models.SecurityPost: "company_id",
    contract_models.PostQualificationRequirement: "post__company_id",
    contract_models.PostCredentialRequirement: "post__company_id",
    contract_models.StaffingRequirement: "company_id",
    contract_models.ServiceLevelAgreement: "contract__company_id",
    Branch: "company_id",
    OperationalZone: "company_id",
    Designation: "company_id",
    Employee: "company_id",
    QualificationType: "company_id",
}
GLOBAL_REFERENCES = {
    contract_models.ClientIndustry,
    contract_models.SiteType,
    contract_models.PostType,
    QualificationType,
}
PRIMARY_PARENT = {
    model: path.split("__", 1)[0]
    for model, path in COMPANY_PATHS.items()
    if path != "company_id" and model.__module__ == contract_models.__name__
}


def company_id_for(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Company):
        return value.pk
    path = COMPANY_PATHS.get(type(value))
    if path is None:
        return None
    for segment in path.split("__"):
        value = getattr(value, segment, None)
        if value is None:
            return None
    return value


def _relation_conditions(model: type[models.Model]) -> tuple[Q, ...]:
    owner = COMPANY_PATHS[model]
    conditions: list[Q] = []
    for field in model._meta.fields:
        remote = getattr(getattr(field, "remote_field", None), "model", None)
        if field.name == "company" or remote not in COMPANY_PATHS:
            continue
        related_path = COMPANY_PATHS[remote]
        relation_path = f"{field.name}__{related_path}"
        condition = Q(**{relation_path: F(owner)})
        if field.null:
            condition |= Q(**{f"{field.name}__isnull": True})
        if remote in GLOBAL_REFERENCES:
            condition |= Q(**{f"{field.name}__company__isnull": True})
        conditions.append(condition)
    return tuple(conditions)


EXTRA_CONSISTENCY: dict[type[models.Model], tuple[Q, ...]] = {
    contract_models.ServiceContract: (
        Q(primary_client_contact__isnull=True)
        | Q(primary_client_contact__client_id=F("client_id")),
    ),
    contract_models.SecuritySite: (
        Q(contract__client_id=F("client_id")),
        Q(primary_contact__isnull=True) | Q(primary_contact__client_id=F("client_id")),
    ),
    contract_models.SiteContact: (
        Q(client_contact__isnull=True) | Q(client_contact__client_id=F("site__client_id")),
    ),
    contract_models.SecurityPost: (Q(site__client_id=F("client_id")),),
    contract_models.StaffingRequirement: (
        Q(site__contract_id=F("contract_id")),
        Q(post__site_id=F("site_id")),
    ),
    contract_models.ServiceLevelAgreement: (
        Q(site__isnull=True) | Q(site__contract_id=F("contract_id")),
    ),
}


def consistent_queryset(queryset: QuerySet[Any]) -> QuerySet[Any]:
    for condition in (
        *_relation_conditions(queryset.model),
        *EXTRA_CONSISTENCY.get(queryset.model, ()),
    ):
        queryset = queryset.filter(condition)
    return queryset


def scoped_queryset(queryset: QuerySet[Any], *, user: User, permission: str) -> QuerySet[Any]:
    if user.is_superuser:
        return queryset
    model = queryset.model
    path = COMPANY_PATHS[model]
    ids = access.get_fully_accessible_company_ids(user, permission=permission)
    scope = Q(**{f"{path}__in": ids})
    if model in GLOBAL_REFERENCES:
        scope |= Q(company__isnull=True)
    queryset = queryset.filter(scope).filter(
        Q(**{f"{path.rsplit('_id', 1)[0]}__isnull": True})
        | Q(**{f"{path.rsplit('_id', 1)[0]}__is_active": True})
        if model in GLOBAL_REFERENCES
        else Q(**{f"{path.rsplit('_id', 1)[0]}__is_active": True})
    )
    queryset = consistent_queryset(queryset).distinct()
    return queryset if queryset.ordered else queryset.order_by("pk")
