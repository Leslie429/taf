import { useNavigate } from 'react-router-dom'

import { IconCheck, IconInfo, IconPhone } from '@/components/Icon'
import { useContribution } from '@/hooks/useGroups'
import { formatXof } from '@/lib'

/** L'écran où l'utilisateur a de l'argent en suspens.
 *
 *  L'opérateur tranche par un callback que le navigateur ne reçoit pas : on
 *  interroge donc l'API jusqu'à ce que la cotisation change d'état. */
export function WaitingScreen({
  groupId,
  contributionId,
}: {
  groupId: string
  contributionId: string
}) {
  const navigate = useNavigate()
  const { contribution } = useContribution(groupId, contributionId, { refetchInterval: 3000 })

  if (contribution?.status === 'paid') {
    return (
      <main className="waiting">
        <div className="pulse">
          <div className="pulse__core" style={{ background: 'var(--positive)' }}>
            <IconCheck size={36} strokeWidth={2.6} />
          </div>
        </div>
        <h1>Cotisation enregistrée</h1>
        <p className="muted">
          Votre part est entrée dans la cagnotte. Elle y reste jusqu'au versement du tour.
        </p>
        <button
          type="button"
          className="btn btn--primary"
          onClick={() => navigate(`/groupes/${groupId}`)}
        >
          Revenir à la tontine
        </button>
      </main>
    )
  }

  // Un refus de l'opérateur remet la cotisation à payer : il faut le dire,
  // sinon l'écran revient au formulaire sans explication.
  if (contribution && contribution.status !== 'processing') {
    return (
      <main className="waiting">
        <div className="pulse">
          <div className="pulse__core" style={{ background: 'var(--urgent)' }}>
            <IconInfo size={36} />
          </div>
        </div>
        <h1>Paiement non abouti</h1>
        <p className="muted">
          L'opérateur n'a pas confirmé — invite expirée, solde insuffisant, ou refus. Votre
          cotisation est de nouveau à payer, et vous n'avez pas été débité.
        </p>
        <button
          type="button"
          className="btn btn--primary"
          onClick={() => navigate(0)}
        >
          Réessayer
        </button>
      </main>
    )
  }

  return (
    <main className="waiting">
      <div className="pulse">
        <span className="pulse__ring" />
        <span className="pulse__ring" style={{ animationDelay: '.9s' }} />
        <span className="pulse__ring" style={{ animationDelay: '1.8s' }} />
        <div className="pulse__core">
          <IconPhone size={35} strokeWidth={1.8} />
        </div>
      </div>

      <div>
        <h1>Confirmez sur votre téléphone</h1>
        <p className="muted" style={{ marginTop: 8 }}>
          Composez votre code secret Mobile Money quand l'invite apparaît. Cet écran se mettra
          à jour tout seul.
        </p>
      </div>

      <div className="card card--soft" style={{ width: '100%', gap: 12 }}>
        <div className="row row--between">
          <span className="label--soft">Montant</span>
          <span className="figure figure--md">
            {contribution ? formatXof(contribution.amount_minor) : '—'}
          </span>
        </div>
        <div className="row row--between">
          <span className="label--soft">Référence</span>
          <span style={{ fontFamily: 'var(--font-figure)', fontSize: 13, fontWeight: 600 }}>
            {contribution?.transaction_id?.slice(0, 18) ?? '—'}
          </span>
        </div>
      </div>

      <div className="steps">
        <div className="steps__row">
          <span className="steps__dot steps__dot--done">
            <IconCheck size={14} strokeWidth={3.4} />
          </span>
          <span style={{ fontWeight: 600 }}>Demande envoyée à l'opérateur</span>
        </div>
        <div className="steps__link" />
        <div className="steps__row">
          <span className="steps__dot steps__dot--active" />
          <span style={{ fontWeight: 700, color: 'var(--primary)' }}>Votre confirmation</span>
        </div>
        <div className="steps__link" />
        <div className="steps__row steps__row--todo">
          <span className="steps__dot" />
          <span>Cotisation enregistrée</span>
        </div>
      </div>

      <div style={{ marginTop: 'auto', width: '100%' }}>
        <p className="muted" style={{ marginBottom: 14 }}>
          Rien reçu ? L'invite expire au bout de deux minutes. Vous pourrez réessayer sans
          être débité deux fois.
        </p>
        {/* Pas de bouton « Annuler » : l'API n'expose aucun moyen d'annuler une
            demande déjà partie chez l'opérateur. Promettre l'inverse serait pire
            que de ne rien promettre. */}
        <button
          type="button"
          className="btn"
          style={{ width: '100%' }}
          onClick={() => navigate(`/groupes/${groupId}`)}
        >
          Revenir à la tontine
        </button>
      </div>
    </main>
  )
}
