from django.core.validators import RegexValidator

CODE_VALIDATOR = RegexValidator(
    regex=r"^[A-Z0-9_-]+$",
    message="Code may only contain uppercase letters, numbers, hyphens, or underscores.",
)


def normalize_code(value: str) -> str:
    """Trim and uppercase a code value for consistent storage and comparison."""
    return value.strip().upper()
