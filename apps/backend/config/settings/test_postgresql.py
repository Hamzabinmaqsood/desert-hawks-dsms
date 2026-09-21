import os
import re
from copy import deepcopy

from . import base as base_settings
from .test import *  # noqa: F403

# Keep the test-only hasher, cache, and throttle settings while exercising the
# same PostgreSQL database configuration used by the Compose runtime.
DATABASES = deepcopy(base_settings.DATABASES)

# An explicit name keeps isolated test runs away from an existing default
# test_<application database> whose ownership may be unknown.
test_database_name = os.environ.get("DSMS_TEST_DATABASE_NAME")
if not test_database_name or not re.fullmatch(
    r"test_desert_hawks_[a-z0-9_]{1,40}", test_database_name
):
    raise ValueError("DSMS_TEST_DATABASE_NAME must name a dedicated test_desert_hawks_* database")
DATABASES["default"]["TEST"] = {"NAME": test_database_name}
