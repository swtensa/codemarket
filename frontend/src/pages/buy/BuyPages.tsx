import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router'

import { client, unwrap } from '../../api/client'
import { Breadcrumbs, ErrorState, FormError, Loading } from '../../components/ui'
import { useTitle } from '../../hooks/misc'
import { useToast } from '../../hooks/useToast'
import { errorText } from '../../lib/forms'
import { formatMoney } from '../../lib/format'
import { goToPayment } from '../../lib/nav'

/** Оформление покупки: что покупается, что будет после оплаты, логин GitHub, согласие с лицензией. */
export function BuyPage() {
  const { slug = '' } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const q = useQuery({
    queryKey: ['buy', slug],
    queryFn: () => unwrap(client.GET('/api/purchases/buy/{slug}', { params: { path: { slug } } })),
  })
  const [github, setGithub] = useState<string | null>(null)
  const [accept, setAccept] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useTitle(q.data ? `Покупка: ${q.data.product.title}` : 'Покупка')
  useEffect(() => {
    if (q.data?.error) {
      toast.push(q.data.error, 'danger')
      navigate(`/p/${slug}/`, { replace: true })
    }
  }, [q.data, slug, navigate, toast])

  if (q.isLoading) return <Loading />
  if (q.isError || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  if (d.existing_purchase_id) return <Navigate to={`/me/purchases/${d.existing_purchase_id}/`} replace />
  if (d.error) return null

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!accept) {
      setError('Нужно принять условия лицензии.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const r = await unwrap(
        client.POST('/api/purchases', {
          body: { slug, github_login: github ?? d.github_login, accept_license: accept },
        }),
      )
      goToPayment(r.url, navigate)
    } catch (err) {
      setError(errorText(err))
      setBusy(false)
    }
  }
  return (
    <>
      <Breadcrumbs
        items={[
          { to: '/', label: 'Каталог' },
          { to: `/p/${slug}/`, label: d.product.title },
          { label: 'Оформление покупки' },
        ]}
      />
      <div className="row justify-content-center">
        <div className="col-lg-8">
          <h1 className="h3 mb-3">Оформление покупки</h1>
          <div className="card mb-3">
            <div className="card-body p-4">
              <div className="d-flex gap-3 align-items-center flex-wrap">
                {d.product.cover && (
                  <img
                    src={d.product.cover}
                    alt=""
                    className="rounded"
                    style={{ width: 120, aspectRatio: '16/10', objectFit: 'cover' }}
                  />
                )}
                <div className="flex-grow-1">
                  <div className="fw-bold fs-5">{d.product.title}</div>
                  <div className="small text-muted">
                    Продавец {d.product.seller} · версия {d.version?.tag_name ?? '—'}
                  </div>
                </div>
                <div className="cm-price fs-3">{formatMoney(d.product.price)}</div>
              </div>
            </div>
          </div>
          <div className="card mb-3">
            <div className="card-body p-4">
              <h2 className="h6">Что будет после оплаты</h2>
              <ul className="mb-0">
                <li>
                  <i className="bi bi-github me-1" />
                  Приглашение в закрытый репозиторий с кодом: получайте обновления через <code>git pull</code>
                  .
                </li>
                <li>
                  <i className="bi bi-file-zip me-1" />
                  Скачивание ZIP одобренной версии со страницы покупки.
                </li>
                <li>
                  <i className="bi bi-arrow-repeat me-1" />
                  Все будущие версии бесплатно и без срока.
                </li>
                <li>
                  <i className="bi bi-shield-check me-1" />
                  {d.hold_days} дней на спор, если продукт не работает или не соответствует описанию. Деньги
                  продавцу переводятся только после этого срока.
                </li>
                <li>
                  <i className="bi bi-info-circle me-1" />
                  Возврат по причине «передумал» не предусмотрен: после выдачи кода деньги возвращаются только
                  по решению администратора.{' '}
                  <Link to="/legal/terms/#refunds" target="_blank">
                    Правила возврата
                  </Link>
                </li>
              </ul>
            </div>
          </div>
          <form className="card" onSubmit={submit} noValidate>
            <div className="card-body p-4">
              <FormError error={error} />
              <div className="mb-3">
                <label className="form-label fw-semibold" htmlFor="github_login">
                  Логин GitHub
                </label>
                <input
                  className="form-control"
                  id="github_login"
                  placeholder="например, octocat"
                  value={github ?? d.github_login}
                  onChange={(e) => setGithub(e.target.value)}
                />
                <div className="form-text">
                  На этот логин придёт приглашение в репозиторий. Можно указать позже, ZIP доступен и без
                  GitHub.
                </div>
              </div>
              <div className="form-check mb-3">
                <input
                  className="form-check-input"
                  type="checkbox"
                  id="accept_license"
                  checked={accept}
                  onChange={(e) => setAccept(e.target.checked)}
                />
                <label className="form-check-label" htmlFor="accept_license">
                  Принимаю условия{' '}
                  <Link to="/legal/license/" target="_blank">
                    стандартной лицензии
                  </Link>{' '}
                  и{' '}
                  <Link to="/legal/terms/" target="_blank">
                    пользовательского соглашения
                  </Link>{' '}
                  <span className="required-mark">*</span>
                </label>
              </div>
              <button className="btn btn-accent btn-lg w-100" type="submit" disabled={busy}>
                <i className="bi bi-credit-card me-1" />
                Оплатить {formatMoney(d.product.price)}
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  )
}

/** Тестовая платёжная страница (PAYMENT_PROVIDER=fake): «Оплатить» или «Отклонить». */
export function FakeCheckoutPage() {
  useTitle('Оплата')
  const { externalId = '' } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const qc = useQueryClient()
  const [busy, setBusy] = useState(false)
  const q = useQuery({
    queryKey: ['fake-payment', externalId],
    queryFn: () =>
      unwrap(
        client.GET('/api/payments/fake/{external_id}', { params: { path: { external_id: externalId } } }),
      ),
  })
  if (q.isLoading) return <Loading />
  if (q.isError || !q.data) return <ErrorState error={q.error} />
  const act = async (action: 'pay' | 'decline') => {
    setBusy(true)
    try {
      const r = await unwrap(
        client.POST('/api/payments/fake/{external_id}', {
          params: { path: { external_id: externalId } },
          body: { action },
        }),
      )
      toast.push(r.message, r.level as 'success' | 'danger' | 'info')
      void qc.invalidateQueries()
      navigate(r.url, { replace: true })
    } catch (e) {
      toast.push(errorText(e), 'danger')
      setBusy(false)
    }
  }
  return (
    <div className="row justify-content-center py-4">
      <div className="col-md-7 col-lg-5">
        <div className="card shadow-sm">
          <div className="card-body p-4 text-center">
            <div className="small text-muted mb-2">
              <i className="bi bi-credit-card-2-front me-1" />
              Тестовая платёжная страница (PAYMENT_PROVIDER=fake)
            </div>
            <h1 className="h4">{q.data.description}</h1>
            <div className="cm-price fs-1 my-3">{formatMoney(q.data.amount)}</div>
            <p className="small text-muted">
              Настоящие деньги не списываются. В рабочем режиме здесь будет страница ЮKassa.
            </p>
            {q.data.status === 'pending' ? (
              <div className="d-grid gap-2">
                <button className="btn btn-accent btn-lg" onClick={() => act('pay')} disabled={busy}>
                  <i className="bi bi-check-lg me-1" />
                  Оплатить
                </button>
                <button className="btn btn-outline-danger" onClick={() => act('decline')} disabled={busy}>
                  Отклонить
                </button>
              </div>
            ) : (
              <div className="alert alert-info mb-0">Платёж уже обработан.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

/** Возврат со страницы оплаты ЮKassa: проверить статус и перейти к покупке или заказу. */
export function PaymentReturnPage() {
  useTitle('Проверка оплаты')
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const qc = useQueryClient()
  const [error, setError] = useState<unknown>(null)
  const done = useRef(false)
  useEffect(() => {
    if (done.current) return
    done.current = true
    unwrap(client.GET('/api/payments/return/{pk}', { params: { path: { pk: Number(id) } } }))
      .then((r) => {
        toast.push(r.message, r.level as 'success' | 'danger' | 'info')
        void qc.invalidateQueries()
        navigate(r.url, { replace: true })
      })
      .catch(setError)
  }, [id, navigate, toast, qc])
  return error ? <ErrorState error={error} /> : <Loading text="Проверяем оплату…" />
}
