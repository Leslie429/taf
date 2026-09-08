import { describe, expect, it } from 'vitest'

import type { Cycle } from '@/api/types'
import { tourStates } from './TourBar'

function cycle(index: number, status: Cycle['status']): Cycle {
  return {
    id: `c${index}`,
    index,
    beneficiary_membership_id: `m${index}`,
    due_date: '2026-10-01',
    status,
    contributions: [],
  }
}

describe('tourStates', () => {
  it('marque comme acquis les tours déjà versés', () => {
    const states = tourStates([
      cycle(0, 'paid_out'),
      cycle(1, 'paid_out'),
      cycle(2, 'pending'),
      cycle(3, 'pending'),
    ])
    expect(states).toEqual(['done', 'done', 'current', 'upcoming'])
  })

  it("désigne le premier tour non versé comme le tour courant", () => {
    const states = tourStates([cycle(0, 'funded'), cycle(1, 'pending')])
    // « Financé » n'est pas « versé » : l'argent est encore dans la cagnotte.
    expect(states).toEqual(['current', 'upcoming'])
  })

  it('traite un tour en retard comme le tour courant', () => {
    const states = tourStates([cycle(0, 'paid_out'), cycle(1, 'late'), cycle(2, 'pending')])
    expect(states).toEqual(['done', 'current', 'upcoming'])
  })

  it('ne désigne aucun tour courant quand tout est versé', () => {
    const states = tourStates([cycle(0, 'paid_out'), cycle(1, 'paid_out')])
    expect(states).toEqual(['done', 'done'])
  })

  it('accepte une tontine sans cycle', () => {
    expect(tourStates([])).toEqual([])
  })
})
