"""Rapprochement entre le grand livre et le relevé de l'opérateur.

Une transaction peut diverger de deux façons, et elles n'ont pas la même
gravité.

**Restée en cours chez nous, tranchée chez l'opérateur.** Un callback perdu, un
réseau coupé au mauvais moment. C'est bénin et réparable : on applique le
verdict de l'opérateur, par le même chemin que le webhook.

**Comptée réussie chez nous, démentie chez l'opérateur.** Là, de l'argent
figure au grand livre sans exister chez l'opérateur. Rien n'est corrigé
automatiquement : la réparation est une contrepassation, et une contrepassation
est une décision, pas un effet de bord de tâche planifiée.

Aucun écart n'est corrigé en silence. Chaque constat laisse une ligne, résolu
ou non — une comptabilité qui se répare sans trace ne vaut pas mieux qu'une
comptabilité fausse.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import DivergenceKind, TransactionStatus, TransactionType
from app.models.ledger import Transaction
from app.models.reconciliation import Divergence, ReconciliationRun
from app.services import momo as momo_service
from app.services import tontine
from app.services.operateurs import Operateurs

# Une transaction qui vient de partir n'est pas un écart : l'opérateur a le
# droit de mettre quelques minutes à trancher.
DELAI_DE_GRACE = timedelta(minutes=15)
# Au-delà, un succès est considéré comme acquis : le rapprochement quotidien
# repasse sur une fenêtre courte, pas sur tout l'historique.
FENETRE_DES_SUCCES = timedelta(days=2)

PRODUIT_PAR_TYPE = {
    TransactionType.CONTRIBUTION: "collection",
    TransactionType.PAYOUT: "disbursement",
}


def _produit(transaction: Transaction) -> str | None:
    return PRODUIT_PAR_TYPE.get(transaction.type)


def _a_examiner(db: Session, maintenant: datetime) -> list[Transaction]:
    """Les transactions dont l'état mérite d'être confronté à l'opérateur."""
    # Le double n'a pas de relevé : confronter ses transactions au vrai
    # opérateur les ferait toutes passer pour des succès sans contrepartie.
    # Écrit en deux prédicats et non en `not_in((None, ...))` : un NULL dans la
    # liste d'un NOT IN annule le prédicat pour toutes les lignes, et le
    # rapprochement n'examinerait plus rien.
    chez_un_operateur = Transaction.provider.is_not(None) & (
        Transaction.provider != momo_service.PROVIDER_DOUBLE
    )
    en_cours = select(Transaction).where(
        Transaction.status.in_((TransactionStatus.PENDING, TransactionStatus.PROCESSING)),
        Transaction.updated_at < maintenant - DELAI_DE_GRACE,
        chez_un_operateur,
    )
    succes_recents = select(Transaction).where(
        Transaction.status == TransactionStatus.SUCCESS,
        Transaction.updated_at >= maintenant - FENETRE_DES_SUCCES,
        chez_un_operateur,
    )
    transactions = list(db.execute(en_cours).scalars().all())
    transactions += list(db.execute(succes_recents).scalars().all())
    return transactions


def _constater(
    db: Session,
    run: ReconciliationRun,
    transaction: Transaction,
    etat: momo_service.EtatOperateur,
    *,
    appliquer: bool,
) -> Divergence | None:
    """Compare un état local à celui de l'opérateur et journalise l'écart."""
    local = transaction.status
    tranche = etat.tranche

    if local in (TransactionStatus.PENDING, TransactionStatus.PROCESSING):
        if tranche is None:
            genre = (
                DivergenceKind.UNKNOWN_AT_OPERATOR
                if etat.inconnue
                else DivergenceKind.OPERATOR_SILENT
            )
            return Divergence(
                run_id=run.id,
                transaction_id=transaction.id,
                kind=genre,
                local_status=local,
                operator_status=etat.statut,
                note=(
                    "L'opérateur ignore cette référence."
                    if etat.inconnue
                    else "Opérateur injoignable ou sans verdict."
                ),
            )

        ecart = Divergence(
            run_id=run.id,
            transaction_id=transaction.id,
            kind=DivergenceKind.UNCONFIRMED,
            local_status=local,
            operator_status=etat.statut,
            note="Verdict de l'opérateur appliqué." if appliquer else "Verdict en attente.",
        )
        if appliquer:
            # Le même chemin que le webhook, jamais un second.
            tontine.appliquer_verdict(db, transaction, success=tranche)
            ecart.resolved = True
        return ecart

    if local == TransactionStatus.SUCCESS and tranche is False:
        return Divergence(
            run_id=run.id,
            transaction_id=transaction.id,
            kind=DivergenceKind.DISPUTED_SUCCESS,
            local_status=local,
            operator_status=etat.statut,
            note="Succès démenti par l'opérateur. Contrepassation à décider.",
        )

    if local == TransactionStatus.SUCCESS and etat.inconnue:
        return Divergence(
            run_id=run.id,
            transaction_id=transaction.id,
            kind=DivergenceKind.UNKNOWN_AT_OPERATOR,
            local_status=local,
            operator_status="",
            note="Succès sans trace chez l'opérateur. Contrepassation à décider.",
        )

    return None


def rapprocher(
    db: Session, reseau: Operateurs, *, appliquer: bool = True
) -> ReconciliationRun:
    """Confronte le grand livre au relevé des opérateurs et journalise les écarts."""
    maintenant = datetime.now(UTC)
    run = ReconciliationRun(started_at=maintenant)
    db.add(run)
    db.flush()

    transactions = _a_examiner(db, maintenant)
    for transaction in transactions:
        produit = _produit(transaction)
        if produit is None:
            # Une contrepassation n'a pas de contrepartie chez l'opérateur.
            continue
        # On repart de l'opérateur consigné : le numéro n'est plus disponible
        # ici, et c'est de toute façon celui qui a traité qu'il faut interroger.
        momo = reseau.pour_code(transaction.provider or "")
        if momo is None:
            continue
        etat = momo_service.etat(momo, reference=transaction.id, product=produit)
        ecart = _constater(db, run, transaction, etat, appliquer=appliquer)
        if ecart is not None:
            db.add(ecart)

    run.examined = len(transactions)
    run.finished_at = datetime.now(UTC)
    db.commit()
    db.refresh(run)
    return run


def dernier_rapprochement(db: Session) -> ReconciliationRun | None:
    return db.execute(
        select(ReconciliationRun).order_by(ReconciliationRun.started_at.desc()).limit(1)
    ).scalar_one_or_none()


def ecarts_non_resolus(db: Session, run_id: UUID) -> list[Divergence]:
    return list(
        db.execute(
            select(Divergence).where(
                Divergence.run_id == run_id, Divergence.resolved.is_(False)
            )
        ).scalars().all()
    )
