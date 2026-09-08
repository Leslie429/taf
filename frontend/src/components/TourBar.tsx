import type { Cycle } from '@/api/types'

export type TourState = 'done' | 'current' | 'upcoming'

/** Traduit les cycles renvoyés par l'API en segments lisibles.
 *
 *  Un tour est « acquis » quand la cagnotte a été versée. Le tour courant est
 *  le premier qui ne l'est pas — y compris s'il est en retard, car c'est
 *  toujours celui sur lequel se joue l'argent. */
export function tourStates(cycles: Cycle[]): TourState[] {
  let currentFound = false
  return cycles.map((cycle) => {
    if (cycle.status === 'paid_out') return 'done'
    if (!currentFound) {
      currentFound = true
      return 'current'
    }
    return 'upcoming'
  })
}

interface Props {
  states: TourState[]
  /** Rang de passage du membre connecté, à partir de 1. */
  minePosition?: number | null
}

export function TourBar({ states, minePosition }: Props) {
  return (
    <div
      className="tours"
      role="img"
      aria-label={`${states.filter((s) => s === 'done').length} tours versés sur ${states.length}`}
    >
      {states.map((state, index) => {
        const isMine = minePosition === index + 1
        // Le tour du membre est signalé par un contour, pas par un remplissage :
        // il ne doit pas se confondre avec un tour déjà acquis.
        const modifier = isMine && state === 'upcoming' ? 'mine' : state
        return (
          <div
            key={index}
            className={`tours__seg tours__seg--${modifier}`}
            style={{ animationDelay: `${index * 0.06}s` }}
          />
        )
      })}
    </div>
  )
}
