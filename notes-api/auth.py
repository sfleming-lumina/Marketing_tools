import os
from typing import Optional

from fastapi import Header, HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
ALLOWED_HOSTED_DOMAIN = os.environ.get("ALLOWED_HOSTED_DOMAIN", "luminasolar.com")


class VerifiedUser:
    def __init__(self, email: str, name: str) -> None:
        self.email = email
        self.name = name


def _verify_token(token: str) -> dict:
    return id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_OAUTH_CLIENT_ID)


def require_google_user(authorization: Optional[str] = Header(default=None)) -> VerifiedUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ")
    try:
        idinfo = _verify_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc
    email = idinfo.get("email", "")
    if idinfo.get("hd") != ALLOWED_HOSTED_DOMAIN and not email.endswith(f"@{ALLOWED_HOSTED_DOMAIN}"):
        raise HTTPException(status_code=403, detail="Account is not part of the allowed organization")
    return VerifiedUser(email=email, name=idinfo.get("name", email))
