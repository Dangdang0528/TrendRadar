import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { api, clearToken, getToken, setToken } from './api/client'
import type { UserPublic } from './api/types'

interface AuthValue {
  user: UserPublic | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, nickname?: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserPublic | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    async function boot() {
      if (!getToken()) {
        setLoading(false)
        return
      }
      try {
        const me = await api.me()
        if (alive) setUser(me)
      } catch {
        clearToken()
      } finally {
        if (alive) setLoading(false)
      }
    }
    boot()
    return () => {
      alive = false
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const token = await api.login({ email, password })
    setToken(token.access_token)
    const me = await api.me()
    setUser(me)
  }, [])

  const register = useCallback(async (email: string, password: string, nickname?: string) => {
    await api.register({ email, password, nickname })
    // 注册后直接登录
    const token = await api.login({ email, password })
    setToken(token.access_token)
    const me = await api.me()
    setUser(me)
  }, [])

  const logout = useCallback(() => {
    clearToken()
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth 必须在 AuthProvider 内使用')
  return ctx
}