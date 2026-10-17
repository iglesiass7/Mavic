"""Casos de uso de autenticación: iniciar sesión, validar sesión, cerrarla y
cambiar la contraseña.

Cómo funciona la sesión (sesión del lado del servidor):

    login OK ──> se genera un token aleatorio de 256 bits
             ├─> al navegador: el token en una cookie HttpOnly
             └─> a la base:   solo el hash SHA-256 del token + vencimiento

    request ──> cookie ──> hash ──> ¿existe una sesión vigente con ese hash?
                                      sí ─> Actor(usuario, empresa, rol)
                                      no ─> 401

¿Por qué no un JWT, como el original? Un JWT es válido hasta que vence: no se
puede "cerrar" desde el servidor. Con la sesión en la base, logout, cambio de
contraseña o desactivar a un usuario cortan el acceso al instante.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from mavic.core.clock import Clock
from mavic.core.errors import (
    AuthenticationError,
    BusinessRuleViolationError,
    PermissionDeniedError,
)
from mavic.modules.identity.application.views import MeView
from mavic.modules.identity.domain.actor import Actor
from mavic.modules.identity.domain.rules import normalize_email, validate_new_password
from mavic.modules.identity.infrastructure import passwords
from mavic.modules.identity.infrastructure.orm import UserModel, UserSessionModel
from mavic.modules.identity.infrastructure.repositories import SessionRepository, UserRepository

INVALID_CREDENTIALS = "Email o contraseña incorrectos."


@dataclass(frozen=True)
class LoginResult:
    token: str  # va SOLO a la cookie; no se guarda en ningún lado
    me: MeView


@dataclass(frozen=True)
class AuthenticatedSession:
    """Resultado de validar la cookie de un request."""

    session_id: UUID
    actor: Actor


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _ensure_can_log_in(user: UserModel) -> None:
    if not user.is_active:
        raise PermissionDeniedError("Tu usuario está desactivado.", code="USER_INACTIVE")
    if user.company is not None and not user.company.is_active:
        raise PermissionDeniedError("Tu empresa está desactivada.", code="COMPANY_INACTIVE")


def login(
    session: Session, *, email: str, password: str, clock: Clock, ttl_hours: int
) -> LoginResult:
    users = UserRepository(session)
    user = users.get_by_email(normalize_email(email))

    if user is None:
        # Mismo tiempo y mismo mensaje exista o no el email: no se puede usar el
        # login para averiguar qué emails están registrados.
        passwords.verify_against_dummy(password)
        raise AuthenticationError(INVALID_CREDENTIALS, code="INVALID_CREDENTIALS")

    if not passwords.verify_password(user.password_hash, password):
        raise AuthenticationError(INVALID_CREDENTIALS, code="INVALID_CREDENTIALS")

    # Recién con la contraseña correcta se dice si el usuario está desactivado.
    _ensure_can_log_in(user)

    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)

    now = clock.now()
    token = secrets.token_urlsafe(32)  # 32 bytes = 256 bits de azar: imposible de adivinar
    SessionRepository(session).add(
        UserSessionModel(
            user_id=user.id,
            token_hash=hash_token(token),
            created_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
        )
    )
    user.last_login_at = now

    session.commit()
    return LoginResult(token=token, me=MeView.from_model(user))


def authenticate(session: Session, *, token: str | None, clock: Clock) -> AuthenticatedSession:
    """Valida la cookie de un request. Lo usa la API en CADA request protegido."""
    if not token:
        raise AuthenticationError()

    found = SessionRepository(session).get_valid_by_token_hash(hash_token(token), clock.now())
    if found is None:
        raise AuthenticationError("Tu sesión expiró o no es válida.", code="SESSION_INVALID")

    user_session, user = found
    # Si al usuario o a su empresa los desactivaron, la sesión deja de valer al instante.
    if not user.is_active or (user.company is not None and not user.company.is_active):
        raise AuthenticationError("Tu sesión expiró o no es válida.", code="SESSION_INVALID")

    return AuthenticatedSession(
        session_id=user_session.id,
        actor=Actor(user_id=user.id, company_id=user.company_id, role=user.role),
    )


def get_me(session: Session, *, actor: Actor) -> MeView:
    user = UserRepository(session).get(actor.user_id)
    if user is None:  # no debería pasar: la sesión se validó en este mismo request
        raise AuthenticationError()
    return MeView.from_model(user)


def logout(session: Session, *, token: str | None, clock: Clock) -> None:
    """Revoca la sesión. Si no había sesión, no hace nada (es idempotente)."""
    if not token:
        return
    user_session = SessionRepository(session).get_by_token_hash(hash_token(token))
    if user_session is not None and user_session.revoked_at is None:
        user_session.revoked_at = clock.now()
        session.commit()


def change_password(
    session: Session,
    *,
    actor: Actor,
    current_session_id: UUID,
    current_password: str,
    new_password: str,
    clock: Clock,
) -> None:
    user = UserRepository(session).get(actor.user_id)
    if user is None or not passwords.verify_password(user.password_hash, current_password):
        # 422 y no 401: la sesión es válida. Un 401 haría que el frontend crea
        # que la sesión venció y saque al usuario de la app.
        raise BusinessRuleViolationError(
            "La contraseña actual es incorrecta.", code="INVALID_CURRENT_PASSWORD"
        )
    validate_new_password(new_password)

    user.password_hash = passwords.hash_password(new_password)
    # Se cierran las OTRAS sesiones (otros navegadores, otra PC): si alguien
    # conocía la contraseña vieja y había entrado, queda afuera. Esta sigue abierta.
    SessionRepository(session).revoke_all_for_user(
        user.id, clock.now(), except_id=current_session_id
    )
    session.commit()
