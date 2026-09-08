export type Frequency = 'weekly' | 'biweekly' | 'monthly'
export type GroupStatus = 'draft' | 'active' | 'completed' | 'cancelled'
export type CycleStatus = 'pending' | 'funded' | 'paid_out' | 'late'
export type ContributionStatus = 'due' | 'processing' | 'paid' | 'failed'
export type TransactionStatus =
  | 'pending'
  | 'processing'
  | 'success'
  | 'failed'
  | 'reversed'

export interface User {
  id: string
  phone: string
  full_name: string
  is_active: boolean
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface Group {
  id: string
  name: string
  description: string | null
  /** En XOF, sans sous-unité : 5000 se lit « 5 000 F ». */
  contribution_minor: number
  currency: string
  frequency: Frequency
  start_date: string
  status: GroupStatus
}

export interface Member {
  id: string
  user_id: string
  payout_position: number
  is_admin: boolean
}

export interface Contribution {
  id: string
  membership_id: string
  amount_minor: number
  status: ContributionStatus
  transaction_id: string | null
}

export interface Cycle {
  id: string
  index: number
  beneficiary_membership_id: string
  due_date: string
  status: CycleStatus
  contributions: Contribution[]
}

export interface Balance {
  account_id: string
  balance_minor: number
  currency: string
}

export interface Transaction {
  id: string
  reference: string
  type: 'contribution' | 'payout' | 'reversal'
  status: TransactionStatus
  amount_minor: number
  currency: string
  external_id: string | null
  failure_reason: string | null
}

export interface HistoryItem {
  id: string
  reference: string
  type: 'contribution' | 'payout' | 'reversal'
  status: TransactionStatus
  amount_minor: number
  currency: string
  created_at: string
  /** Le sens vu de l'utilisateur : « out » quand il cotise, « in » quand il encaisse. */
  direction: 'in' | 'out'
  group_id: string
  group_name: string
  cycle_index: number
}
