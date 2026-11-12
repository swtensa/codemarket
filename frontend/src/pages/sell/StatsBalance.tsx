import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
} from 'chart.js'
import { useState, type FormEvent } from 'react'
import { Chart } from 'react-chartjs-2'
import { Link, useSearchParams } from 'react-router'

import { client, unwrap } from '../../api/client'
import { EmptyState, ErrorState, Loading, Pagination, StatusBadge } from '../../components/ui'
import { useTitle } from '../../hooks/misc'
import { useAuth } from '../../hooks/useAuth'
import { useToast } from '../../hooks/useToast'
import { errorText } from '../../lib/forms'
import { formatDateTime, formatMoney, percent } from '../../lib/format'
import { SellNav } from './common'

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  BarController,
  LineElement,
  LineController,
  PointElement,
  Tooltip,
  Legend,
)
ChartJS.defaults.font.family = 'Manrope, system-ui, sans-serif'
ChartJS.defaults.color = '#657069'

export function SellerStatsPage() {
  useTitle('Статистика')
  const [params, setParams] = useSearchParams()
  const date_from = params.get('from') ?? undefined
  const date_to = params.get('to') ?? undefined
  const q = useQuery({
    queryKey: ['seller-stats', date_from, date_to],
    queryFn: () => unwrap(client.GET('/api/seller/stats', { params: { query: { date_from, date_to } } })),
  })
  const [from, setFrom] = useState<string | null>(null)
  const [to, setTo] = useState<string | null>(null)
  const s = q.data
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const p = new URLSearchParams()
    if (from ?? s?.date_from) p.set('from', (from ?? s?.date_from)!)
    if (to ?? s?.date_to) p.set('to', (to ?? s?.date_to)!)
    setParams(p)
  }
  return (
    <>
      <SellNav />
      <form className="d-flex flex-wrap align-items-end gap-2 mb-4" onSubmit={submit}>
        <div>
          <label className="form-label small" htmlFor="from">
            С
          </label>
          <input
            className="form-control"
            type="date"
            id="from"
            value={from ?? s?.date_from ?? ''}
            onChange={(e) => setFrom(e.target.value)}
          />
        </div>
        <div>
          <label className="form-label small" htmlFor="to">
            По
          </label>
          <input
            className="form-control"
            type="date"
            id="to"
            value={to ?? s?.date_to ?? ''}
            onChange={(e) => setTo(e.target.value)}
          />
        </div>
        <button className="btn btn-primary">Показать</button>
      </form>
      {q.isLoading ? (
        <Loading />
      ) : q.isError || !s ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <>
          <div className="row g-3 mb-4">
            <div className="col-6 col-lg-3">
              <div className="cm-stat">
                <div className="label">Выручка за период</div>
                <div className="value">{formatMoney(s.total_revenue)}</div>
              </div>
            </div>
            <div className="col-6 col-lg-3">
              <div className="cm-stat">
                <div className="label">Продажи</div>
                <div className="value">{s.total_sales}</div>
              </div>
            </div>
            <div className="col-6 col-lg-3">
              <div className="cm-stat">
                <div className="label">Просмотры · конверсия</div>
                <div className="value">
                  {s.total_views} <span className="fs-6 text-muted">· {percent(s.conversion, 1)}</span>
                </div>
              </div>
            </div>
            <div className="col-6 col-lg-3">
              <div className="cm-stat">
                <div className="label">Средний рейтинг</div>
                <div className="value">
                  {s.rating ? (
                    <>
                      {Number(s.rating).toFixed(1).replace('.', ',')}{' '}
                      <span className="fs-6 text-muted">({s.rating_n})</span>
                    </>
                  ) : (
                    '—'
                  )}
                </div>
              </div>
            </div>
          </div>
          <div className="card mb-4">
            <div className="card-body">
              <h2 className="h6">Продажи и выручка по месяцам</h2>
              {s.total_sales || s.total_views ? (
                <div style={{ height: 300 }} role="img" aria-label="График продаж и выручки по месяцам">
                  <Chart
                    type="bar"
                    data={{
                      labels: s.labels,
                      datasets: [
                        {
                          type: 'bar' as const,
                          label: 'Выручка, ₽',
                          data: s.revenue,
                          backgroundColor: '#CB5152',
                          borderRadius: 6,
                          yAxisID: 'y',
                        },
                        {
                          type: 'line' as const,
                          label: 'Продажи',
                          data: s.sales,
                          borderColor: '#293941',
                          backgroundColor: '#293941',
                          tension: 0.3,
                          yAxisID: 'y1',
                        },
                        {
                          type: 'line' as const,
                          label: 'Просмотры',
                          data: s.views,
                          borderColor: '#B2BB8A',
                          backgroundColor: '#B2BB8A',
                          borderDash: [5, 4],
                          tension: 0.3,
                          yAxisID: 'y1',
                        },
                      ],
                    }}
                    options={{
                      maintainAspectRatio: false,
                      interaction: { mode: 'index', intersect: false },
                      scales: {
                        y: {
                          position: 'left',
                          beginAtZero: true,
                          ticks: { callback: (v) => `${Number(v).toLocaleString('ru-RU')} ₽` },
                        },
                        y1: {
                          position: 'right',
                          beginAtZero: true,
                          grid: { drawOnChartArea: false },
                          ticks: { precision: 0 },
                        },
                      },
                    }}
                  />
                </div>
              ) : (
                <EmptyState icon="bi-graph-up" title="Нет данных за выбранный период" />
              )}
            </div>
          </div>
          <div className="card">
            <div className="table-responsive">
              <table className="table align-middle mb-0">
                <thead>
                  <tr>
                    <th>Продукт</th>
                    <th className="text-end">Просмотры</th>
                    <th className="text-end">Продажи</th>
                    <th className="text-end">Конверсия</th>
                    <th className="text-end">Выручка</th>
                    <th className="text-end">Рейтинг</th>
                  </tr>
                </thead>
                <tbody>
                  {s.products.length ? (
                    s.products.map((r) => (
                      <tr key={r.product_id}>
                        <td>
                          <Link to={`/p/${r.slug}/`}>{r.title}</Link>{' '}
                          <span className="small">
                            <StatusBadge status={r.status} label={STATUS_LABEL[r.status] ?? r.status} />
                          </span>
                        </td>
                        <td className="text-end">{r.views}</td>
                        <td className="text-end">{r.sales}</td>
                        <td className="text-end">{percent(r.conversion, 1)}</td>
                        <td className="text-end text-nowrap">{formatMoney(r.revenue)}</td>
                        <td className="text-end">{r.rating ? r.rating.toFixed(1).replace('.', ',') : '—'}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={6} className="cm-empty">
                        Нет продуктов
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </>
  )
}

const STATUS_LABEL: Record<string, string> = {
  draft: 'Черновик',
  checking: 'Проверяется',
  moderation: 'На модерации',
  published: 'Опубликован',
  rejected: 'Отклонён',
  hidden: 'Снят с продажи',
  blocked: 'Заблокирован',
}

export function BalancePage() {
  useTitle('Баланс')
  const { user } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const kind = params.get('kind') ?? ''
  const page = Number(params.get('page') ?? '1') || 1
  const bal = useQuery({ queryKey: ['balance'], queryFn: () => unwrap(client.GET('/api/balance')) })
  const ops = useQuery({
    queryKey: ['balance-ops', kind, page],
    queryFn: () => unwrap(client.GET('/api/balance/operations', { params: { query: { kind, page } } })),
  })
  const [amount, setAmount] = useState('')
  const [requisites, setRequisites] = useState('')
  const payout = useMutation({
    mutationFn: () => unwrap(client.POST('/api/balance/payouts', { body: { amount, requisites } })),
    onSuccess: (r) => {
      toast.push(r.message)
      setAmount('')
      setRequisites('')
      void qc.invalidateQueries({ queryKey: ['balance'] })
      void qc.invalidateQueries({ queryKey: ['balance-ops'] })
    },
    onError: (e) => toast.push(errorText(e), 'danger'),
  })
  const b = bal.data
  const lowFunds = b ? Number(b.available) < Number(b.min_payout) : true
  return (
    <>
      {user?.is_seller ? <SellNav /> : <h1 className="h3 mb-3">Баланс</h1>}
      {bal.isError ? (
        <ErrorState error={bal.error} onRetry={() => bal.refetch()} />
      ) : !b ? (
        <Loading />
      ) : (
        <div className="row g-3 mb-4">
          <div className="col-md-4">
            <div className="cm-stat">
              <div className="label">
                <i className="bi bi-hourglass-split me-1" />
                Удержано
              </div>
              <div className="value">{formatMoney(b.held)}</div>
              <div className="small text-muted">станет доступно через {b.hold_days} дн. после продажи</div>
            </div>
          </div>
          <div className="col-md-4">
            <div className="cm-stat" style={{ borderColor: 'var(--c-sage)' }}>
              <div className="label">
                <i className="bi bi-wallet2 me-1" />
                Доступно
              </div>
              <div className="value" style={{ color: 'var(--c-sage-text)' }}>
                {formatMoney(b.available)}
              </div>
              {Number(b.requested) > 0 && (
                <div className="small text-muted">в заявках: {formatMoney(b.requested)}</div>
              )}
            </div>
          </div>
          <div className="col-md-4">
            <div className="cm-stat">
              <div className="label">
                <i className="bi bi-box-arrow-up-right me-1" />
                Выведено
              </div>
              <div className="value">{formatMoney(b.withdrawn)}</div>
            </div>
          </div>
        </div>
      )}
      <div className="row g-4">
        <div className="col-lg-8">
          <div className="d-flex align-items-center gap-2 mb-2">
            <h2 className="h5 mb-0 me-auto">Операции</h2>
            <select
              className="form-select form-select-sm w-auto"
              aria-label="Тип операции"
              value={kind}
              onChange={(e) => setParams(e.target.value ? { kind: e.target.value } : {})}
            >
              <option value="">Все типы</option>
              {b?.kinds.map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          {ops.isLoading ? (
            <Loading />
          ) : ops.isError || !ops.data ? (
            <ErrorState error={ops.error} onRetry={() => ops.refetch()} />
          ) : ops.data.items.length ? (
            <>
              <div className="card">
                <div className="table-responsive">
                  <table className="table align-middle mb-0">
                    <thead>
                      <tr>
                        <th>Дата</th>
                        <th>Операция</th>
                        <th>Основание</th>
                        <th>Статус</th>
                        <th className="text-end">Сумма</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ops.data.items.map((op) => (
                        <tr key={op.id}>
                          <td className="small text-nowrap">{formatDateTime(op.created_at)}</td>
                          <td>{op.kind_label}</td>
                          <td className="small">
                            {op.order_id ? (
                              <Link to={`/orders/${op.order_id}/`}>{op.title}</Link>
                            ) : op.purchase_id ? (
                              op.title
                            ) : (
                              op.requisites.slice(0, 40)
                            )}
                            {op.status === 'held' && op.available_at && (
                              <div className="text-muted">до {formatDateTime(op.available_at)}</div>
                            )}
                          </td>
                          <td>
                            <StatusBadge status={op.status} label={op.status_label} />
                          </td>
                          <td
                            className={`text-end text-nowrap fw-semibold ${Number(op.amount) < 0 ? 'text-danger' : ''}`}
                          >
                            {formatMoney(op.amount)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <Pagination page={ops.data.page} pages={ops.data.pages} />
            </>
          ) : (
            <div className="card">
              <EmptyState icon="bi-receipt" title="Операций пока нет.">
                {!user?.is_seller && (
                  <Link className="btn btn-primary mt-2" to="/sell/">
                    Начать продавать
                  </Link>
                )}
              </EmptyState>
            </div>
          )}
        </div>
        <div className="col-lg-4">
          <form
            className="card"
            noValidate
            onSubmit={(e: FormEvent) => {
              e.preventDefault()
              payout.mutate()
            }}
          >
            <div className="card-body p-4">
              <h2 className="h5">Вывод денег</h2>
              <p className="small text-muted">
                От {formatMoney(b?.min_payout ?? 500)} и не больше доступного. Сумма сразу списывается из
                доступного.
              </p>
              <label className="form-label fw-semibold" htmlFor="amount">
                Сумма, ₽ <span className="required-mark">*</span>
              </label>
              <input
                className="form-control mb-3"
                type="number"
                min={Number(b?.min_payout ?? 500)}
                step={1}
                id="amount"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
              <label className="form-label fw-semibold" htmlFor="requisites">
                Реквизиты <span className="required-mark">*</span>
              </label>
              <textarea
                className="form-control mb-3"
                id="requisites"
                rows={3}
                value={requisites}
                onChange={(e) => setRequisites(e.target.value)}
                placeholder="Номер карты или счёта, банк, получатель"
              />
              <button className="btn btn-primary w-100" disabled={lowFunds || payout.isPending}>
                Создать заявку
              </button>
              {lowFunds && <div className="form-text">Недостаточно доступных средств.</div>}
            </div>
          </form>
        </div>
      </div>
    </>
  )
}
