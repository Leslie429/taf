import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import {
  clearQueue,
  dequeue,
  enqueue,
  flushQueue,
  issueDeLerreur,
  readQueue,
  subscribeQueue,
} from './queue'

const cotisation = (id: string) => ({ contributionId: id, groupId: 'g1' })

describe('file des cotisations', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('retient une cotisation et la relit après rechargement', () => {
    enqueue(cotisation('c1'))
    expect(readQueue()).toMatchObject([{ contributionId: 'c1', groupId: 'g1' }])
  })

  it("n'inscrit pas deux fois la même cotisation", () => {
    // Deux appuis sur « Payer » hors réseau, c'est une dette, pas deux.
    enqueue(cotisation('c1'))
    enqueue(cotisation('c1'))
    expect(readQueue()).toHaveLength(1)
  })

  it('conserve l\'ordre de mise en file', () => {
    enqueue(cotisation('c1'))
    enqueue(cotisation('c2'))
    expect(readQueue().map((item) => item.contributionId)).toEqual(['c1', 'c2'])
  })

  it('prévient ses abonnés à chaque changement', () => {
    const vu = vi.fn()
    const desabonner = subscribeQueue(vu)
    enqueue(cotisation('c1'))
    dequeue('c1')
    desabonner()
    enqueue(cotisation('c2'))

    expect(vu).toHaveBeenCalledTimes(2)
    expect(vu).toHaveBeenLastCalledWith([])
  })

  it('ignore un contenu de stockage abîmé', () => {
    localStorage.setItem('tontine.queue', '{ ceci n\'est pas du JSON')
    expect(readQueue()).toEqual([])
  })

  it('écarte les entrées qui n\'ont pas la forme attendue', () => {
    // Une version antérieure de l'application a pu écrire autre chose.
    localStorage.setItem('tontine.queue', JSON.stringify([{ contributionId: 'c1' }, 42]))
    expect(readQueue()).toEqual([])
  })
})

describe('sort d\'une entrée après un échec', () => {
  it("abandonne sur un refus qui vient du serveur", () => {
    // 409 : la cotisation est déjà réglée. La regarder revenir indéfiniment
    // ne la rendra pas payable.
    expect(issueDeLerreur(new ApiError(409, 'Déjà réglée.'))).toBe('abandonnée')
    expect(issueDeLerreur(new ApiError(403, 'Pas la vôtre.'))).toBe('abandonnée')
    expect(issueDeLerreur(new ApiError(404, 'Introuvable.'))).toBe('abandonnée')
  })

  it('réessaie quand la panne ne dit rien de la cotisation', () => {
    expect(issueDeLerreur(new TypeError('Failed to fetch'))).toBe('à réessayer')
    expect(issueDeLerreur(new ApiError(502, 'Bad gateway'))).toBe('à réessayer')
    // Le jeton a expiré et le rafraîchissement n'a pas abouti : c'est la
    // session qui manque, pas la cotisation.
    expect(issueDeLerreur(new ApiError(401, 'Jeton expiré.'))).toBe('à réessayer')
    // Trop d'appels : réessayer plus tard est exactement ce qu'on demande.
    expect(issueDeLerreur(new ApiError(429, 'Trop de requêtes.'))).toBe('à réessayer')
  })
})

describe('vidage de la file', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('envoie les cotisations dans leur ordre d\'arrivée et vide la file', async () => {
    enqueue(cotisation('c1'))
    enqueue(cotisation('c2'))

    const envoyées: string[] = []
    const resultat = await flushQueue(async (entry) => {
      envoyées.push(entry.contributionId)
    })

    expect(envoyées).toEqual(['c1', 'c2'])
    expect(resultat.envoyées).toHaveLength(2)
    expect(readQueue()).toEqual([])
  })

  it('retire une cotisation que le serveur refuse définitivement', async () => {
    enqueue(cotisation('c1'))
    const resultat = await flushQueue(() =>
      Promise.reject(new ApiError(409, 'Cette cotisation est déjà réglée.')),
    )

    expect(resultat.abandonnées).toHaveLength(1)
    expect(readQueue()).toEqual([])
  })

  it('garde la file intacte quand le réseau est encore absent', async () => {
    enqueue(cotisation('c1'))
    const resultat = await flushQueue(() => Promise.reject(new TypeError('Failed to fetch')))

    expect(resultat.restantes).toHaveLength(1)
    expect(readQueue().map((item) => item.contributionId)).toEqual(['c1'])
  })

  it('interrompt la passe à la première panne, sans perdre les suivantes', async () => {
    enqueue(cotisation('c1'))
    enqueue(cotisation('c2'))
    enqueue(cotisation('c3'))

    const tentées: string[] = []
    const resultat = await flushQueue(async (entry) => {
      tentées.push(entry.contributionId)
      if (entry.contributionId === 'c2') throw new TypeError('Failed to fetch')
    })

    // c3 n'est même pas tentée : le réseau vient de retomber.
    expect(tentées).toEqual(['c1', 'c2'])
    expect(resultat.envoyées.map((item) => item.contributionId)).toEqual(['c1'])
    expect(readQueue().map((item) => item.contributionId)).toEqual(['c2', 'c3'])
  })

  it('ne fait rien sur une file vide', async () => {
    const envoyer = vi.fn()
    const resultat = await flushQueue(envoyer)

    expect(envoyer).not.toHaveBeenCalled()
    expect(resultat).toEqual({ envoyées: [], abandonnées: [], restantes: [] })
  })

  it('oublie tout à la déconnexion', () => {
    enqueue(cotisation('c1'))
    clearQueue()
    expect(readQueue()).toEqual([])
  })
})
