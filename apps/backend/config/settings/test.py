from .base import *  # noqa: F403
from .base import REST_FRAMEWORK

SECRET_KEY = "test-only-dsms-signing-key-2026-never-use-in-production"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Tests run outside the Docker network (no reachable `redis` host) and must
# not be sensitive to real-world rate limits across test functions sharing
# one process-lifetime cache.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {"login": "1000/min"},
}
