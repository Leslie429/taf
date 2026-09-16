"""Les relances des cotisations en retard.

Une tontine ne tient que si chacun paie à l'échéance. Personne n'est là pour
surveiller les retards, et un membre qui oublie bloque le tour de quelqu'un
d'autre — c'est cette personne-là, au bout de la chaîne, que la relance sert.

**Deux gestes, séparés à dessein.**

`reperer` décide quoi dire : il lit les cotisations en retard et inscrit une
notification en attente. Il ne parle à personne.

`acheminer` décide quand partir : il prend les notifications en attente et les
remet au canal. Un envoi qui échoue est retenté au tour suivant, sans qu'on ait
à recalculer quoi que ce soit.

**Ce qui empêche le harcèlement n'est pas la prudence du code.** C'est une
contrainte d'unicité : la clé porte la cotisation et la journée, si bien qu'une
deuxième passe le même jour se heurte à la base plutôt qu'à une condition qu'on
aurait pu oublier d'écrire.
"""

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import (
    ContributionStatus,
    CycleStatus,
    NotificationKind,
    NotificationStatus,
)
from app.models.notification import Notification
from app.models.tontine import Contribution, Cycle, Membership, TontineGroup
from app.models.user import User
from app.services.sms import SmsClient, SmsError

# Au-delà, la relance quotidienne ne dit plus rien que les précédentes n'aient
# dit : le retard est installé, c'est une conversation qu'il faut, pas un SMS.
RELANCES_MAX_PAR_COTISATION = 5


def _texte(groupe: TontineGroup, cycle: Cycle, contribution: Contribution) -> str:
    """Le message, court et sans reproche.

    Il dit le montant, la tontine et l'échéance — de quoi agir — et rien
    d'autre. Un SMS ne se relit pas, et il peut être lu par-dessus l'épaule.
    """
    retard = (date.today() - cycle.due_date).days
    jours = "1 jour" if retard == 1 else f"{retard} jours"
    return (
        f"Tontine {groupe.name} : votre cotisation de "
        f"{contribution.amount_minor} F pour le tour {cycle.index + 1} "
        f"est en retard de {jours}. Réglez-la depuis l'application."
    )


def _cle(contribution: Contribution, jour: date) -> str:
    return f"relance:contribution:{contribution.id}:{jour.isoformat()}"


def reperer(db: Session, *, aujourdhui: date | None = None) -> int:
    """Inscrit une relance pour chaque cotisation en retard. Renvoie le compte.

    Rien n'est envoyé ici. La notification naît `pending`, et c'est
    `acheminer` qui la remettra au canal.
    """
    jour = aujourdhui or date.today()

    en_retard = db.execute(
        select(Contribution, Cycle, TontineGroup, User)
        .join(Cycle, Cycle.id == Contribution.cycle_id)
        .join(TontineGroup, TontineGroup.id == Cycle.group_id)
        .join(Membership, Membership.id == Contribution.membership_id)
        .join(User, User.id == Membership.user_id)
        .where(
            Contribution.status == ContributionStatus.DUE,
            Cycle.due_date < jour,
            Cycle.status.in_((CycleStatus.PENDING, CycleStatus.LATE)),
        )
    ).all()

    inscrites = 0
    for contribution, cycle, groupe, membre in en_retard:
        # Le tour est en retard : que la relance parte ou non, l'état doit le
        # dire. C'est ce que lit la barre de tours du front.
        cycle.status = CycleStatus.LATE

        deja = db.execute(
            select(Notification).where(Notification.contribution_id == contribution.id)
        ).scalars().all()
        if len(deja) >= RELANCES_MAX_PAR_COTISATION:
            continue

        notification = Notification(
            user_id=membre.id,
            kind=NotificationKind.CONTRIBUTION_LATE,
            dedupe_key=_cle(contribution, jour),
            destination=membre.phone,
            body=_texte(groupe, cycle, contribution),
            contribution_id=contribution.id,
        )
        try:
            # L'ajout se fait *dans* le point de sauvegarde, pas avant : une
            # insertion refusée hors savepoint mettrait toute la session en
            # échec et emporterait les relances déjà inscrites.
            with db.begin_nested():
                db.add(notification)
                db.flush()
        except IntegrityError:
            # Déjà relancée aujourd'hui : c'est exactement ce qu'on voulait.
            # Le rollback du point de sauvegarde a déjà retiré l'objet de la
            # session — l'en expulser une seconde fois lèverait.
            continue
        inscrites += 1

    db.commit()
    return inscrites


def acheminer(db: Session, client: SmsClient, *, lot: int = 50) -> tuple[int, int]:
    """Remet au canal les notifications en attente. Renvoie (parties, échouées).

    Une notification qui échoue reste `failed` avec son motif ; elle ne sera
    pas reprise — le retard du lendemain en produira une nouvelle, à jour.
    Insister sur un message périmé n'aiderait personne.
    """
    en_attente = list(
        db.execute(
            select(Notification)
            .where(Notification.status == NotificationStatus.PENDING)
            .order_by(Notification.created_at)
            .limit(lot)
        ).scalars().all()
    )

    parties = 0
    echouees = 0
    for notification in en_attente:
        notification.attempts += 1
        try:
            client.envoyer(destinataire=notification.destination, texte=notification.body)
        except SmsError as exc:
            notification.status = NotificationStatus.FAILED
            notification.last_error = str(exc)[:300]
            echouees += 1
            continue
        notification.status = NotificationStatus.SENT
        notification.sent_at = datetime.now(UTC)
        parties += 1

    db.commit()
    return parties, echouees
