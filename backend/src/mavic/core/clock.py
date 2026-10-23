"""Reloj de la aplicación.

Problema que resuelve: el original usaba `date.today()` del servidor (que corre
en UTC) para calcular cuántos días lleva vencida una deuda. Entre las 21:00 y
las 24:00 de Argentina, el servidor ya "vive" en el día siguiente.

Además, código que llama directamente a `datetime.now()` es difícil de testear:
el resultado cambia en cada ejecución.

Solución: el código de negocio pide la hora a un `Clock`.
- En producción: `SystemClock`, la hora real.
- En tests: `FixedClock`, una hora fija que elegimos.

    caso de uso --> clock.today()  -->  SystemClock (real) | FixedClock (tests)
"""

from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo


class Clock(Protocol):
    """Contrato: cualquier objeto con estos dos métodos sirve como reloj."""

    def now(self) -> datetime:
        """Momento actual, siempre con zona horaria UTC."""
        ...

    def zone(self) -> ZoneInfo:
        """Zona horaria del negocio (para pasar un día local a un rango de instantes)."""
        ...

    def today(self) -> date:
        """Fecha actual en la zona horaria del negocio."""
        ...


class SystemClock:
    def __init__(self, business_timezone: str) -> None:
        self._tz = ZoneInfo(business_timezone)

    def now(self) -> datetime:
        return datetime.now(UTC)

    def zone(self) -> ZoneInfo:
        return self._tz

    def today(self) -> date:
        return datetime.now(self._tz).date()


class FixedClock:
    """Reloj detenido en un instante: los tests dan siempre el mismo resultado.

    Se puede adelantar a mano con `advance()` para probar vencimientos sin
    esperar de verdad (por ejemplo, que una sesión expire a las 8 horas).
    """

    def __init__(self, instant: datetime, business_timezone: str) -> None:
        if instant.tzinfo is None:
            raise ValueError("FixedClock necesita un datetime con zona horaria")
        self._instant = instant.astimezone(UTC)
        self._tz = ZoneInfo(business_timezone)

    def now(self) -> datetime:
        return self._instant

    def zone(self) -> ZoneInfo:
        return self._tz

    def today(self) -> date:
        return self._instant.astimezone(self._tz).date()

    def advance(self, delta: timedelta) -> None:
        self._instant += delta
