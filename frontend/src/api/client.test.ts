import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, api, tokenStore } from './client'

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })

const unauthorized = () =>
  new Response(JSON.stringify({ detail: 'Jeton expiré.' }), { status: 401 })

describe('client HTTP', () => {
  beforeEach(() => {
    localStorage.clear()
    tokenStore.save({
      access_token: 'vieux-jeton',
      refresh_token: 'jeton-refresh',
      token_type: 'bearer',
    })
  })

  afterEach(() => vi.restoreAllMocks())

  it('rejoue la requête après avoir rafraîchi le jeton', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(unauthorized())
      .mockResolvedValueOnce(
        okJson({ access_token: 'neuf', refresh_token: 'neuf-r', token_type: 'bearer' }),
      )
      .mockResolvedValueOnce(okJson({ id: '1' }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.get('/auth/me')).resolves.toEqual({ id: '1' })
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(tokenStore.access()).toBe('neuf')
  })

  it("ne rafraîchit qu'une fois pour plusieurs 401 simultanés", async () => {
    const fetchMock = vi.fn<typeof fetch>(async (input) => {
      const url = String(input)
      if (url.endsWith('/auth/refresh')) {
        return okJson({ access_token: 'neuf', refresh_token: 'r', token_type: 'bearer' })
      }
      // Les premières requêtes portent l'ancien jeton et échouent.
      return tokenStore.access() === 'neuf' ? okJson({ ok: true }) : unauthorized()
    })
    vi.stubGlobal('fetch', fetchMock)

    await Promise.all([api.get('/a'), api.get('/b'), api.get('/c')])

    const refreshCalls = fetchMock.mock.calls.filter(([input]) =>
      String(input).endsWith('/auth/refresh'),
    )
    expect(refreshCalls).toHaveLength(1)
  })

  it('efface les jetons quand le rafraîchissement est refusé', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(async () => unauthorized()),
    )

    await expect(api.get('/auth/me')).rejects.toBeInstanceOf(ApiError)
    expect(tokenStore.access()).toBeNull()
  })
})
