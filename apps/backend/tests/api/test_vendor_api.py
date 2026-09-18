# mypy: disable-error-code="arg-type"
import pytest
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from dsms.finance import services
from dsms.finance.enums import AccountType
from dsms.finance.models import Account
from dsms.finance.payment_models import PaymentAccountingProfile
from dsms.finance.procurement_models import Vendor
from dsms.identity.enums import AccessScopeType
from dsms.identity.models import User
from tests.factories.finance import accounting_setup
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


def grant(user: User, company: object, *codenames: str) -> None:
    role = RoleFactory.create()
    role.permissions.add(
        *Permission.objects.filter(content_type__app_label="finance", codename__in=codenames)
    )
    UserRoleAssignmentFactory.create(
        user=user, role=role, scope_type=AccessScopeType.COMPANY, company=company
    )


def client(user: User) -> APIClient:
    result = APIClient()
    result.force_authenticate(user)
    return result


def payload(account: Account, code: str = "V-001") -> dict[str, object]:
    return {
        "code": code,
        "name": "Secure Supplier",
        "tax_number": "NTN-1",
        "email": "supplier@example.test",
        "phone": "03000000000",
        "payment_terms_days": 30,
        "payable_account": str(account.id),
        "is_active": True,
        "company": str(CompanyFactory.create().id),
        "bank_details_encrypted": "must-never-pass",
    }


def test_dedicated_vendor_crud_is_least_privilege_scoped_and_minimal() -> None:
    company, other = CompanyFactory.create(), CompanyFactory.create()
    _year, _period, accounts = accounting_setup(company)
    _other_year, _other_period, other_accounts = accounting_setup(other)
    hidden = Vendor.objects.create(
        company=other,
        code="HIDDEN",
        name="Hidden Vendor",
        payable_account=other_accounts["payable"],
        bank_details_encrypted="ciphertext",
    )
    user = UserFactory.create()
    grant(user, company, "view_vendor", "add_vendor", "change_vendor")
    api = client(user)
    created = api.post("/api/v1/finance/vendors/", payload(accounts["payable"]), format="json")
    assert created.status_code == 201, created.data
    vendor = Vendor.objects.get(pk=created.data["id"])
    assert vendor.company == company
    assert vendor.bank_details_encrypted == ""
    assert set(created.data) == {
        "id",
        "code",
        "name",
        "tax_number",
        "email",
        "phone",
        "payment_terms_days",
        "payable_account",
        "payable_account_code",
        "payable_account_name",
        "is_active",
        "created_at",
        "updated_at",
    }
    listed = api.get("/api/v1/finance/vendors/?search=Secure&is_active=true")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.data["results"]] == [str(vendor.id)]
    assert api.get(f"/api/v1/finance/vendors/{hidden.id}/").status_code == 404
    assert api.patch(f"/api/v1/finance/vendors/{hidden.id}/", {"name": "Leak"}).status_code == 404
    updated = api.patch(
        f"/api/v1/finance/vendors/{vendor.id}/",
        {"name": "Updated", "company": str(other.id)},
        format="json",
    )
    assert updated.status_code == 200 and updated.data["name"] == "Updated"
    vendor.refresh_from_db()
    assert vendor.company == company
    assert not user.has_perm("finance.manage_procurement")
    assert not user.has_perm("finance.manage_chart_of_accounts")


def test_vendor_actions_require_generated_permissions() -> None:
    company = CompanyFactory.create()
    _year, _period, accounts = accounting_setup(company)
    viewer, creator, editor = UserFactory.create(), UserFactory.create(), UserFactory.create()
    grant(viewer, company, "view_vendor")
    grant(creator, company, "add_vendor")
    grant(editor, company, "change_vendor")
    assert (
        client(viewer)
        .post("/api/v1/finance/vendors/", payload(accounts["payable"]), format="json")
        .status_code
        == 403
    )
    created = client(creator).post(
        "/api/v1/finance/vendors/", payload(accounts["payable"]), format="json"
    )
    assert created.status_code == 201
    url = f"/api/v1/finance/vendors/{created.data['id']}/"
    assert client(creator).get(url).status_code == 403
    assert client(viewer).patch(url, {"name": "No"}, format="json").status_code == 403
    assert client(editor).patch(url, {"name": "Allowed"}, format="json").status_code == 200


@pytest.mark.parametrize("kind", ["cross", "ASSET", "EXPENSE", "REVENUE", "inactive", "nonposting"])
def test_vendor_payable_account_validation_all_write_paths(kind: str) -> None:
    company, other = CompanyFactory.create(), CompanyFactory.create()
    _year, _period, accounts = accounting_setup(company)
    _oy, _op, other_accounts = accounting_setup(other)
    if kind == "cross":
        account = other_accounts["payable"]
    else:
        account_type = kind if kind in {"ASSET", "EXPENSE", "REVENUE"} else AccountType.LIABILITY
        account = services.create_account(
            company=company,
            code=f"X-{kind}",
            name=kind,
            account_type=account_type,
            allow_posting=kind != "nonposting",
        )
        if kind == "inactive":
            account.is_active = False
            account.save(update_fields=["is_active"])
    user = UserFactory.create()
    grant(user, company, "add_vendor")
    dedicated = client(user).post("/api/v1/finance/vendors/", payload(account), format="json")
    if kind == "cross":
        assert dedicated.status_code == 403
    else:
        assert dedicated.status_code == 400
        assert "payable_account" in dedicated.data
    superuser = UserFactory.create(is_superuser=True)
    legacy_payload = payload(account)
    legacy_payload["company"] = str(company.id)
    legacy = client(superuser).post(
        "/api/v1/finance/domain/vendors/", legacy_payload, format="json"
    )
    assert legacy.status_code == 400
    assert "payable_account" in legacy.data


def test_vendor_uses_configured_payable_control_account() -> None:
    company = CompanyFactory.create()
    _year, _period, accounts = accounting_setup(company)
    alternate = services.create_account(
        company=company,
        code="2099",
        name="Other liability",
        account_type=AccountType.LIABILITY,
    )
    PaymentAccountingProfile.objects.create(
        company=company,
        payroll_payable_account=accounts["deduction"],
        vendor_payable_account=accounts["payable"],
        gateway_clearing_account=accounts["cash"],
        bank_account=accounts["bank"],
        provider_fee_account=accounts["expense"],
    )
    user = UserFactory.create()
    grant(user, company, "add_vendor")
    rejected = client(user).post("/api/v1/finance/vendors/", payload(alternate), format="json")
    assert rejected.status_code == 400
    assert rejected.data["payable_account"] == [
        "Select the configured vendor payable control account."
    ]


def test_vendor_reference_is_minimal_scoped_and_requires_vendor_permission() -> None:
    company, other = CompanyFactory.create(), CompanyFactory.create()
    _year, _period, accounts = accounting_setup(company)
    _oy, _op, other_accounts = accounting_setup(other)
    user = UserFactory.create()
    grant(user, company, "add_vendor")
    response = client(user).get("/api/v1/finance/ap-reference/payable-accounts/")
    assert response.status_code == 200
    assert response.data == [
        {"id": str(accounts["payable"].id), "code": "2000", "name": "Payable"},
        {"id": str(accounts["deduction"].id), "code": "2010", "name": "Deduction Payable"},
    ]
    assert str(other_accounts["payable"].id) not in str(response.data)
    assert APIClient().get("/api/v1/finance/ap-reference/payable-accounts/").status_code == 401
    assert (
        client(UserFactory.create())
        .get("/api/v1/finance/ap-reference/payable-accounts/")
        .status_code
        == 403
    )


def test_duplicate_vendor_code_has_field_error() -> None:
    company = CompanyFactory.create()
    _year, _period, accounts = accounting_setup(company)
    Vendor.objects.create(
        company=company, code="DUP", name="First", payable_account=accounts["payable"]
    )
    user = UserFactory.create()
    grant(user, company, "add_vendor")
    response = client(user).post(
        "/api/v1/finance/vendors/", payload(accounts["payable"], "DUP"), format="json"
    )
    assert response.status_code == 400
    assert response.data["code"] == ["A vendor with this code already exists."]


@pytest.mark.parametrize("multi_company_access", [False, True])
def test_vendor_payable_account_read_enforces_vendor_company(
    multi_company_access: bool,
) -> None:
    company_a, company_b = CompanyFactory.create(), CompanyFactory.create()
    _ay, _ap, accounts_a = accounting_setup(company_a)
    _by, _bp, accounts_b = accounting_setup(company_b)
    accounts_b["payable"].code = "B-2000"
    accounts_b["payable"].name = "Hidden Foreign Payable"
    accounts_b["payable"].save(update_fields=["code", "name"])
    valid = Vendor.objects.create(
        company=company_a,
        code="V-VALID",
        name="Visible Vendor",
        payable_account=accounts_a["payable"],
    )
    corrupt = Vendor.objects.create(
        company=company_a,
        code="V-CORRUPT",
        name="Hidden Corrupt Vendor",
        payable_account=accounts_b["payable"],
    )
    user = UserFactory.create()
    grant(user, company_a, "view_vendor", "manage_procurement")
    if multi_company_access:
        grant(user, company_b, "view_vendor", "manage_procurement")
    api = client(user)

    dedicated = api.get("/api/v1/finance/vendors/")
    legacy = api.get("/api/v1/finance/domain/vendors/")

    assert [row["id"] for row in dedicated.data["results"]] == [str(valid.id)]
    assert [row["id"] for row in legacy.data] == [str(valid.id)]
    assert api.get(f"/api/v1/finance/vendors/{corrupt.id}/").status_code == 404
    assert api.get(f"/api/v1/finance/domain/vendors/{corrupt.id}/").status_code == 404
    serialized = str(dedicated.data) + str(legacy.data)
    assert str(accounts_b["payable"].id) not in serialized
    assert accounts_b["payable"].code not in serialized
    assert accounts_b["payable"].name not in serialized
