import { useEffect, useRef, useState, type FormEvent } from 'react'

import { client, unwrap, upload, type S } from '../api/client'
import { useToast } from '../hooks/useToast'
import { errorText } from '../lib/forms'
import { formatDateTime } from '../lib/format'

type Props = {
  orderId: number
  sellerId?: number
  initial: S['MessageOut'][]
  lastId: number
  status: string
  canWrite: boolean
  canMarkResult: boolean
  onStatusChange: () => void
  sellerName: string
}

/** Чат заказа: опрос новых сообщений раз в 10 секунд (без WebSocket), файлы до 20 МБ, отметка «Результат». */
export function Chat({
  orderId,
  initial,
  lastId,
  status,
  canWrite,
  canMarkResult,
  onStatusChange,
  sellerName,
}: Props) {
  const toast = useToast()
  const [messages, setMessages] = useState(initial)
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [isResult, setIsResult] = useState(false)
  const [busy, setBusy] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const last = useRef(lastId)
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setMessages(initial)
    last.current = lastId
  }, [initial, lastId])

  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight
  }, [messages.length])

  useEffect(() => {
    const timer = setInterval(async () => {
      try {
        const data = await unwrap(
          client.GET('/api/orders/{pk}/messages', {
            params: { path: { pk: orderId }, query: { after: last.current } },
          }),
        )
        if (data.status !== status) onStatusChange()
        else if (data.messages.length) {
          last.current = data.last_id
          setMessages((m) => [...m, ...data.messages.filter((x) => !m.some((y) => y.id === x.id))])
        }
      } catch {
        // сеть пропала — следующая попытка через 10 секунд
      }
    }, 10_000)
    return () => clearInterval(timer)
  }, [orderId, status, onStatusChange])

  const send = async (e: FormEvent) => {
    e.preventDefault()
    if (!text.trim() && !file) return
    setBusy(true)
    const form = new FormData()
    form.append('text', text)
    form.append('is_result', String(isResult))
    form.append('after', String(last.current))
    if (file) form.append('attachment', file)
    try {
      const data = await upload<S['MessagesPoll']>(`/api/orders/${orderId}/messages`, form)
      last.current = data.last_id
      setMessages((m) => [...m, ...data.messages.filter((x) => !m.some((y) => y.id === x.id))])
      setText('')
      setFile(null)
      setIsResult(false)
      if (fileInput.current) fileInput.current.value = ''
      if (data.status !== status) onStatusChange()
    } catch (err) {
      toast.push(errorText(err), 'danger')
    } finally {
      setBusy(false)
    }
  }

  const markResult = async (id: number) => {
    try {
      const r = await unwrap(
        client.POST('/api/orders/{pk}/messages/{mid}/result', { params: { path: { pk: orderId, mid: id } } }),
      )
      toast.push(r.message)
      setMessages((m) => m.map((x) => (x.id === id ? { ...x, is_result: true } : x)))
    } catch (err) {
      toast.push(errorText(err), 'danger')
    }
  }

  return (
    <>
      <div className="cm-chat mb-2" ref={box} aria-live="polite">
        {messages.map((m) =>
          m.is_system ? (
            <div key={m.id} className="text-center small text-muted my-1">
              <i className="bi bi-info-circle me-1" />
              {m.text} · {formatDateTime(m.created_at)}
            </div>
          ) : (
            <div key={m.id} className={`cm-msg ${m.is_mine ? 'mine' : ''} ${m.is_result ? 'result' : ''}`}>
              {m.is_result && (
                <div className="small fw-bold" style={{ color: 'var(--c-sage-text)' }}>
                  <i className="bi bi-patch-check-fill me-1" />
                  Результат
                </div>
              )}
              {m.text && <div style={{ whiteSpace: 'pre-line' }}>{m.text}</div>}
              {m.attachment_url && (
                <a className="cm-attach" href={m.attachment_url}>
                  <i className="bi bi-file-earmark-arrow-down fs-5" />
                  <span className="text-break">{m.attachment_name}</span>
                </a>
              )}
              <div className="meta mt-1">
                {m.author === sellerName ? 'продавец' : 'покупатель'} {m.author} ·{' '}
                {formatDateTime(m.created_at)}
                {m.is_mine && !m.is_result && canMarkResult && (
                  <button
                    type="button"
                    className="btn btn-link btn-sm p-0 ms-1 align-baseline"
                    onClick={() => markResult(m.id)}
                  >
                    отметить как результат
                  </button>
                )}
              </div>
            </div>
          ),
        )}
      </div>
      {canWrite && (
        <form className="card" onSubmit={send}>
          <div className="card-body p-2">
            <label className="visually-hidden" htmlFor="msgText">
              Сообщение
            </label>
            <textarea
              className="form-control border-0"
              id="msgText"
              rows={2}
              placeholder="Сообщение"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <div className="d-flex flex-wrap align-items-center gap-2 mt-2">
              <label className="btn btn-sm btn-outline-primary mb-0">
                <i className="bi bi-paperclip" /> Файл
                <input
                  type="file"
                  className="d-none"
                  ref={fileInput}
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
              </label>
              <span className="small text-muted text-truncate" style={{ maxWidth: 180 }}>
                {file ? file.name : 'до 20 МБ'}
              </span>
              {canMarkResult && (
                <div className="form-check ms-2">
                  <input
                    className="form-check-input"
                    type="checkbox"
                    id="isResult"
                    checked={isResult}
                    onChange={(e) => setIsResult(e.target.checked)}
                  />
                  <label className="form-check-label small" htmlFor="isResult">
                    Это результат работы
                  </label>
                </div>
              )}
              <button className="btn btn-primary btn-sm ms-auto" type="submit" disabled={busy}>
                <i className="bi bi-send" /> Отправить
              </button>
            </div>
          </div>
        </form>
      )}
    </>
  )
}
