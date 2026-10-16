"""Registro central de routers: acá se ve de un vistazo qué expone la API."""

from fastapi import APIRouter

from mavic.modules.ops.api.routes import router as ops_router

api_router = APIRouter()
api_router.include_router(ops_router)
# Próximos pasos: identity, portfolio, cases, negotiation, voice...
