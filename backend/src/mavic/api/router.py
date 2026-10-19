"""Registro central de routers: acá se ve de un vistazo qué expone la API.

AUTENTICACIÓN POR DEFECTO
-------------------------
En el original, la sesión se pedía endpoint por endpoint, y se olvidó en 62 de
71. Acá es al revés: TODO router registrado en `protected` exige sesión. Para que
algo sea público hay que agregarlo a `public` a propósito, y la lista es corta.

    public     ->  /health, /health/ready, /auth/login, /auth/logout
    agent      ->  herramientas del agente de voz y su webhook: no usan sesión,
                   se autentican con un token secreto o con la firma del mensaje
                   (401 si faltan o no coinciden)
    protected  ->  todo lo demás (401 sin una sesión válida)

Un test (tests/api/test_route_protection.py) recorre TODAS las rutas y falla si
alguna que no está en la lista pública responde sin sesión.
"""

from fastapi import APIRouter, Depends

from mavic.api.deps import get_current_session
from mavic.modules.identity.api.routes import public_router as identity_public_router
from mavic.modules.identity.api.routes import router as identity_router
from mavic.modules.negotiation.api.routes import router as negotiation_router
from mavic.modules.ops.api.routes import router as ops_router
from mavic.modules.portfolio.api.routes import router as portfolio_router
from mavic.modules.reporting.api.routes import router as reporting_router
from mavic.modules.voice.api.agent_routes import router as agent_tools_router
from mavic.modules.voice.api.routes import router as voice_router
from mavic.modules.voice.api.webhook_routes import router as webhook_router

# Rutas que se pueden llamar sin sesión (además de /docs y /openapi.json).
PUBLIC_PATHS = frozenset({"/health", "/health/ready", "/auth/login", "/auth/logout"})

public = APIRouter()
public.include_router(ops_router)
public.include_router(identity_public_router)

# Sin sesión, pero cada router trae su propia autenticación (token o firma).
agent = APIRouter()
agent.include_router(agent_tools_router)
agent.include_router(webhook_router)

protected = APIRouter(dependencies=[Depends(get_current_session)])
protected.include_router(identity_router)
protected.include_router(portfolio_router)
protected.include_router(negotiation_router)
protected.include_router(voice_router)
protected.include_router(reporting_router)

api_router = APIRouter()
api_router.include_router(public)
api_router.include_router(agent)
api_router.include_router(protected)
