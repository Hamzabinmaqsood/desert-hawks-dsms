from __future__ import annotations

import re
from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.utils import timezone

CURRENCY_CODE_PATTERN = re.compile(r"^[A-Z]{3}$")
DOCUMENT_PREFIX_PATTERN = re.compile(r"^[A-Z0-9](?:[A-Z0-9_-]{0,8}[A-Z0-9])?$")


class CompanyTimezone(Protocol):
    timezone: str


def normalize_currency_code(value: str) -> str:
    return value.strip().upper()


def validate_currency_code(value: str) -> None:
    if not CURRENCY_CODE_PATTERN.fullmatch(normalize_currency_code(value)):
        raise ValidationError("Enter a three-letter uppercase currency code.")


def normalize_document_prefix(value: str) -> str:
    return value.strip().upper()


def validate_document_prefix(value: str) -> None:
    if not DOCUMENT_PREFIX_PATTERN.fullmatch(normalize_document_prefix(value)):
        raise ValidationError(
            "Use 1-10 uppercase letters, numbers, hyphens, or underscores; "
            "start and end with a letter or number."
        )


def validate_timezone_name(value: str) -> None:
    try:
        ZoneInfo(value.strip())
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationError("Enter a valid IANA timezone name.") from exc


def company_local_date(company: CompanyTimezone, value: datetime | None = None) -> date:
    zone = ZoneInfo(company.timezone)
    moment = value or timezone.now()
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment, zone)
    return moment.astimezone(zone).date()
