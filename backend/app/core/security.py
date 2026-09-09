from dataclasses import dataclass
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


@dataclass(frozen=True)
class TokenClaims:
    subject: UUID
    issued_at: datetime


def decode_token(token: str, expected_type: TokenType) -> TokenClaims | None:
    """Renvoie les revendications du jeton, ou None s'il est invalide.

    La date d'émission fait partie du contrat : c'est elle qui permet de
    révoquer d'un coup tous les jetons délivrés avant une déconnexion, sans
    tenir de liste noire ni interroger la base à chaque appel.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None

    if payload.get("type") != expected_type:
        return None
    try:
        return TokenClaims(
            subject=UUID(payload["sub"]),
            issued_at=datetime.fromtimestamp(int(payload["iat"]), tz=UTC),
        )
    except (KeyError, ValueError, TypeError, OSError):
        return None


def jeton_encore_valide(valides_depuis: datetime | None, emis_le: datetime) -> bool:
    """Le jeton a-t-il été émis après la dernière révocation du compte ?

    `None` signifie qu'aucune déconnexion n'a jamais eu lieu : tout jeton passe.

    `iat` ne porte que des secondes entières, là où la révocation garde ses
    microsecondes. L'arrondi est laissé du côté sûr : un jeton émis pendant la
    seconde de la déconnexion est refusé. Le prix est une reconnexion immédiate
    — dans la même seconde — qui échouerait ; l'inverse aurait laissé survivre
    le jeton même avec lequel on se déconnecte.
    """
    if valides_depuis is None:
        return True
    return emis_le >= valides_depuis
