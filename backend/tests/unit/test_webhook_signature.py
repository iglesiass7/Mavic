from mavic.modules.voice.infrastructure.webhook_signature import (
    TOLERANCE_SECONDS,
    is_valid_signature,
    sign,
)

SECRET = "secreto"
NOW = 1_792_173_000
BODY = b'{"type": "post_call_transcription"}'


def test_a_signature_made_with_the_shared_secret_is_valid() -> None:
    assert is_valid_signature(sign(SECRET, NOW, BODY), BODY, SECRET, NOW)


def test_a_modified_body_is_rejected() -> None:
    header = sign(SECRET, NOW, BODY)
    assert not is_valid_signature(header, BODY.replace(b"post", b"pre"), SECRET, NOW)


def test_a_signature_with_another_secret_is_rejected() -> None:
    assert not is_valid_signature(sign("otro", NOW, BODY), BODY, SECRET, NOW)


def test_an_old_signature_cannot_be_replayed() -> None:
    old = NOW - TOLERANCE_SECONDS - 1
    assert not is_valid_signature(sign(SECRET, old, BODY), BODY, SECRET, NOW)


def test_missing_or_malformed_headers_are_rejected() -> None:
    for header in [None, "", "basura", "t=abc,v0=123", f"t={NOW}"]:
        assert not is_valid_signature(header, BODY, SECRET, NOW)
