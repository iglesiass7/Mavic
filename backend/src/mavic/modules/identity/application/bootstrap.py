"""Alta del primer usuario: el dueño de la plataforma.

Es un caso especial: no hay nadie logueado que lo pueda crear (el problema del
huevo y la gallina). Por eso NO se expone por la API: solo se ejecuta desde la
consola del servidor (ver `mavic.cli`), donde ya hace falta tener acceso a la
máquina.
"""

from sqlalchemy.orm import Session

from mavic.core.errors import ConflictError
from mavic.modules.identity.application.views import UserView
from mavic.modules.identity.domain.roles import UserRole
from mavic.modules.identity.domain.rules import normalize_email, validate_new_password
from mavic.modules.identity.infrastructure import passwords
from mavic.modules.identity.infrastructure.orm import UserModel
from mavic.modules.identity.infrastructure.repositories import UserRepository


def create_platform_admin(session: Session, *, name: str, email: str, password: str) -> UserView:
    validate_new_password(password)
    users = UserRepository(session)
    email = normalize_email(email)
    if users.email_exists(email):
        raise ConflictError("Ya existe un usuario con ese email.", code="EMAIL_ALREADY_REGISTERED")

    user = UserModel(
        company_id=None,
        name=name.strip(),
        email=email,
        password_hash=passwords.hash_password(password),
        role=UserRole.PLATFORM_ADMIN,
    )
    users.add(user)
    session.commit()
    return UserView.from_model(user)
