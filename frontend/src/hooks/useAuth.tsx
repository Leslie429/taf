import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { api, tokenStore } from '@/api/client'
import type { TokenPair, User } from '@/api/types'

interface AuthValue {
  user: User | null
  isLoading: boolean
  login: (phone: string, password: string) => Promise<void>
  register: (phone: string, fullName: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [hasToken, setHasToken] = useState(() => tokenStore.access() !== null)
  const queryClient = useQueryClient()

  const { data: user, isLoading } = useQuery({
    queryKey: ['me'],
    queryFn: () => api.get<User>('/auth/me'),
    enabled: hasToken,
    retry: false,
  })

  const authenticate = useCallback(
    async (path: string, body: unknown) => {
      const pair = await api.post<TokenPair>(path, body, { auth: false })
      tokenStore.save(pair)
      setHasToken(true)
      await queryClient.invalidateQueries({ queryKey: ['me'] })
    },
    [queryClient],
  )

  const value = useMemo<AuthValue>(
    () => ({
      user: user ?? null,
      isLoading: hasToken && isLoading,
      login: (phone, password) => authenticate('/auth/login', { phone, password }),
      register: (phone, full_name, password) =>
        authenticate('/auth/register', { phone, full_name, password }),
      logout: () => {
        tokenStore.clear()
        setHasToken(false)
        queryClient.clear()
      },
    }),
    [user, hasToken, isLoading, authenticate, queryClient],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const context = useContext(AuthContext)
  if (context === null) {
    throw new Error('useAuth doit être utilisé dans un AuthProvider.')
  }
  return context
}
