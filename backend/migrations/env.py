"""Entorno de Alembic: cómo se conecta a la base y qué modelos compara.

`alembic revision --autogenerate` compara `Base.metadata` (las tablas que dicen
los modelos) contra la base real y propone una migración con las diferencias.
Siempre hay que REVISAR la migración generada antes de commitearla.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from mavic.core.config import get_settings

# Importar el registro de modelos carga todas las tablas en Base.metadata.
from mavic.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# La URL sale de la configuración de la app (variable DATABASE_URL).
# Se escapa "%" porque configparser lo interpreta como interpolación.
database_url = get_settings().database_url.get_secret_value()
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse (alembic upgrade head --sql)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica las migraciones conectándose a la base."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # detecta también cambios de tipo de columna
            # Una transacción por migración: si la 3 falla, la 1 y la 2 quedan aplicadas
            # y la 3 se deshace entera, sin dejar la base a medio migrar.
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
