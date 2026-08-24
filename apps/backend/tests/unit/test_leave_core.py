from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone

from dsms.leave.services import calculate_leave_units


def test_hourly_leave_units_use_decimal_hours() -> None:
    starts_at = timezone.now()
    units = calculate_leave_units(
        employee=SimpleNamespace(),
        leave_type=SimpleNamespace(unit="HOURS"),
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=2, minutes=30),
        policy_rule=SimpleNamespace(charge_method="CALENDAR_DAYS"),
    )
    assert units == Decimal("2.50")


def test_leave_unit_calculation_rejects_empty_or_negative_interval() -> None:
    moment = timezone.now()
    with pytest.raises(ValueError):
        calculate_leave_units(
            employee=SimpleNamespace(),
            leave_type=SimpleNamespace(unit="HOURS"),
            starts_at=moment,
            ends_at=moment,
            policy_rule=SimpleNamespace(charge_method="CALENDAR_DAYS"),
        )
