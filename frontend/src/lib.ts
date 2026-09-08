import type {
  ContributionStatus,
  CycleStatus,
  Frequency,
  GroupStatus,
  TransactionStatus,
} from '@/api/types'

/** Le franc CFA n'a pas de sous-unité : le montant mineur est le montant. */
export function formatXof(amountMinor: number): string {
  return `${new Intl.NumberFormat('fr-FR').format(amountMinor)} F`
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('fr-FR', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
  })
}

export const FREQUENCY_LABELS: Record<Frequency, string> = {
  weekly: 'Hebdomadaire',
  biweekly: 'Toutes les deux semaines',
  monthly: 'Mensuelle',
}

export const GROUP_STATUS_LABELS: Record<GroupStatus, string> = {
  draft: 'Brouillon',
  active: 'En cours',
  completed: 'Terminée',
  cancelled: 'Annulée',
}

export const CYCLE_STATUS_LABELS: Record<CycleStatus, string> = {
  pending: 'Collecte en cours',
  funded: 'Financé',
  paid_out: 'Versé',
  late: 'En retard',
}

export const CONTRIBUTION_STATUS_LABELS: Record<ContributionStatus, string> = {
  due: 'À payer',
  processing: 'En cours',
  paid: 'Payée',
  failed: 'Échouée',
}

export const TRANSACTION_STATUS_LABELS: Record<TransactionStatus, string> = {
  pending: 'en attente',
  processing: 'en cours',
  success: 'aboutie',
  failed: 'échouée',
  reversed: 'contrepassée',
}
