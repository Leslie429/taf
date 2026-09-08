import { describe, expect, it } from 'vitest'

import { formatXof } from '@/lib'

describe('formatXof', () => {
  it('sépare les milliers', () => {
    // L'espace inséré par Intl est une espace insécable étroite (U+202F).
    expect(formatXof(5000).replace(/ | /g, ' ')).toBe('5 000 F')
  })

  it('gère un montant nul', () => {
    expect(formatXof(0)).toBe('0 F')
  })
})
