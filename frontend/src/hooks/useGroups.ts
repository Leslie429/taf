import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, api } from '@/api/client'
import { enqueue } from '@/offline/queue'
import type {
  Balance,
  Contribution,
  Cycle,
  Group,
  HistoryItem,
  Member,
  Transaction,
} from '@/api/types'

export function useGroups() {
  return useQuery({
    queryKey: ['groups'],
    queryFn: () => api.get<Group[]>('/groups'),
  })
}

export function useGroup(groupId: string) {
  return useQuery({
    queryKey: ['groups', groupId],
    queryFn: () => api.get<Group>(`/groups/${groupId}`),
  })
}

export function useCycles(groupId: string, options?: { refetchInterval?: number }) {
  return useQuery({
    queryKey: ['groups', groupId, 'cycles'],
    queryFn: () => api.get<Cycle[]>(`/groups/${groupId}/cycles`),
    // L'écran d'attente interroge en boucle : c'est l'opérateur qui tranche,
    // par un callback qu'on ne reçoit pas côté navigateur.
    refetchInterval: options?.refetchInterval,
  })
}

export function useMembers(groupId: string) {
  return useQuery({
    queryKey: ['groups', groupId, 'members'],
    queryFn: () => api.get<Member[]>(`/groups/${groupId}/members`),
  })
}

export function useBalance(groupId: string) {
  return useQuery({
    queryKey: ['groups', groupId, 'balance'],
    queryFn: () => api.get<Balance>(`/groups/${groupId}/balance`),
  })
}

export function useCreateGroup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: {
      name: string
      contribution_minor: number
      frequency: string
      start_date: string
    }) => api.post<Group>('/groups', payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['groups'] }),
  })
}

export function useAddMember(groupId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (phone: string) =>
      api.post<Member>(`/groups/${groupId}/members`, { phone }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['groups', groupId, 'members'] }),
  })
}

export function useActivateGroup(groupId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<Cycle[]>(`/groups/${groupId}/activate`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['groups', groupId] }),
  })
}

/** Soit l'opérateur a été sollicité, soit la cotisation attend le réseau. */
export type PayOutcome = { queued: true } | { queued: false; transaction: Transaction }

export function usePayContribution(groupId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (contributionId: string): Promise<PayOutcome> => {
      // Le réseau manque : inutile de tenter l'envoi pour afficher une erreur
      // que l'utilisateur ne peut pas corriger. La cotisation entre en file.
      if (!navigator.onLine) {
        enqueue({ contributionId, groupId })
        return { queued: true }
      }
      try {
        const transaction = await api.post<Transaction>(
          `/contributions/${contributionId}/pay`,
        )
        return { queued: false, transaction }
      } catch (erreur) {
        // Une réponse de l'API, même un refus, est un verdict : elle remonte.
        // Un `fetch` qui échoue n'en est pas un — le réseau a lâché entre le
        // téléphone et nous, et rien ne dit que la demande soit partie. Elle
        // sera rejouée, ce que la clé d'idempotence rend sans conséquence.
        if (erreur instanceof ApiError) throw erreur
        enqueue({ contributionId, groupId })
        return { queued: true }
      }
    },
    // L'opérateur répond par callback : on rafraîchit cycles et solde ensemble.
    onSuccess: (outcome) => {
      if (outcome.queued) return
      void queryClient.invalidateQueries({ queryKey: ['groups', groupId, 'cycles'] })
      void queryClient.invalidateQueries({ queryKey: ['groups', groupId, 'balance'] })
    },
  })
}

export function useHistory() {
  return useQuery({
    queryKey: ['history'],
    queryFn: () => api.get<HistoryItem[]>('/me/transactions'),
  })
}

/** L'API n'expose pas une cotisation seule : on la retrouve dans les cycles,
 *  ce qui évite un aller-retour de plus et garde une source unique. */
export function useContribution(
  groupId: string,
  contributionId: string,
  options?: { refetchInterval?: number },
) {
  const cycles = useCycles(groupId, options)
  let contribution: Contribution | undefined
  let cycle: Cycle | undefined
  for (const candidate of cycles.data ?? []) {
    const found = candidate.contributions.find((item) => item.id === contributionId)
    if (found) {
      contribution = found
      cycle = candidate
      break
    }
  }
  return { ...cycles, contribution, cycle }
}
