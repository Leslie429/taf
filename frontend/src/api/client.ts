import type { TokenPair } from './types'

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1'

const ACCESS_KEY = 'tontine.access'
const REFRESH_KEY = 'tontine.refresh'

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export const tokenStore = {
  access: () => localStorage.getItem(ACCESS_KEY),
  refresh: () => localStorage.getItem(REFRESH_KEY),
  save({ access_token, refresh_token }: TokenPair) {
    localStorage.setItem(ACCESS_KEY, access_token)
    localStorage.setItem(REFRESH_KEY, refresh_token)
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

/**
 * Rafraîchissement en vol unique : si trois requêtes reçoivent 401 en même
 * temps, une seule appelle /auth/refresh et les deux autres attendent son
 * résultat. Sans cela on brûle le jeton de rafraîchissement en concurrence.
 */
let refreshing: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  const token = tokenStore.refresh()
  if (!token) return null

  refreshing ??= (async () => {
    try {
      const response = await fetch(`${BASE_URL}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: token }),
      })
      if (!response.ok) {
        tokenStore.clear()
        return null
      }
      const pair = (await response.json()) as TokenPair
      tokenStore.save(pair)
      return pair.access_token
    } finally {
      refreshing = null
    }
  })()

  return refreshing
}

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
    return JSON.stringify(body.detail ?? body)
  } catch {
    return response.statusText
  }
}

export async function request<T>(
  path: string,
  options: RequestInit & { auth?: boolean } = {},
): Promise<T> {
  const { auth = true, ...init } = options

  const send = (accessToken: string | null) =>
    fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...init.headers,
      },
    })

  let response = await send(auth ? tokenStore.access() : null)

  if (response.status === 401 && auth) {
    const renewed = await refreshAccessToken()
    if (renewed) response = await send(renewed)
  }

  if (!response.ok) {
    throw new ApiError(response.status, await readError(response))
  }
  if (response.status === 204) return undefined as T

  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown, options?: { auth?: boolean }) =>
    request<T>(path, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
      ...options,
    }),
}
