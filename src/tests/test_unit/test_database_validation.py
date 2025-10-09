import re

import pytest

from database.validators.accounts import validate_email, validate_password_strength


def test_email_validator():
    """
    Tests email validation.

    Checks that the right error is raised if email is invalid.
    """
    invalid_email = "invalid_email"
    with pytest.raises(ValueError):
        validate_email(invalid_email)

    valid_email = "test_email@test.com"
    assert (
        validate_email(valid_email) == valid_email
    ), "Returned email does not match the input one."


def test_password_validator():
    """
    Tests password strength validation.

    Checks that the right error and message is raised if password is weak, and
    that the correct password is returned.
    """
    short_password = "pass"
    with pytest.raises(
        ValueError, match="Password must contain at least 8 characters."
    ):
        validate_password_strength(short_password)

    lowercase_password = "password1234!"
    with pytest.raises(
        ValueError, match="Password must contain at least one uppercase letter."
    ):
        validate_password_strength(lowercase_password)

    uppercase_password = "PASSWORD1234!"
    with pytest.raises(
        ValueError, match="Password must contain at least one lower letter."
    ):
        validate_password_strength(uppercase_password)

    no_digit_password = "Password!"
    with pytest.raises(ValueError, match="Password must contain at least one digit."):
        validate_password_strength(no_digit_password)

    no_special_char_password = "Password1234"
    expected_message = (
        "Password must contain at least one special character: @, $, !, %, *, ?, #, &."
    )
    escaped_regex = re.escape(expected_message)
    with pytest.raises(ValueError, match=escaped_regex):
        validate_password_strength(no_special_char_password)

    strong_password = "StrongPassword1234!"
    assert validate_password_strength(strong_password) == strong_password
