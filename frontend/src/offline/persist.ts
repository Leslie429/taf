import { dehydrate, hydrate } from '@tanstack/react-query'
import type { DehydratedState, QueryClient } from '@tanstack/react-query'

/* Persistance du cache applicatif — ce qui rend la consultation possible sans
 * réseau.
 *
 * Le cache de TanStack Query vit en mémoire et meurt avec l'onglet. On le
 * recopie dans le stockage local à chaque changement, et on le rend au
 * démarrage : l'application rouvre sur les données de la dernière visite au
 * lieu d'un écran de chargement qui n'aboutira pas.
 *
 * Ces données sont celles d'un compte — montants, échéances, historique. Elles
 * sont donc effacées à la déconnexion comme à la connexion, et jamais confiées
 * au Cache Storage du service worker, qui survit aux deux.
 */

const CACHE_KEY = 'tontine.cache'
const VERSION = 1
// Au-delà, une reprise hors connexion afficherait un état trop ancien pour
// qu'on puisse raisonnablement s'y fier.
const PEREMPTION_MS = 7 * 24 * 60 * 60 * 1000
const DELAI_ECRITURE_MS = 1_000

interface Enveloppe {
  version: number
  savedAt: number
  /** Le type est déclaré, pas garanti : ce contenu vient du stockage. C'est
   *  l'appel à `hydrate` qui le vérifie, sous protection. */
  state: DehydratedState
}

function lireEnveloppe(): Enveloppe | null {
  try {
    const brut = localStorage.getItem(CACHE_KEY)
    if (!brut) return null
    const valeur = JSON.parse(brut) as Partial<Enveloppe>
    if (valeur.version !== VERSION || typeof valeur.savedAt !== 'number') return null
    return valeur as Enveloppe
  } catch {
    return null
  }
}

/** Date de la dernière copie réussie, ou `null` si le cache est vide. */
export function lastSyncedAt(): Date | null {
  const enveloppe = lireEnveloppe()
  return enveloppe ? new Date(enveloppe.savedAt) : null
}

export function clearPersistedCache(): void {
  try {
    localStorage.removeItem(CACHE_KEY)
  } catch {
    // Rien à faire : le stockage est indisponible, il n'y a donc rien dedans.
  }
}

/** Rend au client le cache de la dernière visite. À appeler avant le rendu. */
export function hydrateFromStorage(queryClient: QueryClient): void {
  const enveloppe = lireEnveloppe()
  if (!enveloppe) return

  if (Date.now() - enveloppe.savedAt > PEREMPTION_MS) {
    clearPersistedCache()
    return
  }
  try {
    hydrate(queryClient, enveloppe.state)
  } catch {
    // Un état illisible vient d'une version antérieure du modèle : on repart
    // de zéro plutôt que de rendre une application à moitié hydratée.
    clearPersistedCache()
  }
}

/**
 * Recopie le cache à chaque changement, au plus une fois par seconde.
 *
 * Renvoie la fonction de désabonnement. Seules les requêtes abouties sont
 * gardées : une requête en erreur ou en cours n'a rien à rendre au prochain
 * démarrage.
 */
export function persistQueryCache(queryClient: QueryClient): () => void {
  let minuterie: ReturnType<typeof setTimeout> | null = null

  const ecrire = () => {
    minuterie = null
    try {
      const state = dehydrate(queryClient, {
        shouldDehydrateQuery: (query) => query.state.status === 'success',
        // Une mutation en vol ne se rejoue pas au démarrage : les paiements en
        // attente passent par la file, qui sait quand s'arrêter.
        shouldDehydrateMutation: () => false,
      })
      const enveloppe: Enveloppe = { version: VERSION, savedAt: Date.now(), state }
      localStorage.setItem(CACHE_KEY, JSON.stringify(enveloppe))
    } catch {
      // Quota dépassé ou stockage refusé : l'application continue, elle perd
      // seulement sa mémoire hors connexion.
    }
  }

  return queryClient.getQueryCache().subscribe(() => {
    if (minuterie !== null) return
    minuterie = setTimeout(ecrire, DELAI_ECRITURE_MS)
  })
}
