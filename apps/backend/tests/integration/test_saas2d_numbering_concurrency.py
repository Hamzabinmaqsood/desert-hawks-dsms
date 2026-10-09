from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID

import pytest
from django.db import close_old_connections

from dsms.finance.services import next_company_document_number
from dsms.organization.models import Company
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db(transaction=True)


def allocate(company_id: UUID, count: int) -> list[str]:
    barrier = Barrier(count)

    def run(_index: int) -> str:
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            company = Company.objects.get(pk=company_id)
            return next_company_document_number(company=company, family="invoice", year=2026)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(run, range(count)))


def test_configurable_first_allocation_is_unique_under_concurrency() -> None:
    company = CompanyFactory.create(invoice_number_prefix="AINV")
    numbers = allocate(company.pk, 4)
    assert len(set(numbers)) == 4
    assert sorted(numbers) == [f"AINV-2026-{number:06d}" for number in range(1, 5)]


def test_concurrent_company_sequences_remain_independent() -> None:
    company_a = CompanyFactory.create(invoice_number_prefix="AINV")
    company_b = CompanyFactory.create(invoice_number_prefix="BINV")
    with ThreadPoolExecutor(max_workers=2) as pool:
        future_a = pool.submit(allocate, company_a.pk, 2)
        future_b = pool.submit(allocate, company_b.pk, 2)
        numbers_a, numbers_b = future_a.result(), future_b.result()
    assert sorted(numbers_a) == ["AINV-2026-000001", "AINV-2026-000002"]
    assert sorted(numbers_b) == ["BINV-2026-000001", "BINV-2026-000002"]
