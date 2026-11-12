/* eslint-disable react-refresh/only-export-components */
import { useState, type ReactNode } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router'

import { ApiError } from '../api/client'
import { similarityTone } from '../lib/format'

// Цвет статуса: success / warning / danger / neutral (как в Django-версии)
export const STATUS_TONE: Record<string, 'success' | 'warning' | 'danger' | 'neutral'> = {
  draft: 'neutral',
  checking: 'warning',
  moderation: 'warning',
  published: 'success',
  rejected: 'danger',
  hidden: 'neutral',
  blocked: 'danger',
  rejected_auto: 'danger',
  appeal: 'warning',
  approved: 'success',
  pending: 'warning',
  paid: 'success',
  completed: 'success',
  cancelled: 'neutral',
  dispute: 'danger',
  refunded: 'danger',
  partially_refunded: 'danger',
  new: 'warning',
  offer: 'warning',
  awaiting_payment: 'warning',
  in_work: 'warning',
  submitted: 'warning',
  revision: 'warning',
  accepted: 'success',
  held: 'warning',
  available: 'success',
  requested: 'warning',
  none: 'neutral',
  invited: 'warning',
  granted: 'success',
  revoked: 'danger',
  open: 'danger',
  closed: 'neutral',
  active: 'success',
  succeeded: 'success',
  canceled: 'neutral',
}

const TONE_ICON = {
  danger: 'bi-exclamation-octagon',
  success: 'bi-check-circle',
  warning: 'bi-hourglass-split',
  neutral: 'bi-dot',
}

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const tone = STATUS_TONE[status] ?? 'neutral'
  return (
    <span className={`cm-status cm-status-${tone}`}>
      <i className={`bi ${TONE_ICON[tone]}`} aria-hidden="true" /> {label ?? status}
    </span>
  )
}

export function Stars({ value }: { value: number | string | null | undefined }) {
  const r = Number(value ?? 0) || 0
  return (
    <span className="cm-stars" aria-label={`Рейтинг ${r.toFixed(1)} из 5`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <i
          key={i}
          className={`bi ${r >= i - 0.25 ? 'bi-star-fill' : r >= i - 0.75 ? 'bi-star-half' : 'bi-star'}`}
          aria-hidden="true"
        />
      ))}
    </span>
  )
}

export function SimilarityBar({ value }: { value: number | null | undefined }) {
  const v = value ?? 0
  const tone = similarityTone(v)
  return (
    <div className="d-flex align-items-center gap-2">
      <div
        className={`cm-sim cm-sim-${tone} flex-grow-1`}
        role="img"
        aria-label={`Сходство ${Math.round(v * 100)} %`}
      >
        <div style={{ width: `${Math.min(100, v * 100)}%` }} />
      </div>
      <span className="small fw-semibold">{Math.round(v * 100)}&nbsp;%</span>
    </div>
  )
}

/** Пагинация: меняет ?page= и сохраняет остальные параметры адреса. */
export function Pagination({ page, pages }: { page: number; pages: number }) {
  const [params] = useSearchParams()
  const { pathname } = useLocation()
  if (pages <= 1) return null
  const href = (n: number) => {
    const p = new URLSearchParams(params)
    if (n === 1) p.delete('page')
    else p.set('page', String(n))
    const q = p.toString()
    return q ? `${pathname}?${q}` : pathname
  }
  const nums = Array.from({ length: pages }, (_, i) => i + 1).filter(
    (n) => Math.abs(n - page) <= 2 || n === 1 || n === pages,
  )
  return (
    <nav aria-label="Страницы" className="mt-4">
      <ul className="pagination justify-content-center flex-wrap">
        <li className={`page-item ${page <= 1 ? 'disabled' : ''}`}>
          <Link className="page-link" to={href(page - 1)} aria-label="Предыдущая">
            ‹
          </Link>
        </li>
        {nums.map((n, i) => (
          <li key={n} className={`page-item ${n === page ? 'active' : ''}`}>
            {i > 0 && n - nums[i - 1] > 1 ? <span className="page-link border-0">…</span> : null}
            <Link className="page-link" to={href(n)} aria-current={n === page ? 'page' : undefined}>
              {n}
            </Link>
          </li>
        ))}
        <li className={`page-item ${page >= pages ? 'disabled' : ''}`}>
          <Link className="page-link" to={href(page + 1)} aria-label="Следующая">
            ›
          </Link>
        </li>
      </ul>
    </nav>
  )
}

export function EmptyState({
  icon = 'bi-inbox',
  title,
  children,
}: {
  icon?: string
  title: string
  children?: ReactNode
}) {
  return (
    <div className="cm-empty">
      <i className={`bi ${icon}`} aria-hidden="true" />
      <div className="fw-semibold mb-1">{title}</div>
      {children}
    </div>
  )
}

export function Loading({ text = 'Загрузка…' }: { text?: string }) {
  return (
    <div className="text-center text-muted py-5" role="status">
      <div className="spinner-border spinner-border-sm me-2" aria-hidden="true" />
      {text}
    </div>
  )
}

/** Ошибка загрузки с кнопкой «Повторить»; 403/404 — понятный текст. */
export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const e = error instanceof ApiError ? error : null
  if (e?.status === 404) return <NotFoundBlock />
  if (e?.status === 403) return <ForbiddenBlock text={e.message} />
  return (
    <div className="cm-empty" role="alert">
      <i className="bi bi-wifi-off" aria-hidden="true" />
      <div className="fw-semibold mb-2">{e?.message ?? 'Не удалось загрузить данные.'}</div>
      {onRetry && (
        <button type="button" className="btn btn-outline-primary" onClick={onRetry}>
          <i className="bi bi-arrow-clockwise me-1" />
          Повторить
        </button>
      )}
    </div>
  )
}

export function NotFoundBlock() {
  return (
    <div className="cm-empty">
      <i className="bi bi-signpost-split" aria-hidden="true" />
      <h1 className="h4">Страница не найдена</h1>
      <p>Возможно, адрес набран с ошибкой или страница удалена.</p>
      <Link className="btn btn-primary" to="/">
        В каталог
      </Link>
    </div>
  )
}

export function ForbiddenBlock({ text = 'Доступ запрещён' }: { text?: string }) {
  return (
    <div className="cm-empty">
      <i className="bi bi-shield-lock" aria-hidden="true" />
      <h1 className="h4">Доступ запрещён</h1>
      <p>{text === 'Доступ запрещён' ? 'У вас нет прав на просмотр этой страницы.' : text}</p>
      <Link className="btn btn-primary" to="/">
        В каталог
      </Link>
    </div>
  )
}

/** Поле формы с подписью, подсказкой и ошибкой под полем. */
export function Field({
  label,
  id,
  error,
  help,
  required,
  children,
}: {
  label: ReactNode
  id: string
  error?: string
  help?: ReactNode
  required?: boolean
  children: ReactNode
}) {
  return (
    <div className="mb-3">
      <label className="form-label fw-semibold" htmlFor={id}>
        {label}
        {required && <span className="required-mark"> *</span>}
      </label>
      {children}
      {help && !error && <div className="form-text">{help}</div>}
      {error && (
        <div className="cm-field-error" id={`${id}-error`}>
          <i className="bi bi-exclamation-circle" aria-hidden="true" />
          {error}
        </div>
      )}
    </div>
  )
}

export function FormError({ error }: { error?: string }) {
  if (!error) return null
  return (
    <div className="alert alert-danger d-flex gap-2" role="alert">
      <i className="bi bi-exclamation-octagon-fill" aria-hidden="true" />
      <div>{error}</div>
    </div>
  )
}

/** Модальное окно подтверждения опасного действия. */
export function ConfirmButton({
  className,
  children,
  text,
  onConfirm,
  disabled,
  okLabel = 'Подтвердить',
}: {
  className: string
  children: ReactNode
  text: string
  onConfirm: () => void
  disabled?: boolean
  okLabel?: string
}) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type="button" className={className} onClick={() => setOpen(true)} disabled={disabled}>
        {children}
      </button>
      {open && (
        <>
          <div
            className="modal fade show d-block"
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            onClick={() => setOpen(false)}
          >
            <div className="modal-dialog modal-dialog-centered" onClick={(e) => e.stopPropagation()}>
              <div className="modal-content">
                <div className="modal-header">
                  <h5 className="modal-title">
                    <i className="bi bi-exclamation-triangle text-danger me-2" />
                    Подтвердите действие
                  </h5>
                  <button
                    type="button"
                    className="btn-close"
                    aria-label="Закрыть"
                    onClick={() => setOpen(false)}
                  />
                </div>
                <div className="modal-body">{text}</div>
                <div className="modal-footer">
                  <button type="button" className="btn btn-outline-primary" onClick={() => setOpen(false)}>
                    Отмена
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger"
                    autoFocus
                    onClick={() => {
                      setOpen(false)
                      onConfirm()
                    }}
                  >
                    {okLabel}
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div className="modal-backdrop fade show" />
        </>
      )}
    </>
  )
}

export function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false)
  return (
    <button
      type="button"
      className="btn btn-outline-primary btn-sm"
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(() => {
          setDone(true)
          setTimeout(() => setDone(false), 1500)
        })
      }}
    >
      {done ? (
        <>
          <i className="bi bi-check2" /> Скопировано
        </>
      ) : (
        <>
          <i className="bi bi-clipboard" /> Копировать
        </>
      )}
    </button>
  )
}

export function Breadcrumbs({ items }: { items: { to?: string; label: string }[] }) {
  return (
    <nav aria-label="breadcrumb">
      <ol className="breadcrumb">
        {items.map((it, i) =>
          it.to && i < items.length - 1 ? (
            <li key={i} className="breadcrumb-item">
              <Link to={it.to}>{it.label}</Link>
            </li>
          ) : (
            <li key={i} className="breadcrumb-item active" aria-current="page">
              {it.label}
            </li>
          ),
        )}
      </ol>
    </nav>
  )
}

/** Текст с переносами строк и кликабельными ссылками (как linebreaks|urlize). */
export function RichText({ text }: { text: string }) {
  const paragraphs = text.split(/\n{2,}/)
  return (
    <>
      {paragraphs.map((p, i) => (
        <p key={i}>
          {p.split('\n').map((line, j) => (
            <span key={j}>
              {j > 0 && <br />}
              {line.split(/(https?:\/\/[^\s]+)/g).map((part, k) =>
                /^https?:\/\//.test(part) ? (
                  <a key={k} href={part} target="_blank" rel="nofollow noopener noreferrer">
                    {part}
                  </a>
                ) : (
                  part
                ),
              )}
            </span>
          ))}
        </p>
      ))}
    </>
  )
}
