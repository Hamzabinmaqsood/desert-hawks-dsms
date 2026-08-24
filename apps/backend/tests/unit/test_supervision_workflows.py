# mypy: disable-error-code="arg-type,misc,no-untyped-def,no-untyped-call"
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from dsms.contracts.models import Client, ClientIndustry, SecuritySite, ServiceContract
from dsms.supervision.models import SupervisionAssignment
from dsms.supervision.services import end_site_visit, start_site_visit
from tests.factories.identity import UserFactory
from tests.factories.organization import BranchFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db


def site_fixture():
    branch = BranchFactory()
    user = UserFactory()
    supervisor = EmployeeFactory(
        company=branch.company,
        user=user,
        employee_type="SUPERVISOR",
        employment_status="ACTIVE",
    )
    industry = ClientIndustry.objects.create(company=branch.company, code="BANK", name="Bank")
    client = Client.objects.create(
        company=branch.company,
        client_code="ABC",
        legal_name="ABC Bank",
        industry=industry,
        status="ACTIVE",
    )
    contract = ServiceContract.objects.create(
        company=branch.company,
        client=client,
        contract_number="SUP-CTR",
        contract_type="FIXED_TERM",
        title="Guarding",
        start_date=date.today(),
        status="ACTIVE",
        created_by=user,
    )
    site = SecuritySite.objects.create(
        company=branch.company,
        client=client,
        contract=contract,
        site_code="SUP-SITE",
        name="Blue Area Site",
        managing_branch=branch,
        address_line_1="Blue Area",
        city_name="Islamabad",
        latitude=Decimal("33.710000"),
        longitude=Decimal("73.060000"),
        geofence_radius_meters=100,
        risk_level="HIGH",
        status="ACTIVE",
    )
    assignment = SupervisionAssignment.objects.create(
        company=branch.company,
        supervisor=supervisor,
        scope_type="SITE",
        branch=branch,
        site=site,
        effective_from=date.today(),
        status="ACTIVE",
        created_by=user,
    )
    return user, supervisor, site, assignment


def test_assignment_rejects_cross_company_supervisor() -> None:
    branch = BranchFactory()
    assignment = SupervisionAssignment(
        company=branch.company,
        supervisor=EmployeeFactory(employment_status="ACTIVE"),
        scope_type="BRANCH",
        branch=branch,
        effective_from=date.today(),
        created_by=UserFactory(),
    )
    with pytest.raises(ValidationError):
        assignment.full_clean()


def test_visit_start_geofence_and_end_without_inspection_is_incomplete() -> None:
    user, supervisor, site, _ = site_fixture()
    visit = start_site_visit(
        actor=user,
        supervisor=supervisor,
        site=site,
        gps={"latitude": "33.710000", "longitude": "73.060000", "accuracy_meters": "5"},
    )
    assert visit.verification_result == "VERIFIED"
    assert visit.arrival_distance_from_site_meters == Decimal("0.00")
    visit = end_site_visit(visit=visit, actor=user, summary="No checklist available")
    assert visit.status == "INCOMPLETE"
    assert visit.duration_minutes is not None


def test_outside_geofence_is_preserved_as_warning() -> None:
    user, supervisor, site, _ = site_fixture()
    visit = start_site_visit(
        actor=user,
        supervisor=supervisor,
        site=site,
        gps={"latitude": "34.000000", "longitude": "74.000000"},
    )
    assert visit.verification_result == "WARNING"
    assert visit.arrival_distance_from_site_meters > site.geofence_radius_meters
