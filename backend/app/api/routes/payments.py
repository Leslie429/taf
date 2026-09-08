from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession, MoMo
from app.models.enums import MembershipStatus, TransactionType
from app.models.ledger import Transaction, WebhookEvent
from app.models.tontine import Contribution, Cycle, Membership
from app.schemas.payment import MoMoCallback, TransactionOut
from app.services import momo as momo_service
from app.services import tontine

router = APIRouter(tags=["paiements"])


@router.post("/contributions/{contribution_id}/pay", response_model=TransactionOut)
def pay_contribution(
    contribution_id: UUID, db: DbSession, user: CurrentUser, momo: MoMo
) -> Transaction:
    """Déclenche la demande de paiement Mobile Money pour sa propre cotisation."""
    contribution = db.get(Contribution, contribution_id)
    if contribution is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cotisation introuvable.")

    membership = db.get(Membership, contribution.membership_id)
    if membership is None or membership.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cette cotisation n'est pas la vôtre.")
    if membership.status != MembershipStatus.ACTIVE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Adhésion inactive.")

    try:
        transaction = tontine.initiate_contribution(
            db, contribution=contribution, payer=user, momo=momo
        )
    except tontine.TontineError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    db.commit()
    db.refresh(transaction)
    return transaction


@router.post("/cycles/{cycle_id}/payout", response_model=TransactionOut)
def payout(cycle_id: UUID, db: DbSession, user: CurrentUser, momo: MoMo) -> Transaction:
    """Verse la cagnotte au bénéficiaire. Réservé à l'administrateur du groupe."""
    cycle = db.get(Cycle, cycle_id)
    if cycle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cycle introuvable.")

    caller = db.execute(
        select(Membership).where(
            Membership.group_id == cycle.group_id,
            Membership.user_id == user.id,
        )
    ).scalar_one_or_none()
    if caller is None or not caller.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Action réservée à l'administrateur.")

    try:
        transaction = tontine.pay_out_cycle(db, cycle, momo)
    except tontine.TontineError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    db.commit()
    db.refresh(transaction)
    return transaction


@router.post("/webhooks/momo", status_code=status.HTTP_202_ACCEPTED)
async def momo_webhook(request: Request, db: DbSession) -> dict[str, str]:
    """Reçoit le verdict de l'opérateur.

    Trois protections : la signature HMAC, l'unicité de l'événement en base pour
    absorber les rejeux, et une réponse 202 systématique pour éviter que
    l'opérateur ne réessaie indéfiniment sur une erreur qui nous appartient.
    """
    raw = await request.body()
    signature = request.headers.get("X-Callback-Signature", "")

    if not momo_service.verify_signature(raw, signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Signature invalide.")

    payload = MoMoCallback.model_validate_json(raw)

    # L'identifiant renvoyé est celui qu'on a nous-même fourni en X-Reference-Id.
    # S'il n'est pas un UUID, le callback ne nous concerne pas.
    try:
        transaction_id = UUID(payload.externalId)
    except ValueError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Identifiant externe inexploitable."
        ) from None

    event = WebhookEvent(
        provider=tontine.PROVIDER,
        event_id=payload.externalId,
        signature_valid=True,
        payload=payload.model_dump(),
    )
    db.add(event)
    try:
        db.flush()
    except IntegrityError:
        # Déjà reçu : on acquitte sans rejouer l'effet métier.
        db.rollback()
        return {"status": "duplicate"}

    transaction = db.execute(
        select(Transaction).where(Transaction.id == transaction_id)
    ).scalar_one_or_none()
    if transaction is None:
        event.last_error = "Transaction inconnue"
        db.commit()
        return {"status": "unknown_transaction"}

    success = payload.status.upper() in {"SUCCESSFUL", "SUCCESS"}

    if transaction.type == TransactionType.CONTRIBUTION:
        tontine.confirm_contribution(db, transaction, success=success)
    elif transaction.type == TransactionType.PAYOUT:
        cycle = db.execute(
            select(Cycle).where(Cycle.id == UUID(transaction.idempotency_key.split(":")[1]))
        ).scalar_one_or_none()
        if cycle is not None:
            tontine.confirm_payout(db, transaction, cycle, success=success)

    event.processed = True
    db.commit()
    return {"status": "processed"}
