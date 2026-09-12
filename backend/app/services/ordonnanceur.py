"""Ce qui tourne tout seul, dans le conteneur de l'API.

Deux gestes périodiques, et il importe de ne pas les confondre.

**Le rapprochement** confronte le grand livre au relevé des opérateurs réels.
C'est le besoin de production : MTN ne rappelle pas toujours — sur Render, pas
du tout — et sans cette passe un versement resterait « en cours » indéfiniment,
alors que l'opérateur l'a tranché depuis longtemps. Le service est écrit et
testé par ailleurs ; on ne fait ici que l'appeler à intervalle régulier.

**Le verdict du double** est autre chose, et n'est surtout pas du
rapprochement. Le client simulé accepte les demandes mais n'émet aucun
callback : une cotisation de démonstration tourne donc sur l'écran d'attente
sans fin. Ce que [`scripts/confirmer_paiements.py`](../../scripts/confirmer_paiements.py)
fait depuis un poste, cette tâche le fait depuis le conteneur — pour que la
démonstration se termine sans que personne ait à lancer quoi que ce soit.

**La frontière entre les deux est la règle à ne pas franchir.** Le
rapprochement n'invente jamais un verdict : il applique celui de l'opérateur,
et refuse d'examiner les transactions du double, faute de relevé à leur
opposer. Le verdict du double, symétriquement, ne touche jamais une transaction
partie chez un opérateur réel. Les confondre ferait passer pour encaissé de
l'argent qui n'a jamais bougé — c'est-à-dire, au grand livre, pour une fraude.

Une seule instance exécute ces boucles : l'offre gratuite de Render n'en lance
qu'une, et uvicorn y tourne avec `--workers 1`. Deux instances feraient deux
passes concurrentes, sans dommage — les deux chemins sont idempotents — mais
sans intérêt non plus.
"""

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.enums import TransactionStatus
from app.models.ledger import Transaction
from app.services import momo as momo_service
from app.services import rapprochement, tontine
from app.services.operateurs import Operateurs

logger = logging.getLogger(__name__)


def trancher_les_transactions_du_double(db: Session, *, succes: bool = True) -> int:
    """Rend le verdict que le double n'émet jamais lui-même.

    Le filtre sur le fournisseur n'est pas une précaution de confort : c'est
    lui qui garantit qu'aucune transaction partie chez un opérateur réel ne
    sera jamais tranchée sans son avis.

    Seules les transactions `processing` sont concernées — une `pending` n'a
    pas atteint l'opérateur, il n'y a pas de verdict à rendre pour elle.
    """
    en_cours = list(
        db.execute(
            select(Transaction).where(
                Transaction.status == TransactionStatus.PROCESSING,
                Transaction.provider == momo_service.PROVIDER_DOUBLE,
            )
        ).scalars().all()
    )
    for transaction in en_cours:
        # Le même chemin que le webhook et le rapprochement, jamais un second.
        tontine.appliquer_verdict(db, transaction, success=succes)
    if en_cours:
        db.commit()
    return len(en_cours)


def passe_du_double() -> None:
    with SessionLocal() as db:
        tranchees = trancher_les_transactions_du_double(db)
    if tranchees:
        logger.info("Double : %d transaction(s) tranchée(s).", tranchees)


def passe_de_rapprochement(reseau: Operateurs) -> None:
    with SessionLocal() as db:
        run = rapprochement.rapprocher(db, reseau)
        ecarts = len(rapprochement.ecarts_non_resolus(db, run.id))
    if run.examined:
        logger.info(
            "Rapprochement : %d transaction(s) examinée(s), %d écart(s) non résolu(s).",
            run.examined,
            ecarts,
        )


async def _boucler(nom: str, intervalle: float, geste: Callable[[], None]) -> None:
    """Répète un geste, indéfiniment, sans jamais mourir de ses erreurs.

    La première passe attend un intervalle : au démarrage, la base vient
    peut-être d'être migrée, et rien ne presse.
    """
    while True:
        await asyncio.sleep(intervalle)
        try:
            # Le geste est synchrone — SQLAlchemy l'est ici — et le confier à
            # un fil évite qu'une passe un peu longue ne gèle les requêtes en
            # cours de traitement.
            await asyncio.to_thread(geste)
        except Exception:
            # Une passe en échec ne doit pas emporter l'ordonnanceur : la
            # suivante retentera. Sans ce filet, une base momentanément
            # injoignable arrêterait les confirmations pour de bon.
            logger.exception("Passe « %s » en échec.", nom)


def demarrer(nom: str, intervalle: float, geste: Callable[[], None]) -> asyncio.Task[None] | None:
    """Lance une boucle, ou rien du tout si l'intervalle est nul.

    Un intervalle à zéro est le réglage des tests et de tout contexte où
    l'application ne doit rien entreprendre d'elle-même.
    """
    if intervalle <= 0:
        return None
    logger.info("Ordonnanceur « %s » : toutes les %g s.", nom, intervalle)
    return asyncio.create_task(_boucler(nom, intervalle, geste), name=f"ordonnanceur:{nom}")


async def arreter(taches: list[asyncio.Task[None] | None]) -> None:
    """Arrête les boucles et attend qu'elles aient rendu la main."""
    vivantes = [tache for tache in taches if tache is not None]
    for tache in vivantes:
        tache.cancel()
    for tache in vivantes:
        with suppress(asyncio.CancelledError):
            await tache
