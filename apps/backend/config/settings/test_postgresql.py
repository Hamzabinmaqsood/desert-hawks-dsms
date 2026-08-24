from . import base as base_settings
from .test import *  # noqa: F403

# Keep the test-only hasher, cache, and throttle settings while exercising the
# same PostgreSQL database configuration used by the Compose runtime.
DATABASES = base_settings.DATABASES
