"""Compteur de tentatives, pour la limitation de débit.

Le compteur vit en base plutôt qu'en mémoire : l'API tourne sur plusieurs
machines, et un compteur par processus se contournerait en insistant jusqu'à
tomber sur l'autre.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, PrimaryKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RateLimitCounter(Base):
    __tablename__ = "rate_limit_counters"
    __table_args__ = (PrimaryKeyConstraint("bucket", "window_start", name="pk_rate_limit"),)

    # Ce qui est compté : « login:ip:1.2.3.4 », « login:phone:+229... ».
    bucket: Mapped[str] = mapped_column(String(160))
    # Début de la fenêtre. Deux fenêtres voisines sont deux lignes distinctes,
    # ce qui rend l'incrément atomique sans verrou ni lecture préalable.
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    count: Mapped[int] = mapped_column(BigInteger, default=0)
