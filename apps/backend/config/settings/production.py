from .base import *  # noqa: F403
from .base import SECRET_KEY

DEBUG = False

if SECRET_KEY == "unsafe-local-development-key-change-me":
    raise RuntimeError("DJANGO_SECRET_KEY must be configured in production")

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
