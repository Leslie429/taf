from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    jeton_encore_valide,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenPair
from app.schemas.user import UserOut
from app.services import limitation

router = APIRouter(prefix="/auth", tags=["auth"])


def _tokens(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_token(user.id, "access"),
        refresh_token=create_token(user.id, "refresh"),
    )


def _refuser_si_trop_de_tentatives(
    db: DbSession, seaux: list[tuple[str, int]], fenetre: int
) -> None:
    """Compte la tentative sur chaque seau et refuse si l'un déborde.

    Tous les seaux sont comptés, même après un dépassement : s'arrêter au
    premier laisserait les autres compteurs en retard, et une attaque pourrait
    les remettre à zéro en alternant.
    """
    depasse = False
    for seau, limite in seaux:
        if not limitation.compter(db, seau, limite=limite, fenetre_secondes=fenetre):
            depasse = True
    if depasse:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Trop de tentatives. Réessayez plus tard.",
            headers={"Retry-After": str(fenetre)},
        )


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: DbSession, request: Request) -> TokenPair:
    _refuser_si_trop_de_tentatives(
        db,
        [
            (
                f"register:ip:{limitation.adresse_client(request)}",
                settings.register_max_par_adresse,
            )
        ],
        settings.register_fenetre_secondes,
    )

    exists = db.execute(select(User).where(User.phone == payload.phone)).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce numéro est déjà inscrit.")

    user = User(
        phone=payload.phone,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _tokens(user)


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, db: DbSession, request: Request) -> TokenPair:
    _refuser_si_trop_de_tentatives(
        db,
        [
            (f"login:ip:{limitation.adresse_client(request)}", settings.login_max_par_adresse),
            (f"login:phone:{payload.phone}", settings.login_max_par_numero),
        ],
        settings.login_fenetre_secondes,
    )

    user = db.execute(select(User).where(User.phone == payload.phone)).scalar_one_or_none()
    # Message identique dans les deux cas : on n'indique pas si le numéro existe.
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiants invalides.")
    return _tokens(user)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    claims = decode_token(payload.refresh_token, "refresh")
    if claims is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton de rafraîchissement invalide.")

    user = db.get(User, claims.subject)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Compte introuvable ou désactivé.")
    if not jeton_encore_valide(user.tokens_valid_from, claims.issued_at):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session close.")
    return _tokens(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: CurrentUser, db: DbSession) -> None:
    """Révoque tous les jetons de l'utilisateur, accès et rafraîchissement.

    On ne noircit pas une liste de jetons : on déplace la frontière de validité.
    Tout jeton émis avant cet instant est refusé, et la vérification ne coûte
    aucune requête de plus — la ligne de l'utilisateur est déjà chargée pour
    l'authentifier.

    La contrepartie est assumée : la déconnexion vaut pour toutes les sessions
    de l'utilisateur, pas seulement celle du terminal courant.
    """
    user.tokens_valid_from = datetime.now(UTC)
    db.commit()


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user
