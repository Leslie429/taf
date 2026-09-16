from enum import StrEnum


class GroupStatus(StrEnum):
    DRAFT = "draft"          # on peut encore ajouter des membres
    ACTIVE = "active"        # les cycles tournent
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Frequency(StrEnum):
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    LEFT = "left"
    EXCLUDED = "excluded"


class CycleStatus(StrEnum):
    PENDING = "pending"      # cotisations en cours de collecte
    FUNDED = "funded"        # tout le monde a payé
    PAID_OUT = "paid_out"    # la cagnotte a été versée au bénéficiaire
    LATE = "late"


class ContributionStatus(StrEnum):
    DUE = "due"
    PROCESSING = "processing"
    PAID = "paid"
    FAILED = "failed"


class TransactionType(StrEnum):
    CONTRIBUTION = "contribution"   # membre -> cagnotte du groupe
    PAYOUT = "payout"               # cagnotte -> bénéficiaire
    REVERSAL = "reversal"


class TransactionStatus(StrEnum):
    """Machine à états d'une transaction. Les transitions sont contrôlées côté service."""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    REVERSED = "reversed"


class AccountKind(StrEnum):
    USER_WALLET = "user_wallet"       # passif : ce que la plateforme doit au membre
    GROUP_POT = "group_pot"           # passif : la cagnotte d'un groupe
    MOMO_CLEARING = "momo_clearing"   # actif : les fonds détenus chez l'opérateur
    FEES = "fees"                     # produit : les commissions de la plateforme


class EntryDirection(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class DivergenceKind(StrEnum):
    """Ce qu'un rapprochement peut trouver entre le grand livre et l'opérateur."""

    # Nous l'avons laissée en cours, l'opérateur a tranché depuis.
    UNCONFIRMED = "unconfirmed"
    # Nous la comptons réussie, l'opérateur dit le contraire. Le cas grave :
    # de l'argent figure au grand livre sans exister chez l'opérateur.
    DISPUTED_SUCCESS = "disputed_success"
    # L'opérateur répond mais ignore la référence.
    UNKNOWN_AT_OPERATOR = "unknown_at_operator"
    # L'opérateur n'a rien tranché, ou n'a pas répondu.
    OPERATOR_SILENT = "operator_silent"


class AuditAction(StrEnum):
    """Ce qu'un journal d'audit retient.

    Seules y figurent les actions qui engagent de l'argent ou déplacent un
    droit. Journaliser les lectures noierait ces lignes-là dans le bruit.
    """

    GROUP_CREATED = "group.created"
    MEMBER_ADDED = "group.member_added"
    GROUP_ACTIVATED = "group.activated"
    CYCLE_PAID_OUT = "cycle.paid_out"
    RECONCILIATION_LAUNCHED = "reconciliation.launched"


class AuditOutcome(StrEnum):
    """Une tentative refusée vaut d'être consignée autant qu'une réussie.

    C'est même souvent elle qui compte : une série de refus sur le versement
    d'une cagnotte dit quelque chose qu'aucun succès ne dira.
    """

    ALLOWED = "allowed"
    DENIED = "denied"


class NotificationKind(StrEnum):
    """Ce qui vaut d'être signalé à un membre."""

    # La cotisation du tour en cours est en retard.
    CONTRIBUTION_LATE = "contribution.late"


class NotificationStatus(StrEnum):
    """Où en est l'acheminement d'une notification.

    `pending` est l'état d'une notification créée mais pas encore partie : la
    relance décide *quoi* envoyer, l'acheminement décide *quand*. Les séparer
    permet à un envoi qui échoue d'être retenté sans recalculer le retard.
    """

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
