import { Link, useParams } from 'react-router-dom'

import { IconBack, IconCheck, IconLock } from '@/components/Icon'
import { useAuth } from '@/hooks/useAuth'
import { useCycles, useGroup, useMembers } from '@/hooks/useGroups'
import { formatDate, formatXof } from '@/lib'

export function MembersPage() {
  const { groupId = '' } = useParams()
  const { user } = useAuth()

  const group = useGroup(groupId)
  const members = useMembers(groupId)
  const cycles = useCycles(groupId)

  if (group.isLoading || members.isLoading) return <p className="muted app__main">Chargement…</p>
  if (!group.data) return <p className="alert app__main">Tontine introuvable.</p>

  const potTotal = group.data.contribution_minor * (members.data?.length ?? 0)
  const cycleFor = (membershipId: string) =>
    cycles.data?.find((cycle) => cycle.beneficiary_membership_id === membershipId)

  return (
    <>
      <header className="block wipe">
        <div className="row" style={{ gap: 14 }}>
          <Link to={`/groupes/${groupId}`} className="btn btn--icon" aria-label="Retour">
            <IconBack size={19} />
          </Link>
          <div>
            <h1 style={{ fontSize: 22 }}>Ordre de passage</h1>
            <p className="block__muted" style={{ fontSize: 12 }}>
              {group.data.name} · {members.data?.length ?? 0} membres
            </p>
          </div>
        </div>

        {group.data.status !== 'draft' && (
          <div className="notice" style={{ background: 'rgba(255,255,255,.1)', color: 'inherit' }}>
            <IconLock size={16} />
            <span>
              L'ordre a été figé au démarrage. Il ne peut plus être modifié.
            </span>
          </div>
        )}
      </header>

      <main className="app__main">
        <ul className="list">
          {members.data?.map((member, index) => {
            const cycle = cycleFor(member.id)
            const isMe = member.user_id === user?.id
            const isDone = cycle?.status === 'paid_out'
            const isCurrent = cycle !== undefined && !isDone && cycle === cycles.data?.find((c) => c.status !== 'paid_out')

            const paidCount = cycle?.contributions.filter((c) => c.status === 'paid').length ?? 0
            const total = cycle?.contributions.length ?? 0

            let detail: string
            if (isDone) detail = `${cycle && formatDate(cycle.due_date)} · a reçu ${formatXof(potTotal)}`
            else if (isCurrent) detail = `${cycle && formatDate(cycle.due_date)} · collecte en cours`
            else if (cycle) detail = formatDate(cycle.due_date)
            else detail = 'La tontine n’a pas encore démarré'

            const tone = isMe ? ' member--me' : isCurrent ? ' member--current' : ''

            return (
              <li
                key={member.id}
                className={`member rise${tone}`}
                style={{ animationDelay: `${index * 0.05}s` }}
              >
                <span className="member__rank">{member.payout_position}</span>
                <span
                  className={`avatar${isMe ? ' avatar--me' : isDone ? ' avatar--done' : ''}`}
                >
                  {isMe ? 'moi' : `n°${member.payout_position}`}
                </span>
                <span className="row__grow">
                  <span style={{ display: 'block', fontWeight: isMe ? 800 : 700, fontSize: 14.5 }}>
                    {isMe ? user?.full_name : `Membre n°${member.payout_position}`}
                  </span>
                  <span className="muted" style={{ display: 'block' }}>
                    {detail}
                  </span>
                </span>
                {isDone && <IconCheck size={18} />}
                {isCurrent && !isDone && (
                  <span className="badge badge--progress">
                    {paidCount}/{total}
                  </span>
                )}
                {isMe && !isDone && !isCurrent && <span className="badge badge--accent">Vous</span>}
                {member.is_admin && !isMe && <span className="badge badge--neutral">Admin</span>}
              </li>
            )
          })}
        </ul>
      </main>
    </>
  )
}
