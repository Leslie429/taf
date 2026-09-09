"""Consultation du rapprochement, réservée à l'équipe de la plateforme."""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession, Reseau
from app.models.reconciliation import ReconciliationRun
from app.models.user import User
from app.schemas.reconciliation import ReconciliationOut
from app.services import rapprochement

router = APIRouter(prefix="/admin", tags=["administration"])


def _exiger_equipe(user: User) -> None:
    # `Membership.is_admin` n'administre qu'une tontine ; le rapprochement
    # expose l'état de toutes.
    if not user.is_staff:
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
def lancer(user: CurrentUser, db: DbSession, reseau: Reseau) -> ReconciliationRun:
    """Déclenche un rapprochement à la demande.

    La tâche quotidienne fait la même chose ; cette route sert à la provoquer
    sans attendre, pour vérifier un écart signalé.
    """
    _exiger_equipe(user)
    return rapprochement.rapprocher(db, reseau)
