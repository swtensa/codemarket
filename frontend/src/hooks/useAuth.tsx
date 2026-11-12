/* eslint-disable react-refresh/only-export-components */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, type ReactNode } from 'react'

import { ApiError, client, unwrap, type S } from '../api/client'

type AuthCtx = {
  user: S['UserOut'] | null
  config: S['SiteConfig'] | null
  loading: boolean
  blockedReason: string
  setUser: (user: S['UserOut'] | null) => void
  reloadUser: () => Promise<unknown>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthCtx | null>(null)

/** Текущий пользователь (/api/auth/me) и параметры площадки (/api/auth/config). */
export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const me = useQuery({
    queryKey: ['me'],
    queryFn: () => unwrap(client.GET('/api/auth/me')),
    staleTime: 60_000,
    retry: false,
  })
  const config = useQuery({
    queryKey: ['config'],
    queryFn: () => unwrap(client.GET('/api/auth/config')),
    staleTime: Infinity,
  })
  // Смена пользователя: убрать данные прежнего (кроме me и config), затем записать нового
  const setUser = useCallback(
    (user: S['UserOut'] | null) => {
      qc.removeQueries({ predicate: (q) => !['me', 'config'].includes(String(q.queryKey[0])) })
      qc.setQueryData(['me'], user)
    },
    [qc],
  )
  const logout = useCallback(async () => {
    await client.POST('/api/auth/logout')
    setUser(null)
  }, [setUser])

  const error = me.error as ApiError | null
  const blockedReason = error?.status === 403 ? error.message : ''
  useEffect(() => {
    if (blockedReason) qc.setQueryData(['me'], null)
  }, [blockedReason, qc])

  const value: AuthCtx = {
    user: me.data ?? null,
    config: config.data ?? null,
    loading: me.isLoading,
    blockedReason,
    setUser,
    reloadUser: () => me.refetch(),
    logout,
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthCtx {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth вне AuthProvider')
  return ctx
}
