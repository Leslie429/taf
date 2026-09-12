import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react'

import { api } from '@/api/client'
import { flushQueue, readQueue, subscribeQueue } from '@/offline/queue'
import type { QueuedPayment } from '@/offline/queue'

function subscribeReseau(onChange: () => void): () => void {
  window.addEventListener('online', onChange)
  window.addEventListener('offline', onChange)
  return () => {
    window.removeEventListener('online', onChange)
    window.removeEventListener('offline', onChange)
  }
}

/** `true` tant que le navigateur se croit connecté.
 *
 *  Se croit : `navigator.onLine` ne prouve qu'une chose, l'existence d'une
 *  interface active. Un envoi peut échouer alors qu'il vaut `true` — c'est
 *  pourquoi la mise en file regarde aussi l'échec lui-même. */
export function useOnline(): boolean {
  return useSyncExternalStore(
    subscribeReseau,
    () => navigator.onLine,
    () => true,
  )
}

export function useQueue(): QueuedPayment[] {
  return useSyncExternalStore(subscribeQueue, readQueue, () => [])
}

/**
 * Vide la file dès que le réseau revient, et une fois au démarrage.
 *
 * À monter une seule fois dans l'application : deux passes concurrentes
 * enverraient la même cotisation deux fois. Le serveur y survivrait — sa clé
 * d'idempotence retomberait sur la transaction en cours — mais autant ne pas
 * s'en remettre à lui pour un défaut qui nous appartient.
 */
export function useQueueFlush(): void {
  const queryClient = useQueryClient()
  const enCours = useRef(false)

  const vider = useCallback(async () => {
    if (enCours.current || readQueue().length === 0) return
    enCours.current = true
    try {
      const resultat = await flushQueue((entry) =>
        api.post(`/contributions/${entry.contributionId}/pay`),
      )
      if (resultat.envoyées.length > 0 || resultat.abandonnées.length > 0) {
        // Les cycles portent l'état des cotisations, le solde en découle.
        await queryClient.invalidateQueries({ queryKey: ['groups'] })
      }
    } finally {
      enCours.current = false
    }
  }, [queryClient])

  useEffect(() => {
    void vider()
    const auRetour = () => void vider()
    window.addEventListener('online', auRetour)
    return () => window.removeEventListener('online', auRetour)
  }, [vider])
}
