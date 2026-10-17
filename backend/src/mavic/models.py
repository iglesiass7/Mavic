"""Registro de tablas.

Importar este módulo registra todas las tablas en `Base.metadata`. Lo usan
Alembic (para comparar modelos contra la base) y los tests (para crear el esquema).

Cada módulo de negocio con tablas se agrega acá.
"""

from mavic.core.db import Base
from mavic.modules.identity.infrastructure import orm as identity_orm

__all__ = ["Base", "identity_orm"]
