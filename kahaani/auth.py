"""Who is signed in. Google sign-in happens in the browser through Supabase Auth; the site
sends the Supabase access token, and this module verifies it.

Supports Supabase's asymmetric signing keys (checked against the project's public JWKS)
and the older shared-secret tokens (SUPABASE_JWT_SECRET).

For local development without Supabase, KAHAANI_DEV_AUTH=1 accepts an `X-Dev-User` header
instead. It refuses to turn on when SUPABASE_URL is set, so it can't leak into production.
"""

import os
from dataclasses import dataclass
from functools import cache

import jwt
from fastapi import HTTPException, Request


@dataclass(frozen=True)
class User:
    id: str
    email: str | None
    name: str | None


def dev_auth_enabled() -> bool:
    return os.environ.get("KAHAANI_DEV_AUTH") == "1" and not os.environ.get("SUPABASE_URL")


@cache
def _jwks(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{url.rstrip('/')}/auth/v1/.well-known/jwks.json", cache_keys=True)


def verify_token(token: str) -> User:
    url = os.environ.get("SUPABASE_URL", "")
    secret = os.environ.get("SUPABASE_JWT_SECRET")
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") == "HS256":
            if not secret:
                raise jwt.InvalidTokenError("no shared secret configured")
            key = secret
        else:
            key = _jwks(url).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["HS256", "RS256", "ES256"],
            audience="authenticated",
            options={"require": ["sub", "exp"]},
        )
    except jwt.PyJWTError as e:
        raise HTTPException(401, "Please sign in again.") from e
    meta = claims.get("user_metadata") or {}
    return User(claims["sub"], claims.get("email"), meta.get("full_name") or meta.get("name"))


def current_user(request: Request) -> User:
    if dev_auth_enabled() and (dev := request.headers.get("x-dev-user")):
        return User(f"dev-{dev}", f"{dev}@example.com", dev.title())
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Please sign in with Google to continue.")
    return verify_token(auth.split(" ", 1)[1])
