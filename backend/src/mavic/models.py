"""Registro de tablas.

Importar este módulo registra todas las tablas en `Base.metadata`. Lo usan
Alembic (para comparar modelos contra la base) y los tests (para crear el esquema).

Cada módulo de negocio con tablas se agrega acá.
"""

from mavic.core.db import Base
from mavic.modules.audit.infrastructure import orm as audit_orm
from mavic.modules.costs.infrastructure import orm as costs_orm
from mavic.modules.identity.infrastructure import orm as identity_orm
from mavic.modules.negotiation.infrastructure import orm as negotiation_orm
from mavic.modules.notices.infrastructure import orm as notices_orm
from mavic.modules.portfolio.infrastructure import orm as portfolio_orm
from mavic.modules.voice.infrastructure import orm as voice_orm

__all__ = [
    "Base",
    "audit_orm",
    "costs_orm",
    "identity_orm",
    "negotiation_orm",
    "notices_orm",
    "portfolio_orm",
    "voice_orm",
]
