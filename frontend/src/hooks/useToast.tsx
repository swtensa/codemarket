/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

export type ToastLevel = 'success' | 'danger' | 'warning' | 'info'
type Toast = { id: number; text: string; level: ToastLevel }

const ICONS: Record<ToastLevel, string> = {
  success: 'bi-check-circle-fill',
  danger: 'bi-exclamation-octagon-fill',
  warning: 'bi-exclamation-triangle-fill',
  info: 'bi-info-circle-fill',
}

type Ctx = { push: (text: string, level?: ToastLevel) => void }
const ToastContext = createContext<Ctx>({ push: () => undefined })

let seq = 0

/** Тосты успеха и ошибок, исчезают через 5 секунд. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const remove = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), [])
  const push = useCallback(
    (text: string, level: ToastLevel = 'success') => {
      const id = ++seq
      setToasts((t) => [...t.slice(-3), { id, text, level }])
      setTimeout(() => remove(id), 5000)
    },
    [remove],
  )
  const value = useMemo(() => ({ push }), [push])
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="cm-toasts" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`alert alert-${t.level} shadow-sm d-flex gap-2 align-items-start`}
            role="alert"
          >
            <i className={`bi ${ICONS[t.level]}`} aria-hidden="true" />
            <div className="flex-grow-1">{t.text}</div>
            <button
              type="button"
              className="btn-close btn-sm"
              aria-label="Закрыть"
              onClick={() => remove(t.id)}
            />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}
