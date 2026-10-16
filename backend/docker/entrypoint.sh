#!/bin/sh
# Arranque del contenedor del backend.
# 1. Aplica las migraciones pendientes (deja la base en la última versión).
# 2. Levanta el servidor.
# `set -e` corta el script si un paso falla: si la migración falla, la app no
# arranca con un esquema incompleto.
set -e

echo "Aplicando migraciones..."
alembic upgrade head

echo "Iniciando servidor en el puerto 8000..."
# `exec` reemplaza al shell por uvicorn: así recibe las señales de apagado
# (Ctrl+C, docker stop) y se cierra prolijamente.
exec uvicorn mavic.main:create_app --factory --host 0.0.0.0 --port 8000 --proxy-headers
