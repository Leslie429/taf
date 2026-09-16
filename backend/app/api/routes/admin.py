"""Consultation du rapprochement et du journal d'audit.

Réservé à l'équipe de la plateforme : `Membership.is_admin` n'administre qu'une
tontine, ces écrans-là portent sur toutes.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuditSession, CurrentUser, DbSession, Reseau
from app.models.audit import AuditEvent
from app.models.enums import AuditAction, AuditOutcome
from app.models.reconciliation import ReconciliationRun
from app.models.user import User
from app.schemas.audit import AuditEventOut
from app.schemas.reconciliation import ReconciliationOut
from app.services import audit, rapprochement

router = APIRouter(prefix="/admin", tags=["administration"])


def _exiger_equipe(
    user: User,
    *,
    journal: Session | None = None,
    action: AuditAction | None = None,
    requete: Request | None = None,
) -> None:
    """Exige l'appartenance à l'équipe de la plateforme.

    Le refus n'est consigné que pour les routes qui agissent. Journaliser les
    refus de lecture noierait les autres dans le bruit.
    """
    if user.is_staff:
        return
    if journal is not None and action is not None:
        audit.consigner_refus(
            journal,
            acteur=user,
            action=action,
            motif="Réservé à l'équipe.",
            requete=requete,
        )
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé à l'équipe.")


@router.get("/reconciliation", response_model=ReconciliationOut)
def dernier(user: CurrentUser, db: DbSession) -> ReconciliationRun:
    """Le dernier rapprochement et ses écarts."""
    _exiger_equipe(user)
    run = rapprochement.dernier_rapprochement(db)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aucun rapprochement encore effectué.")
    return run


@router.post("/reconciliation", response_model=ReconciliationOut, status_code=201)
def lancer(
    user: CurrentUser,
    db: DbSession,
    reseau: Reseau,
    request: Request,
    journal: AuditSession,
) -> ReconciliationRun:
    """Déclenche un rapprochement à la demande.

    L'ordonnanceur fait la même chose toutes les dix minutes ; cette route sert
    à la provoquer sans attendre, pour vérifier un écart signalé. Elle applique
    des verdicts : elle se journalise.
    """
    _exiger_equipe(
        user, journal=journal, action=AuditAction.RECONCILIATION_LAUNCHED, requete=request
    )
    run = rapprochement.rapprocher(db, reseau)
    audit.consigner(
        db,
        acteur=user,
        action=AuditAction.RECONCILIATION_LAUNCHED,
        cible_type="reconciliation_run",
        cible_id=run.id,
        requete=request,
        examined=run.examined,
    )
    db.commit()
    return run


@router.get("/audit", response_model=list[AuditEventOut])
def journal_daudit(
    user: CurrentUser,
    db: DbSession,
    action: AuditAction | None = None,
    outcome: AuditOutcome | None = None,
    actor_id: UUID | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[AuditEvent]:
    """Le journal, du plus récent au plus ancien.

    Il se lit, il ne s'écrit pas : aucune route ne permet d'y ajouter, d'y
    modifier ou d'en retirer une ligne. Ce qui y figure y est arrivé par
    l'action qu'il consigne, et rien d'autre.
    """
    _exiger_equipe(user)

    stmt = select(AuditEvent).order_by(AuditEvent.occurred_at.desc())
    if action is not None:
        stmt = stmt.where(AuditEvent.action == action)
    if outcome is not None:
        stmt = stmt.where(AuditEvent.outcome == outcome)
    if actor_id is not None:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)

    return list(db.execute(stmt.limit(limit).offset(offset)).scalars().all())
