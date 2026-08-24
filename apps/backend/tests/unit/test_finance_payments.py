from datetime import date
from decimal import Decimal

import pytest

from dsms.finance import domain_services
from dsms.finance.enums import WorkflowStatus
from dsms.finance.exceptions import MakerCheckerError
from dsms.finance.operations_models import FundTransfer
from tests.factories.finance import accounting_setup
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


def test_fund_transfer_requires_independent_approval_and_posts_once() -> None:
    company = CompanyFactory.create()
    maker, checker = UserFactory.create(), UserFactory.create()
    _year, _period, accounts = accounting_setup(company)
    transfer = FundTransfer.objects.create(
        company=company,
        transfer_number="FT-1",
        transfer_date=date(2026, 8, 10),
        amount=Decimal("50"),
        source_account=accounts["cash"],
        destination_account=accounts["bank"],
        status=WorkflowStatus.SUBMITTED,
        created_by=maker,
    )
    with pytest.raises(MakerCheckerError):
        domain_services.approve_finance_document(
            obj=transfer, actor=maker, document_type="FUND_TRANSFER"
        )
    transfer = domain_services.approve_finance_document(
        obj=transfer, actor=checker, document_type="FUND_TRANSFER"
    )
    first = domain_services.post_fund_transfer(transfer=transfer, actor=checker)
    second = domain_services.post_fund_transfer(transfer=first, actor=checker)
    assert first.journal_entry_id == second.journal_entry_id
