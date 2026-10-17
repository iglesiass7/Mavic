import pytest
from pydantic import ValidationError

from mavic.core.config import Settings


def test_cors_origins_are_split_and_trimmed() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://u:p@h/db",
        cors_allowed_origins=" http://a.com, http://b.com ,,",
        _env_file=None,
    )
    assert settings.cors_origins == ["http://a.com", "http://b.com"]


def test_missing_database_url_fails_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    # Si falta una variable obligatoria, la app no debe arrancar "a medias".
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)


def test_database_password_is_hidden_when_printed() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://u:supersecreta@h/db",
        _env_file=None,
    )
    assert "supersecreta" not in repr(settings)
    assert "supersecreta" not in str(settings.database_url)


def test_empty_agent_credentials_mean_not_configured() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://u:p@h/db",
        agent_tools_token="",
        elevenlabs_webhook_secret="",
        _env_file=None,
    )
    assert settings.agent_tools_token is None
    assert settings.elevenlabs_webhook_secret is None


def test_a_short_agent_token_is_rejected_at_startup() -> None:
    with pytest.raises(ValidationError, match="al menos 32"):
        Settings(
            database_url="postgresql+psycopg://u:p@h/db",
            agent_tools_token="1234",
            _env_file=None,
        )
