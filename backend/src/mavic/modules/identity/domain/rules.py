"""Reglas de negocio de identidad: funciones puras, fáciles de testear."""

from mavic.core.errors import BusinessRuleViolationError, ConflictError

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128


def normalize_email(email: str) -> str:
    """El mismo email escrito distinto es el mismo usuario.

    >>> normalize_email("  Laura@FibraSur.com ")
    'laura@fibrasur.com'
    """
    return email.strip().lower()


def validate_new_password(password: str) -> None:
    """Política de contraseñas.

    Se exige LARGO y no combinaciones raras de símbolos: es lo que recomienda
    hoy el NIST (SP 800-63B). Una frase larga es más segura y más fácil de
    recordar que "P@ssw0rd!".
    """
    if len(password) < PASSWORD_MIN_LENGTH:
        raise BusinessRuleViolationError(
            f"La contraseña debe tener al menos {PASSWORD_MIN_LENGTH} caracteres.",
            code="PASSWORD_TOO_SHORT",
        )
    if len(password) > PASSWORD_MAX_LENGTH:
        raise BusinessRuleViolationError(
            f"La contraseña no puede superar {PASSWORD_MAX_LENGTH} caracteres.",
            code="PASSWORD_TOO_LONG",
        )
    if not password.strip():
        raise BusinessRuleViolationError(
            "La contraseña no puede ser solo espacios.", code="PASSWORD_BLANK"
        )


def ensure_company_keeps_an_admin(*, other_active_admins: int, loses_admin: bool) -> None:
    """Una empresa nunca puede quedarse sin un administrador activo.

    Si pasara, nadie podría dar de alta usuarios ni cambiar reglas: la empresa
    quedaría "huérfana".

    - other_active_admins: administradores activos SIN contar al usuario afectado.
    - loses_admin: True si el cambio hace que el usuario deje de ser admin activo
      (se lo desactiva o se le cambia el rol).
    """
    if loses_admin and other_active_admins == 0:
        # 409: el pedido es válido en sí, pero choca con el estado actual.
        raise ConflictError(
            "La empresa debe tener al menos un administrador activo.",
            code="LAST_ACTIVE_ADMIN",
        )
