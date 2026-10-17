from datetime import UTC, datetime, timedelta

import pytest

from mavic.core.clock import FixedClock
from mavic.core.errors import TooManyRequestsError
from mavic.modules.identity.api.login_throttle import LoginThrottle


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 10, 16, 15, 0, tzinfo=UTC), "America/Argentina/Buenos_Aires")


@pytest.fixture
def throttle(clock: FixedClock) -> LoginThrottle:
    return LoginThrottle(max_failures=3, window=timedelta(minutes=15), clock=clock)


def test_blocks_after_max_failures(throttle: LoginThrottle) -> None:
    for _ in range(3):
        throttle.check("ana@mail.com")
        throttle.record_failure("ana@mail.com")

    with pytest.raises(TooManyRequestsError) as error:
        throttle.check("ana@mail.com")
    assert error.value.retry_after_seconds == 15 * 60


def test_other_emails_are_not_affected(throttle: LoginThrottle) -> None:
    for _ in range(3):
        throttle.record_failure("ana@mail.com")
    throttle.check("otro@mail.com")  # no lanza


def test_unblocks_when_the_window_passes(throttle: LoginThrottle, clock: FixedClock) -> None:
    for _ in range(3):
        throttle.record_failure("ana@mail.com")
    clock.advance(timedelta(minutes=15, seconds=1))
    throttle.check("ana@mail.com")  # no lanza


def test_successful_login_resets_the_counter(throttle: LoginThrottle) -> None:
    for _ in range(2):
        throttle.record_failure("ana@mail.com")
    throttle.reset("ana@mail.com")
    throttle.record_failure("ana@mail.com")
    throttle.check("ana@mail.com")  # 1 fallo, no 3
