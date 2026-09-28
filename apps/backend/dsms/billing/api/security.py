"""Tenant consistency for Billing configuration and collection CRUD."""

from __future__ import annotations

from typing import Any

from django.db import models
from django.db.models import F, Q, QuerySet

from dsms.contracts.api.security import COMPANY_PATHS as CONTRACT_PATHS
from dsms.finance.models import Account, CostCenter
from dsms.identity import access
from dsms.identity.models import User
from dsms.organization.models import Company

from .. import models as billing_models

COMPANY_PATHS: dict[type[models.Model], str] = {
    billing_models.ClientBillingProfile: "company_id",
    billing_models.BillingSchedule: "company_id",
    billing_models.BillingRule: "billing_schedule__company_id",
    billing_models.TaxCode: "company_id",
    billing_models.ClientCollectionActivity: "company_id",
    billing_models.ClientInvoice: "company_id",
    Account: "company_id",
    CostCenter: "company_id",
    **CONTRACT_PATHS,
}
GLOBAL_REFERENCES = {billing_models.TaxCode}
PRIMARY_PARENT = {billing_models.BillingRule: "billing_schedule"}


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


def consistent_queryset(queryset: QuerySet[Any]) -> QuerySet[Any]:
    model = queryset.model
    owner = COMPANY_PATHS[model]
    for field in model._meta.fields:
        remote = getattr(getattr(field, "remote_field", None), "model", None)
        if field.name == "company" or remote not in COMPANY_PATHS:
            continue
        condition = Q(**{f"{field.name}__{COMPANY_PATHS[remote]}": F(owner)})
        if field.null:
            condition |= Q(**{f"{field.name}__isnull": True})
        if remote in GLOBAL_REFERENCES:
            condition |= Q(**{f"{field.name}__company__isnull": True})
        queryset = queryset.filter(condition)
    if model is billing_models.BillingSchedule:
        queryset = queryset.filter(contract__client_id=F("client_id"))
    if model is billing_models.BillingRule:
        queryset = queryset.filter(
            Q(contract_service__isnull=True)
            | Q(contract_service__contract_id=F("billing_schedule__contract_id")),
            Q(site__isnull=True) | Q(site__contract_id=F("billing_schedule__contract_id")),
            billing_schedule__client__company_id=F("billing_schedule__company_id"),
            billing_schedule__contract__company_id=F("billing_schedule__company_id"),
            billing_schedule__contract__client_id=F("billing_schedule__client_id"),
        )
    if model is billing_models.ClientCollectionActivity:
        queryset = queryset.filter(Q(invoice__isnull=True) | Q(invoice__client_id=F("client_id")))
    return queryset


def scoped_queryset(queryset: QuerySet[Any], *, user: User, permission: str) -> QuerySet[Any]:
    if user.is_superuser:
        return queryset
    path = COMPANY_PATHS[queryset.model]
    ids = access.get_fully_accessible_company_ids(user, permission=permission)
    scope = Q(**{f"{path}__in": ids})
    if queryset.model in GLOBAL_REFERENCES:
        scope |= Q(company__isnull=True)
    active = Q(**{f"{path.rsplit('_id', 1)[0]}__is_active": True})
    if queryset.model in GLOBAL_REFERENCES:
        active |= Q(company__isnull=True)
    queryset = queryset.filter(scope).filter(active)
    queryset = consistent_queryset(queryset).distinct()
    return queryset if queryset.ordered else queryset.order_by("pk")
