"""Tenant consistency for Billing configuration and collection CRUD."""

from __future__ import annotations

from typing import Any

from django.db import models
from django.db.models import F, Q, QuerySet

from dsms.contracts.api.security import COMPANY_PATHS as CONTRACT_PATHS
from dsms.finance.models import Account, CostCenter, JournalEntry
from dsms.finance.operations_models import BankAccount
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
    billing_models.ClientInvoiceLine: "invoice__company_id",
    billing_models.ClientInvoiceDocument: "company_id",
    billing_models.ClientReceipt: "company_id",
    billing_models.ClientReceiptAllocation: "receipt__company_id",
    billing_models.ClientAccountTransaction: "company_id",
    billing_models.ClientCreditNote: "company_id",
    billing_models.ClientCreditNoteLine: "credit_note__company_id",
    billing_models.ClientDebitNote: "company_id",
    billing_models.ClientDebitNoteLine: "debit_note__company_id",
    Account: "company_id",
    BankAccount: "company_id",
    CostCenter: "company_id",
    JournalEntry: "company_id",
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
    if model is billing_models.ClientInvoice:
        queryset = queryset.filter(
            Q(contract__isnull=True) | Q(contract__client_id=F("client_id")),
            Q(source_billing_schedule__isnull=True)
            | Q(source_billing_schedule__client_id=F("client_id")),
        )
    if model is billing_models.ClientInvoiceLine:
        queryset = queryset.filter(
            Q(contract_service__isnull=True)
            | Q(contract_service__contract_id=F("invoice__contract_id")),
            Q(site__isnull=True) | Q(site__contract_id=F("invoice__contract_id")),
            Q(billing_rule__isnull=True)
            | Q(billing_rule__billing_schedule__contract_id=F("invoice__contract_id")),
        )
    if model is billing_models.ClientReceiptAllocation:
        queryset = queryset.filter(
            invoice__client_id=F("receipt__client_id"),
            invoice__currency=F("receipt__currency"),
        )
    if model is billing_models.ClientAccountTransaction:
        queryset = queryset.filter(
            Q(invoice__isnull=True) | Q(invoice__client_id=F("client_id")),
            Q(receipt__isnull=True) | Q(receipt__client_id=F("client_id")),
            Q(allocation__isnull=True) | Q(allocation__receipt__client_id=F("client_id")),
            Q(allocation__isnull=True) | Q(allocation__invoice__client_id=F("client_id")),
        )
    if model is billing_models.ClientCreditNote:
        queryset = queryset.filter(
            invoice__client_id=F("client_id"),
            invoice__currency=F("currency"),
        )
    if model is billing_models.ClientDebitNote:
        queryset = queryset.filter(
            Q(invoice__isnull=True) | Q(invoice__client_id=F("client_id")),
            Q(invoice__isnull=True) | Q(invoice__currency=F("currency")),
        )
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
