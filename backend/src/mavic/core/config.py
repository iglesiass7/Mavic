"""Configuración de la aplicación.

Problema que resuelve: en el proyecto original cada archivo leía variables con
`os.getenv` al importarse. Eso dispersa la configuración y obliga a tener variables
reales hasta para correr un test.

Acá hay UNA sola fuente de configuración, validada al arrancar: si falta algo
obligatorio o tiene un formato inválido, la app no levanta y dice qué falta.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variables de entorno de la app. El nombre en mayúsculas es la variable.

    Ejemplo: `database_url` se lee de la variable `DATABASE_URL`.
    """

    model_config = SettingsConfigDict(
        env_file=".env",  # en desarrollo se puede usar un archivo .env
        env_file_encoding="utf-8",
        extra="ignore",  # ignora variables que no son nuestras
    )

    app_env: Literal["local", "test", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Obligatoria: sin base de datos la app no tiene sentido.
    # SecretStr evita que la contraseña aparezca si alguien imprime la config.
    database_url: SecretStr = Field(
        description="URL de PostgreSQL, ej. postgresql+psycopg://user:pass@host:5432/db",
    )

    # Orígenes del navegador que pueden llamar a la API (el frontend).
    cors_allowed_origins: str = "http://localhost:3000"

    # Swagger (/docs) es útil en desarrollo; en producción se apaga.
    docs_enabled: bool = True

    # Zona horaria del negocio: “hoy” para calcular la antigüedad de una deuda
    # depende de dónde opera la empresa, no de dónde corre el servidor.
    business_timezone: str = "America/Argentina/Buenos_Aires"

    # Sesión de usuario (cookie).
    session_ttl_hours: int = Field(default=8, ge=1, le=72)
    # Secure=True: el navegador solo manda la cookie por HTTPS. En tu PC se usa
    # http://localhost, así que va en False; en un servidor real, siempre True.
    session_cookie_secure: bool = False

    # Freno a la fuerza bruta: intentos fallidos de login permitidos por email.
    login_max_failures: int = Field(default=5, ge=1)
    login_lockout_minutes: int = Field(default=15, ge=1)

    @property
    def cors_origins(self) -> list[str]:
        """Convierte "a,b,c" en ["a", "b", "c"], ignorando espacios y vacíos."""
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración, leída una sola vez y reutilizada.

    `lru_cache` hace que la segunda llamada devuelva el mismo objeto sin volver
    a leer el entorno.
    """
    # pydantic-settings completa database_url leyendo el entorno.
    return Settings()
