import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ValidationError


def _fernet() -> Fernet:
    digest = hashlib.sha256(f"dsms-payment-v1:{settings.SECRET_KEY}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_payment_destination(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_payment_destination(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ValidationError("Payment destination could not be decrypted.") from exc
