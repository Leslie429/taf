import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/Badge'
import { IconPhone } from '@/components/Icon'
import type { Group } from '@/api/types'
import { useAuth } from '@/hooks/useAuth'
import { useCreateGroup, useGroups } from '@/hooks/useGroups'
import { FREQUENCY_LABELS, GROUP_STATUS_LABELS, formatXof } from '@/lib'

export function GroupsPage() {
  const { user } = useAuth()
  const { data: groups, isLoading, error } = useGroups()
  const createGroup = useCreateGroup()
  const [open, setOpen] = useState(false)

  const today = new Date().toLocaleDateString('fr-FR', {
    weekday: 'short',
    day: '2-digit',
    month: 'short',
  })

  return (
    <>
      <header className="block wipe">
        <div className="row row--between">
          <span className="label">{user?.full_name}</span>
          <span className="block__muted" style={{ fontSize: 11.5, fontWeight: 600 }}>
            {today.toUpperCase()}
          </span>
        </div>

        <div>
          <div className="label--accent">Mes tontines</div>
          <div className="figure figure--hero">
            {groups?.length ?? 0}
            <span className="figure__unit">
              {groups?.length === 1 ? 'tontine' : 'tontines'}
            </span>
          </div>
        </div>

        <button
          type="button"
          className="btn btn--primary"
          onClick={() => setOpen(!open)}
        >
          {open ? 'Annuler' : 'Créer une tontine'}
        </button>
      </header>

      <main className="app__main">
        {open && (
          <form
            className="card form rise"
            onSubmit={(event) => {
              event.preventDefault()
              const data = new FormData(event.currentTarget)
              createGroup.mutate(
                {
                  name: String(data.get('name')),
                  contribution_minor: Number(data.get('contribution')),
                  frequency: String(data.get('frequency')),
                  start_date: String(data.get('start_date')),
                },
                { onSuccess: () => setOpen(false) },
              )
            }}
          >
            <label className="field">
              <span>Nom</span>
              <input name="name" required minLength={2} placeholder="Tontine du marché" />
            </label>
            <label className="field">
              <span>Cotisation par tour (F)</span>
              <input name="contribution" type="number" min={1} required defaultValue={5000} />
            </label>
            <label className="field">
              <span>Fréquence</span>
              <select name="frequency" defaultValue="monthly">
                {Object.entries(FREQUENCY_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Premier versement</span>
              <input name="start_date" type="date" required />
            </label>

            {createGroup.error && <p className="alert">{createGroup.error.message}</p>}

            <button type="submit" className="btn btn--primary" disabled={createGroup.isPending}>
              {createGroup.isPending ? 'Création…' : 'Créer'}
            </button>
          </form>
        )}

        {isLoading && <p className="muted">Chargement…</p>}
        {error && <p className="alert">Impossible de charger vos tontines.</p>}

        {groups && groups.length === 0 && !open && (
          <div className="card card--soft rise" style={{ alignItems: 'flex-start' }}>
            <IconPhone size={20} />
            <h2>Aucune tontine pour l'instant</h2>
            <p className="muted">
              Créez-en une, invitez vos membres, et fixez l'ordre de passage avant de démarrer.
            </p>
          </div>
        )}

        {groups && groups.length > 0 && (
          <ul className="list">
            {groups.map((group, index) => (
              <li key={group.id}>
                <GroupCard group={group} delay={index * 0.06} />
              </li>
            ))}
          </ul>
        )}
      </main>
    </>
  )
}

function GroupCard({ group, delay }: { group: Group; delay: number }) {
  return (
    <Link
      to={`/groupes/${group.id}`}
      className="card rise"
      style={{ animationDelay: `${delay}s`, color: 'inherit', textDecoration: 'none' }}
    >
      <div className="card__head">
        <h2>{group.name}</h2>
        <Badge status={group.status} label={GROUP_STATUS_LABELS[group.status]} />
      </div>

      {/* La barre de tours vit sur l'écran de détail : la liste ne charge pas
          les cycles, et une barre vide vaut moins que pas de barre. */}
      <div className="row row--between" style={{ alignItems: 'flex-end' }}>
        <div>
          <div className="label--soft">Cotisation par tour</div>
          <div className="figure figure--md">
            {formatXof(group.contribution_minor)}
          </div>
        </div>
        <div className="muted" style={{ textAlign: 'right' }}>
          {FREQUENCY_LABELS[group.frequency].toLowerCase()}
        </div>
      </div>
    </Link>
  )
}
