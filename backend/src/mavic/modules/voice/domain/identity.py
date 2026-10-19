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

import json
import re
import unicodedata
from typing import Any

# Si la respuesta COMPLETA es una de estas, cuenta como "sí".
_YES_EXACT = frozenset({"si", "s", "yes", "true", "1"})
# Palabras o frases que indican "sí" dentro de una frase más larga
# ("Buenos días. Sí, sí, soy Ricardo Pérez").
_YES_WORDS = frozenset({"si", "correcto", "afirmativo", "claro", "exacto", "efectivamente"})
_YES_PHRASES = ("soy yo", "el habla", "ella habla")
# Si aparece alguna de estas, NO se verifica aunque también haya un "sí".
# Ante la duda, se protege el dato: es preferible derivar a una persona que
# contarle la deuda a quien no es el titular.
_NO_WORDS = frozenset({"no", "equivocado", "equivocada", "equivocaste", "equivoco"})


def normalize(text: str) -> str:
    """Minúsculas, sin tildes, sin signos y con un solo espacio entre palabras.

    >>> normalize("  ¡Sí, Ricardo  PÉREZ! ")
    'si ricardo perez'
    """
    without_accents = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    words = re.sub(r"[^a-z0-9]+", " ", without_accents.lower())
    return " ".join(words.split())


def unwrap_answer(answer: str) -> str | bool:
    """Saca la respuesta real cuando ElevenLabs manda el historial en vez del texto.

    En la primera prueba con el agente, el parámetro `respuesta` llegó así:

        {"x-elevenlabs-history": true, "entries": [
            {"role": "agent", "message": "¿Hablo con Ricardo Pérez?"},
            {"role": "user", "message": "Sí, soy Ricardo Pérez."},
            {"role": "agent", "tool_requests": [{"tool_name": "...",
                "params_as_json": {"respuesta": "Sí, soy Ricardo Pérez."}}]}]}

    Si llega algo con esa forma, se usa el `respuesta` del último pedido. Si es
    JSON con otra forma, se devuelve vacío (no se verifica: no adivinamos).
    """
    text = answer.strip()
    if not text.startswith("{"):
        return answer
    try:
        data: Any = json.loads(text)
    except ValueError:
        return ""
    if not isinstance(data, dict):
        return ""
    # Los pedidos a herramientas pueden estar arriba de todo o dentro de las
    # entradas del historial. Se busca desde el final: vale el último.
    entries = data.get("entries")
    places = [data, *(entries if isinstance(entries, list) else [])]
    for place in reversed(places):
        requests = place.get("tool_requests") if isinstance(place, dict) else None
        for request in reversed(requests if isinstance(requests, list) else []):
            params = request.get("params_as_json") if isinstance(request, dict) else None
            if isinstance(params, dict) and isinstance(params.get("respuesta"), str | bool):
                value: str | bool = params["respuesta"]
                return value
    return ""


def is_affirmative(answer: str | bool) -> bool:
    """¿La persona dijo que sí?

    >>> [is_affirmative(a) for a in ["Sí", "si, soy yo", "true", True, "no", "sigo", ""]]
    [True, True, True, True, False, False, False]
    >>> is_affirmative("Buenos días. Sí, sí, soy Ricardo Pérez.")
    True
    >>> is_affirmative("No, no soy yo, sí lo conozco")
    False
    """
    if isinstance(answer, bool):
        return answer
    unwrapped = unwrap_answer(answer)
    if isinstance(unwrapped, bool):
        return unwrapped
    text = normalize(unwrapped)
    if text in _YES_EXACT:
        return True
    words = set(text.split())
    if not words or words & _NO_WORDS:
        return False
    padded = f" {text} "
    return bool(words & _YES_WORDS) or any(f" {phrase} " in padded for phrase in _YES_PHRASES)


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
