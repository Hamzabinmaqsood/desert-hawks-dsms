import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from dsms.common.integrity import IntegrityExecutionError
from dsms.finance.enums import AccountType
from dsms.finance.models import Account
from dsms.finance.payment_models import PaymentAccountingProfile
from dsms.organization.models import Company
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


def account(company, code: str, account_type: str = AccountType.ASSET):  # type: ignore[no-untyped-def]
    return Account.objects.create(
        company=company,
        code=code,
        name=f"Account {code}",
        account_type=account_type,
        allow_posting=True,
    )


def corrupt_payment_profile() -> tuple[Company, Company, PaymentAccountingProfile]:
    company_a = CompanyFactory.create(code="COMMAND-A")
    company_b = CompanyFactory.create(code="COMMAND-B")
    profile = PaymentAccountingProfile.objects.create(
        company=company_a,
        payroll_payable_account=account(company_a, "A-2010", AccountType.LIABILITY),
        vendor_payable_account=account(company_a, "A-2020", AccountType.LIABILITY),
        gateway_clearing_account=account(company_a, "A-2030", AccountType.LIABILITY),
        bank_account=account(company_a, "A-1010"),
        provider_fee_account=account(company_a, "A-5010", AccountType.EXPENSE),
    )
    foreign = account(company_b, "B-1010")
    PaymentAccountingProfile.objects.filter(pk=profile.pk).update(bank_account=foreign)
    return company_a, company_b, profile


def test_clean_text_and_json_commands() -> None:
    text_output = StringIO()
    call_command("tenant_integrity_scan", stdout=text_output)
    assert "17 checks, 0 findings (0 errors, 0 warnings)" in text_output.getvalue()

    json_output = StringIO()
    call_command("tenant_integrity_scan", "--format", "json", stdout=json_output)
    payload = json.loads(json_output.getvalue())
    assert payload["schema_version"] == 1
    assert payload["summary"]["total_checks"] == 17
    assert payload["summary"]["total_findings"] == 0


def test_corrupted_json_is_clean_and_error_exit_is_deliberate() -> None:
    company_a, company_b, profile = corrupt_payment_profile()
    stdout = StringIO()
    stderr = StringIO()

    with pytest.raises(CommandError) as captured:
        call_command(
            "tenant_integrity_scan",
            "--format",
            "json",
            "--check",
            "finance.payment_accounting_profile.account_company_match",
            "--company",
            company_a.code,
            stdout=stdout,
            stderr=stderr,
        )

    assert captured.value.returncode == 1
    payload = json.loads(stdout.getvalue())
    assert payload["summary"] == {
        "total_checks": 1,
        "passed_checks": 0,
        "failed_checks": 1,
        "total_findings": 1,
        "errors": 1,
        "warnings": 0,
        "findings_by_domain": {"finance": 1},
    }
    finding = payload["findings"][0]
    assert finding["record_id"] == str(profile.id)
    assert finding["owning_company_id"] == str(company_a.id)
    assert finding["conflicting_company_id"] == str(company_b.id)
    assert "account_number" not in stdout.getvalue()
    assert "encrypted" not in stdout.getvalue()


def test_domain_check_and_company_selection() -> None:
    company = CompanyFactory.create(code="FILTER-A")
    stdout = StringIO()

    call_command(
        "tenant_integrity_scan",
        "--format",
        "json",
        "--domain",
        "billing",
        "--company",
        str(company.id),
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert payload["scope"] == {"company_id": str(company.id)}
    assert payload["summary"]["total_checks"] == 3
    assert {check["domain"] for check in payload["checks_run"]} == {"billing"}


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (("--domain", "typo"), "Unknown integrity domain"),
        (("--check", "tests.missing"), "Unknown integrity check"),
        (("--company", "NO-SUCH-COMPANY"), "Unknown Company"),
    ],
)
def test_unknown_operator_selectors_fail_cleanly(arguments, message: str) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(CommandError, match=message) as captured:
        call_command("tenant_integrity_scan", *arguments, stdout=StringIO(), stderr=StringIO())

    assert captured.value.returncode == 2


def test_internal_scanner_failure_has_distinct_exit_semantics() -> None:
    from unittest.mock import patch

    with (
        patch(
            "dsms.common.management.commands.tenant_integrity_scan.run_integrity_scan",
            side_effect=IntegrityExecutionError("tests.crash"),
        ),
        pytest.raises(CommandError, match="tests.crash") as captured,
    ):
        call_command("tenant_integrity_scan", stdout=StringIO(), stderr=StringIO())

    assert captured.value.returncode == 2
