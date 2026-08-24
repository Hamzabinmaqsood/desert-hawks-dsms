import pytest
from rest_framework.test import APIClient

from dsms.finance.crypto import decrypt_payment_destination
from dsms.finance.payment_models import PaymentBeneficiaryProfile
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db


def test_payment_destination_api_masks_and_separates_approval_steps() -> None:
    company = CompanyFactory.create()
    employee = EmployeeFactory.create(company=company)
    requester, verifier, approver, activator = UserFactory.create_batch(4, is_superuser=True)
    client = APIClient()
    client.force_authenticate(requester)
    created = client.post(
        "/api/v1/finance/payment-beneficiaries/",
        {
            "company": str(company.id),
            "employee": str(employee.id),
            "destination": "03123456789",
            "account_title": "Employee",
            "provider_type": "TEST",
            "currency": "PKR",
        },
        format="json",
    )
    assert created.status_code == 201
    body = created.json()
    assert "destination_encrypted" not in body and body["destination_masked"] == "***6789"
    profile = PaymentBeneficiaryProfile.objects.get(pk=body["id"])
    assert decrypt_payment_destination(profile.destination_encrypted) == "03123456789"

    for actor, action, expected in [
        (verifier, "verify", "UNDER_VERIFICATION"),
        (approver, "approve", "APPROVED"),
        (activator, "activate", "ACTIVATED"),
    ]:
        client.force_authenticate(actor)
        result = client.post(
            f"/api/v1/finance/payment-beneficiaries/{profile.id}/{action}/", {}, format="json"
        )
        assert result.status_code == 200 and result.json()["status"] == expected


def test_payment_provider_api_never_returns_secret_reference() -> None:
    company = CompanyFactory.create()
    user = UserFactory.create(is_superuser=True)
    client = APIClient()
    client.force_authenticate(user)
    created = client.post(
        "/api/v1/finance/payment-providers/",
        {
            "company": str(company.id),
            "code": "TEST",
            "provider_type": "TEST",
            "display_name": "Test provider",
            "currency": "PKR",
            "adapter_code": "TEST_SUCCESS",
            "safe_configuration": {},
        },
        format="json",
    )
    assert created.status_code == 201
    assert "secret_reference" not in created.json()
