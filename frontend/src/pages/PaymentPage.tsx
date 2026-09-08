import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { IconCheck, IconInfo, IconPhone } from '@/components/Icon'
import { useAuth } from '@/hooks/useAuth'
import { useContribution, useGroup, useMembers, usePayContribution } from '@/hooks/useGroups'
import { formatDate, formatXof } from '@/lib'
import { WaitingScreen } from '@/pages/WaitingScreen'

const OPERATEURS = [
  { id: 'mtn', tag: 'MTN', name: 'MTN MoMo' },
  { id: 'moov', tag: 'MOOV', name: 'Moov Africa' },
] as const

export function PaymentPage() {
  const { groupId = '', contributionId = '' } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()

  const group = useGroup(groupId)
  const members = useMembers(groupId)
  const { contribution, cycle, isLoading } = useContribution(groupId, contributionId)
  const pay = usePayContribution(groupId)

  const [operateur, setOperateur] = useState<string>('mtn')

  if (isLoading || group.isLoading) return <p className="muted app__main">Chargement…</p>
  if (!contribution || !cycle || !group.data) {
    return <p className="alert app__main">Cotisation introuvable.</p>
  }

  // Une cotisation déjà engagée reprend directement à l'écran d'attente, même
  // après un rechargement : c'est l'état réel, pas un état de composant.
  if (contribution.status === 'processing') {
    return <WaitingScreen groupId={groupId} contributionId={contributionId} />
  }

  if (contribution.status === 'paid') {
    return (
      <main className="app__main">
        <div className="card rise">
          <IconCheck size={24} />
          <h2>Cotisation déjà réglée</h2>
          <p className="muted">
            Votre part du tour {cycle.index + 1} a été encaissée. Rien de plus à faire.
          </p>
          <button type="button" className="btn" onClick={() => navigate(`/groupes/${groupId}`)}>
            Revenir à la tontine
          </button>
        </div>
      </main>
    )
  }

  const beneficiaire = members.data?.find((m) => m.id === cycle.beneficiary_membership_id)
  const beneficiaireLabel = beneficiaire
    ? beneficiaire.user_id === user?.id
      ? 'vous'
      : `le membre n°${beneficiaire.payout_position}`
    : '—'

  return (
    <>
      <header className="block wipe">
        <div className="row row--between">
          <button
            type="button"
            className="btn btn--icon"
            aria-label="Fermer"
            onClick={() => navigate(`/groupes/${groupId}`)}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" aria-hidden="true">
              <path d="M6 6l12 12" />
              <path d="M18 6L6 18" />
            </svg>
          </button>
          <span className="label">Payer ma cotisation</span>
          <span style={{ width: 40 }} />
        </div>

        <div style={{ textAlign: 'center' }}>
          <div className="label--accent">Montant</div>
          <div className="figure figure--hero">
            {new Intl.NumberFormat('fr-FR').format(contribution.amount_minor)}
            <span className="figure__unit">F</span>
          </div>
        </div>
      </header>

      <main className="app__main" style={{ paddingBottom: 96 }}>
        <div className="recap rise">
          <div className="recap__row">
            <span className="recap__key">Tontine</span>
            <span>{group.data.name}</span>
          </div>
          <div className="recap__row">
            <span className="recap__key">Tour</span>
            <span>
              {cycle.index + 1} · pour {beneficiaireLabel}
            </span>
          </div>
          <div className="recap__row">
            <span className="recap__key">Échéance</span>
            <span>{formatDate(cycle.due_date)}</span>
          </div>
        </div>

        <section className="stack rise" style={{ animationDelay: '.06s' }}>
          <div className="label">Opérateur</div>
          <div className="choices">
            {OPERATEURS.map((op) => (
              <button
                key={op.id}
                type="button"
                aria-pressed={operateur === op.id}
                className={`choice${operateur === op.id ? ' choice--selected' : ''}`}
                onClick={() => setOperateur(op.id)}
              >
                <span className="choice__tag">{op.tag}</span>
                <span>{op.name}</span>
                <span className="muted">Frais : 0 F</span>
                {operateur === op.id && (
                  <span className="choice__mark">
                    <IconCheck size={12} strokeWidth={3.4} />
                  </span>
                )}
              </button>
            ))}
          </div>
        </section>

        <section className="stack rise" style={{ animationDelay: '.12s' }}>
          <div className="label">Numéro à débiter</div>
          <div className="card" style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
            <span
              className="row__grow"
              style={{ fontFamily: 'var(--font-figure)', fontSize: 18, fontWeight: 600 }}
            >
              {user?.phone}
            </span>
          </div>
          <p className="muted">Le numéro du compte — c'est lui qui reçoit l'invite.</p>
        </section>

        <div className="notice rise" style={{ animationDelay: '.18s' }}>
          <IconInfo size={17} />
          <span>
            Une invite arrivera sur votre téléphone. Composez votre code secret Mobile Money
            pour valider — nous ne le voyons jamais.
          </span>
        </div>

        {pay.error && <p className="alert">{pay.error.message}</p>}
      </main>

      <div className="action-bar" style={{ bottom: 0 }}>
        <button
          type="button"
          className="btn btn--primary btn--breathing"
          disabled={pay.isPending}
          onClick={() => pay.mutate(contribution.id)}
        >
          <IconPhone size={20} />
          {pay.isPending ? 'Envoi…' : `Confirmer · ${formatXof(contribution.amount_minor)}`}
        </button>
      </div>
    </>
  )
}
