import { createBrowserRouter } from 'react-router'

import { RequireAuth, RequireSeller, RequireStaff } from './components/guards'
import { Layout } from './components/Layout'
import { NotFoundBlock } from './components/ui'
import {
  BlockedPage,
  LoginPage,
  PasswordChangePage,
  PasswordResetConfirmPage,
  PasswordResetPage,
} from './pages/auth/AuthPages'
import RegisterPage from './pages/auth/RegisterPage'
import CatalogPage from './pages/catalog/CatalogPage'
import ProductPage from './pages/catalog/ProductPage'
import LegalPage from './pages/LegalPage'
import { buyerRoutes, sellerRoutes, staffRoutes } from './routes'

/** Адреса страниц (/, /p/<slug>/, /me/…, /sell/…, /orders/<id>/, /moderation/…, /legal/…). */
export const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: '/', element: <CatalogPage /> },
      { path: '/p/:slug/', element: <ProductPage /> },
      { path: '/legal/:doc/', element: <LegalPage /> },
      { path: '/accounts/login/', element: <LoginPage /> },
      { path: '/accounts/register/', element: <RegisterPage /> },
      { path: '/accounts/blocked/', element: <BlockedPage /> },
      { path: '/accounts/password/reset/', element: <PasswordResetPage /> },
      { path: '/accounts/password/reset/:token/', element: <PasswordResetConfirmPage /> },
      {
        element: <RequireAuth />,
        children: [
          { path: '/accounts/password/change/', element: <PasswordChangePage /> },
          ...buyerRoutes,
          { element: <RequireSeller />, children: sellerRoutes.filter((r) => r.seller) },
          ...sellerRoutes.filter((r) => !r.seller),
          { element: <RequireStaff />, children: staffRoutes },
        ],
      },
      { path: '*', element: <NotFoundBlock /> },
    ],
  },
])
