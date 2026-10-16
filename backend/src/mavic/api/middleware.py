"""Middleware de contexto del request.

Un middleware es código que envuelve a TODOS los requests:

    request --> [middleware] --> router/endpoint --> [middleware] --> respuesta

Este hace tres cosas:
1. Asigna un `request_id`: reutiliza el header `X-Request-ID` si viene uno válido
   (útil si hay un proxy adelante) o genera uno nuevo.
2. Lo guarda en `request_id_var` para que todas las líneas de log lo incluyan,
   y lo devuelve en la respuesta para que el cliente pueda reportarlo.
3. Escribe una línea de log por request: método, ruta, código y duración.

Está escrito como middleware ASGI "puro" (sin BaseHTTPMiddleware) porque es más
liviano y no interfiere con respuestas en streaming.
"""

import logging
import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mavic.core.logging import request_id_var

logger = logging.getLogger("mavic.access")

REQUEST_ID_HEADER = "x-request-id"
# Solo aceptamos ids "sanos" del cliente: evita inyectar texto raro en los logs.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # websockets, lifespan: pasan sin tocar
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(REQUEST_ID_HEADER.encode(), b"").decode()
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500  # si algo explota antes de responder, queda como 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER.encode(), request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            logger.info(
                "%s %s -> %s",
                scope["method"],
                scope["path"],
                status_code,
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
            request_id_var.reset(token)
