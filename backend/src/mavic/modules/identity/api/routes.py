"""Endpoints de identidad.

Hay dos routers:
- `public_router`: lo único que se puede llamar SIN sesión (login y logout).
- `router`:        todo lo demás. Se registra con la sesión como requisito
                   (ver `mavic.api.router`), así que acá no hace falta repetirlo.

Los endpoints son finos: traducen HTTP <-> caso de uso, nada más. Las reglas y
los permisos viven en la capa application.
"""

from uuid import UUID

from fastapi import APIRouter, Request, Response, status

from mavic.api.deps import (
    ActorDep,
    ClockDep,
    CurrentSessionDep,
    LoginThrottleDep,
    SessionDep,
    SettingsDep,
)
from mavic.core.errors import AuthenticationError
from mavic.modules.identity.api.cookies import (
    SESSION_COOKIE,
    clear_session_cookie,
    set_session_cookie,
)
from mavic.modules.identity.api.schemas import (
    CompanyCreateIn,
    CompanyOut,
    CompanyWithAdminOut,
    LoginIn,
    MeOut,
    PasswordChangeIn,
    UserCreateIn,
    UserOut,
    UserUpdateIn,
)
from mavic.modules.identity.application import auth, companies, users
from mavic.modules.identity.domain.roles import UserRole
from mavic.modules.identity.domain.rules import normalize_email

public_router = APIRouter(tags=["auth"])
router = APIRouter()

# ---------------------------------------------------------------- auth


@public_router.post("/auth/login", response_model=MeOut)
def login(
    payload: LoginIn,
    response: Response,
    session: SessionDep,
    clock: ClockDep,
    settings: SettingsDep,
    throttle: LoginThrottleDep,
) -> MeOut:
    key = normalize_email(payload.email)
    throttle.check(key)
    try:
        result = auth.login(
            session,
            email=payload.email,
            password=payload.password,
            clock=clock,
            ttl_hours=settings.session_ttl_hours,
        )
    except AuthenticationError:
        throttle.record_failure(key)
        raise
    throttle.reset(key)
    set_session_cookie(response, result.token, settings)
    return MeOut.from_view(result.me)


@public_router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    session: SessionDep,
    clock: ClockDep,
    settings: SettingsDep,
) -> None:
    auth.logout(session, token=request.cookies.get(SESSION_COOKIE), clock=clock)
    clear_session_cookie(response, settings)


@router.get("/auth/me", response_model=MeOut, tags=["auth"])
def me(session: SessionDep, actor: ActorDep) -> MeOut:
    return MeOut.from_view(auth.get_me(session, actor=actor))


@router.put("/auth/password", status_code=status.HTTP_204_NO_CONTENT, tags=["auth"])
def change_password(
    payload: PasswordChangeIn, session: SessionDep, current: CurrentSessionDep, clock: ClockDep
) -> None:
    auth.change_password(
        session,
        actor=current.actor,
        current_session_id=current.session_id,
        current_password=payload.current_password,
        new_password=payload.new_password,
        clock=clock,
    )


# ---------------------------------------------------------------- usuarios de la empresa


@router.get("/users", response_model=list[UserOut], tags=["users"])
def list_users(session: SessionDep, actor: ActorDep) -> list[UserOut]:
    return [UserOut.from_view(user) for user in users.list_users(session, actor=actor)]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED, tags=["users"])
def create_user(payload: UserCreateIn, session: SessionDep, actor: ActorDep) -> UserOut:
    view = users.create_user(
        session,
        actor=actor,
        name=payload.name,
        email=payload.email,
        password=payload.password,
        role=UserRole(payload.role),
    )
    return UserOut.from_view(view)


@router.patch("/users/{user_id}", response_model=UserOut, tags=["users"])
def update_user(
    user_id: UUID, payload: UserUpdateIn, session: SessionDep, actor: ActorDep, clock: ClockDep
) -> UserOut:
    changes = users.UserChanges(
        name=payload.name,
        role=UserRole(payload.role) if payload.role is not None else None,
        is_active=payload.is_active,
    )
    view = users.update_user(session, actor=actor, user_id=user_id, changes=changes, clock=clock)
    return UserOut.from_view(view)


# ---------------------------------------------------------------- plataforma


@router.get("/platform/companies", response_model=list[CompanyOut], tags=["platform"])
def list_companies(session: SessionDep, actor: ActorDep) -> list[CompanyOut]:
    return [CompanyOut.from_view(c) for c in companies.list_companies(session, actor=actor)]


@router.post(
    "/platform/companies",
    response_model=CompanyWithAdminOut,
    status_code=status.HTTP_201_CREATED,
    tags=["platform"],
)
def create_company(
    payload: CompanyCreateIn, session: SessionDep, actor: ActorDep
) -> CompanyWithAdminOut:
    result = companies.create_company_with_admin(
        session,
        actor=actor,
        name=payload.name,
        admin=companies.NewAdmin(
            name=payload.admin.name, email=payload.admin.email, password=payload.admin.password
        ),
    )
    return CompanyWithAdminOut(
        company=CompanyOut.from_view(result.company), admin=UserOut.from_view(result.admin)
    )
