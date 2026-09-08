import { Link, useNavigate, useParams } from 'react-router-dom'

import type { Contribution, Cycle } from '@/api/types'
import { Badge } from '@/components/Badge'
import { IconBack, IconCheck, IconLock, IconPerson, IconPhone } from '@/components/Icon'
import { TourBar, tourStates } from '@/components/TourBar'
import { useAuth } from '@/hooks/useAuth'
import {
  useActivateGroup,
  useAddMember,
  useBalance,
  useCycles,
  useGroup,
  useMembers,
} from '@/hooks/useGroups'
import {
  CONTRIBUTION_STATUS_LABELS,
  CYCLE_STATUS_LABELS,
  GROUP_STATUS_LABELS,
  formatDate,
  formatXof,
} from '@/lib'

export function GroupDetailPage() {
  const { groupId = '' } = useParams()
  const { user } = useAuth()

  const group = useGroup(groupId)
  const members = useMembers(groupId)
  const cycles = useCycles(groupId)
  const balance = useBalance(groupId)

  const addMember = useAddMember(groupId)
  const activate = useActivateGroup(groupId)
  const navigate = useNavigate()

  if (group.isLoading) return <p className="muted app__main">Chargement…</p>
  if (group.error || !group.data) return <p className="alert app__main">Tontine introuvable.</p>

  const myMembership = members.data?.find((member) => member.user_id === user?.id)
  const isAdmin = myMembership?.is_admin ?? false
  const isDraft = group.data.status === 'draft'

  const memberLabel = (membershipId: string) => {
    const member = members.data?.find((m) => m.id === membershipId)
    if (!member) return '—'
    return member.user_id === user?.id ? 'Vous' : `Membre n°${member.payout_position}`
  }

  const currentCycle = cycles.data?.find((cycle) => cycle.status !== 'paid_out')
  const myDueContribution = currentCycle?.contributions.find(
    (contribution) =>
      contribution.membership_id === myMembership?.id && contribution.status === 'due',
  )

  return (
    <>
      <header className="block wipe">
        <div className="row row--between">
          <Link to="/" className="btn btn--icon" aria-label="Retour">
            <IconBack size={19} />
          </Link>
          <span className="label--accent">
            {GROUP_STATUS_LABELS[group.data.status]} · {members.data?.length ?? 0} membres
          </span>
          <span style={{ width: 40 }} />
        </div>

        <h1>{group.data.name}</h1>

        <div className="row row--between" style={{ alignItems: 'flex-end' }}>
          <div>
            <div className="label--soft block__muted">Cagnotte disponible</div>
            <div className="figure figure--lg">
              {balance.data ? formatXof(balance.data.balance_minor) : '—'}
            </div>
          </div>
          {currentCycle && (
            <Badge status={currentCycle.status} label={CYCLE_STATUS_LABELS[currentCycle.status]} />
          )}
        </div>

        {cycles.data && cycles.data.length > 0 && (
          <TourBar
            states={tourStates(cycles.data)}
            minePosition={myMembership?.payout_position}
          />
        )}
      </header>

      <main className="app__main" style={{ paddingBottom: myDueContribution ? 96 : 24 }}>
        {isDraft && (
          <section className="stack rise">
            <div className="label">Membres · {members.data?.length ?? 0}</div>
            <ul className="list">
              {members.data?.map((member) => (
                <li key={member.id} className="card card--soft row" style={{ gap: 12 }}>
                  <span className="avatar">{member.payout_position}</span>
                  <span className="row__grow">
                    {member.user_id === user?.id ? 'Vous' : `Membre n°${member.payout_position}`}
                  </span>
                  {member.is_admin && <span className="badge badge--neutral">Admin</span>}
                </li>
              ))}
            </ul>

            {isAdmin && (
              <>
                <form
                  className="form"
                  onSubmit={(event) => {
                    event.preventDefault()
                    const data = new FormData(event.currentTarget)
                    addMember.mutate(String(data.get('phone')))
                    event.currentTarget.reset()
                  }}
                >
                  <label className="field">
                    <span>Inviter par numéro</span>
                    <input name="phone" type="tel" placeholder="+229…" required />
                  </label>
                  <button type="submit" className="btn" disabled={addMember.isPending}>
                    Inviter
                  </button>
                </form>
                {addMember.error && <p className="alert">{addMember.error.message}</p>}

                <div className="notice">
                  <IconLock size={17} />
                  <span>
                    Au démarrage, l'ordre de passage est figé et les échéances sont engendrées.
                    Il ne pourra plus être modifié.
                  </span>
                </div>

                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={() => activate.mutate()}
                  disabled={activate.isPending}
                >
                  {activate.isPending ? 'Démarrage…' : 'Démarrer la tontine'}
                </button>
                {activate.error && <p className="alert">{activate.error.message}</p>}
              </>
            )}
          </section>
        )}

        {!isDraft && (
          <Link
            to={`/groupes/${groupId}/ordre`}
            className="card card--soft rise row"
            style={{ color: 'inherit', textDecoration: 'none', flexDirection: 'row' }}
          >
            <IconPerson size={20} />
            <span className="row__grow" style={{ fontWeight: 700 }}>
              Ordre de passage
            </span>
            <span className="muted">{members.data?.length ?? 0} membres</span>
          </Link>
        )}

        {cycles.data && cycles.data.length > 0 && (
          <section className="stack rise">
            <div className="label">Échéances</div>
            <ul className="list">
              {cycles.data.map((cycle, index) => (
                <li key={cycle.id}>
                  <CycleCard
                    cycle={cycle}
                    delay={index * 0.06}
                    beneficiary={memberLabel(cycle.beneficiary_membership_id)}
                    myMembershipId={myMembership?.id}
                    onPay={(contribution) =>
                      navigate(`/groupes/${groupId}/cotisations/${contribution.id}`)
                    }
                  />
                </li>
              ))}
            </ul>
          </section>
        )}
      </main>

      {myDueContribution && (
        <div className="action-bar">
          <button
            type="button"
            className="btn btn--primary btn--breathing"
            onClick={() =>
              navigate(`/groupes/${groupId}/cotisations/${myDueContribution.id}`)
            }
          >
            <IconPhone size={20} />
            Payer ma part · {formatXof(myDueContribution.amount_minor)}
          </button>
        </div>
      )}
    </>
  )
}

function CycleCard({
  cycle,
  delay,
  beneficiary,
  myMembershipId,
  onPay,
}: {
  cycle: Cycle
  delay: number
  beneficiary: string
  myMembershipId?: string
  onPay: (contribution: Contribution) => void
}) {
  const paidCount = cycle.contributions.filter((c) => c.status === 'paid').length
  const mine = cycle.contributions.find((c) => c.membership_id === myMembershipId)
  const isSettled = cycle.status === 'paid_out'

  return (
    <article
      className={isSettled ? 'card card--soft rise' : 'card rise'}
      style={{ animationDelay: `${delay}s` }}
    >
      <div className="card__head">
        <div>
          <h2>
            Tour {cycle.index + 1} · pour {beneficiary}
          </h2>
          <p className="muted">{formatDate(cycle.due_date)}</p>
        </div>
        <Badge status={cycle.status} label={CYCLE_STATUS_LABELS[cycle.status]} />
      </div>

      <div className="row row--between">
        <span className="muted">
          {paidCount} sur {cycle.contributions.length} ont payé
        </span>
        {mine && (
          <span className="row" style={{ gap: 7 }}>
            {mine.status === 'paid' && <IconCheck size={16} />}
            <span className="muted">
              Votre part : {CONTRIBUTION_STATUS_LABELS[mine.status].toLowerCase()}
            </span>
          </span>
        )}
      </div>

      {mine?.status === 'due' && (
        <button type="button" className="btn" onClick={() => onPay(mine)}>
          <IconPhone size={18} />
          Payer {formatXof(mine.amount_minor)}
        </button>
      )}
    </article>
  )
}
