/** Маршруты кабинетов (покупатель, продавец, администратор). Страницы подключаются лениво. */
import { lazy, Suspense, type ComponentType } from 'react'
import type { RouteObject } from 'react-router'

import { Loading } from './components/ui'

function page(load: () => Promise<{ default: ComponentType }>) {
  const C = lazy(load)
  return (
    <Suspense fallback={<Loading />}>
      <C />
    </Suspense>
  )
}

type R = RouteObject & { seller?: boolean }

export const buyerRoutes: R[] = []
export const sellerRoutes: R[] = []
export const staffRoutes: R[] = []

export { page }
