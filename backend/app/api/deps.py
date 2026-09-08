from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User
from app.services.momo import FakeMoMoClient, MoMoClient, MtnMoMoClient

bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton manquant.")

    user_id = decode_token(credentials.credentials, "access")
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton invalide ou expiré.")

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Compte introuvable ou désactivé.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_momo_client() -> MoMoClient:
    """Sans clé sandbox configurée, on tourne sur le double : le développement
    local reste possible sans compte MTN."""
    if settings.momo_subscription_key:
        return MtnMoMoClient()
    return FakeMoMoClient()


MoMo = Annotated[MoMoClient, Depends(get_momo_client)]
