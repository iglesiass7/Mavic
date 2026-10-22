"""El "enchufe" para iniciar llamadas: qué necesita Mavic de un proveedor de voz.

El caso de uso (application/calls.py) depende de esta interfaz, no del SDK de
ElevenLabs. La implementación real está en infrastructure/elevenlabs_calls.py;
los tests usan una falsa que no llama a nadie.
"""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class OutboundCallResult:
    accepted: bool
    message: str
    conversation_id: str | None
    call_sid: str | None


class CallGatewayError(Exception):
    """El proveedor no respondió o rechazó el pedido (red, clave inválida, número mal)."""


class CallGateway(Protocol):
    def start_call(
        self, *, to_number: str, dynamic_variables: dict[str, Any], branch_id: str | None
    ) -> OutboundCallResult: ...
