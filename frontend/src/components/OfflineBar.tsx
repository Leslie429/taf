import { useOnline, useQueue } from '@/offline/useOffline'
import { lastSyncedAt } from '@/offline/persist'

/** Depuis quand les données affichées datent, en clair. */
function fraicheur(date: Date): string {
  const minutes = Math.round((Date.now() - date.getTime()) / 60_000)
  if (minutes < 2) return "à l'instant"
  if (minutes < 60) return `il y a ${minutes} min`

  const heures = Math.round(minutes / 60)
  if (heures < 24) return `il y a ${heures} h`
  const jours = Math.round(heures / 24)
  return jours === 1 ? 'hier' : `il y a ${jours} jours`
}

/**
 * Le bandeau d'état du réseau.
 *
 * Il ne s'affiche que lorsqu'il a quelque chose à dire : coupure en cours, ou
 * cotisations qui attendent leur envoi. Une application qui annonce en
 * permanence qu'elle va bien finit par n'être plus lue.
 */
export function OfflineBar() {
  const online = useOnline()
  const queue = useQueue()

  if (online && queue.length === 0) return null

  const enAttente =
    queue.length === 0
      ? null
      : queue.length === 1
        ? '1 cotisation part dès le retour du réseau'
        : `${queue.length} cotisations partent dès le retour du réseau`

  const synchro = lastSyncedAt()

  return (
    <div
      className={`offline${online ? ' offline--pending' : ''}`}
      role="status"
      aria-live="polite"
    >
      <span className="offline__dot" aria-hidden="true" />
      <span className="offline__text">
        {online ? 'Envoi en attente' : 'Hors connexion'}
        {enAttente && <> — {enAttente}</>}
        {!online && !enAttente && synchro && <> — données de {fraicheur(synchro)}</>}
      </span>
    </div>
  )
}
