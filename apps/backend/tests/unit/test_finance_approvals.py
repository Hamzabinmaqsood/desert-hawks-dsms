from decimal import Decimal

import pytest

from dsms.finance import domain_services
from dsms.finance.enums import ApprovalDocumentType
from dsms.finance.operations_models import ApprovalPolicy, ApprovalStep
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


def test_amount_based_policy_and_ordered_steps() -> None:
    company = CompanyFactory.create()
    policy = ApprovalPolicy.objects.create(
        company=company,
        document_type=ApprovalDocumentType.PAYMENT_VOUCHER,
        name="Large payment",
        minimum_amount=Decimal("1000"),
    )
    ApprovalStep.objects.create(policy=policy, sequence=2, role_code="FINANCE_ADMIN")
    ApprovalStep.objects.create(policy=policy, sequence=1, role_code="FINANCE_APPROVER")
    selected = domain_services.applicable_policy(
        company_id=company.id,
        document_type=ApprovalDocumentType.PAYMENT_VOUCHER,
        amount=Decimal("1500"),
    )
    assert selected == policy
    assert list(policy.steps.order_by("sequence").values_list("role_code", flat=True)) == [
        "FINANCE_APPROVER",
        "FINANCE_ADMIN",
    ]


def test_no_policy_outside_amount_range() -> None:
    company = CompanyFactory.create()
    ApprovalPolicy.objects.create(
        company=company,
        document_type=ApprovalDocumentType.BUDGET,
        name="Limited",
        minimum_amount=Decimal("100"),
        maximum_amount=Decimal("200"),
    )
    assert (
        domain_services.applicable_policy(
            company_id=company.id,
            document_type=ApprovalDocumentType.BUDGET,
            amount=Decimal("201"),
        )
        is None
    )
