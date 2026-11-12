import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, NavLink, useNavigate, useParams, useSearchParams } from 'react-router'

import { ApiError, client, unwrap } from '../../api/client'
import {
  Breadcrumbs,
  CopyButton,
  EmptyState,
  ErrorState,
  Field,
  FormError,
  Loading,
  Pagination,
  Stars,
  StatusBadge,
} from '../../components/ui'
import { useTitle, useUnreadCount } from '../../hooks/misc'
import { useAuth } from '../../hooks/useAuth'
import { useToast } from '../../hooks/useToast'
import { errorText } from '../../lib/forms'
import { formatDateTime, formatMoney, plural } from '../../lib/format'

export function MeTabs() {
  const unread = useUnreadCount()
  const tab = (to: string, label: string, badge?: number) => (
    <li className="nav-item">
      <NavLink className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} to={to}>
        {label}
        {badge ? <span className="badge rounded-pill text-bg-danger ms-1">{badge}</span> : null}
      </NavLink>
    </li>
  )
  return (
    <>
      <h1 className="h3 mb-3">Личный кабинет</h1>
      <ul className="nav nav-tabs mb-4">
        {tab('/me/purchases/', 'Покупки')}
        {tab('/me/orders/', 'Заказы')}
        {tab('/notifications/', 'Уведомления', unread)}
        {tab('/me/profile/', 'Профиль')}
      </ul>
    </>
  )
}

function usePage() {
  const [params] = useSearchParams()
  return Number(params.get('page') ?? '1') || 1
}

// ---------------------------------------------------------------- покупки

export function PurchasesPage() {
  useTitle('Мои покупки')
  const page = usePage()
  const q = useQuery({
    queryKey: ['purchases', page],
    queryFn: () => unwrap(client.GET('/api/purchases', { params: { query: { page } } })),
  })
  return (
    <>
      <MeTabs />
      {q.isLoading ? (
        <Loading />
      ) : q.isError || !q.data ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data.items.length ? (
        <>
          <div className="card">
            <div className="table-responsive">
              <table className="table table-hover align-middle mb-0">
                <thead>
                  <tr>
                    <th>Продукт</th>
                    <th>Дата</th>
                    <th className="text-end">Цена</th>
                    <th>Статус</th>
                    <th>Доступ</th>
                  </tr>
                </thead>
                <tbody>
                  {q.data.items.map((p) => (
                    <tr key={p.id}>
                      <td>
                        <Link className="fw-semibold" to={`/me/purchases/${p.id}/`}>
                          {p.product.title}
                        </Link>
                      </td>
                      <td className="small text-nowrap">{formatDateTime(p.created_at)}</td>
                      <td className="text-end text-nowrap">{formatMoney(p.price)}</td>
                      <td>
                        <StatusBadge status={p.status} label={p.status_label} />
                      </td>
                      <td>
                        <StatusBadge status={p.access_status} label={p.access_label} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <Pagination page={q.data.page} pages={q.data.pages} />
        </>
      ) : (
        <div className="card">
          <EmptyState icon="bi-bag" title="Покупок пока нет">
            <Link className="btn btn-primary mt-2" to="/">
              Перейти в каталог
            </Link>
          </EmptyState>
        </div>
      )}
    </>
  )
}

function bannerTone(status: string) {
  if (status === 'paid' || status === 'completed') return 'success'
  if (status === 'pending') return 'warning'
  if (status === 'cancelled') return 'neutral'
  return 'danger'
}

export function PurchaseDetailPage() {
  const { id = '' } = useParams()
  const pk = Number(id)
  const qc = useQueryClient()
  const toast = useToast()
  const { user } = useAuth()
  const q = useQuery({
    queryKey: ['purchase', pk],
    queryFn: () => unwrap(client.GET('/api/purchases/{pk}', { params: { path: { pk } } })),
  })
  const [login, setLogin] = useState<string | null>(null)
  const access = useMutation({
    mutationFn: () =>
      unwrap(
        client.POST('/api/purchases/{pk}/access', {
          params: { path: { pk } },
          body: { github_login: login ?? user?.github_login ?? '' },
        }),
      ),
    onSuccess: (r) => {
      toast.push(r.message)
      void qc.invalidateQueries({ queryKey: ['purchase', pk] })
      void qc.invalidateQueries({ queryKey: ['me'] })
    },
    onError: (e) => toast.push(errorText(e), 'danger'),
  })
  useTitle(q.data ? `Покупка №${q.data.id}` : 'Покупка')
  if (q.isLoading) return <Loading />
  if (q.isError || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const p = q.data
  const active = ['paid', 'completed', 'partially_refunded'].includes(p.status)
  const repoName = p.mirror_url.replace('https://github.com/', '')

  return (
    <>
      <Breadcrumbs items={[{ to: '/me/purchases/', label: 'Покупки' }, { label: p.product.title }]} />
      <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
        <h1 className="h3 mb-0 me-auto">{p.product.title}</h1>
        <Link className="btn btn-sm btn-outline-primary" to={`/p/${p.product.slug}/`}>
          Страница продукта
        </Link>
      </div>
      <div
        className={`cm-banner-status cm-status-${bannerTone(p.status)} mb-4 d-flex flex-wrap gap-3 align-items-center`}
      >
        <span>
          <i
            className={`bi ${p.status === 'paid' || p.status === 'completed' ? 'bi-check-circle-fill' : 'bi-info-circle-fill'} me-1`}
          />
          {p.status_label}
        </span>
        <span className="fw-normal small">
          Покупка №{p.id} от {formatDateTime(p.created_at)} · {formatMoney(p.price)}
          {p.paid_at && ` · оплачена ${formatDateTime(p.paid_at)}`} · лицензия {p.license_version}
        </span>
      </div>
      {p.status === 'pending' && (
        <div className="alert alert-warning d-flex gap-2">
          <i className="bi bi-hourglass-split" />
          <div>
            Покупка ждёт оплаты. <Link to={`/buy/${p.product.slug}/`}>Перейти к оплате</Link>
          </div>
        </div>
      )}
      <div className="row g-4">
        <div className="col-lg-7">
          <div className="card mb-4">
            <div className="card-body p-4">
              <h2 className="h5">
                <i className="bi bi-code-square me-1" />
                Доступ к коду
              </h2>
              {p.access_status === 'revoked' ? (
                <div className="alert alert-danger d-flex gap-2 mb-0">
                  <i className="bi bi-slash-circle-fill" />
                  <div>Доступ к коду отозван после возврата денег.</div>
                </div>
              ) : p.status === 'pending' || p.status === 'cancelled' ? (
                <p className="text-muted mb-0">Доступ появится после оплаты.</p>
              ) : (
                <>
                  <dl className="row mb-3">
                    <dt className="col-sm-4 fw-normal text-muted">Репозиторий</dt>
                    <dd className="col-sm-8">
                      {p.mirror_url ? (
                        <a href={p.mirror_url} target="_blank" rel="noopener noreferrer">
                          {repoName}
                        </a>
                      ) : (
                        '—'
                      )}
                    </dd>
                    <dt className="col-sm-4 fw-normal text-muted">Приглашение</dt>
                    <dd className="col-sm-8">
                      <StatusBadge status={p.access_status} label={p.access_label} />
                    </dd>
                  </dl>
                  {p.access_status === 'none' ? (
                    <form
                      className="row g-2 align-items-end mb-3"
                      onSubmit={(e: FormEvent) => {
                        e.preventDefault()
                        access.mutate()
                      }}
                    >
                      <div className="col-sm-7">
                        <label className="form-label small fw-semibold" htmlFor="gh">
                          Логин GitHub
                        </label>
                        <input
                          className="form-control"
                          id="gh"
                          placeholder="octocat"
                          value={login ?? p.github_login}
                          onChange={(e) => setLogin(e.target.value)}
                        />
                      </div>
                      <div className="col-sm-5">
                        <button className="btn btn-primary w-100" disabled={access.isPending}>
                          <i className="bi bi-github me-1" />
                          Получить доступ
                        </button>
                      </div>
                    </form>
                  ) : (
                    <>
                      <p className="small mb-1">Примите приглашение на GitHub и выполните:</p>
                      <div className="input-group mb-3 flex-nowrap">
                        <code className="form-control bg-light text-truncate">{p.clone_command}</code>
                        <CopyButton text={p.clone_command} />
                      </div>
                      <p className="small text-muted">
                        Обновления: <code>git pull</code> в папке проекта.
                      </p>
                    </>
                  )}
                  {p.can_download && (
                    <a className="btn btn-outline-primary" href={`/api/purchases/${p.id}/download`}>
                      <i className="bi bi-file-zip me-1" />
                      Скачать ZIP
                    </a>
                  )}
                </>
              )}
            </div>
          </div>
          <div className="card">
            <div className="card-body p-4">
              <h2 className="h5">
                <i className="bi bi-tags me-1" />
                Версии
              </h2>
              <ul className="list-group list-group-flush">
                {p.versions.length ? (
                  p.versions.map((v) => (
                    <li key={v.id} className="list-group-item px-0 d-flex justify-content-between">
                      <span className="fw-semibold">
                        {v.tag_name}{' '}
                        {p.paid_at && v.approved_at && v.approved_at > p.paid_at && (
                          <span className="cm-status cm-status-success ms-1">новая</span>
                        )}
                      </span>
                      <span className="small text-muted">{formatDateTime(v.approved_at)}</span>
                    </li>
                  ))
                ) : (
                  <li className="list-group-item px-0 text-muted">Нет одобренных версий</li>
                )}
              </ul>
            </div>
          </div>
        </div>
        <div className="col-lg-5">
          <div className="card mb-3">
            <div className="card-body p-4 d-grid gap-2">
              {active && (
                <>
                  <Link className="btn btn-cream" to={`/orders/new/?purchase=${p.id}`}>
                    <i className="bi bi-tools me-1" />
                    Заказать доработку
                  </Link>
                  {p.review ? (
                    <div className="small text-muted text-center">
                      Ваш отзыв: <Stars value={p.review.rating} />
                    </div>
                  ) : p.can_review ? (
                    <Link className="btn btn-outline-primary" to={`/reviews/new/?purchase=${p.id}`}>
                      <i className="bi bi-star me-1" />
                      Оставить отзыв
                    </Link>
                  ) : null}
                </>
              )}
              {p.status === 'paid' && p.dispute_days_left > 0 ? (
                <>
                  <Link className="btn btn-outline-danger" to={`/disputes/new/?purchase=${p.id}`}>
                    <i className="bi bi-exclamation-octagon me-1" />
                    Открыть спор
                  </Link>
                  <div className="small text-muted text-center">
                    Осталось {p.dispute_days_left} {plural(p.dispute_days_left, ['день', 'дня', 'дней'])} на
                    открытие спора
                  </div>
                </>
              ) : p.status === 'dispute' ? (
                <div className="alert alert-danger d-flex gap-2 mb-0">
                  <i className="bi bi-exclamation-octagon-fill" />
                  <div>Открыт спор. Администратор рассмотрит его и сообщит решение.</div>
                </div>
              ) : null}
              {!active && p.status !== 'paid' && p.status !== 'dispute' && (
                <div className="small text-muted text-center">Действий нет</div>
              )}
            </div>
          </div>
          {p.orders.length > 0 && (
            <div className="card">
              <div className="card-body">
                <h2 className="h6">Заказы по этой покупке</h2>
                {p.orders.map((o) => (
                  <div key={o.id} className="d-flex justify-content-between small py-1">
                    <Link to={`/orders/${o.id}/`}>Заказ №{o.id}</Link>
                    <StatusBadge status={o.status} label={o.status_label} />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}

// ---------------------------------------------------------------- заказы покупателя

export function BuyerOrdersPage() {
  useTitle('Мои заказы')
  const page = usePage()
  const q = useQuery({
    queryKey: ['buyer-orders', page],
    queryFn: () => unwrap(client.GET('/api/orders', { params: { query: { page } } })),
  })
  return (
    <>
      <MeTabs />
      {q.isLoading ? (
        <Loading />
      ) : q.isError || !q.data ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data.items.length ? (
        <>
          <div className="card">
            <div className="table-responsive">
              <table className="table table-hover align-middle mb-0">
                <thead>
                  <tr>
                    <th>Продукт</th>
                    <th>Тип</th>
                    <th>Статус</th>
                    <th className="text-end">Сумма</th>
                    <th>Крайний срок</th>
                  </tr>
                </thead>
                <tbody>
                  {q.data.items.map((o) => (
                    <tr key={o.id}>
                      <td>
                        <Link className="fw-semibold" to={`/orders/${o.id}/`}>
                          №{o.id} · {o.product.title}
                        </Link>
                        {o.unread > 0 && (
                          <span className="badge rounded-pill text-bg-danger ms-2">{o.unread}</span>
                        )}
                      </td>
                      <td className="small">{o.kind_label}</td>
                      <td>
                        <StatusBadge status={o.status} label={o.status_label} />
                      </td>
                      <td className="text-end text-nowrap">{o.price ? formatMoney(o.price) : '—'}</td>
                      <td className="small text-nowrap">{formatDateTime(o.deadline)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <Pagination page={q.data.page} pages={q.data.pages} />
        </>
      ) : (
        <div className="card">
          <EmptyState icon="bi-chat-square-text" title="Заказов и вопросов пока нет">
            <Link className="btn btn-primary mt-2" to="/">
              Найти продукт
            </Link>
          </EmptyState>
        </div>
      )}
    </>
  )
}

// ---------------------------------------------------------------- уведомления

export function NotificationsPage() {
  useTitle('Уведомления')
  const page = usePage()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const toast = useToast()
  const unread = useUnreadCount()
  const q = useQuery({
    queryKey: ['notifications', page],
    queryFn: () => unwrap(client.GET('/api/notifications', { params: { query: { page } } })),
  })
  const readAll = useMutation({
    mutationFn: () => unwrap(client.POST('/api/notifications/read-all')),
    onSuccess: (r) => {
      toast.push(r.message)
      void qc.invalidateQueries({ queryKey: ['notifications'] })
      void qc.invalidateQueries({ queryKey: ['unread'] })
    },
  })
  const open = async (id: number) => {
    try {
      const r = await unwrap(client.POST('/api/notifications/{pk}/open', { params: { path: { pk: id } } }))
      void qc.invalidateQueries({ queryKey: ['unread'] })
      void qc.invalidateQueries({ queryKey: ['notifications'] })
      navigate(r.url)
    } catch (e) {
      toast.push(errorText(e), 'danger')
    }
  }
  return (
    <>
      <MeTabs />
      <div className="d-flex align-items-center mb-3">
        <h2 className="h5 mb-0 me-auto">Уведомления</h2>
        {unread > 0 && (
          <button
            className="btn btn-sm btn-outline-primary"
            onClick={() => readAll.mutate()}
            disabled={readAll.isPending}
          >
            <i className="bi bi-check2-all me-1" />
            Отметить всё прочитанным
          </button>
        )}
      </div>
      {q.isLoading ? (
        <Loading />
      ) : q.isError || !q.data ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data.items.length ? (
        <>
          <div className="list-group">
            {q.data.items.map((n) => (
              <button
                key={n.id}
                type="button"
                className={`list-group-item list-group-item-action d-flex gap-3 align-items-start text-start ${n.is_read ? '' : 'fw-semibold'}`}
                style={n.is_read ? undefined : { background: 'var(--c-sage-light)' }}
                onClick={() => open(n.id)}
              >
                <i className={`bi ${n.is_read ? 'bi-bell text-muted' : 'bi-bell-fill'} mt-1`} />
                <div className="flex-grow-1">{n.text}</div>
                <div className="small text-muted text-nowrap fw-normal">{formatDateTime(n.created_at)}</div>
              </button>
            ))}
          </div>
          <Pagination page={q.data.page} pages={q.data.pages} />
        </>
      ) : (
        <div className="card">
          <EmptyState icon="bi-bell-slash" title="Уведомлений пока нет">
            <Link className="btn btn-primary mt-2" to="/">
              В каталог
            </Link>
          </EmptyState>
        </div>
      )}
    </>
  )
}

// ---------------------------------------------------------------- профиль

export function ProfilePage() {
  useTitle('Профиль')
  const { user, setUser } = useAuth()
  const toast = useToast()
  const [username, setUsername] = useState(user?.username ?? '')
  const [github, setGithub] = useState(user?.github_login ?? '')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  if (!user) return null
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setErrors({})
    setError('')
    try {
      const u = await unwrap(client.PUT('/api/profile', { body: { username, github_login: github } }))
      setUser(u)
      setGithub(u.github_login)
      toast.push('Профиль сохранён.')
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fields).length) setErrors(err.fields)
      else setError(errorText(err))
    }
  }
  return (
    <>
      <MeTabs />
      <div className="row g-4">
        <div className="col-lg-6">
          <div className="card">
            <div className="card-body p-4">
              <h2 className="h5 mb-3">Профиль</h2>
              <form onSubmit={submit} noValidate>
                <FormError error={error} />
                <div className="mb-3">
                  <label className="form-label fw-semibold" htmlFor="email">
                    Email
                  </label>
                  <input id="email" className="form-control" value={user.email} disabled />
                </div>
                <Field
                  label="Имя пользователя"
                  id="username"
                  required
                  error={errors.username}
                  help="3–30 символов: латинские буквы, цифры, «_»."
                >
                  <input
                    id="username"
                    className="form-control"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                  />
                </Field>
                <Field
                  label="Логин GitHub"
                  id="github_login"
                  error={errors.github_login}
                  help="Нужен, чтобы получить доступ к купленному коду через GitHub."
                >
                  <input
                    id="github_login"
                    className="form-control"
                    value={github}
                    onChange={(e) => setGithub(e.target.value)}
                  />
                </Field>
                <button className="btn btn-primary" type="submit">
                  Сохранить
                </button>
              </form>
            </div>
          </div>
        </div>
        <div className="col-lg-6">
          <div className="card">
            <div className="card-body p-4">
              <h2 className="h5 mb-3">Безопасность</h2>
              <p className="text-muted">Зарегистрирован {formatDateTime(user.created_at)}</p>
              <Link className="btn btn-outline-primary" to="/accounts/password/change/">
                <i className="bi bi-key me-1" />
                Сменить пароль
              </Link>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
