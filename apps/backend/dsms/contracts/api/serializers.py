"""Explicit Contract API projections and tenant-safe writable relationships."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models as django_models
from django.db.models import Q
from rest_framework import serializers

from dsms.identity import access
from dsms.identity.models import User
from dsms.organization.business_defaults import (
    normalize_currency_code,
    validate_currency_code,
    validate_timezone_name,
)
from dsms.organization.models import Company

from .. import models
from .security import COMPANY_PATHS, GLOBAL_REFERENCES, PRIMARY_PARENT, company_id_for

COMMON = ("id", "created_at", "updated_at")
FIELDS: dict[type[django_models.Model], tuple[str, ...]] = {
    models.ClientIndustry: COMMON + tuple(["company", "code", "name", "is_active"]),
    models.Client: COMMON
    + tuple(
        [
            "company",
            "client_code",
            "legal_name",
            "trade_name",
            "industry",
            "registration_number",
            "tax_number",
            "website",
            "main_email",
            "main_phone",
            "billing_address",
            "head_office_address",
            "city",
            "province_or_state",
            "country_code",
            "status",
            "notes",
            "account_manager",
        ]
    ),
    models.ClientContact: COMMON
    + tuple(
        [
            "client",
            "name",
            "designation",
            "department",
            "email",
            "mobile_number",
            "office_phone",
            "contact_type",
            "is_primary",
            "notes",
            "is_active",
        ]
    ),
    models.ServiceContract: COMMON
    + tuple(
        [
            "company",
            "client",
            "contract_number",
            "contract_type",
            "title",
            "description",
            "signed_date",
            "start_date",
            "end_date",
            "notice_period_days",
            "auto_renew",
            "currency",
            "status",
            "client_reference",
            "purchase_order_reference",
            "internal_reference",
            "primary_client_contact",
            "account_manager",
            "created_by",
            "approved_by",
            "approved_at",
            "activated_at",
            "terminated_at",
            "termination_reason",
        ]
    ),
    models.ContractService: COMMON
    + tuple(
        ["contract", "service_type", "name", "description", "start_date", "end_date", "is_active"]
    ),
    models.ContractAmendment: ("id", "created_at")
    + tuple(
        [
            "contract",
            "amendment_number",
            "effective_date",
            "title",
            "description",
            "change_type",
            "previous_end_date",
            "revised_end_date",
            "previous_value",
            "revised_value",
            "approved_by",
            "approved_at",
            "created_by",
        ]
    ),
    models.ContractCommercialTerms: COMMON
    + tuple(
        [
            "contract",
            "billing_frequency",
            "agreed_contract_value",
            "monthly_service_value",
            "payment_terms_days",
            "security_deposit",
            "notes",
        ]
    ),
    models.SiteType: COMMON + tuple(["company", "code", "name", "is_active"]),
    models.SecuritySite: COMMON
    + tuple(
        [
            "company",
            "client",
            "contract",
            "site_code",
            "name",
            "description",
            "site_type",
            "managing_branch",
            "operational_zone",
            "address_line_1",
            "address_line_2",
            "city_name",
            "province_or_state",
            "postal_code",
            "country_code",
            "timezone",
            "latitude",
            "longitude",
            "geofence_radius_meters",
            "risk_level",
            "status",
            "start_date",
            "end_date",
            "primary_contact",
            "emergency_phone",
            "notes",
        ]
    ),
    models.SiteContact: COMMON
    + tuple(
        [
            "site",
            "client_contact",
            "name",
            "designation",
            "mobile_number",
            "email",
            "contact_type",
            "is_active",
        ]
    ),
    models.SiteOperationalProfile: COMMON
    + tuple(
        [
            "site",
            "operating_hours_notes",
            "access_control_notes",
            "emergency_procedure_notes",
            "reporting_instructions",
            "uniform_requirements",
            "equipment_notes",
            "visitor_handling_notes",
            "prohibited_actions_notes",
            "escalation_notes",
            "special_instructions",
            "updated_by",
        ]
    ),
    models.SiteEscalationContact: COMMON
    + tuple(
        [
            "site",
            "sequence",
            "contact_name",
            "organization",
            "designation",
            "phone",
            "alternate_phone",
            "email",
            "escalation_type",
            "available_24_7",
            "is_active",
        ]
    ),
    models.SiteCalendarException: ("id", "created_at")
    + tuple(
        ["site", "date", "name", "is_closed", "special_hours_start", "special_hours_end", "notes"]
    ),
    models.PostType: COMMON + tuple(["company", "code", "name", "is_active"]),
    models.SecurityPost: COMMON
    + tuple(
        [
            "company",
            "client",
            "site",
            "post_code",
            "name",
            "description",
            "location_description",
            "risk_level",
            "post_type",
            "requires_supervisor",
            "is_armed_post",
            "status",
            "sort_order",
            "instructions",
        ]
    ),
    models.PostQualificationRequirement: COMMON
    + tuple(
        [
            "post",
            "qualification_type",
            "requirement_level",
            "minimum_level",
            "effective_from",
            "effective_to",
            "is_active",
        ]
    ),
    models.PostCredentialRequirement: COMMON
    + tuple(
        [
            "post",
            "document_type",
            "requirement_level",
            "must_be_verified",
            "must_be_unexpired",
            "is_active",
        ]
    ),
    models.StaffingRequirement: COMMON
    + tuple(
        [
            "company",
            "contract",
            "site",
            "post",
            "requirement_code",
            "employee_type",
            "designation",
            "required_headcount",
            "coverage_type",
            "start_time",
            "end_time",
            "crosses_midnight",
            "effective_from",
            "effective_to",
            "status",
            "armed_required",
            "supervisor_required",
            "notes",
        ]
    ),
    models.ServiceLevelAgreement: COMMON
    + tuple(
        [
            "contract",
            "site",
            "sla_type",
            "name",
            "description",
            "target_value",
            "target_unit",
            "effective_from",
            "effective_to",
            "is_active",
        ]
    ),
}
READ_ONLY: dict[type[django_models.Model], tuple[str, ...]] = {
    model: tuple(name for name in COMMON if name in FIELDS[model]) for model in FIELDS
}
READ_ONLY.update(
    {
        models.Client: READ_ONLY[models.Client] + ("status",),
        models.ServiceContract: READ_ONLY[models.ServiceContract]
        + (
            "status",
            "created_by",
            "approved_by",
            "approved_at",
            "activated_at",
            "terminated_at",
            "termination_reason",
        ),
        models.ContractAmendment: FIELDS[models.ContractAmendment],
        models.SecuritySite: READ_ONLY[models.SecuritySite] + ("status",),
        models.SiteOperationalProfile: READ_ONLY[models.SiteOperationalProfile] + ("updated_by",),
        models.SecurityPost: READ_ONLY[models.SecurityPost] + ("status",),
        models.StaffingRequirement: READ_ONLY[models.StaffingRequirement] + ("status",),
    }
)


class TenantSafeContractSerializer(serializers.ModelSerializer[Any]):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        if not isinstance(actor, User) or actor.is_superuser:
            return
        view = self.context.get("view")
        permission = view.get_scope_permission() if view is not None else None
        ids = access.get_fully_accessible_company_ids(actor, permission=permission)
        for field in self.fields.values():
            if not isinstance(field, serializers.PrimaryKeyRelatedField) or field.queryset is None:
                continue
            remote = field.queryset.model
            if remote is Company:
                field.queryset = field.queryset.filter(pk__in=ids, is_active=True)
                continue
            path = COMPANY_PATHS.get(remote)
            if path:
                condition = Q(**{f"{path}__in": ids})
                if remote in GLOBAL_REFERENCES:
                    condition |= Q(company__isnull=True)
                field.queryset = field.queryset.filter(condition)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        model = self.Meta.model
        instance = self.instance
        parent = PRIMARY_PARENT.get(model)
        if parent:
            if (
                instance is not None
                and parent in attrs
                and attrs[parent] != getattr(instance, parent)
            ):
                raise serializers.ValidationError({parent: "Tenant ownership cannot be changed."})
            owner = attrs.get(parent, getattr(instance, parent, None))
        else:
            if instance is not None and "company" in attrs and attrs["company"] != instance.company:
                raise serializers.ValidationError(
                    {"company": "Company ownership cannot be changed."}
                )
            owner = attrs.get("company", getattr(instance, "company", None))
        company_id = company_id_for(owner)
        errors: dict[str, str] = {}
        if (
            model is models.ServiceContract
            and instance is None
            and "currency" not in attrs
            and owner
        ):
            attrs["currency"] = owner.default_currency
        if model is models.ServiceContract and "currency" in attrs:
            attrs["currency"] = normalize_currency_code(attrs["currency"])
            try:
                validate_currency_code(attrs["currency"])
            except DjangoValidationError as exc:
                errors["currency"] = "; ".join(exc.messages)
        if model is models.SecuritySite and instance is None and owner:
            attrs.setdefault("country_code", owner.country_code)
            attrs.setdefault("timezone", owner.timezone)
        if model is models.SecuritySite and "timezone" in attrs:
            try:
                validate_timezone_name(attrs["timezone"])
            except DjangoValidationError as exc:
                errors["timezone"] = "; ".join(exc.messages)
        for field in model._meta.fields:  # type: ignore[attr-defined]
            remote = getattr(getattr(field, "remote_field", None), "model", None)
            if field.name == "company" or remote not in COMPANY_PATHS:
                continue
            value = attrs.get(field.name, getattr(instance, field.name, None))
            related_company_id = company_id_for(value)
            if (
                value is not None
                and related_company_id != company_id
                and not (remote in GLOBAL_REFERENCES and related_company_id is None)
            ):
                errors[field.name] = "Must belong to the same company."
        if model is models.ServiceContract:
            contact = attrs.get(
                "primary_client_contact", getattr(instance, "primary_client_contact", None)
            )
            client = attrs.get("client", getattr(instance, "client", None))
            if contact and client and contact.client_id != client.pk:
                errors["primary_client_contact"] = "Must belong to the selected client."
        if model is models.SecuritySite:
            contract = attrs.get("contract", getattr(instance, "contract", None))
            client = attrs.get("client", getattr(instance, "client", None))
            contact = attrs.get("primary_contact", getattr(instance, "primary_contact", None))
            if contract and client and contract.client_id != client.pk:
                errors["contract"] = "Must belong to the selected client."
            if contact and client and contact.client_id != client.pk:
                errors["primary_contact"] = "Must belong to the selected client."
        if model is models.SecurityPost:
            site = attrs.get("site", getattr(instance, "site", None))
            client = attrs.get("client", getattr(instance, "client", None))
            if site and client and site.client_id != client.pk:
                errors["site"] = "Must belong to the selected client."
        if model is models.StaffingRequirement:
            contract = attrs.get("contract", getattr(instance, "contract", None))
            site = attrs.get("site", getattr(instance, "site", None))
            post = attrs.get("post", getattr(instance, "post", None))
            if contract and site and site.contract_id != contract.pk:
                errors["site"] = "Must belong to the selected contract."
            if site and post and post.site_id != site.pk:
                errors["post"] = "Must belong to the selected site."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


def serializer_for(model: type[django_models.Model]) -> type[TenantSafeContractSerializer]:
    meta = type(
        "Meta", (), {"model": model, "fields": FIELDS[model], "read_only_fields": READ_ONLY[model]}
    )
    return type(f"{model.__name__}Serializer", (TenantSafeContractSerializer,), {"Meta": meta})


SERIALIZERS = {model.__name__: serializer_for(model) for model in FIELDS}


class ClientSerializer(TenantSafeContractSerializer):
    industry_name = serializers.CharField(source="industry.name", read_only=True)
    account_manager_name = serializers.CharField(
        source="account_manager.full_name", read_only=True, default=None
    )

    class Meta:
        model = models.Client
        fields = FIELDS[models.Client] + (
            "industry_name",
            "account_manager_name",
        )
        read_only_fields = READ_ONLY[models.Client] + (
            "industry_name",
            "account_manager_name",
        )


class ServiceContractSerializer(TenantSafeContractSerializer):
    client_name = serializers.CharField(source="client.legal_name", read_only=True)
    primary_client_contact_name = serializers.CharField(
        source="primary_client_contact.name", read_only=True, default=None
    )
    account_manager_name = serializers.CharField(
        source="account_manager.full_name", read_only=True, default=None
    )

    class Meta:
        model = models.ServiceContract
        fields = FIELDS[models.ServiceContract] + (
            "client_name",
            "primary_client_contact_name",
            "account_manager_name",
        )
        read_only_fields = READ_ONLY[models.ServiceContract] + (
            "client_name",
            "primary_client_contact_name",
            "account_manager_name",
        )


SERIALIZERS["Client"] = ClientSerializer
SERIALIZERS["ServiceContract"] = ServiceContractSerializer
