import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
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

export function usePayContribution(groupId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (contributionId: string) =>
      api.post<Transaction>(`/contributions/${contributionId}/pay`),
    // L'opérateur répond par callback : on rafraîchit cycles et solde ensemble.
    onSuccess: () => {
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
