# Imagen del backend.
# Se construye en dos etapas: la primera instala dependencias (con herramientas
# de compilación), la segunda solo copia lo necesario para correr. Resultado:
# una imagen más chica y con menos superficie de ataque.

# ---------- Etapa 1: construir el paquete y sus dependencias ----------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
# Se instala el paquete en un entorno virtual aislado (/opt/venv) que después
# se copia entero a la imagen final.
COPY pyproject.toml ./
COPY src ./src
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install .

# ---------- Etapa 2: imagen final ----------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Usuario sin privilegios: si alguien encontrara una falla en la app, no
# tendría permisos de root dentro del contenedor.
RUN useradd --create-home --uid 1000 app

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY docker/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

USER app
EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
