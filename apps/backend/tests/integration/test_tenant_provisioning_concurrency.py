from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from django.contrib.auth.models import Permission
from django.db import close_old_connections

from dsms.identity.models import Role, User, UserRoleAssignment
from dsms.identity.platform_access import PROVISION_TENANT
from dsms.organization.models import Company, TenantProvisioningRequest
from dsms.organization.provisioning import (
    InitialAdminData,
    ProvisionCompanyRequest,
    ProvisionedCompanyData,
    provision_company,
)
from dsms.organization.provisioning_exceptions import TenantProvisioningConflictError
from tests.factories.identity import RoleFactory, UserFactory

pytestmark = pytest.mark.django_db(transaction=True)


def tenant_admin_roles() -> tuple[Role, Role]:
    return (
        RoleFactory.create(code="ORGANIZATION_ADMIN", is_system=True),
        RoleFactory.create(code="ACCESS_ADMIN", is_system=True),
    )


def platform_actor() -> User:
    actor = UserFactory.create(is_staff=False, is_superuser=False)
    actor.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="organization",
            codename=PROVISION_TENANT.split(".", maxsplit=1)[1],
        )
    )
    return actor


def request_data(code: str) -> ProvisionCompanyRequest:
    return ProvisionCompanyRequest(
        company=ProvisionedCompanyData(
            code=code,
            legal_name=f"{code.title()} Security Limited",
            country_code="PK",
            timezone="Asia/Karachi",
            default_currency="PKR",
            brand_tagline=f"{code.title()} assurance",
            brand_primary_color="#123456" if code == "ALPHA" else "#654321",
            invoice_number_prefix=f"{code[:3]}I",
            receipt_number_prefix=f"{code[:3]}R",
            credit_note_number_prefix=f"{code[:3]}C",
            debit_note_number_prefix=f"{code[:3]}D",
        ),
        initial_admin=InitialAdminData(email=f"admin@{code.lower()}.example"),
    )


def concurrent_provision(
    actor_id: UUID, calls: list[tuple[UUID, ProvisionCompanyRequest]]
) -> list[tuple[str, UUID | None, UUID | None, bool]]:
    barrier = Barrier(len(calls))

    def run(
        call: tuple[UUID, ProvisionCompanyRequest],
    ) -> tuple[str, UUID | None, UUID | None, bool]:
        close_old_connections()
        try:
            actor = User.objects.get(pk=actor_id)
            barrier.wait(timeout=10)
            result = provision_company(actor=actor, idempotency_key=call[0], request=call[1])
            record = result.provisioning_request
            return "ok", record.pk, record.company_id, result.replayed
        except TenantProvisioningConflictError:
            return "conflict", None, None, False
        except Exception as exc:
            return type(exc).__name__, None, None, False
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=len(calls)) as executor:
        return list(executor.map(run, calls))


def test_concurrent_duplicate_requests_resolve_to_one_tenant() -> None:
    tenant_admin_roles()
    actor = platform_actor()
    key = uuid4()
    request = request_data("ALPHA")

    results = concurrent_provision(actor.pk, [(key, request), (key, request)])

    assert all(status == "ok" for status, _record, _company, _replayed in results), results
    assert len({record for _status, record, _company, _replayed in results}) == 1
    assert len({company for _status, _record, company, _replayed in results}) == 1
    assert sorted(replayed for _status, _record, _company, replayed in results) == [False, True]
    assert TenantProvisioningRequest.objects.count() == 1
    assert Company.objects.count() == 1
    company = Company.objects.get()
    assert UserRoleAssignment.objects.filter(company=company, is_active=True).count() == 2


def test_concurrent_conflicting_payloads_yield_one_success_and_one_conflict() -> None:
    tenant_admin_roles()
    actor = platform_actor()
    key = uuid4()

    results = concurrent_provision(
        actor.pk, [(key, request_data("ALPHA")), (key, request_data("BRAVO"))]
    )

    assert sorted(status for status, _record, _company, _replayed in results) == [
        "conflict",
        "ok",
    ]
    assert TenantProvisioningRequest.objects.count() == 1
    assert Company.objects.count() == 1


def test_concurrent_distinct_requests_create_isolated_tenants() -> None:
    tenant_admin_roles()
    actor = platform_actor()

    results = concurrent_provision(
        actor.pk,
        [(uuid4(), request_data("ALPHA")), (uuid4(), request_data("BRAVO"))],
    )

    assert all(status == "ok" for status, _record, _company, _replayed in results), results
    assert len({record for _status, record, _company, _replayed in results}) == 2
    assert len({company for _status, _record, company, _replayed in results}) == 2
    alpha = Company.objects.get(code="ALPHA")
    bravo = Company.objects.get(code="BRAVO")
    assert alpha.brand_primary_color == "#123456"
    assert bravo.brand_primary_color == "#654321"
    assert alpha.invoice_number_prefix != bravo.invoice_number_prefix
    assert UserRoleAssignment.objects.filter(company=alpha, is_active=True).count() == 2
    assert UserRoleAssignment.objects.filter(company=bravo, is_active=True).count() == 2
    assert not UserRoleAssignment.objects.filter(
        company=alpha, user__email="admin@bravo.example"
    ).exists()
    assert not UserRoleAssignment.objects.filter(
        company=bravo, user__email="admin@alpha.example"
    ).exists()
