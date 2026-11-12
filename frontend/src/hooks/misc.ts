import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'

import { client, unwrap } from '../api/client'
import { useAuth } from './useAuth'

/** Заголовок вкладки «<страница> — CodeMarket». */
export function useTitle(title: string | undefined) {
  useEffect(() => {
    document.title = title ? `${title} — CodeMarket` : 'CodeMarket'
  }, [title])
}

/** Число непрочитанных уведомлений; обновляется раз в 30 секунд. */
export function useUnreadCount() {
  const { user } = useAuth()
  const q = useQuery({
    queryKey: ['unread'],
    queryFn: () => unwrap(client.GET('/api/notifications/unread')),
    enabled: !!user,
    refetchInterval: 30_000,
  })
  return user ? (q.data?.count ?? 0) : 0
}
