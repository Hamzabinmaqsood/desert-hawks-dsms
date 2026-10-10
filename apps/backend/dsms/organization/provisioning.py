import hashlib
import json
import logging
from dataclasses import asdict, dataclass, replace
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction

from dsms.audit.models import AuditCategory, AuditSeverity
from dsms.audit.services import record_audit_event
from dsms.identity.enums import AccessScopeType
from dsms.identity.exceptions import IdentityError, IdentityValidationError
from dsms.identity.models import Role, User
from dsms.identity.services import assign_role, create_user

from . import services as organization_services
from .business_defaults import normalize_currency_code, normalize_document_prefix
from .exceptions import OrganizationError, OrganizationValidationError
from .models import Company, TenantProvisioningRequest, TenantProvisioningStatus
from .models.base import normalize_code
from .provisioning_exceptions import (
    InactiveInitialAdminError,
    TenantProvisioningAuthorizationError,
    TenantProvisioningConfigurationError,
    TenantProvisioningConflictError,
    TenantProvisioningError,
    TenantProvisioningValidationError,
)

logger = logging.getLogger(__name__)

TENANT_ADMIN_ROLE_CODES = ("ORGANIZATION_ADMIN", "ACCESS_ADMIN")


@dataclass(frozen=True)
class ProvisionedCompanyData:
    code: str
    legal_name: str
    timezone: str
    default_currency: str
    country_code: str
    trade_name: str = ""
    registration_number: str | None = None
    tax_number: str | None = None
    brand_tagline: str = ""
    brand_primary_color: str = ""
    brand_accent_color: str = ""
    invoice_number_prefix: str = "INV"
    receipt_number_prefix: str = "RCPT"
    credit_note_number_prefix: str = "CN"
    debit_note_number_prefix: str = "DN"


@dataclass(frozen=True)
class InitialAdminData:
    email: str
    first_name: str = ""
    last_name: str = ""


@dataclass(frozen=True)
class ProvisionCompanyRequest:
    company: ProvisionedCompanyData
    initial_admin: InitialAdminData


@dataclass(frozen=True)
class ProvisionCompanyResult:
    provisioning_request: TenantProvisioningRequest
    replayed: bool


def _normalized_request(request: ProvisionCompanyRequest) -> ProvisionCompanyRequest:
    company = request.company
    normalized_company = replace(
        company,
        code=normalize_code(company.code),
        legal_name=company.legal_name.strip(),
        trade_name=company.trade_name.strip(),
        registration_number=(company.registration_number or "").strip() or None,
        tax_number=(company.tax_number or "").strip() or None,
        brand_tagline=company.brand_tagline.strip(),
        brand_primary_color=company.brand_primary_color.strip().upper(),
        brand_accent_color=company.brand_accent_color.strip().upper(),
        timezone=company.timezone.strip(),
        default_currency=normalize_currency_code(company.default_currency),
        country_code=company.country_code.strip().upper(),
        invoice_number_prefix=normalize_document_prefix(company.invoice_number_prefix),
        receipt_number_prefix=normalize_document_prefix(company.receipt_number_prefix),
        credit_note_number_prefix=normalize_document_prefix(company.credit_note_number_prefix),
        debit_note_number_prefix=normalize_document_prefix(company.debit_note_number_prefix),
    )
    normalized_admin = replace(
        request.initial_admin,
        email=request.initial_admin.email.strip().lower(),
        first_name=request.initial_admin.first_name.strip(),
        last_name=request.initial_admin.last_name.strip(),
    )
    return replace(request, company=normalized_company, initial_admin=normalized_admin)


def _request_fingerprint(request: ProvisionCompanyRequest) -> str:
    canonical = json.dumps(asdict(request), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_platform_actor(actor: User) -> None:
    if not actor.is_authenticated or not actor.is_active or not actor.is_superuser:
        raise TenantProvisioningAuthorizationError(
            "Only an active platform superuser may provision a tenant."
        )


def _reserve_request(
    *, actor: User, idempotency_key: UUID, fingerprint: str
) -> TenantProvisioningRequest:
    record, _created = TenantProvisioningRequest.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={"request_fingerprint": fingerprint, "initiated_by": actor},
    )
    if record.request_fingerprint != fingerprint:
        raise TenantProvisioningConflictError(
            "This idempotency key was already used for a different provisioning request."
        )
    return record


def _tenant_admin_roles() -> list[Role]:
    roles = list(
        Role.objects.filter(
            company__isnull=True,
            code__in=TENANT_ADMIN_ROLE_CODES,
            is_system=True,
            is_active=True,
        )
    )
    by_code = {role.code: role for role in roles}
    missing = [code for code in TENANT_ADMIN_ROLE_CODES if code not in by_code]
    if missing:
        raise TenantProvisioningConfigurationError(
            "Required tenant-administrator system roles are not bootstrapped."
        )
    return [by_code[code] for code in TENANT_ADMIN_ROLE_CODES]


def _create_company(data: ProvisionedCompanyData) -> Company:
    try:
        return organization_services.create_company(**asdict(data))
    except OrganizationValidationError as exc:
        raise TenantProvisioningValidationError({"company": exc.errors}) from exc
    except OrganizationError as exc:
        raise TenantProvisioningValidationError({"company": {"detail": [str(exc)]}}) from exc


def _initial_admin(data: InitialAdminData) -> User:
    user = User.objects.select_for_update().filter(email__iexact=data.email).first()
    if user is None:
        try:
            with transaction.atomic():
                user = create_user(
                    email=data.email,
                    password=None,
                    first_name=data.first_name,
                    last_name=data.last_name,
                    is_staff=False,
                    is_active=True,
                )
        except (IntegrityError, IdentityValidationError) as exc:
            user = User.objects.select_for_update().filter(email__iexact=data.email).first()
            if user is None:
                errors = getattr(exc, "errors", {"email": ["Administrator email is invalid."]})
                raise TenantProvisioningValidationError({"initial_admin": errors}) from exc
    if not user.is_active:
        raise InactiveInitialAdminError(
            {"initial_admin": {"email": ["The existing user account is inactive."]}}
        )
    if user.is_superuser:
        raise TenantProvisioningValidationError(
            {
                "initial_admin": {
                    "email": [
                        "A platform superuser cannot be assigned as the tenant administrator."
                    ]
                }
            }
        )
    return user


def _bootstrap_initial_admin(
    *, actor: User, user: User, company: Company, roles: list[Role]
) -> None:
    try:
        for role in roles:
            assign_role(
                actor=actor,
                user=user,
                role=role,
                scope_type=AccessScopeType.COMPANY,
                company=company,
            )
    except IdentityError as exc:
        raise TenantProvisioningValidationError({"initial_admin": {"roles": [str(exc)]}}) from exc


def _failure_details(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, InactiveInitialAdminError):
        return "inactive_initial_admin", "The existing administrator account is inactive."
    if isinstance(exc, TenantProvisioningConfigurationError):
        return "platform_configuration", str(exc)
    if isinstance(exc, TenantProvisioningValidationError):
        return "request_validation", "The provisioning request failed validation."
    if isinstance(exc, TenantProvisioningError):
        return "provisioning_error", "The provisioning request could not be completed."
    return "database_phase_failed", "Provisioning failed during database setup."


def _mark_failed(*, record_id: UUID, exc: Exception, request_context: Any = None) -> None:
    code, message = _failure_details(exc)
    try:
        with transaction.atomic():
            record = (
                TenantProvisioningRequest.objects.select_for_update()
                .select_related("initiated_by")
                .get(pk=record_id)
            )
            if record.status == TenantProvisioningStatus.SUCCEEDED:
                return
            record.status = TenantProvisioningStatus.FAILED
            record.attempt_count += 1
            record.failure_code = code
            record.failure_message = message
            record.company = None
            record.initial_admin = None
            record.save()
            record_audit_event(
                action="TENANT_PROVISIONING_FAILED",
                category=AuditCategory.SYSTEM,
                severity=AuditSeverity.WARNING,
                summary="Tenant provisioning database phase failed.",
                actor_user=record.initiated_by,
                source_object=record,
                reason_code=code,
                request_context=request_context,
                metadata_safe={
                    "provisioning_id": str(record.pk),
                    "idempotency_key": str(record.idempotency_key),
                },
                success=False,
            )
    except Exception:
        logger.exception("Could not persist safe tenant provisioning failure state: %s", record_id)


def provision_company(
    *,
    actor: User,
    idempotency_key: UUID,
    request: ProvisionCompanyRequest,
    request_context: Any = None,
) -> ProvisionCompanyResult:
    """Provision one tenant exactly once for a platform-scoped idempotency key."""

    _require_platform_actor(actor)
    normalized = _normalized_request(request)
    fingerprint = _request_fingerprint(normalized)
    record = _reserve_request(actor=actor, idempotency_key=idempotency_key, fingerprint=fingerprint)

    try:
        with transaction.atomic():
            record = TenantProvisioningRequest.objects.select_for_update().get(pk=record.pk)
            if record.request_fingerprint != fingerprint:
                raise TenantProvisioningConflictError(
                    "This idempotency key was already used for a different provisioning request."
                )
            if record.status == TenantProvisioningStatus.SUCCEEDED:
                if record.company is None or record.initial_admin is None:
                    raise TenantProvisioningConfigurationError(
                        "The stored provisioning result is incomplete."
                    )
                record_audit_event(
                    action="TENANT_PROVISIONING_REPLAYED",
                    category=AuditCategory.SYSTEM,
                    summary="Tenant provisioning result replayed idempotently.",
                    actor_user=actor,
                    company=record.company,
                    source_object=record,
                    request_context=request_context,
                    metadata_safe={"provisioning_id": str(record.pk)},
                )
                return ProvisionCompanyResult(record, replayed=True)

            record.status = TenantProvisioningStatus.IN_PROGRESS
            record.failure_code = ""
            record.failure_message = ""
            record.save()

            roles = _tenant_admin_roles()
            company = _create_company(normalized.company)
            initial_admin = _initial_admin(normalized.initial_admin)
            _bootstrap_initial_admin(actor=actor, user=initial_admin, company=company, roles=roles)

            record.status = TenantProvisioningStatus.SUCCEEDED
            record.company = company
            record.initial_admin = initial_admin
            record.attempt_count += 1
            record.save()
            record_audit_event(
                action="TENANT_PROVISIONED",
                category=AuditCategory.SYSTEM,
                summary="Tenant Company and initial administrator access provisioned.",
                actor_user=actor,
                company=company,
                source_object=record,
                request_context=request_context,
                metadata_safe={
                    "provisioning_id": str(record.pk),
                    "idempotency_key": str(record.idempotency_key),
                    "company_id": str(company.pk),
                    "initial_admin_id": str(initial_admin.pk),
                    "role_codes": list(TENANT_ADMIN_ROLE_CODES),
                },
            )
            return ProvisionCompanyResult(record, replayed=False)
    except Exception as exc:
        _mark_failed(record_id=record.pk, exc=exc, request_context=request_context)
        raise
