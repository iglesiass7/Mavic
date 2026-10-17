"""Verificación de identidad al inicio de la llamada.

Cómo lo hace el agente (según quien lo arma): el primer mensaje pregunta
"¿hablo con Ricardo Pérez?". Si la persona dice que sí, la identidad queda
verificada; si dice que no, NO se le da ningún dato de la deuda.

El agente manda a la herramienta el nombre por el que preguntó
(`nombre_consultado`) y lo que contestó la persona (`respuesta`). Acá se decide:

    nombre_consultado coincide con el deudor   Y   respuesta afirmativa   ->  verificada

Se pide que el nombre coincida para que un error del agente (preguntar por
otra persona) no deje pasar a quien no es el titular.
"""

import re
import unicodedata

# Respuestas que cuentan como "sí". Se comparan sin tildes ni mayúsculas.
_AFFIRMATIVE = frozenset(
    {
        "si",
        "s",
        "yes",
        "true",
        "1",
        "correcto",
        "afirmativo",
        "claro",
        "soy yo",
        "el habla",
        "ella habla",
    }
)


def normalize(text: str) -> str:
    """Minúsculas, sin tildes, sin signos y con un solo espacio entre palabras.

    >>> normalize("  ¡Sí, Ricardo  PÉREZ! ")
    'si ricardo perez'
    """
    without_accents = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    words = re.sub(r"[^a-z0-9]+", " ", without_accents.lower())
    return " ".join(words.split())


def is_affirmative(answer: str | bool) -> bool:
    """¿La persona dijo que sí?

    >>> [is_affirmative(a) for a in ["Sí", "si, soy yo", "true", True, "no", "sigo", ""]]
    [True, True, True, True, False, False, False]
    """
    if isinstance(answer, bool):
        return answer
    text = normalize(answer)
    return text in _AFFIRMATIVE or text.startswith("si ")


def name_matches(asked_name: str, debtor_name: str) -> bool:
    """Todas las palabras del nombre consultado están en el nombre del deudor.

    Así vale preguntar por "Ricardo" o por "Ricardo Pérez", pero no por "Ana".

    >>> name_matches("ricardo perez", "Ricardo Pérez")
    True
    >>> name_matches("Ana", "Ricardo Pérez")
    False
    """
    asked = set(normalize(asked_name).split())
    return bool(asked) and asked <= set(normalize(debtor_name).split())


def identity_verified(asked_name: str, answer: str | bool, debtor_name: str) -> bool:
    return name_matches(asked_name, debtor_name) and is_affirmative(answer)
