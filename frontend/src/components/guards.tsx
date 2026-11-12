import type { ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router'

import { useAuth } from '../hooks/useAuth'
import { ForbiddenBlock, Loading } from './ui'

/** Защищённые страницы: гость уходит на вход с возвратом обратно. */
export function RequireAuth({ children }: { children?: ReactNode }) {
  const { user, loading, blockedReason } = useAuth()
  const { pathname, search } = useLocation()
  if (loading) return <Loading />
  if (blockedReason) return <Navigate to="/accounts/blocked/" replace />
  if (!user) return <Navigate to={`/accounts/login/?next=${encodeURIComponent(pathname + search)}`} replace />
  return <>{children ?? <Outlet />}</>
}

/** Страницы администратора: только is_staff, остальным — «Доступ запрещён». */
export function RequireStaff({ children }: { children?: ReactNode }) {
  const { user } = useAuth()
  if (!user?.is_staff) return <ForbiddenBlock />
  return <>{children ?? <Outlet />}</>
}

/** Страницы продавца: без подключённого GitHub — на страницу «Продажи». */
export function RequireSeller({ children }: { children?: ReactNode }) {
  const { user } = useAuth()
  if (!user?.is_seller) return <Navigate to="/sell/" replace state={{ needGithub: true }} />
  return <>{children ?? <Outlet />}</>
}
