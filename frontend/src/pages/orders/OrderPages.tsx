import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'

import { client, unwrap } from '../../api/client'
import { Chat } from '../../components/Chat'
import { OrderActions, type OrderAction } from '../../components/OrderActions'
import { Breadcrumbs, ErrorState, FormError, Loading, StatusBadge } from '../../components/ui'
import { useTitle } from '../../hooks/misc'
import { useToast } from '../../hooks/useToast'
import { errorText } from '../../lib/forms'
import { formatDateTime, formatMoney, plural, timeLeft } from '../../lib/format'
import { goToPayment } from '../../lib/nav'

/** Создание заказа: вопрос, «Купить с доработкой» (?product=&kind=) или доработка купленного (?purchase=). */
export function OrderNewPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const product = params.get('product') ?? ''
  const purchase = params.get('purchase') ? Number(params.get('purchase')) : undefined
  const q = useQuery({
    queryKey: ['order-new', product, params.get('kind'), purchase],
    queryFn: () =>
      unwrap(
        client.GET('/api/orders/new', {
          params: { query: { product, kind: params.get('kind') ?? 'question', purchase } },
        }),
      ),
  })
  const [task, setTask] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const kind = q.data?.kind
  useTitle(kind === 'question' ? 'Вопрос продавцу' : 'Заказ доработки')
  if (q.isLoading) return <Loading />
  if (q.isError || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const o = await unwrap(
        client.POST('/api/orders', {
          body: { product_slug: d.product.slug, purchase_id: d.purchase_id, kind: d.kind, task },
        }),
      )
      toast.push(d.kind === 'question' ? 'Вопрос отправлен продавцу.' : 'Заказ создан.')
      navigate(`/orders/${o.id}/`)
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
          { to: `/p/${d.product.slug}/`, label: d.product.title },
          { label: d.kind === 'question' ? 'Вопрос' : 'Доработка' },
        ]}
      />
      <div className="row justify-content-center">
        <div className="col-lg-8">
          <h1 className="h3 mb-3">
            {d.kind === 'question'
              ? 'Задать вопрос продавцу'
              : d.kind === 'with_purchase'
                ? 'Купить с доработкой'
                : 'Заказать доработку'}
          </h1>
          <div className="card mb-3">
            <div className="card-body d-flex justify-content-between align-items-center">
              <div>
                <div className="fw-bold">{d.product.title}</div>
                <div className="small text-muted">Продавец {d.product.seller}</div>
              </div>
              <div className="cm-price fs-5">{formatMoney(d.product.price)}</div>
            </div>
          </div>
          <div className="alert alert-info d-flex gap-2">
            <i className="bi bi-info-circle-fill" />
            <div>
              {d.kind === 'question'
                ? 'Вопрос бесплатный. Если договоритесь о доработке, продавец предложит цену и срок прямо в переписке. Текст вопроса и первый ответ продавца будут видны на странице продукта без вашего имени.'
                : d.kind === 'with_purchase'
                  ? 'Опишите, что нужно доработать. Продавец предложит цену и срок, после согласия вы оплатите продукт и доработку одним платежом. Деньги за доработку продавец получит только после того, как вы примете работу.'
                  : 'Опишите, что нужно доработать в купленном продукте. Продавец предложит цену и срок. Оплата удерживается площадкой до приёмки работы.'}
            </div>
          </div>
          <form className="card" onSubmit={submit}>
            <div className="card-body p-4">
              <FormError error={error} />
              <label className="form-label fw-semibold" htmlFor="task">
                {d.kind === 'question' ? 'Ваш вопрос' : 'Задача'} <span className="required-mark">*</span>
              </label>
              <textarea
                className="form-control mb-3"
                id="task"
                rows={6}
                required
                minLength={5}
                value={task}
                onChange={(e) => setTask(e.target.value)}
                placeholder={
                  d.kind === 'question'
                    ? 'Например: подойдёт ли шаблон для WordPress?'
                    : 'Например: добавить форму обратной связи с отправкой в Telegram'
                }
              />
              <button className="btn btn-primary" type="submit" disabled={busy || d.is_owner}>
                {d.kind === 'question' ? 'Отправить вопрос' : 'Отправить заказ'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  )
}

/** Страница заказа: чат, шаги, условия, обратный отсчёт и кнопки по статусу. */
export function OrderDetailPage() {
  const { id = '' } = useParams()
  const pk = Number(id)
  const qc = useQueryClient()
  const toast = useToast()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const q = useQuery({
    queryKey: ['order', pk],
    queryFn: () => unwrap(client.GET('/api/orders/{pk}', { params: { path: { pk } } })),
  })
  const reload = useCallback(() => {
    void qc.invalidateQueries({ queryKey: ['order', pk] })
    void qc.invalidateQueries({ queryKey: ['unread'] })
  }, [qc, pk])
  const o = q.data
  useTitle(o ? `Заказ №${o.id}` : 'Заказ')
  if (q.isLoading) return <Loading />
  if (q.isError || !o) return <ErrorState error={q.error} onRetry={() => q.refetch()} />

  const path = { params: { path: { pk } } }
  const run = async (a: OrderAction) => {
    setBusy(true)
    try {
      if (a.type === 'accept_offer' || a.type === 'pay') {
        const r = await unwrap(
          a.type === 'pay'
            ? client.POST('/api/orders/{pk}/pay', path)
            : client.POST('/api/orders/{pk}/accept-offer', path),
        )
        goToPayment(r.url, navigate)
        return
      }
      let r
      if (a.type === 'offer')
        r = await unwrap(
          client.POST('/api/orders/{pk}/offer', { ...path, body: { price: a.price, days: a.days } }),
        )
      else if (a.type === 'revision')
        r = await unwrap(client.POST('/api/orders/{pk}/revision', { ...path, body: { comment: a.comment } }))
      else if (a.type === 'refuse')
        r = await unwrap(client.POST('/api/orders/{pk}/refuse', { ...path, body: { reason: a.reason } }))
      else if (a.type === 'submit') r = await unwrap(client.POST('/api/orders/{pk}/submit', path))
      else if (a.type === 'accept') r = await unwrap(client.POST('/api/orders/{pk}/accept', path))
      else if (a.type === 'cancel_overdue')
        r = await unwrap(client.POST('/api/orders/{pk}/cancel-overdue', path))
      else r = await unwrap(client.POST('/api/orders/{pk}/cancel', path))
      toast.push(r.message)
      reload()
    } catch (err) {
      toast.push(errorText(err), 'danger')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Breadcrumbs
        items={[
          o.is_seller
            ? { to: '/sell/orders/', label: 'Заказы и вопросы' }
            : { to: '/me/orders/', label: 'Мои заказы' },
          { label: `Заказ №${o.id}` },
        ]}
      />
      <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
        <h1 className="h3 mb-0 me-auto">
          {o.kind === 'question' && o.status === 'new' ? 'Вопрос' : `Заказ №${o.id}`}:{' '}
          <Link to={`/p/${o.product.slug}/`}>{o.product.title}</Link>
        </h1>
        <StatusBadge status={o.status} label={o.status_label} />
      </div>
      <div className="row g-4">
        <div className="col-lg-7 order-2 order-lg-1">
          <Chat
            key={`${o.id}-${o.status}`}
            orderId={o.id}
            initial={o.messages}
            lastId={o.last_id}
            status={o.status}
            canWrite={o.can_write}
            canMarkResult={o.can_mark_result}
            onStatusChange={reload}
            sellerName={o.seller}
          />
        </div>
        <div className="col-lg-5 order-1 order-lg-2">
          <div className="card mb-3">
            <div className="card-body">
              <div className="cm-steps mb-3">
                {o.steps.map((s) => (
                  <span key={s.code} className={s.current ? 'current' : s.done ? 'done' : ''}>
                    {s.label}
                  </span>
                ))}
              </div>
              <dl className="row small mb-0">
                <dt className="col-5 fw-normal text-muted">Тип</dt>
                <dd className="col-7">{o.kind_label}</dd>
                <dt className="col-5 fw-normal text-muted">Покупатель</dt>
                <dd className="col-7">{o.buyer}</dd>
                <dt className="col-5 fw-normal text-muted">Продавец</dt>
                <dd className="col-7">{o.seller}</dd>
                <dt className="col-5 fw-normal text-muted">Задача</dt>
                <dd className="col-7" style={{ whiteSpace: 'pre-line' }}>
                  {o.task}
                </dd>
                <dt className="col-5 fw-normal text-muted">Цена доработки</dt>
                <dd className="col-7">
                  {o.price ? <span className="cm-price">{formatMoney(o.price)}</span> : 'не согласована'}
                </dd>
                {o.price && o.includes_product && (
                  <>
                    <dt className="col-5 fw-normal text-muted">К оплате</dt>
                    <dd className="col-7">
                      {formatMoney(o.payment_amount)} <span className="text-muted">(с продуктом)</span>
                    </dd>
                  </>
                )}
                <dt className="col-5 fw-normal text-muted">Срок</dt>
                <dd className="col-7">
                  {o.days ? `${o.days} ${plural(o.days, ['день', 'дня', 'дней'])}` : '—'}
                </dd>
                {o.deadline && (
                  <>
                    <dt className="col-5 fw-normal text-muted">Крайняя дата</dt>
                    <dd className="col-7">
                      {formatDateTime(o.deadline)}
                      {o.deadline_left_seconds !== null && (
                        <div className={`small ${o.overdue ? 'text-danger fw-semibold' : 'text-muted'}`}>
                          {o.overdue ? (
                            <>
                              <i className="bi bi-exclamation-triangle-fill" /> срок прошёл
                            </>
                          ) : (
                            `осталось ${timeLeft(o.deadline_left_seconds)}`
                          )}
                        </div>
                      )}
                    </dd>
                  </>
                )}
                <dt className="col-5 fw-normal text-muted">Возвраты</dt>
                <dd className="col-7">
                  {o.revisions} из {o.max_revisions}
                </dd>
                {o.purchase_id && o.is_buyer && (
                  <>
                    <dt className="col-5 fw-normal text-muted">Покупка</dt>
                    <dd className="col-7">
                      <Link to={`/me/purchases/${o.purchase_id}/`}>№{o.purchase_id}</Link>
                    </dd>
                  </>
                )}
              </dl>
            </div>
          </div>
          {o.dispute && (
            <div
              className={`alert ${o.dispute.status === 'open' ? 'alert-danger' : 'alert-info'} d-flex gap-2`}
            >
              <i className="bi bi-exclamation-octagon-fill" />
              <div>
                {o.dispute.status === 'open'
                  ? `Открыт спор (${o.dispute.reason_type_label.toLowerCase()}). Решение примет администратор.`
                  : `Спор закрыт: ${o.dispute.resolution_label.toLowerCase()}${Number(o.dispute.refund_amount) ? `, возврат ${formatMoney(o.dispute.refund_amount)}` : ''}.`}
              </div>
            </div>
          )}
          {o.status === 'submitted' && o.is_buyer && (
            <div className="alert alert-info small d-flex gap-2">
              <i className="bi bi-hourglass-split" />
              <div>
                Работа сдана. Без ответа через {o.auto_accept_days} дн. заказ будет принят автоматически.
              </div>
            </div>
          )}
          <OrderActions order={o} onAction={run} busy={busy} />
        </div>
      </div>
    </>
  )
}
