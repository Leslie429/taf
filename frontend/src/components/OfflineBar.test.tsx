import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { OfflineBar } from '@/components/OfflineBar'
import { clearQueue, enqueue, queueSnapshot } from '@/offline/queue'

// Régression du 2026-09-24 : la page restait blanche en production. `useQueue` donnait à
// `useSyncExternalStore` un tableau neuf à chaque lecture ; React bouclait jusqu'à
// « Maximum update depth exceeded ». Aucun test ne rendait le bandeau : celui-ci le fait.
describe('bandeau hors connexion', () => {
  beforeEach(() => {
    localStorage.clear()
    clearQueue()
  })

  it('se rend sans boucle et ne dit rien quand tout va bien', () => {
    const { container } = render(<OfflineBar />)
    expect(container).toBeEmptyDOMElement()
  })

  it("annonce une cotisation en attente, puis se tait quand elle est partie", () => {
    render(<OfflineBar />)
    act(() => {
      enqueue({ contributionId: 'c1', groupId: 'g1' })
    })
    expect(screen.getByRole('status')).toHaveTextContent('1 cotisation part dès le retour du réseau')
    act(() => {
      clearQueue()
    })
    expect(screen.queryByRole('status')).toBeNull()
  })
})

describe('instantané de la file', () => {
  beforeEach(() => {
    localStorage.clear()
    clearQueue()
  })

  it('rend la même référence tant que la file ne change pas', () => {
    expect(queueSnapshot()).toBe(queueSnapshot())
  })

  it('change de référence quand la file change', () => {
    const avant = queueSnapshot()
    enqueue({ contributionId: 'c1', groupId: 'g1' })
    expect(queueSnapshot()).not.toBe(avant)
    expect(queueSnapshot()).toMatchObject([{ contributionId: 'c1' }])
  })
})
