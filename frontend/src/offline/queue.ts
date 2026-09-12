import { ApiError } from '@/api/client'

/** Une cotisation dont l'envoi attend le retour du réseau. */
export interface QueuedPayment {
  contributionId: string
  groupId: string
  /** ISO 8601 — sert à dater l'attente dans l'interface. */
  queuedAt: string
}

const QUEUE_KEY = 'tontine.queue'

const listeners = new Set<(queue: QueuedPayment[]) => void>()

function estEntree(valeur: unknown): valeur is QueuedPayment {
  if (typeof valeur !== 'object' || valeur === null) return false
  const candidat = valeur as Record<string, unknown>
  return (
    typeof candidat.contributionId === 'string' &&
    typeof candidat.groupId === 'string' &&
    typeof candidat.queuedAt === 'string'
  )
}

export function readQueue(): QueuedPayment[] {
  // Le navigateur peut refuser le stockage (navigation privée, quota), et le
  // contenu vient d'une version antérieure de l'application : on ne fait
  // confiance ni à la lecture ni à la forme.
  try {
    const brut = localStorage.getItem(QUEUE_KEY)
    if (!brut) return []
    const valeur: unknown = JSON.parse(brut)
    return Array.isArray(valeur) ? valeur.filter(estEntree) : []
  } catch {
    return []
  }
}

function writeQueue(queue: QueuedPayment[]): QueuedPayment[] {
  try {
    localStorage.setItem(QUEUE_KEY, JSON.stringify(queue))
  } catch {
    // Tant pis pour la persistance : les abonnés doivent quand même voir
    // l'état courant, sans quoi l'interface mentirait sur ce qui est en file.
  }
  for (const listener of listeners) listener(queue)
  return queue
}

/** S'abonne aux changements de la file. Renvoie la fonction de désabonnement. */
export function subscribeQueue(listener: (queue: QueuedPayment[]) => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Met une cotisation en file. Une cotisation déjà en attente n'y entre pas
 *  deux fois : c'est la même dette, pas deux paiements. */
export function enqueue(entry: Omit<QueuedPayment, 'queuedAt'>): QueuedPayment[] {
  const queue = readQueue()
  if (queue.some((item) => item.contributionId === entry.contributionId)) return queue
  return writeQueue([...queue, { ...entry, queuedAt: new Date().toISOString() }])
}

export function dequeue(contributionId: string): QueuedPayment[] {
  return writeQueue(readQueue().filter((item) => item.contributionId !== contributionId))
}

export function clearQueue(): QueuedPayment[] {
  return writeQueue([])
}

/** Ce qu'il faut conclure d'une tentative d'envoi. */
export type Issue = 'envoyée' | 'abandonnée' | 'à réessayer'

/**
 * Une erreur de l'API tranche le sort de l'entrée en file.
 *
 * Un refus qui vient du serveur est définitif : la cotisation est déjà réglée
 * (409), n'existe pas (404), ou n'est pas la nôtre (403). La garder en file
 * reviendrait à la représenter indéfiniment.
 *
 * Une panne — réseau coupé, 502 de l'hébergeur, 401 dont le rafraîchissement
 * n'a rien donné — ne dit rien de la cotisation elle-même : on réessaiera.
 */
export function issueDeLerreur(erreur: unknown): Issue {
  if (erreur instanceof ApiError && erreur.status >= 400 && erreur.status < 500) {
    return erreur.status === 401 || erreur.status === 429 ? 'à réessayer' : 'abandonnée'
  }
  return 'à réessayer'
}

export interface FlushResult {
  envoyées: QueuedPayment[]
  abandonnées: { entry: QueuedPayment; erreur: unknown }[]
  restantes: QueuedPayment[]
}

/**
 * Vide la file, une entrée à la fois.
 *
 * Rejouer un paiement est sans danger : la clé d'idempotence est dérivée côté
 * serveur de l'état de la cotisation, si bien qu'un envoi rejoué retombe sur
 * la transaction déjà engagée au lieu d'en ouvrir une seconde. C'est ce qui
 * autorise cette file à réessayer sans compter.
 *
 * Les entrées sont traitées en série, et la passe s'arrête à la première
 * panne : si le réseau est retombé, marteler les suivantes n'apporte rien.
 */
export async function flushQueue(
  envoyer: (entry: QueuedPayment) => Promise<unknown>,
): Promise<FlushResult> {
  const resultat: FlushResult = { envoyées: [], abandonnées: [], restantes: [] }

  for (const entry of readQueue()) {
    if (resultat.restantes.length > 0) {
      // La passe est interrompue : les suivantes restent en file, intactes.
      resultat.restantes.push(entry)
      continue
    }
    try {
      await envoyer(entry)
      resultat.envoyées.push(entry)
      dequeue(entry.contributionId)
    } catch (erreur) {
      if (issueDeLerreur(erreur) === 'abandonnée') {
        resultat.abandonnées.push({ entry, erreur })
        dequeue(entry.contributionId)
      } else {
        resultat.restantes.push(entry)
      }
    }
  }
  return resultat
}
