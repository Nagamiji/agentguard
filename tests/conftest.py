import pytest

from keel.config import settings


@pytest.fixture(autouse=True)
def disable_rate_limiting() -> None:
    # Disable rate limiting for all tests by default to prevent blocking
    # test cases that run in quick succession.
    settings.rate_limit_enabled = False
