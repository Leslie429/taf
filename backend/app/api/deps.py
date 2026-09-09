from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_token, jeton_encore_valide
from app.db.session import get_db
from app.models.user import User
from app.services.momo import (
    FakeMoMoClient,
    MoMoClient,
    MtnMoMoClient,
    ProductRoutedClient,
)

bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton manquant.")

    claims = decode_token(credentials.credentials, "access")
    if claims is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton invalide ou expiré.")

    user = db.get(User, claims.subject)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Compte introuvable ou désactivé.")
    # La révocation ne coûte aucune requête : la ligne est déjà chargée.
    if not jeton_encore_valide(user.tokens_valid_from, claims.issued_at):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session close.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def _client_pour(product: str) -> MoMoClient:
    """Réel si le produit a sa clé d'abonnement, double sinon."""
    if settings.momo_key_for(product):
        return MtnMoMoClient()
    return FakeMoMoClient()


def get_momo_client() -> MoMoClient:
    """Le client à utiliser, décidé produit par produit.

    Sans aucune clé, tout tourne sur le double : le développement local ne
    dépend pas d'un compte MTN. Avec une seule des deux clés, seul le produit
    concerné part chez l'opérateur — l'autre continue sur le double plutôt que
    d'échouer en 401.
    """
    collection = _client_pour("collection")
    disbursement = _client_pour("disbursement")

    # Même sort pour les deux produits : le routage n'apporterait rien.
    if type(collection) is type(disbursement):
        return collection

    return ProductRoutedClient(collection=collection, disbursement=disbursement)


MoMo = Annotated[MoMoClient, Depends(get_momo_client)]
