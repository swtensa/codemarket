import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Fragment, useState, type FormEvent, type ReactNode } from 'react'
import { Link, NavLink, useNavigate, useParams, useSearchParams } from 'react-router'

import { ApiError, client, unwrap, type S } from '../../api/client'
import {
  Breadcrumbs,
  ConfirmButton,
  EmptyState,
  ErrorState,
  Loading,
  Pagination,
  SimilarityBar,
  StatusBadge,
} from '../../components/ui'
import { useTitle } from '../../hooks/misc'
import { useToast } from '../../hooks/useToast'
import { errorText } from '../../lib/forms'
import { fileSize, formatDateTime, formatMoney } from '../../lib/format'

/** Левое меню администрирования с числами ожидающих задач. */
export function ModLayout({ children }: { children: ReactNode }) {
  const counts = useQuery({
    queryKey: ['mod-counts'],
    queryFn: () => unwrap(client.GET('/api/admin/counts')),
    refetchInterval: 60_000,
  })
  const link = (to: string, label: string, badge?: number, tone = 'warning', end = false) => (
    <NavLink
      end={end}
      className={({ isActive }) => `nav-link d-flex justify-content-between ${isActive ? 'active' : ''}`}
      to={to}
    >
      {label}
      {badge ? <span className={`badge rounded-pill text-bg-${tone}`}>{badge}</span> : null}
    </NavLink>
  )
  return (
    <div className="row g-4">
      <aside className="col-lg-3 col-xl-2">
        <div className="small text-muted text-uppercase fw-bold mb-2">Администрирование</div>
        <nav className="nav nav-pills flex-lg-column cm-side-menu gap-1">
          {link('/moderation/', 'Версии', counts.data?.versions, 'warning', true)}
          {link('/moderation/disputes/', 'Споры', counts.data?.disputes, 'danger')}
          {link('/moderation/payouts/', 'Выплаты', counts.data?.payouts)}
          {link('/moderation/users/', 'Пользователи')}
          {link('/moderation/refs/', 'Справочники')}
          {link('/moderation/reports/', 'Отчёты')}
        </nav>
      </aside>
      <section className="col-lg-9 col-xl-10">{children}</section>
    </div>
  )
}

function useInvalidateMod() {
  const qc = useQueryClient()
  return () => {
    void qc.invalidateQueries({ queryKey: ['mod-counts'] })
  }
}

// ---------------------------------------------------------------- очередь и версия

export function QueuePage() {
  useTitle('Модерация версий')
  const q = useQuery({ queryKey: ['mod-queue'], queryFn: () => unwrap(client.GET('/api/admin/versions')) })
  return (
    <ModLayout>
      <h1 className="h3 mb-3">Очередь модерации</h1>
      {q.isLoading ? (
        <Loading />
      ) : q.isError || !q.data ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data.length ? (
        <div className="card">
          <div className="table-responsive">
            <table className="table table-hover align-middle mb-0">
              <thead>
                <tr>
                  <th>Продукт / версия</th>
                  <th>Продавец</th>
                  <th style={{ minWidth: 150 }}>Сходство</th>
                  <th>Совпадения</th>
                  <th>Получена</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {q.data.map((item) => {
                  const v = item.version
                  return (
                    <tr key={v.id}>
                      <td>
                        <Link className="fw-semibold" to={`/moderation/versions/${v.id}/`}>
                          {item.product_title}
                        </Link>{' '}
                        <span className="text-muted">{v.tag_name}</span>
                        <div className="d-flex flex-wrap gap-1 mt-1">
                          {v.status === 'appeal' && (
                            <span className="cm-status cm-status-warning">
                              <i className="bi bi-megaphone" /> Обжалование
                            </span>
                          )}
                          {v.flagged && (
                            <span className="cm-status cm-status-warning">
                              <i className="bi bi-flag-fill" /> Отмечена
                            </span>
                          )}
                          {item.product_status !== 'published' && (
                            <span className="cm-status cm-status-neutral">Новый продукт</span>
                          )}
                        </div>
                      </td>
                      <td>{item.seller}</td>
                      <td>
                        <SimilarityBar value={v.similarity} />
                      </td>
                      <td className="small">
                        {v.matches.length ? (
                          v.matches.map((m) => (
                            <div key={m.matched_version_id}>
                              <Link to={`/p/${m.product_slug}/`} target="_blank">
                                {m.product_title}
                              </Link>{' '}
                              — {Math.round(m.similarity * 100)}&nbsp;%
                              {m.files_other.length > 0 && (
                                <div className="text-muted">{m.files_other.join(', ')}</div>
                              )}
                            </div>
                          ))
                        ) : (
                          <span className="text-muted">нет</span>
                        )}
                      </td>
                      <td className="small text-nowrap">{formatDateTime(v.created_at)}</td>
                      <td>
                        <Link className="btn btn-sm btn-primary" to={`/moderation/versions/${v.id}/`}>
                          Проверить
                        </Link>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="card">
          <EmptyState icon="bi-check2-all" title="Очередь пуста: все версии проверены" />
        </div>
      )}
    </ModLayout>
  )
}

export function VersionDetailPage() {
  const { id = '' } = useParams()
  const pk = Number(id)
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const qc = useQueryClient()
  const invalidate = useInvalidateMod()
  const [comment, setComment] = useState('')
  const q = useQuery({
    queryKey: ['mod-version', pk],
    queryFn: () => unwrap(client.GET('/api/admin/versions/{pk}', { params: { path: { pk } } })),
  })
  const d = q.data
  const current = params.get('file') ?? d?.tree.find((t) => t.path)?.path ?? ''
  const file = useQuery({
    queryKey: ['mod-file', pk, current],
    enabled: !!current,
    queryFn: () =>
      unwrap(
        client.GET('/api/admin/versions/{pk}/file', { params: { path: { pk }, query: { path: current } } }),
      ),
  })
  useTitle(d ? `Версия ${d.version.tag_name}: ${d.product.title}` : 'Версия')
  if (q.isLoading)
    return (
      <ModLayout>
        <Loading />
      </ModLayout>
    )
  if (q.isError || !d)
    return (
      <ModLayout>
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      </ModLayout>
    )
  const v = d.version
  const decide = async (action: 'approve' | 'reject') => {
    try {
      const r = await unwrap(
        action === 'approve'
          ? client.POST('/api/admin/versions/{pk}/approve', { params: { path: { pk } } })
          : client.POST('/api/admin/versions/{pk}/reject', { params: { path: { pk } }, body: { comment } }),
      )
      toast.push(r.message)
      invalidate()
      void qc.invalidateQueries({ queryKey: ['mod-queue'] })
      navigate('/moderation/')
    } catch (e) {
      toast.push(errorText(e), 'danger')
    }
  }
  return (
    <ModLayout>
      <style>{d.highlight_css}</style>
      <Breadcrumbs
        items={[{ to: '/moderation/', label: 'Очередь' }, { label: `${d.product.title} ${v.tag_name}` }]}
      />
      <div className="card mb-3">
        <div className="card-body">
          <div className="row g-3 align-items-center">
            <div className="col-md-5">
              <div className="small text-muted">Продукт</div>
              <Link className="fw-bold fs-5" to={`/p/${d.product.slug}/`} target="_blank">
                {d.product.title}
              </Link>
              <div className="small">
                {d.category} · {formatMoney(d.product.price)} ·{' '}
                <StatusBadge status={d.product.status} label={d.product.status_label} />
              </div>
            </div>
            <div className="col-md-3">
              <div className="small text-muted">Продавец</div>
              <div className="fw-semibold">{d.seller.username}</div>
              <div className="small text-muted">{d.seller.email}</div>
            </div>
            <div className="col-md-4">
              <div className="small text-muted">Коэффициент сходства</div>
              <SimilarityBar value={v.similarity} />
              <div className="mt-1">
                <StatusBadge status={v.status} label={v.status_label} />{' '}
                {v.flagged && (
                  <span className="cm-status cm-status-warning">
                    <i className="bi bi-flag-fill" /> Отмечена
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="small text-muted mt-2">
            Тег {v.tag_name} · файлов {v.files_count} · {fileSize(v.size)} · получена{' '}
            {formatDateTime(v.created_at)}
          </div>
          {v.appeal_text && (
            <div className="alert alert-warning d-flex gap-2 mt-3 mb-0">
              <i className="bi bi-megaphone-fill" />
              <div>
                <strong>Обжалование продавца:</strong> {v.appeal_text}
              </div>
            </div>
          )}
        </div>
      </div>
      <div className="card mb-3">
        <div className="card-body">
          <h2 className="h6">Совпадения с каталогом</h2>
          {v.matches.length ? (
            <div className="table-responsive">
              <table className="table table-sm mb-0">
                <thead>
                  <tr>
                    <th>Продукт</th>
                    <th>Доля</th>
                    <th>Файлы этой версии</th>
                    <th>Файлы совпавшей</th>
                  </tr>
                </thead>
                <tbody>
                  {v.matches.map((m) => (
                    <tr key={m.matched_version_id}>
                      <td>
                        <Link to={`/p/${m.product_slug}/`} target="_blank">
                          {m.product_title}
                        </Link>{' '}
                        <span className="text-muted">
                          {m.matched_tag}, {m.seller}
                        </span>
                      </td>
                      <td>
                        <b>{Math.round(m.similarity * 100)}&nbsp;%</b>{' '}
                        <span className="small text-muted">({m.common_count} общих)</span>
                      </td>
                      <td className="small">
                        {m.files.map((f, i) => (
                          <span key={f}>
                            {i > 0 && ', '}
                            <button
                              type="button"
                              className="btn btn-link btn-sm p-0 align-baseline"
                              onClick={() => setParams({ file: f })}
                            >
                              {f}
                            </button>
                          </span>
                        ))}
                      </td>
                      <td className="small">{m.files_other.join(', ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-muted mb-0">Совпадений с S ≥ 10 % нет.</p>
          )}
        </div>
      </div>
      <div className="row g-3 mb-3">
        <div className="col-md-4 col-xl-3">
          <div className="card">
            <div className="card-body p-2 cm-tree">
              {d.tree.length ? (
                d.tree.map((t, i) =>
                  t.path ? (
                    <a
                      key={i}
                      href={`?file=${encodeURIComponent(t.path)}`}
                      className={t.path === current ? 'active' : ''}
                      style={{ paddingLeft: `${t.depth + 1}em` }}
                      onClick={(e) => {
                        e.preventDefault()
                        setParams({ file: t.path! })
                      }}
                    >
                      <i className="bi bi-file-earmark-code me-1" />
                      {t.name}
                    </a>
                  ) : (
                    <div key={i} style={{ paddingLeft: `${t.depth}em` }} className="fw-semibold">
                      <i className="bi bi-folder2-open me-1" />
                      {t.name}
                    </div>
                  ),
                )
              ) : (
                <span className="text-muted">Архив пуст или повреждён</span>
              )}
            </div>
          </div>
        </div>
        <div className="col-md-8 col-xl-9">
          {current && (
            <div className="small fw-semibold mb-1">
              <i className="bi bi-file-earmark-code me-1" />
              {current}
            </div>
          )}
          {file.isLoading ? (
            <Loading />
          ) : file.data?.error ? (
            <div className="alert alert-warning">{file.data.error}</div>
          ) : file.data?.html ? (
            <div className="cm-code" dangerouslySetInnerHTML={{ __html: file.data.html }} />
          ) : null}
        </div>
      </div>
      {d.can_decide ? (
        <div className="card">
          <div className="card-body">
            <div className="row g-3">
              <div className="col-md-4">
                <ConfirmButton
                  className="btn btn-accent w-100"
                  text={`Одобрить версию ${v.tag_name}? Она будет опубликована в репозиторий-копию${d.product.status !== 'published' ? ', продукт появится в каталоге' : ''}.`}
                  onConfirm={() => decide('approve')}
                >
                  <i className="bi bi-check-lg me-1" />
                  Одобрить
                </ConfirmButton>
              </div>
              <div className="col-md-8">
                <label className="form-label fw-semibold" htmlFor="comment">
                  Комментарий для продавца <span className="required-mark">*</span>
                </label>
                <textarea
                  className="form-control mb-2"
                  id="comment"
                  rows={2}
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="Что нужно исправить"
                />
                <ConfirmButton
                  className="btn btn-outline-danger"
                  text={`Отклонить версию ${v.tag_name}?`}
                  onConfirm={() => decide('reject')}
                >
                  <i className="bi bi-x-lg me-1" />
                  Отклонить
                </ConfirmButton>
              </div>
            </div>
          </div>
        </div>
      ) : (
        v.admin_comment && <div className="alert alert-info">Комментарий модератора: {v.admin_comment}</div>
      )}
    </ModLayout>
  )
}

// ---------------------------------------------------------------- споры

export function DisputesPage() {
  useTitle('Споры')
  const [params] = useSearchParams()
  const status = params.get('status') ?? 'open'
  const page = Number(params.get('page') ?? '1') || 1
  const q = useQuery({
    queryKey: ['mod-disputes', status, page],
    queryFn: () => unwrap(client.GET('/api/admin/disputes', { params: { query: { status, page } } })),
  })
  const pill = (s: string, label: string) => (
    <li className="nav-item">
      <Link className={`nav-link ${status === s ? 'active' : ''}`} to={`?status=${s}`}>
        {label}
      </Link>
    </li>
  )
  return (
    <ModLayout>
      <h1 className="h3 mb-3">Споры</h1>
      <ul className="nav nav-pills mb-3">
        {pill('open', 'Открытые')}
        {pill('closed', 'Закрытые')}
        {pill('all', 'Все')}
      </ul>
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
                    <th>Спор</th>
                    <th>Причина</th>
                    <th>Открыт</th>
                    <th>Статус</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {q.data.items.map((d) => (
                    <tr key={d.id}>
                      <td>
                        <div className="fw-semibold">
                          {d.target} · {d.product.title}
                        </div>
                        <div className="small text-muted">
                          покупатель {d.buyer}, продавец {d.seller}
                        </div>
                      </td>
                      <td className="small">{d.reason_type_label}</td>
                      <td className="small text-nowrap">{formatDateTime(d.opened_at)}</td>
                      <td>
                        <StatusBadge status={d.status} label={d.status_label} />
                        {d.resolution_label && <div className="small text-muted">{d.resolution_label}</div>}
                      </td>
                      <td>
                        <Link className="btn btn-sm btn-primary" to={`/moderation/disputes/${d.id}/`}>
                          {d.status === 'open' ? 'Рассмотреть' : 'Открыть'}
                        </Link>
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
          <EmptyState icon="bi-emoji-smile" title="Споров нет" />
        </div>
      )}
    </ModLayout>
  )
}

function ChatView({ messages, seller }: { messages: S['MessageOut'][]; seller: string }) {
  return (
    <div className="cm-chat" style={{ height: 340 }}>
      {messages.map((m) =>
        m.is_system ? (
          <div key={m.id} className="text-center small text-muted">
            {m.text} · {formatDateTime(m.created_at)}
          </div>
        ) : (
          <div
            key={m.id}
            className={`cm-msg ${m.author === seller ? 'mine' : ''} ${m.is_result ? 'result' : ''}`}
          >
            <div style={{ whiteSpace: 'pre-line' }}>{m.text}</div>
            {m.attachment_url && (
              <a className="cm-attach" href={m.attachment_url}>
                <i className="bi bi-file-earmark-arrow-down" />
                {m.attachment_name}
              </a>
            )}
            <div className="meta">
              {m.author === seller ? 'продавец' : 'покупатель'} {m.author} · {formatDateTime(m.created_at)}
            </div>
          </div>
        ),
      )}
    </div>
  )
}

export function DisputeDetailPage() {
  const { id = '' } = useParams()
  const pk = Number(id)
  const navigate = useNavigate()
  const toast = useToast()
  const invalidate = useInvalidateMod()
  const qc = useQueryClient()
  const q = useQuery({
    queryKey: ['mod-dispute', pk],
    queryFn: () => unwrap(client.GET('/api/admin/disputes/{pk}', { params: { path: { pk } } })),
  })
  const [resolution, setResolution] = useState('')
  const [amount, setAmount] = useState('')
  const [comment, setComment] = useState('')
  useTitle(`Спор №${pk}`)
  if (q.isLoading)
    return (
      <ModLayout>
        <Loading />
      </ModLayout>
    )
  if (q.isError || !q.data)
    return (
      <ModLayout>
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      </ModLayout>
    )
  const d = q.data
  const row = d.row
  const save = async () => {
    try {
      const r = await unwrap(
        client.POST('/api/admin/disputes/{pk}/resolve', {
          params: { path: { pk } },
          body: { resolution, refund_amount: amount || null, comment },
        }),
      )
      toast.push(r.message)
      invalidate()
      void qc.invalidateQueries({ queryKey: ['mod-disputes'] })
      navigate('/moderation/disputes/')
    } catch (e) {
      toast.push(errorText(e), 'danger')
    }
  }
  return (
    <ModLayout>
      <Breadcrumbs items={[{ to: '/moderation/disputes/', label: 'Споры' }, { label: `Спор №${pk}` }]} />
      <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
        <h1 className="h3 mb-0 me-auto">
          Спор по {d.purchase_id ? `покупке №${d.purchase_id}` : `заказу №${d.order_id}`}
        </h1>
        <StatusBadge status={d.dispute.status} label={d.dispute.status_label} />
      </div>
      <div className="row g-3 mb-3">
        <div className="col-md-6">
          <div className="card h-100">
            <div className="card-body">
              <h2 className="h6">Стороны</h2>
              <dl className="row small mb-0">
                <dt className="col-5 fw-normal text-muted">Покупатель</dt>
                <dd className="col-7">{row.buyer}</dd>
                <dt className="col-5 fw-normal text-muted">Продавец</dt>
                <dd className="col-7">{row.seller}</dd>
                <dt className="col-5 fw-normal text-muted">Продукт</dt>
                <dd className="col-7">
                  <Link to={`/p/${row.product.slug}/`} target="_blank">
                    {row.product.title}
                  </Link>
                </dd>
                <dt className="col-5 fw-normal text-muted">Сумма</dt>
                <dd className="col-7 fw-semibold">{formatMoney(row.price)}</dd>
                {d.purchase_status && (
                  <>
                    <dt className="col-5 fw-normal text-muted">Покупка</dt>
                    <dd className="col-7">{d.purchase_status}</dd>
                  </>
                )}
                {d.order_id && (
                  <>
                    <dt className="col-5 fw-normal text-muted">Заказ</dt>
                    <dd className="col-7">
                      <Link to={`/orders/${d.order_id}/`} target="_blank">
                        открыть
                      </Link>
                    </dd>
                  </>
                )}
                {d.version_id && (
                  <>
                    <dt className="col-5 fw-normal text-muted">Код версии</dt>
                    <dd className="col-7">
                      <Link to={`/moderation/versions/${d.version_id}/`} target="_blank">
                        {d.version_tag}
                      </Link>
                    </dd>
                  </>
                )}
              </dl>
            </div>
          </div>
        </div>
        <div className="col-md-6">
          <div className="card h-100">
            <div className="card-body">
              <h2 className="h6">Причина: {row.reason_type_label}</h2>
              <p className="mb-1" style={{ whiteSpace: 'pre-line' }}>
                {d.reason}
              </p>
              {d.task && (
                <p className="small mb-1">
                  <span className="text-muted">Задача заказа:</span> {d.task}
                </p>
              )}
              <div className="small text-muted">
                Открыл {d.opened_by} {formatDateTime(row.opened_at)}
              </div>
            </div>
          </div>
        </div>
      </div>
      {d.results.length > 0 && (
        <div className="card mb-3">
          <div className="card-body">
            <h2 className="h6">
              <i className="bi bi-patch-check me-1" />
              Результат работы
            </h2>
            {d.results.map((m) => (
              <div key={m.id} className="cm-msg result mb-2">
                <div style={{ whiteSpace: 'pre-line' }}>{m.text}</div>
                {m.attachment_url && (
                  <a className="cm-attach" href={m.attachment_url}>
                    <i className="bi bi-file-earmark-arrow-down" />
                    {m.attachment_name}
                  </a>
                )}
                <div className="meta">{formatDateTime(m.created_at)}</div>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="card mb-3">
        <div className="card-body">
          <h2 className="h6">Переписка</h2>
          {d.chat_messages.length ? (
            <ChatView messages={d.chat_messages} seller={row.seller} />
          ) : (
            <p className="text-muted mb-0">Переписки нет.</p>
          )}
        </div>
      </div>
      {d.dispute.status === 'open' ? (
        <form className="card" onSubmit={(e: FormEvent) => e.preventDefault()}>
          <div className="card-body">
            <h2 className="h6">Решение</h2>
            <div className="d-flex flex-wrap gap-3 mb-3">
              {[
                ['seller', 'В пользу продавца'],
                ['refund', `Полный возврат ${formatMoney(row.price)}`],
                ['partial', 'Частичный возврат'],
              ].map(([v, label]) => (
                <div className="form-check" key={v}>
                  <input
                    className="form-check-input"
                    type="radio"
                    name="resolution"
                    id={`res-${v}`}
                    checked={resolution === v}
                    onChange={() => setResolution(v)}
                  />
                  <label className="form-check-label" htmlFor={`res-${v}`}>
                    {label}
                  </label>
                </div>
              ))}
            </div>
            <div className="row g-2 mb-2">
              <div className="col-md-4">
                <label className="form-label small" htmlFor="refund_amount">
                  Сумма частичного возврата, ₽
                </label>
                <input
                  className="form-control"
                  type="number"
                  min={1}
                  step="0.01"
                  id="refund_amount"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  disabled={resolution !== 'partial'}
                />
              </div>
              <div className="col-md-8">
                <label className="form-label small" htmlFor="comment">
                  Комментарий сторонам
                </label>
                <input
                  className="form-control"
                  id="comment"
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                />
              </div>
            </div>
            <div className="alert alert-info small d-flex gap-2">
              <i className="bi bi-info-circle-fill" />
              <div>
                При возврате верните деньги в кабинете ЮKassa и отметьте здесь.{' '}
                {d.purchase_id &&
                  'Полный возврат по покупке отзовёт доступ к репозиторию и ZIP и отменит начисление продавцу.'}
              </div>
            </div>
            <ConfirmButton
              className="btn btn-primary"
              text="Сохранить решение по спору? Изменить его будет нельзя."
              onConfirm={save}
              disabled={!resolution}
            >
              Сохранить решение
            </ConfirmButton>
          </div>
        </form>
      ) : (
        <div className="alert alert-info">
          Решение: <strong>{d.dispute.resolution_label}</strong>
          {Number(d.dispute.refund_amount) > 0 && `, возврат ${formatMoney(d.dispute.refund_amount)}`}.{' '}
          {d.dispute.admin_comment} · {formatDateTime(d.dispute.closed_at)}
        </div>
      )}
    </ModLayout>
  )
}

// ---------------------------------------------------------------- выплаты

function PayoutActions({ op, onDone }: { op: S['PayoutRow']; onDone: () => void }) {
  const toast = useToast()
  const [reason, setReason] = useState('')
  const act = async (paid: boolean) => {
    try {
      const path = { params: { path: { pk: op.id } } }
      const r = await unwrap(
        paid
          ? client.POST('/api/admin/payouts/{pk}/paid', path)
          : client.POST('/api/admin/payouts/{pk}/reject', { ...path, body: { reason } }),
      )
      toast.push(r.message)
      onDone()
    } catch (e) {
      toast.push(errorText(e), 'danger')
    }
  }
  return (
    <div className="d-flex flex-wrap gap-2">
      <ConfirmButton
        className="btn btn-sm btn-sage"
        text={`Отметить выплату ${formatMoney(op.amount)} как отправленную?`}
        onConfirm={() => act(true)}
      >
        Выплачено
      </ConfirmButton>
      <input
        className="form-control form-control-sm"
        style={{ maxWidth: 140 }}
        placeholder="причина отказа"
        aria-label="Причина отказа"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      <ConfirmButton
        className="btn btn-sm btn-outline-danger"
        text="Отклонить заявку? Деньги вернутся продавцу в доступные."
        onConfirm={() => act(false)}
      >
        Отклонить
      </ConfirmButton>
    </div>
  )
}

export function PayoutsPage() {
  useTitle('Выплаты')
  const qc = useQueryClient()
  const invalidate = useInvalidateMod()
  const q = useQuery({ queryKey: ['mod-payouts'], queryFn: () => unwrap(client.GET('/api/admin/payouts')) })
  const done = () => {
    invalidate()
    void qc.invalidateQueries({ queryKey: ['mod-payouts'] })
  }
  return (
    <ModLayout>
      <h1 className="h3 mb-3">Заявки на вывод</h1>
      <p className="text-muted small">
        Реальных переводов система не делает: переведите деньги по реквизитам вручную и отметьте заявку.
      </p>
      {q.isLoading ? (
        <Loading />
      ) : q.isError || !q.data ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <>
          {q.data.requested.length ? (
            <div className="card mb-4">
              <div className="table-responsive">
                <table className="table align-middle mb-0">
                  <thead>
                    <tr>
                      <th>Продавец</th>
                      <th>Дата</th>
                      <th className="text-end">Сумма</th>
                      <th>Реквизиты</th>
                      <th style={{ minWidth: 260 }}>Действия</th>
                    </tr>
                  </thead>
                  <tbody>
                    {q.data.requested.map((op) => (
                      <tr key={op.id}>
                        <td>
                          <div className="fw-semibold">{op.username}</div>
                          <div className="small text-muted">{op.email}</div>
                        </td>
                        <td className="small text-nowrap">{formatDateTime(op.created_at)}</td>
                        <td className="text-end fw-bold text-nowrap">{formatMoney(op.amount)}</td>
                        <td className="small" style={{ whiteSpace: 'pre-line' }}>
                          {op.requisites}
                        </td>
                        <td>
                          <PayoutActions op={op} onDone={done} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="card mb-4">
              <EmptyState icon="bi-check2-all" title="Новых заявок нет" />
            </div>
          )}
          {q.data.history.length > 0 && (
            <>
              <h2 className="h5">История</h2>
              <div className="card">
                <div className="table-responsive">
                  <table className="table table-sm mb-0">
                    <thead>
                      <tr>
                        <th>Продавец</th>
                        <th>Создана</th>
                        <th>Обработана</th>
                        <th className="text-end">Сумма</th>
                        <th>Статус</th>
                      </tr>
                    </thead>
                    <tbody>
                      {q.data.history.map((op) => (
                        <tr key={op.id}>
                          <td>{op.username}</td>
                          <td className="small">{formatDateTime(op.created_at)}</td>
                          <td className="small">{formatDateTime(op.processed_at)}</td>
                          <td className="text-end">{formatMoney(op.amount)}</td>
                          <td>
                            <StatusBadge status={op.status} label={op.status_label} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </>
      )}
    </ModLayout>
  )
}

// ---------------------------------------------------------------- пользователи

function BlockForm({ user, onDone }: { user: S['AdminUserOut']; onDone: () => void }) {
  const toast = useToast()
  const [reason, setReason] = useState('')
  const act = async (block: boolean) => {
    try {
      const path = { params: { path: { pk: user.id } } }
      const r = await unwrap(
        block
          ? client.POST('/api/admin/users/{pk}/block', { ...path, body: { reason } })
          : client.POST('/api/admin/users/{pk}/unblock', path),
      )
      toast.push(r.message)
      onDone()
    } catch (e) {
      toast.push(errorText(e), 'danger')
    }
  }
  if (user.is_staff) return <span className="text-muted small">—</span>
  if (user.status !== 'active') {
    return (
      <button className="btn btn-sm btn-outline-primary" onClick={() => act(false)}>
        Разблокировать
      </button>
    )
  }
  return (
    <div className="d-flex gap-2">
      <input
        className="form-control form-control-sm"
        placeholder="Причина блокировки"
        aria-label="Причина"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      <ConfirmButton
        className="btn btn-sm btn-danger text-nowrap"
        text={`Заблокировать ${user.username}? Его продукты скроются из каталога, незавершённые заказы будут отменены или переданы в спор.`}
        onConfirm={() => act(true)}
      >
        Заблокировать
      </ConfirmButton>
    </div>
  )
}

export function UsersPage() {
  useTitle('Пользователи')
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const q0 = params.get('q') ?? ''
  const status = params.get('status') ?? ''
  const page = Number(params.get('page') ?? '1') || 1
  const [search, setSearch] = useState(q0)
  const [st, setSt] = useState(status)
  const q = useQuery({
    queryKey: ['mod-users', q0, status, page],
    queryFn: () => unwrap(client.GET('/api/admin/users', { params: { query: { q: q0, status, page } } })),
  })
  return (
    <ModLayout>
      <h1 className="h3 mb-3">Пользователи</h1>
      <form
        className="d-flex flex-wrap gap-2 mb-3"
        onSubmit={(e: FormEvent) => {
          e.preventDefault()
          const p: Record<string, string> = {}
          if (search.trim()) p.q = search.trim()
          if (st) p.status = st
          setParams(p)
        }}
      >
        <input
          className="form-control"
          style={{ maxWidth: 320 }}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Email или имя"
          aria-label="Поиск"
        />
        <select
          className="form-select"
          style={{ maxWidth: 200 }}
          value={st}
          onChange={(e) => setSt(e.target.value)}
          aria-label="Статус"
        >
          <option value="">Все</option>
          <option value="active">Активные</option>
          <option value="blocked">Заблокированные</option>
        </select>
        <button className="btn btn-primary">Найти</button>
      </form>
      {q.isLoading ? (
        <Loading />
      ) : q.isError || !q.data ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <>
          <div className="card">
            <div className="table-responsive">
              <table className="table align-middle mb-0">
                <thead>
                  <tr>
                    <th>Пользователь</th>
                    <th>Роль</th>
                    <th>Статус</th>
                    <th>Зарегистрирован</th>
                    <th style={{ minWidth: 300 }}>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {q.data.items.length ? (
                    q.data.items.map((u) => (
                      <tr key={u.id}>
                        <td>
                          <div className="fw-semibold">{u.username}</div>
                          <div className="small text-muted">{u.email}</div>
                        </td>
                        <td className="small">
                          {u.is_staff ? 'Администратор' : u.is_seller ? 'Продавец' : 'Покупатель'}
                        </td>
                        <td>
                          <StatusBadge
                            status={u.status}
                            label={u.status === 'active' ? 'Активен' : 'Заблокирован'}
                          />
                          {u.block_reason && <div className="small text-muted">{u.block_reason}</div>}
                        </td>
                        <td className="small">{formatDateTime(u.created_at)}</td>
                        <td>
                          <BlockForm
                            user={u}
                            onDone={() => void qc.invalidateQueries({ queryKey: ['mod-users'] })}
                          />
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={5} className="cm-empty">
                        Никого не нашли
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
          <Pagination page={q.data.page} pages={q.data.pages} />
        </>
      )}
    </ModLayout>
  )
}

// ---------------------------------------------------------------- справочники

type RefKind = 'categories' | 'technologies' | 'platforms'
type Draft = { name: string; slug: string; parent_id: number | null; position: number; icon: string }
const EMPTY: Draft = { name: '', slug: '', parent_id: null, position: 0, icon: '' }

function RefEditor({
  kind,
  rows,
  sections,
  onDone,
}: {
  kind: RefKind
  rows: S['RefRow'][]
  sections: S['RefRow'][]
  onDone: () => void
}) {
  const toast = useToast()
  const [editing, setEditing] = useState<number | 'new' | null>(null)
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const save = useMutation({
    mutationFn: async () => {
      const body = kind === 'categories' ? draft : { name: draft.name, slug: draft.slug }
      if (editing === 'new') {
        if (kind === 'categories') return unwrap(client.POST('/api/admin/refs/categories', { body: draft }))
        if (kind === 'technologies') return unwrap(client.POST('/api/admin/refs/technologies', { body }))
        return unwrap(client.POST('/api/admin/refs/platforms', { body }))
      }
      const path = { params: { path: { pk: editing as number } } }
      if (kind === 'categories')
        return unwrap(client.PUT('/api/admin/refs/categories/{pk}', { ...path, body: draft }))
      if (kind === 'technologies')
        return unwrap(client.PUT('/api/admin/refs/technologies/{pk}', { ...path, body }))
      return unwrap(client.PUT('/api/admin/refs/platforms/{pk}', { ...path, body }))
    },
    onSuccess: (r) => {
      toast.push(r.message)
      setEditing(null)
      setErrors({})
      onDone()
    },
    onError: (e) => {
      if (e instanceof ApiError && Object.keys(e.fields).length) setErrors(e.fields)
      else toast.push(errorText(e), 'danger')
    },
  })
  const remove = async (pk: number) => {
    try {
      const path = { params: { path: { pk } } }
      const r = await unwrap(
        kind === 'categories'
          ? client.DELETE('/api/admin/refs/categories/{pk}', path)
          : kind === 'technologies'
            ? client.DELETE('/api/admin/refs/technologies/{pk}', path)
            : client.DELETE('/api/admin/refs/platforms/{pk}', path),
      )
      toast.push(r.message)
      onDone()
    } catch (e) {
      toast.push(errorText(e), 'danger')
    }
  }
  const startEdit = (r: S['RefRow'] | null) => {
    setErrors({})
    setEditing(r ? r.id : 'new')
    setDraft(
      r
        ? {
            name: r.name,
            slug: r.slug,
            parent_id: r.parent_id ?? null,
            position: r.position ?? 0,
            icon: r.icon ?? '',
          }
        : EMPTY,
    )
  }
  const form = (
    <tr className="table-light">
      <td colSpan={4}>
        <form
          className="row g-2 align-items-start"
          onSubmit={(e: FormEvent) => {
            e.preventDefault()
            save.mutate()
          }}
        >
          <div className="col-sm-3">
            <input
              className={`form-control form-control-sm ${errors.name ? 'is-invalid' : ''}`}
              placeholder="Название"
              aria-label="Название"
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
            {errors.name && <div className="invalid-feedback">{errors.name}</div>}
          </div>
          <div className="col-sm-3">
            <input
              className={`form-control form-control-sm ${errors.slug ? 'is-invalid' : ''}`}
              placeholder="адрес (latin-slug)"
              aria-label="Адрес"
              value={draft.slug}
              onChange={(e) => setDraft({ ...draft, slug: e.target.value })}
            />
            {errors.slug && <div className="invalid-feedback">{errors.slug}</div>}
          </div>
          {kind === 'categories' && (
            <>
              <div className="col-sm-2">
                <select
                  className="form-select form-select-sm"
                  aria-label="Раздел"
                  value={draft.parent_id ?? ''}
                  onChange={(e) =>
                    setDraft({ ...draft, parent_id: e.target.value ? Number(e.target.value) : null })
                  }
                >
                  <option value="">— раздел —</option>
                  {sections.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
                {errors.parent_id && <div className="small text-danger">{errors.parent_id}</div>}
              </div>
              <div className="col-sm-1">
                <input
                  className="form-control form-control-sm"
                  type="number"
                  aria-label="Порядок"
                  value={draft.position}
                  onChange={(e) => setDraft({ ...draft, position: Number(e.target.value) })}
                />
              </div>
              <div className="col-sm-1">
                <input
                  className="form-control form-control-sm"
                  placeholder="bi-…"
                  aria-label="Иконка"
                  value={draft.icon}
                  onChange={(e) => setDraft({ ...draft, icon: e.target.value })}
                />
              </div>
            </>
          )}
          <div className="col-sm-2 d-flex gap-1">
            <button className="btn btn-sm btn-primary" disabled={save.isPending}>
              Сохранить
            </button>
            <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => setEditing(null)}>
              Отмена
            </button>
          </div>
        </form>
      </td>
    </tr>
  )
  return (
    <div className="card mb-4">
      <div className="table-responsive">
        <table className="table table-sm align-middle mb-0">
          <thead>
            <tr>
              <th>Название</th>
              <th>Адрес</th>
              <th className="text-end">Продуктов</th>
              <th className="text-end">
                <button className="btn btn-sm btn-outline-primary" onClick={() => startEdit(null)}>
                  <i className="bi bi-plus-lg" /> Добавить
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            {editing === 'new' && form}
            {rows.map((r) =>
              editing === r.id ? (
                <Fragment key={r.id}>{form}</Fragment>
              ) : (
                <tr key={r.id}>
                  <td className={kind === 'categories' && r.parent_id ? 'ps-4' : 'fw-semibold'}>
                    {r.icon && <i className={`bi ${r.icon} me-1`} />}
                    {r.name}
                  </td>
                  <td className="small text-muted">{r.slug}</td>
                  <td className="text-end">{r.products}</td>
                  <td className="text-end text-nowrap">
                    <button className="btn btn-sm btn-link" onClick={() => startEdit(r)}>
                      Изменить
                    </button>
                    <ConfirmButton
                      className="btn btn-sm btn-link text-danger"
                      text={`Удалить «${r.name}»?`}
                      onConfirm={() => remove(r.id)}
                      disabled={r.products > 0 || (r.children ?? 0) > 0}
                    >
                      Удалить
                    </ConfirmButton>
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function RefsPage() {
  useTitle('Справочники')
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['mod-refs'], queryFn: () => unwrap(client.GET('/api/admin/refs')) })
  const done = () => {
    void qc.invalidateQueries({ queryKey: ['mod-refs'] })
    void qc.invalidateQueries({ queryKey: ['refs'] })
  }
  return (
    <ModLayout>
      <h1 className="h3 mb-3">Справочники</h1>
      <p className="text-muted small">
        Удалить можно только запись без связанных продуктов (и раздел без подкатегорий).
      </p>
      {q.isLoading ? (
        <Loading />
      ) : q.isError || !q.data ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <>
          <h2 className="h5">Разделы и подкатегории</h2>
          <RefEditor
            kind="categories"
            rows={q.data.categories}
            sections={q.data.categories.filter((c) => !c.parent_id)}
            onDone={done}
          />
          <h2 className="h5">Технологии</h2>
          <RefEditor kind="technologies" rows={q.data.technologies} sections={[]} onDone={done} />
          <h2 className="h5">Платформы</h2>
          <RefEditor kind="platforms" rows={q.data.platforms} sections={[]} onDone={done} />
        </>
      )}
    </ModLayout>
  )
}

// ---------------------------------------------------------------- отчёты

export function ReportsPage() {
  useTitle('Отчёты')
  const [params, setParams] = useSearchParams()
  const date_from = params.get('from') ?? undefined
  const date_to = params.get('to') ?? undefined
  const q = useQuery({
    queryKey: ['mod-reports', date_from, date_to],
    queryFn: () => unwrap(client.GET('/api/admin/reports', { params: { query: { date_from, date_to } } })),
  })
  const [from, setFrom] = useState<string | null>(null)
  const [to, setTo] = useState<string | null>(null)
  const r = q.data
  const f = from ?? r?.date_from ?? ''
  const t = to ?? r?.date_to ?? ''
  const table = (rows: S['ReportRow'][], withUsers: boolean, first: string) => (
    <div className="card mb-4">
      <div className="table-responsive">
        <table className="table table-sm align-middle mb-0">
          <thead>
            <tr>
              <th>{first}</th>
              {withUsers && <th className="text-end">Пользователи</th>}
              <th className="text-end">Продукты</th>
              <th className="text-end">Покупки</th>
              <th className="text-end">Заказы</th>
              <th className="text-end">Оборот</th>
              <th className="text-end">Доход платформы</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((x) => (
              <tr key={x.label}>
                <td>{x.label}</td>
                {withUsers && <td className="text-end">{x.users}</td>}
                <td className="text-end">{x.products}</td>
                <td className="text-end">{x.purchases}</td>
                <td className="text-end">{x.orders}</td>
                <td className="text-end text-nowrap">{formatMoney(x.turnover)}</td>
                <td className="text-end text-nowrap">{formatMoney(x.income)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
  return (
    <ModLayout>
      <h1 className="h3 mb-3">Отчёт по площадке</h1>
      <form
        className="d-flex flex-wrap align-items-end gap-2 mb-4"
        onSubmit={(e: FormEvent) => {
          e.preventDefault()
          setParams({ from: f, to: t })
        }}
      >
        <div>
          <label className="form-label small" htmlFor="from">
            С
          </label>
          <input
            className="form-control"
            type="date"
            id="from"
            value={f}
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
            value={t}
            onChange={(e) => setTo(e.target.value)}
          />
        </div>
        <button className="btn btn-primary">Показать</button>
        <a
          className="btn btn-outline-primary"
          href={`/api/admin/reports/excel?date_from=${r?.date_from ?? ''}&date_to=${r?.date_to ?? ''}`}
        >
          <i className="bi bi-file-earmark-excel me-1" />
          Выгрузить в Excel
        </a>
      </form>
      {q.isLoading ? (
        <Loading />
      ) : q.isError || !r ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : r.is_empty ? (
        <div className="card">
          <EmptyState icon="bi-inbox" title="Нет данных" />
        </div>
      ) : (
        <>
          <div className="row g-3 mb-4">
            {[
              ['Новые пользователи', r.totals.users],
              ['Опубликовано', r.totals.products],
              ['Покупки', r.totals.purchases],
              ['Заказы', r.totals.orders],
            ].map(([label, value]) => (
              <div className="col-6 col-xl-2" key={label}>
                <div className="cm-stat">
                  <div className="label">{label}</div>
                  <div className="value">{value}</div>
                </div>
              </div>
            ))}
            <div className="col-6 col-xl-2">
              <div className="cm-stat">
                <div className="label">Оборот</div>
                <div className="value fs-5">{formatMoney(r.totals.turnover)}</div>
              </div>
            </div>
            <div className="col-6 col-xl-2">
              <div className="cm-stat">
                <div className="label">Доход платформы</div>
                <div className="value fs-5" style={{ color: 'var(--c-accent)' }}>
                  {formatMoney(r.totals.income)}
                </div>
              </div>
            </div>
          </div>
          <h2 className="h5">По месяцам</h2>
          {table(r.by_month, true, 'Месяц')}
          <h2 className="h5">По разделам</h2>
          {table(r.by_section, false, 'Раздел')}
        </>
      )}
    </ModLayout>
  )
}
