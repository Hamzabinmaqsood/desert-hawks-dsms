from dataclasses import replace
from unittest.mock import patch
from uuid import uuid4

import pytest

from dsms.audit.models import AuditEvent
from dsms.finance.models import DocumentSequence
from dsms.identity.enums import AccessScopeType
from dsms.identity.models import Role, User, UserRoleAssignment
from dsms.organization.models import Company, TenantProvisioningRequest, TenantProvisioningStatus
from dsms.organization.provisioning import (
    InitialAdminData,
    ProvisionCompanyRequest,
    ProvisionedCompanyData,
    provision_company,
)
from dsms.organization.provisioning_exceptions import (
    InactiveInitialAdminError,
    TenantProvisioningAuthorizationError,
    TenantProvisioningConfigurationError,
    TenantProvisioningConflictError,
    TenantProvisioningValidationError,
)
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


def tenant_admin_roles() -> tuple[Role, Role]:
    return (
        RoleFactory.create(code="ORGANIZATION_ADMIN", is_system=True),
        RoleFactory.create(code="ACCESS_ADMIN", is_system=True),
    )


def request_data(
    *, code: str = "ALPHA", email: str = "admin@alpha.example"
) -> ProvisionCompanyRequest:
    return ProvisionCompanyRequest(
        company=ProvisionedCompanyData(
            code=code,
            legal_name=f"{code.title()} Security (Private) Limited",
            trade_name=f"{code.title()} Security",
            registration_number=f"REG-{code}",
            tax_number=f"TAX-{code}",
            country_code="pk",
            timezone="Asia/Karachi",
            default_currency="pkr",
            brand_tagline="  Always ready  ",
            brand_primary_color="#1a2b3c",
            brand_accent_color="#d4e5f6",
            invoice_number_prefix=f"{code[:3]}I",
            receipt_number_prefix=f"{code[:3]}R",
            credit_note_number_prefix=f"{code[:3]}C",
            debit_note_number_prefix=f"{code[:3]}D",
        ),
        initial_admin=InitialAdminData(
            email=email.upper(), first_name=" Tenant ", last_name=" Admin "
        ),
    )


def platform_actor() -> User:
    return UserFactory.create(is_staff=True, is_superuser=True)


def test_provision_company_creates_minimal_configured_tenant_and_admin_access() -> None:
    tenant_admin_roles()
    actor = platform_actor()

    result = provision_company(actor=actor, idempotency_key=uuid4(), request=request_data())

    record = result.provisioning_request
    company = record.company
    admin = record.initial_admin
    assert result.replayed is False
    assert record.status == TenantProvisioningStatus.SUCCEEDED
    assert record.attempt_count == 1
    assert company is not None
    assert admin is not None
    assert company.code == "ALPHA"
    assert company.country_code == "PK"
    assert company.default_currency == "PKR"
    assert company.brand_tagline == "Always ready"
    assert company.brand_primary_color == "#1A2B3C"
    assert company.invoice_number_prefix == "ALPI"
    assert admin.email == "admin@alpha.example"
    assert admin.first_name == "Tenant"
    assert admin.has_usable_password() is False
    assert admin.is_staff is False
    assert admin.is_superuser is False
    assert set(
        admin.role_assignments.filter(company=company, is_active=True).values_list(
            "role__code", flat=True
        )
    ) == {"ORGANIZATION_ADMIN", "ACCESS_ADMIN"}
    assert admin.role_assignments.count() == 2
    assert set(admin.role_assignments.values_list("scope_type", flat=True)) == {
        AccessScopeType.COMPANY
    }
    assert DocumentSequence.objects.filter(company=company).count() == 0
    assert AuditEvent.objects.filter(action="TENANT_PROVISIONED", company=company).count() == 1


def test_same_request_replays_without_duplicates() -> None:
    tenant_admin_roles()
    actor = platform_actor()
    key = uuid4()
    request = request_data()

    first = provision_company(actor=actor, idempotency_key=key, request=request)
    normalized_equivalent = replace(
        request,
        company=replace(
            request.company,
            country_code="PK",
            default_currency="PKR",
            brand_tagline="Always ready",
            brand_primary_color="#1A2B3C",
            brand_accent_color="#D4E5F6",
        ),
        initial_admin=replace(
            request.initial_admin,
            email="admin@alpha.example",
            first_name="Tenant",
            last_name="Admin",
        ),
    )
    second = provision_company(actor=actor, idempotency_key=key, request=normalized_equivalent)

    assert second.replayed is True
    assert second.provisioning_request.pk == first.provisioning_request.pk
    assert second.provisioning_request.company_id == first.provisioning_request.company_id
    assert Company.objects.filter(code="ALPHA").count() == 1
    assert TenantProvisioningRequest.objects.filter(idempotency_key=key).count() == 1
    assert (
        UserRoleAssignment.objects.filter(
            user=first.provisioning_request.initial_admin,
            company=first.provisioning_request.company,
            is_active=True,
        ).count()
        == 2
    )


def test_same_key_with_conflicting_payload_is_rejected_without_mutating_result() -> None:
    tenant_admin_roles()
    actor = platform_actor()
    key = uuid4()
    first = provision_company(actor=actor, idempotency_key=key, request=request_data())

    with pytest.raises(TenantProvisioningConflictError):
        provision_company(
            actor=actor,
            idempotency_key=key,
            request=request_data(code="BRAVO", email="admin@bravo.example"),
        )

    record = TenantProvisioningRequest.objects.get(pk=first.provisioning_request.pk)
    assert record.status == TenantProvisioningStatus.SUCCEEDED
    assert record.company_id == first.provisioning_request.company_id
    assert Company.objects.count() == 1


def test_non_platform_actor_cannot_create_provisioning_record() -> None:
    actor = UserFactory.create()

    with pytest.raises(TenantProvisioningAuthorizationError):
        provision_company(actor=actor, idempotency_key=uuid4(), request=request_data())

    assert TenantProvisioningRequest.objects.count() == 0
    assert Company.objects.count() == 0


def test_missing_system_roles_fails_as_platform_configuration_without_company() -> None:
    actor = platform_actor()

    with pytest.raises(TenantProvisioningConfigurationError):
        provision_company(actor=actor, idempotency_key=uuid4(), request=request_data())

    record = TenantProvisioningRequest.objects.get()
    assert record.status == TenantProvisioningStatus.FAILED
    assert record.failure_code == "platform_configuration"
    assert Company.objects.count() == 0


def test_company_code_collision_never_takes_over_existing_tenant() -> None:
    tenant_admin_roles()
    actor = platform_actor()
    existing = CompanyFactory.create(code="ALPHA", legal_name="Existing Alpha")

    with pytest.raises(TenantProvisioningValidationError):
        provision_company(actor=actor, idempotency_key=uuid4(), request=request_data())

    existing.refresh_from_db()
    record = TenantProvisioningRequest.objects.get()
    assert existing.legal_name == "Existing Alpha"
    assert Company.objects.count() == 1
    assert record.status == TenantProvisioningStatus.FAILED
    assert record.company_id is None


def test_tax_identifier_collision_rolls_back_without_existing_tenant_takeover() -> None:
    tenant_admin_roles()
    actor = platform_actor()
    existing = CompanyFactory.create(code="EXISTING", tax_number="TAX-SHARED")
    request = request_data(code="BRAVO", email="admin@bravo.example")
    request = replace(
        request,
        company=replace(request.company, tax_number="TAX-SHARED"),
    )

    with pytest.raises(TenantProvisioningValidationError):
        provision_company(actor=actor, idempotency_key=uuid4(), request=request)

    existing.refresh_from_db()
    assert existing.tax_number == "TAX-SHARED"
    assert Company.objects.count() == 1
    assert not User.objects.filter(email="admin@bravo.example").exists()


def test_existing_user_keeps_company_a_access_and_gains_only_company_b_roles() -> None:
    tenant_admin_roles()
    actor = platform_actor()
    company_a = CompanyFactory.create(code="EXISTING")
    existing_user = UserFactory.create(email="consultant@example.com")
    prior_role = RoleFactory.create(code="EXISTING_VIEWER")
    prior_assignment = UserRoleAssignmentFactory.create(
        user=existing_user,
        role=prior_role,
        scope_type=AccessScopeType.COMPANY,
        company=company_a,
    )

    result = provision_company(
        actor=actor,
        idempotency_key=uuid4(),
        request=request_data(code="BRAVO", email="consultant@example.com"),
    )

    company_b = result.provisioning_request.company
    assert result.provisioning_request.initial_admin_id == existing_user.pk
    assert UserRoleAssignment.objects.filter(pk=prior_assignment.pk, is_active=True).exists()
    assert UserRoleAssignment.objects.filter(user=existing_user, company=company_a).count() == 1
    assert UserRoleAssignment.objects.filter(user=existing_user, company=company_b).count() == 2
    assert UserRoleAssignment.objects.filter(user=existing_user).count() == 3


def test_inactive_existing_user_fails_without_reactivation_or_company() -> None:
    tenant_admin_roles()
    actor = platform_actor()
    inactive = UserFactory.create(email="admin@alpha.example", is_active=False)

    with pytest.raises(InactiveInitialAdminError):
        provision_company(actor=actor, idempotency_key=uuid4(), request=request_data())

    inactive.refresh_from_db()
    record = TenantProvisioningRequest.objects.get()
    assert inactive.is_active is False
    assert Company.objects.count() == 0
    assert record.status == TenantProvisioningStatus.FAILED
    assert record.failure_code == "inactive_initial_admin"
    assert record.company_id is None


def test_mid_phase_failure_rolls_back_and_same_key_retries_cleanly() -> None:
    tenant_admin_roles()
    actor = platform_actor()
    key = uuid4()
    request = request_data()
    with (
        patch(
            "dsms.organization.provisioning._bootstrap_initial_admin",
            side_effect=RuntimeError("simulated private failure detail"),
        ),
        pytest.raises(RuntimeError, match="simulated private failure detail"),
    ):
        provision_company(actor=actor, idempotency_key=key, request=request)

    record = TenantProvisioningRequest.objects.get(idempotency_key=key)
    assert record.status == TenantProvisioningStatus.FAILED
    assert record.failure_code == "database_phase_failed"
    assert "private" not in record.failure_message
    assert Company.objects.count() == 0
    assert User.objects.filter(email="admin@alpha.example").count() == 0
    assert UserRoleAssignment.objects.count() == 0

    result = provision_company(actor=actor, idempotency_key=key, request=request)
    assert result.provisioning_request.status == TenantProvisioningStatus.SUCCEEDED
    assert result.provisioning_request.attempt_count == 2
    assert Company.objects.filter(code="ALPHA").count() == 1
    assert (
        UserRoleAssignment.objects.filter(company=result.provisioning_request.company).count() == 2
    )
