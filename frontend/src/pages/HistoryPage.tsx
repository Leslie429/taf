import { Link } from 'react-router-dom'

import type { HistoryItem } from '@/api/types'
import { useHistory } from '@/hooks/useGroups'
import { TRANSACTION_STATUS_LABELS, formatDate, formatXof } from '@/lib'

export function HistoryPage() {
  const { data: items, isLoading, error } = useHistory()

  const recu = items
    ?.filter((item) => item.direction === 'in' && item.status === 'success')
    .reduce((total, item) => total + item.amount_minor, 0)
  const verse = items
    ?.filter((item) => item.direction === 'out' && item.status === 'success')
    .reduce((total, item) => total + item.amount_minor, 0)

  return (
    <>
      <header className="block wipe">
        <div className="label--accent">Historique</div>
        <div className="row row--between" style={{ alignItems: 'flex-end' }}>
          <div>
            <div className="label--soft block__muted">Versé</div>
            <div className="figure figure--lg">{formatXof(verse ?? 0)}</div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div className="label--soft block__muted">Reçu</div>
            <div className="figure figure--lg">{formatXof(recu ?? 0)}</div>
          </div>
        </div>
      </header>

      <main className="app__main">
        {isLoading && <p className="muted">Chargement…</p>}
        {error && <p className="alert">Impossible de charger l'historique.</p>}

        {items && items.length === 0 && (
          <div className="card card--soft rise">
            <h2>Rien à afficher</h2>
            <p className="muted">
              Vos cotisations et vos versements apparaîtront ici dès le premier mouvement.
            </p>
          </div>
        )}

        {items && items.length > 0 && (
          <ul className="list">
            {items.map((item, index) => (
              <li key={item.id}>
                <HistoryRow item={item} delay={index * 0.04} />
              </li>
            ))}
          </ul>
        )}
      </main>
    </>
  )
}

function HistoryRow({ item, delay }: { item: HistoryItem; delay: number }) {
  const entrant = item.direction === 'in'
  const abouti = item.status === 'success'

  return (
    <Link
      to={`/groupes/${item.group_id}`}
      className="member rise"
      style={{ animationDelay: `${delay}s`, color: 'inherit', textDecoration: 'none' }}
    >
      <span className={`avatar${entrant && abouti ? ' avatar--done' : ''}`}>
        {entrant ? '↓' : '↑'}
      </span>
      <span className="row__grow">
        <span style={{ display: 'block', fontWeight: 700, fontSize: 14.5 }}>
          {item.group_name}
        </span>
        <span className="muted" style={{ display: 'block' }}>
          Tour {item.cycle_index + 1} · {formatDate(item.created_at)}
          {!abouti && ` · ${TRANSACTION_STATUS_LABELS[item.status]}`}
        </span>
      </span>
      {/* Le signe porte le sens, la couleur porte le statut : un montant reste
          en encre tant que la transaction a abouti. */}
      <span
        className="figure figure--md"
        style={{ color: abouti ? 'var(--ink)' : 'var(--ink-muted)' }}
      >
        {entrant ? '+' : '−'}
        {formatXof(item.amount_minor)}
      </span>
    </Link>
  )
}
