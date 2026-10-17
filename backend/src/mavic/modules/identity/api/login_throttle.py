"""Freno a la fuerza bruta en el login.

Problema: sin límite, un atacante puede probar miles de contraseñas por minuto
contra un email.

Regla: después de N intentos fallidos para un mismo email dentro de una ventana
de tiempo, ese email queda bloqueado hasta que pase la ventana. Un login
correcto borra el contador.

Limitación consciente: los intentos se guardan EN MEMORIA del proceso. Alcanza
para esta app (un solo proceso), pero si se corrieran varias copias del backend,
cada una tendría su propio contador. En ese caso se movería a Redis o a la base.

Concurrencia: FastAPI atiende los endpoints `def` en varios hilos a la vez, así
que el diccionario se protege con un Lock (si no, dos hilos podrían pisarse al
actualizar la misma lista).
"""

import threading
from collections import defaultdict
from datetime import datetime, timedelta

from mavic.core.clock import Clock
from mavic.core.errors import TooManyRequestsError


class LoginThrottle:
    def __init__(self, *, max_failures: int, window: timedelta, clock: Clock) -> None:
        self._max_failures = max_failures
        self._window = window
        self._clock = clock
        self._failures: dict[str, list[datetime]] = defaultdict(list)
        self._lock = threading.Lock()

    def _recent(self, key: str, now: datetime) -> list[datetime]:
        """Intentos fallidos dentro de la ventana (descarta los viejos)."""
        recent = [t for t in self._failures[key] if now - t < self._window]
        self._failures[key] = recent
        return recent

    def check(self, key: str) -> None:
        """Lanza TooManyRequestsError si la clave está bloqueada."""
        with self._lock:
            now = self._clock.now()
            recent = self._recent(key, now)
            if len(recent) >= self._max_failures:
                unlock_at = recent[0] + self._window
                seconds = max(1, int((unlock_at - now).total_seconds()))
                minutes = -(-seconds // 60)  # redondeo hacia arriba
                raise TooManyRequestsError(
                    f"Demasiados intentos fallidos. Probá de nuevo en {minutes} minuto(s).",
                    retry_after_seconds=seconds,
                )

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._failures[key].append(self._clock.now())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
