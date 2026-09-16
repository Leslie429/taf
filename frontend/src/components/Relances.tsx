import { useNotifications } from '@/hooks/useGroups'
import { formatDate } from '@/lib'

/**
 * Les relances de cotisation en retard.
 *
 * Une relance part par SMS, mais rien ne garantit qu'il arrive — et sur la
 * démonstration, sans opérateur configuré, rien ne part du tout. Cet écran est
 * donc le seul endroit où la relance se lit à coup sûr.
 *
 * Il ne s'affiche que lorsqu'il y a quelque chose à dire : un encart permanent
 * « aucun retard » finirait par ne plus être lu.
 */
export function Relances() {
  const { data: relances } = useNotifications()

  if (!relances || relances.length === 0) return null

  return (
    <section className="stack rise" aria-label="Relances">
      <div className="label">À régler</div>
      <ul className="list">
        {relances.map((relance) => (
          <li key={relance.id}>
            <div className="card card--soft" style={{ alignItems: 'flex-start', gap: 6 }}>
              <p style={{ margin: 0, fontWeight: 600, lineHeight: 1.45 }}>{relance.body}</p>
              <span className="muted" style={{ fontSize: 12 }}>
                {formatDate(relance.created_at)}
              </span>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
