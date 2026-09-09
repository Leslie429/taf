from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    # Le numéro de téléphone est l'identifiant métier : c'est aussi la clé Mobile Money.
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Membre de l'équipe de la plateforme, à ne pas confondre avec
    # `Membership.is_admin`, qui n'administre qu'une tontine.
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False)

    # Tout jeton émis avant cette date est refusé. Une déconnexion la fixe à
    # l'instant présent, ce qui révoque d'un coup l'accès et le rafraîchissement
    # — sans liste noire, et sans une requête de plus par appel authentifié :
    # la ligne de l'utilisateur est de toute façon déjà chargée.
    tokens_valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
