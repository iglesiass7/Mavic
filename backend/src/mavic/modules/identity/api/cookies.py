"""Cookie de sesión.

Atributos y por qué:
- HttpOnly:  el JavaScript de la página NO puede leerla. Si alguien lograra
             inyectar un script (XSS), no podría robar la sesión.
- SameSite=Lax: el navegador no la manda en pedidos que otro sitio dispara
             contra nuestra API (formularios ocultos, etc.). Es la protección
             contra CSRF. El original usaba SameSite=None, que la desactiva.
- Secure:    solo viaja por HTTPS. Configurable porque en tu PC se usa http.
- Max-Age:   vence junto con la sesión del servidor.

Nota: localhost:3000 (frontend) y localhost:8000 (API) son el mismo "sitio"
para el navegador (el puerto no cuenta), así que Lax no molesta en desarrollo.
"""

from fastapi import Response

from mavic.core.config import Settings

SESSION_COOKIE = "mavic_session"


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
