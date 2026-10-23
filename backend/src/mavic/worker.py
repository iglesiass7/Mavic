"""Proceso de fondo: manda los avisos automáticos a la hora configurada (ADR-038).

    cada minuto ──> ¿a alguna empresa le llegó la hora de su envío y hoy no corrió?
                     └─ sí: manda sus avisos (preventivo y/o día de vencimiento)

Corre aparte del servidor web, en su propio contenedor:

    docker compose up            (el servicio "worker" ya lo levanta)
    python -m mavic.worker       (en tu PC, sin Docker)
    python -m mavic.worker --once  (una sola pasada: para un cron o AWS EventBridge)

Si corren dos a la vez no pasa nada: cada envío lo toma uno solo (ver
`claim_due_runs`) y cada aviso se manda una sola vez (índice único).
"""

import argparse
import logging
import signal
import sys
import threading
from types import FrameType

from mavic.core.clock import SystemClock
from mavic.core.config import get_settings
from mavic.core.db import Database
from mavic.core.logging import configure_logging
from mavic.main import configured_senders
from mavic.modules.notices.application.sending import run_scheduled

logger = logging.getLogger("mavic.worker")
INTERVAL_SECONDS = 60


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mavic.worker", description=__doc__)
    parser.add_argument("--once", action="store_true", help="Una sola pasada y termina")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)
    database = Database(settings.database_url.get_secret_value())
    clock = SystemClock(settings.business_timezone)
    senders = configured_senders(settings)

    stop = threading.Event()

    def _stop(signum: int, _frame: FrameType | None) -> None:
        logger.info("Señal %s: termino después de esta pasada.", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    logger.info("Worker de avisos iniciado (revisa cada %s s).", INTERVAL_SECONDS)
    try:
        while True:
            try:
                for report in run_scheduled(database, clock=clock, senders=senders):
                    logger.info(
                        "Avisos %s por %s: %s mandados, %s fallaron, %s sin contacto.",
                        report.stage,
                        report.channel,
                        report.sent,
                        report.failed,
                        report.without_contact,
                    )
            except Exception:
                # Un error (la base no responde, por ejemplo) no tiene que matar al worker.
                logger.exception("Falló una pasada del worker; reintento en el próximo minuto.")
            if args.once or stop.wait(INTERVAL_SECONDS):
                break
    finally:
        database.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
