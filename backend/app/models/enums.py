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
