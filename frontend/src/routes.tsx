/** Маршруты кабинетов (покупатель, продавец, администратор). Страницы подключаются лениво. */
import { lazy, Suspense, type ComponentType } from 'react'
import type { RouteObject } from 'react-router'

import { Loading } from './components/ui'

function page<M>(load: () => Promise<M>, pick: (m: M) => ComponentType) {
  const C = lazy(() => load().then((m) => ({ default: pick(m) })))
  return (
    <Suspense fallback={<Loading />}>
      <C />
    </Suspense>
  )
}

const me = () => import('./pages/me/MePages')
const buy = () => import('./pages/buy/BuyPages')
const orders = () => import('./pages/orders/OrderPages')
const forms = () => import('./pages/orders/FormPages')
const sell = () => import('./pages/sell/SellPages')
const stats = () => import('./pages/sell/StatsBalance')
const mod = () => import('./pages/moderation/ModPages')

type R = RouteObject & { seller?: boolean }

export const buyerRoutes: R[] = [
  { path: '/me/', element: page(me, (m) => m.PurchasesPage) },
  { path: '/me/purchases/', element: page(me, (m) => m.PurchasesPage) },
  { path: '/me/purchases/:id/', element: page(me, (m) => m.PurchaseDetailPage) },
  { path: '/me/orders/', element: page(me, (m) => m.BuyerOrdersPage) },
  { path: '/me/profile/', element: page(me, (m) => m.ProfilePage) },
  { path: '/notifications/', element: page(me, (m) => m.NotificationsPage) },
  { path: '/buy/:slug/', element: page(buy, (m) => m.BuyPage) },
  { path: '/payments/fake/:externalId/', element: page(buy, (m) => m.FakeCheckoutPage) },
  { path: '/payments/return/:id/', element: page(buy, (m) => m.PaymentReturnPage) },
  { path: '/orders/new/', element: page(orders, (m) => m.OrderNewPage) },
  { path: '/orders/:id/', element: page(orders, (m) => m.OrderDetailPage) },
  { path: '/disputes/new/', element: page(forms, (m) => m.DisputeNewPage) },
  { path: '/reviews/new/', element: page(forms, (m) => m.ReviewNewPage) },
  { path: '/balance/', element: page(stats, (m) => m.BalancePage) },
]

export const sellerRoutes: R[] = [
  { path: '/sell/', element: page(sell, (m) => m.SellDashboardPage) },
  { path: '/sell/github/', element: page(sell, (m) => m.GithubConnectPage) },
  { path: '/sell/github/callback/', element: page(sell, (m) => m.GithubCallbackPage) },
  { path: '/sell/orders/', element: page(sell, (m) => m.SellerOrdersPage) },
  { seller: true, path: '/sell/stats/', element: page(stats, (m) => m.SellerStatsPage) },
  { seller: true, path: '/sell/products/new/', element: page(sell, (m) => m.ProductWizardPage) },
  { seller: true, path: '/sell/products/:id/edit/', element: page(sell, (m) => m.ProductEditPage) },
  { seller: true, path: '/sell/products/:id/media/', element: page(sell, (m) => m.ProductMediaPage) },
  { seller: true, path: '/sell/products/:id/versions/', element: page(sell, (m) => m.VersionsPage) },
]

export const staffRoutes: R[] = [
  { path: '/moderation/', element: page(mod, (m) => m.QueuePage) },
  { path: '/moderation/versions/:id/', element: page(mod, (m) => m.VersionDetailPage) },
  { path: '/moderation/disputes/', element: page(mod, (m) => m.DisputesPage) },
  { path: '/moderation/disputes/:id/', element: page(mod, (m) => m.DisputeDetailPage) },
  { path: '/moderation/payouts/', element: page(mod, (m) => m.PayoutsPage) },
  { path: '/moderation/users/', element: page(mod, (m) => m.UsersPage) },
  { path: '/moderation/refs/', element: page(mod, (m) => m.RefsPage) },
  { path: '/moderation/reports/', element: page(mod, (m) => m.ReportsPage) },
]
