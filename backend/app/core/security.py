from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

TokenType = Literal["access", "refresh"]

# bcrypt ignore tout ce qui dépasse 72 octets et lève au-delà : on tronque
# explicitement, des deux côtés, pour accepter les mots de passe longs.
_BCRYPT_MAX_BYTES = 72


def _secret(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_secret(password), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_secret(plain), hashed.encode("ascii"))
    except ValueError:
        # Empreinte illisible en base : on refuse plutôt que de propager.
        return False


def create_token(subject: UUID, token_type: TokenType) -> str:
    now = datetime.now(UTC)
    if token_type == "access":
        expires = now + timedelta(minutes=settings.access_token_ttl_minutes)
    else:
        expires = now + timedelta(days=settings.refresh_token_ttl_days)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: TokenType) -> UUID | None:
    """Renvoie l'identifiant du sujet, ou None si le jeton est invalide."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None

    if payload.get("type") != expected_type:
        return None
    try:
        return UUID(payload["sub"])
    except (KeyError, ValueError):
        return None
