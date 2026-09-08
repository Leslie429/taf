import type { ContributionStatus, CycleStatus, GroupStatus } from '@/api/types'

type Tone = 'neutral' | 'progress' | 'success' | 'danger'

/** La couleur porte le statut, jamais la valeur : aucun montant n'est coloré. */
const TONES: Record<GroupStatus | CycleStatus | ContributionStatus, Tone> = {
  draft: 'neutral',
  active: 'progress',
  completed: 'success',
  cancelled: 'danger',
  pending: 'neutral',
  funded: 'success',
  paid_out: 'success',
  late: 'danger',
  due: 'neutral',
  processing: 'progress',
  paid: 'success',
  failed: 'danger',
}

export function Badge({
  status,
  label,
}: {
  status: GroupStatus | CycleStatus | ContributionStatus
  label: string
}) {
  return <span className={`badge badge--${TONES[status]}`}>{label}</span>
}
