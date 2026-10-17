"""Hash de contraseñas con Argon2id.

Nunca se guarda la contraseña: se guarda un "hash", una huella de la que no se
puede volver atrás. Al iniciar sesión se calcula la huella de lo que escribió la
persona y se compara.

¿Por qué Argon2id y no SHA-256? SHA-256 es RÁPIDO a propósito: un atacante con
una copia de la base podría probar miles de millones de contraseñas por segundo.
Argon2id es LENTO y usa mucha memoria a propósito: probar contraseñas se vuelve
carísimo. Es el algoritmo que recomienda OWASP para contraseñas.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()  # parámetros por defecto de argon2-cffi (perfil recomendado)

# Hash de una contraseña que nadie conoce. Se usa cuando el email no existe:
# así el login tarda lo mismo exista o no el usuario, y nadie puede averiguar
# qué emails están registrados midiendo el tiempo de respuesta.
_DUMMY_HASH = _hasher.hash("contraseña-ficticia-para-igualar-tiempos")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def verify_against_dummy(password: str) -> None:
    """Gasta el mismo tiempo que una verificación real. El resultado no importa."""
    verify_password(_DUMMY_HASH, password)


def needs_rehash(password_hash: str) -> bool:
    """True si el hash se hizo con parámetros viejos (por ejemplo, tras subir el costo)."""
    return _hasher.check_needs_rehash(password_hash)
