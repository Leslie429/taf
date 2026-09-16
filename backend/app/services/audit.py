"""Consignation des actions qui engagent la plateforme.

La question qui gouverne ce module n'est pas quoi écrire, mais **dans quelle
transaction**.

Une action réussie et sa trace doivent vivre ou mourir ensemble : la trace part
donc dans la session de la requête, et le `commit` qui valide l'action valide
la ligne d'audit du même geste. Les séparer produirait tôt ou tard un versement
sans trace, ou une trace de versement qui n'a pas eu lieu.

Une action **refusée** n'a pas cette chance. Il n'y a pas de transaction métier
à laquelle s'accrocher, et celle de la requête sera défaite en même temps que
l'exception remonte. Écrire le refus dans cette session-là reviendrait à ne
rien écrire du tout — précisément pour les faits qu'un journal d'audit existe
pour retenir. Le refus part donc dans une session à lui, validée aussitôt.
"""

from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.models.enums import AuditAction, AuditOutcome
from app.models.user import User
from app.services.limitation import adresse_client


def _evenement(
    *,
    acteur: User | None,
    action: AuditAction,
    issue: AuditOutcome,
    cible_type: str,
    cible_id: UUID | None,
    requete: Request | None,
    details: dict[str, Any],
) -> AuditEvent:
    return AuditEvent(
        actor_id=acteur.id if acteur else None,
        # Recopié : la ligne doit rester lisible si le compte disparaît.
        actor_phone=acteur.phone if acteur else "",
        action=action,
        outcome=issue,
        target_type=cible_type,
        target_id=cible_id,
        ip=adresse_client(requete) if requete is not None else "",
        details=details,
    )


def consigner(
    db: Session,
    *,
    acteur: User | None,
    action: AuditAction,
    cible_type: str = "",
    cible_id: UUID | None = None,
    requete: Request | None = None,
    **details: Any,
) -> AuditEvent:
    """Consigne une action réussie, dans la transaction qui la porte.

    Sans `commit` : c'est celui de la route qui scellera les deux ensemble. Une
    action annulée ne doit pas laisser de trace prétendant le contraire.
    """
    evenement = _evenement(
        acteur=acteur,
        action=action,
        issue=AuditOutcome.ALLOWED,
        cible_type=cible_type,
        cible_id=cible_id,
        requete=requete,
        details=details,
    )
    db.add(evenement)
    db.flush()
    return evenement


def consigner_refus(
    journal: Session,
    *,
    acteur: User | None,
    action: AuditAction,
    motif: str,
    cible_type: str = "",
    cible_id: UUID | None = None,
    requete: Request | None = None,
    **details: Any,
) -> AuditEvent:
    """Consigne une tentative refusée, et la valide sur-le-champ.

    `journal` est une session distincte de celle de la requête — voir l'entête
    du module. Le `commit` est ici, et il est délibéré : l'exception qui suit
    ne doit pas pouvoir effacer ce constat.
    """
    evenement = _evenement(
        acteur=acteur,
        action=action,
        issue=AuditOutcome.DENIED,
        cible_type=cible_type,
        cible_id=cible_id,
        requete=requete,
        details={"motif": motif, **details},
    )
    journal.add(evenement)
    journal.commit()
    return evenement
