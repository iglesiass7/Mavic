"""Configuración de la aplicación.

Problema que resuelve: en el proyecto original cada archivo leía variables con
`os.getenv` al importarse. Eso dispersa la configuración y obliga a tener variables
reales hasta para correr un test.

Acá hay UNA sola fuente de configuración, validada al arrancar: si falta algo
obligatorio o tiene un formato inválido, la app no levanta y dice qué falta.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_TOKEN_LENGTH = 32


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

    # Agente de voz (ElevenLabs). Si quedan vacíos, esa parte está apagada y
    # responde 503 diciendo qué variable falta.
    # - Token que el agente manda en cada herramienta (encabezado Authorization).
    agent_tools_token: SecretStr | None = None
    # - Secreto que genera ElevenLabs al crear el webhook de fin de llamada.
    elevenlabs_webhook_secret: SecretStr | None = None

    # Llamadas salientes (ADR-034): Mavic le pide a ElevenLabs que llame al
    # deudor por Twilio. Si falta alguno de los tres primeros, el botón
    # "Llamar" responde 503 diciendo qué falta.
    # - Clave de la API del workspace de ElevenLabs.
    elevenlabs_api_key: SecretStr | None = None
    # - Agente "Gestión de Deuda".
    elevenlabs_agent_id: str | None = None
    # - Número de teléfono (de Twilio) vinculado al agente en ElevenLabs.
    elevenlabs_phone_number_id: str | None = None
    # - Rama del agente a usar. Vacío: la que ElevenLabs tenga publicada.
    elevenlabs_branch_id: str | None = None

    @field_validator(
        "agent_tools_token",
        "elevenlabs_webhook_secret",
        "elevenlabs_api_key",
        "elevenlabs_agent_id",
        "elevenlabs_phone_number_id",
        "elevenlabs_branch_id",
        mode="before",
    )
    @classmethod
    def _empty_means_not_configured(cls, value: object) -> object:
        """`AGENT_TOOLS_TOKEN=` (vacío) es lo mismo que no definirla."""
        if isinstance(value, str) and value.strip() == "":
            return None
        return value.strip() if isinstance(value, str) else value

    @field_validator("agent_tools_token")
    @classmethod
    def _token_is_long_enough(cls, value: SecretStr | None) -> SecretStr | None:
        # Un token corto se adivina probando. 32 caracteres al azar no.
        if value is not None and len(value.get_secret_value()) < MIN_TOKEN_LENGTH:
            raise ValueError(
                f"AGENT_TOOLS_TOKEN tiene que tener al menos {MIN_TOKEN_LENGTH} caracteres. "
                'Generá uno con: python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )
        return value

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
