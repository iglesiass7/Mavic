"""Verificación de la firma de los webhooks de ElevenLabs.

PROBLEMA: el endpoint del webhook es público (ElevenLabs tiene que poder
llamarlo). Sin verificación, cualquiera podría mandar una "transcripción" falsa.

SOLUCIÓN (la que define ElevenLabs): al crear el webhook, ElevenLabs genera un
secreto compartido. En cada envío manda el encabezado

    ElevenLabs-Signature: t=<timestamp>,v0=<firma>

donde firma = HMAC-SHA256(secreto, "<timestamp>.<cuerpo exacto del request>"),
en hexadecimal. Nosotros calculamos lo mismo con NUESTRA copia del secreto: si
coincide, el mensaje lo mandó quien conoce el secreto y nadie lo modificó.

El timestamp evita que alguien que capturó un envío viejo lo vuelva a mandar:
se rechazan firmas de más de 30 minutos (el margen que usa el ejemplo oficial).
"""

import hashlib
import hmac

TOLERANCE_SECONDS = 30 * 60


def sign(secret: str, timestamp: int, body: bytes) -> str:
    """El valor del encabezado para ese cuerpo. Lo usan los tests para simular a ElevenLabs."""
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"t={timestamp},v0={digest.hexdigest()}"


def is_valid_signature(header: str | None, body: bytes, secret: str, now: int) -> bool:
    if not header:
        return False
    parts = dict(part.split("=", 1) for part in header.split(",") if "=" in part)
    timestamp, signature = parts.get("t", ""), parts.get("v0", "")
    if not timestamp.isdigit() or not signature:
        return False
    if abs(now - int(timestamp)) > TOLERANCE_SECONDS:
        return False
    expected = sign(secret, int(timestamp), body)
    # compare_digest tarda lo mismo acierte o no: no da pistas a quien prueba firmas.
    return hmac.compare_digest(expected, f"t={timestamp},v0={signature}")
