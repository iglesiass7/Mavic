from datetime import UTC, date, datetime

import pytest

from mavic.core.clock import FixedClock

BUSINESS_TZ = "America/Argentina/Buenos_Aires"


def test_today_uses_business_timezone_not_utc() -> None:
    # 17/10 a la 01:30 UTC todavía es 16/10 a las 22:30 en Argentina.
    # Este es exactamente el error del sistema original con date.today().
    clock = FixedClock(datetime(2026, 10, 17, 1, 30, tzinfo=UTC), BUSINESS_TZ)
    assert clock.today() == date(2026, 10, 16)


def test_now_is_always_utc() -> None:
    clock = FixedClock(datetime(2026, 10, 16, 12, 0, tzinfo=UTC), BUSINESS_TZ)
    assert clock.now().tzinfo == UTC


def test_fixed_clock_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="zona horaria"):
        FixedClock(datetime(2026, 10, 16, 12, 0), BUSINESS_TZ)
