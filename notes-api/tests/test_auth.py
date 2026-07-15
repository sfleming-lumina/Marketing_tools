from unittest.mock import patch

import pytest
from fastapi import HTTPException

from auth import require_google_user


@patch("auth._verify_token")
def test_valid_token_matching_hosted_domain_returns_user(mock_verify):
    mock_verify.return_value = {"email": "jane@luminasolar.com", "name": "Jane Doe", "hd": "luminasolar.com"}
    user = require_google_user(authorization="Bearer faketoken")
    assert user.email == "jane@luminasolar.com"
    assert user.name == "Jane Doe"


@patch("auth._verify_token")
def test_valid_token_wrong_domain_raises_403(mock_verify):
    mock_verify.return_value = {"email": "someone@gmail.com", "name": "Someone", "hd": "gmail.com"}
    with pytest.raises(HTTPException) as exc_info:
        require_google_user(authorization="Bearer faketoken")
    assert exc_info.value.status_code == 403


def test_missing_header_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        require_google_user(authorization=None)
    assert exc_info.value.status_code == 401


@patch("auth._verify_token")
def test_invalid_token_raises_401(mock_verify):
    mock_verify.side_effect = ValueError("Token expired")
    with pytest.raises(HTTPException) as exc_info:
        require_google_user(authorization="Bearer badtoken")
    assert exc_info.value.status_code == 401
