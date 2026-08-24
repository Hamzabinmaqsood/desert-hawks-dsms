"""National identity number normalization and masking.

CNIC/passport/other national identity references are stored as-typed (minus
incidental whitespace) so they can be matched for per-company uniqueness, but
must never be echoed back in full to callers who lack the dedicated
sensitive-data permission -- see ``Employee.masked_national_identity_number``
and ``EmployeeDetailSerializer``.
"""

import re

_IGNORED_SEPARATOR_RE = re.compile(r"[\s-]+")


def normalize_identity_number(value: str) -> str:
    """Canonicalize whitespace/hyphens and format a 13-digit Pakistani CNIC."""
    normalized = _IGNORED_SEPARATOR_RE.sub("", value.strip().upper())
    if normalized.isdigit() and len(normalized) == 13:
        return f"{normalized[:5]}-{normalized[5:12]}-{normalized[12]}"
    return normalized


def mask_identity_number(value: str) -> str:
    """Mask all but the last character, preserving separators (e.g. hyphens).

    ``12345-1234567-1`` -> ``*****-*******-1``.
    """
    if not value:
        return ""
    last_index = len(value) - 1
    return "".join(
        char if (not char.isalnum() or index == last_index) else "*"
        for index, char in enumerate(value)
    )
