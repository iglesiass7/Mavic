"""Los "enchufes" para mandar avisos: qué necesita Mavic de un proveedor.

Los casos de uso dependen de estas interfaces, no de SMTP ni de Twilio. Las
implementaciones reales están en infrastructure/; los tests usan unas falsas
que anotan lo que se "mandó".

    send_notices ──> MessageSender ──┬── SmtpEmailSender   (email)
                                     └── TwilioWhatsAppSender (WhatsApp)
"""

from dataclasses import dataclass, field
from typing import Protocol

from mavic.modules.notices.domain.notices import Channel


@dataclass(frozen=True)
class OutgoingMessage:
    to: str  # email, o teléfono en formato internacional (+5491155550101)
    body: str
    subject: str = ""  # solo email
    # Solo WhatsApp con plantilla aprobada: el código y los valores {"1": ..., "2": ...}.
    template_sid: str | None = None
    template_variables: dict[str, str] = field(default_factory=dict)


class DeliveryError(Exception):
    """El proveedor rechazó el mensaje o no respondió. El texto dice por qué."""


class MessageSender(Protocol):
    def send(self, message: OutgoingMessage) -> str:
        """Manda el mensaje. Devuelve el id que le dio el proveedor (o "" si no da)."""
        ...

    def close(self) -> None:
        """Libera la conexión (el de email reusa una sola para toda la tanda)."""
        ...


class SenderFactory(Protocol):
    """Arma un remitente NUEVO por tanda (no se comparten conexiones entre pedidos)."""

    def sender_for(self, channel: Channel) -> MessageSender | None:
        """None: ese canal no está configurado en el .env."""
        ...

    def configured(self, channel: Channel) -> bool: ...
