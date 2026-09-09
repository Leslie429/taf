"""Limitation de débit sur les points d'entrée non authentifiés.

Le compteur vit en base. Un compteur en mémoire se contournerait en insistant :
l'API tourne sur plusieurs machines, et rien ne garantit que deux tentatives
consécutives tombent sur la même.

La fenêtre est fixe plutôt que glissante. Une fenêtre glissante serait plus
juste, mais elle exige de garder chaque tentative ; la fenêtre fixe tient dans
un seul entier par seau, et son défaut connu — jusqu'à deux fois la limite à
cheval sur deux fenêtres — reste sans conséquence face à une attaque par force
brute, qui se compte en milliers d'essais.
"""

from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.rate_limit import RateLimitCounter


def adresse_client(request: Request) -> str:
    """L'adresse de l'appelant, vue à travers le proxy de l'hébergeur.

    Fly réécrit lui-même `Fly-Client-IP` : l'en-tête n'est pas falsifiable
    depuis l'extérieur. `X-Forwarded-For` sert de repli pour les autres
    hébergeurs, dont le proxy écrase aussi la valeur reçue.
    """
    for entete in ("Fly-Client-IP", "X-Forwarded-For"):
        valeur = request.headers.get(entete, "")
        if valeur:
            return valeur.split(",")[0].strip()
    return request.client.host if request.client else "inconnue"


def _debut_de_fenetre(fenetre_secondes: int, maintenant: datetime | None = None) -> datetime:
    instant = maintenant or datetime.now(UTC)
    epoch = int(instant.timestamp())
    return datetime.fromtimestamp(epoch - epoch % fenetre_secondes, tz=UTC)


def compter(db: Session, seau: str, *, limite: int, fenetre_secondes: int) -> bool:
    """Compte une tentative et dit si elle reste sous la limite.

    L'incrément est atomique : PostgreSQL tranche sur la clé primaire, sans
    lecture préalable ni verrou. Deux requêtes simultanées ne peuvent donc pas
    lire le même compteur et l'écraser l'une après l'autre.
    """
    debut = _debut_de_fenetre(fenetre_secondes)
    stmt = (
        insert(RateLimitCounter)
        .values(bucket=seau, window_start=debut, count=1)
        .on_conflict_do_update(
            constraint="pk_rate_limit",
            set_={"count": RateLimitCounter.count + 1},
        )
        .returning(RateLimitCounter.count)
    )
    total = int(db.execute(stmt).scalar_one())
    # La tentative doit rester comptée même si la requête échoue ensuite :
    # sans ce commit, un refus annulerait le compteur qui l'a motivé.
    db.commit()
    return total <= limite


def purger(db: Session, *, avant: datetime | None = None) -> int:
    """Efface les fenêtres périmées. La table grossit à chaque tentative."""
    seuil = avant or datetime.now(UTC) - timedelta(days=1)
    resultat = db.execute(
        delete(RateLimitCounter).where(RateLimitCounter.window_start < seuil)
    )
    db.commit()
    return int(getattr(resultat, "rowcount", 0) or 0)
