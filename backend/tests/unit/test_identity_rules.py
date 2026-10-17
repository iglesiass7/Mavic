import pytest

from mavic.core.errors import BusinessRuleViolationError, ConflictError
from mavic.modules.identity.domain.rules import (
    ensure_company_keeps_an_admin,
    normalize_email,
    validate_new_password,
)


def test_normalize_email_trims_and_lowercases() -> None:
    assert normalize_email("  Laura@FibraSur.COM ") == "laura@fibrasur.com"


@pytest.mark.parametrize(
    ("password", "code"),
    [
        ("corta", "PASSWORD_TOO_SHORT"),
        ("x" * 129, "PASSWORD_TOO_LONG"),
        (" " * 12, "PASSWORD_BLANK"),
    ],
)
def test_invalid_passwords_are_rejected_with_a_specific_code(password: str, code: str) -> None:
    with pytest.raises(BusinessRuleViolationError) as error:
        validate_new_password(password)
    assert error.value.code == code


def test_long_passphrase_is_accepted() -> None:
    validate_new_password("mi perro se llama toby")


def test_cannot_remove_the_last_active_admin() -> None:
    with pytest.raises(ConflictError) as error:
        ensure_company_keeps_an_admin(other_active_admins=0, loses_admin=True)
    assert error.value.code == "LAST_ACTIVE_ADMIN"


def test_can_remove_an_admin_when_another_one_remains() -> None:
    ensure_company_keeps_an_admin(other_active_admins=1, loses_admin=True)


def test_changes_that_keep_the_admin_are_always_allowed() -> None:
    ensure_company_keeps_an_admin(other_active_admins=0, loses_admin=False)
