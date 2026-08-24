# mypy: disable-error-code="misc,arg-type,attr-defined"
from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from dsms.attendance.enums import VerificationResult
from dsms.attendance.models import AttendancePolicy, AttendanceQRStation
from dsms.attendance.services import (
    evaluate_geofence,
    generate_qr_station_token,
    verify_attendance_qr,
)
from dsms.contracts.models import Client, ClientIndustry, SecuritySite, ServiceContract
from tests.factories.identity import UserFactory
from tests.factories.organization import BranchFactory

pytestmark = pytest.mark.django_db


def test_qr_secret_is_hashed_and_geofence_is_deterministic() -> None:
    actor = UserFactory()
    branch = BranchFactory()
    company = branch.company
    industry = ClientIndustry.objects.create(company=company, code="BANK", name="Bank")
    client = Client.objects.create(
        company=company,
        client_code="ABC",
        legal_name="ABC Bank",
        industry=industry,
        status="ACTIVE",
    )
    contract = ServiceContract.objects.create(
        company=company,
        client=client,
        contract_number="CTR-A",
        contract_type="FIXED_TERM",
        title="Guarding",
        start_date=date.today(),
        status="ACTIVE",
        created_by=actor,
    )
    site = SecuritySite.objects.create(
        company=company,
        client=client,
        contract=contract,
        site_code="SITE-A",
        name="Blue Area",
        managing_branch=branch,
        address_line_1="Blue Area",
        city_name="Islamabad",
        latitude=Decimal("33.710000"),
        longitude=Decimal("73.060000"),
        geofence_radius_meters=100,
        risk_level="HIGH",
        status="ACTIVE",
    )
    policy = AttendancePolicy.objects.create(
        company=company,
        site=site,
        name="Site policy",
        effective_from=date.today(),
        require_gps=True,
        require_qr=True,
        maximum_gps_accuracy_meters=Decimal("50"),
    )
    station = AttendanceQRStation.objects.create(
        company=company,
        site=site,
        station_code="QR-1",
        name="Main QR",
        token_hash="",
        generated_by=actor,
        generated_at=timezone.now(),
    )
    token = generate_qr_station_token(station=station)
    station.refresh_from_db()
    assert token not in station.token_hash
    assert verify_attendance_qr(station=station, submitted_token=token, site=site)
    assert not verify_attendance_qr(station=station, submitted_token="wrong", site=site)
    result = evaluate_geofence(
        site=site,
        latitude=Decimal("33.710000"),
        longitude=Decimal("73.060000"),
        accuracy_meters=Decimal("5"),
        policy=policy,
    )
    assert result.result == VerificationResult.PASSED
    assert result.inside_geofence
