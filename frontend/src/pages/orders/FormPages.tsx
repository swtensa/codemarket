import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import { client, unwrap } from '../../api/client'
import { Breadcrumbs, ConfirmButton, ErrorState, FormError, Loading } from '../../components/ui'
import { useTitle } from '../../hooks/misc'
import { useAuth } from '../../hooks/useAuth'
import { useToast } from '../../hooks/useToast'
import { errorText } from '../../lib/forms'
import { plural } from '../../lib/format'

function useTarget(kind: 'disputes' | 'reviews') {
  const [params] = useSearchParams()
  const purchase = params.get('purchase') ? Number(params.get('purchase')) : undefined
  const order = params.get('order') ? Number(params.get('order')) : undefined
  return useQuery({
    queryKey: [kind, 'new', purchase, order],
    queryFn: () =>
      unwrap(
        kind === 'disputes'
          ? client.GET('/api/disputes/new', { params: { query: { purchase, order } } })
          : client.GET('/api/reviews/new', { params: { query: { purchase, order } } }),
      ),
  })
}

/** Открыть спор по покупке (?purchase=) или заказу (?order=). */
export function DisputeNewPage() {
  useTitle('Открыть спор')
  const q = useTarget('disputes')
  const { config } = useAuth()
  const navigate = useNavigate()
  const toast = useToast()
  const qc = useQueryClient()
  const [reasonType, setReasonType] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  if (q.isLoading) return <Loading />
  if (q.isError || !q.data) return <ErrorState error={q.error} />
  const d = q.data
  const submit = async () => {
    setError('')
    try {
      const r = await unwrap(
        client.POST('/api/disputes', {
          body: { purchase_id: d.purchase_id, order_id: d.order_id, reason_type: reasonType, reason },
        }),
      )
      toast.push('Спор открыт. Администратор рассмотрит его и сообщит решение.')
      void qc.invalidateQueries()
      navigate(r.url)
    } catch (err) {
      setError(errorText(err))
    }
  }
  const label = d.purchase_id ? `Покупка №${d.purchase_id}` : `Заказ №${d.order_id}`
  return (
    <>
      <Breadcrumbs items={[{ to: d.back, label }, { label: 'Открыть спор' }]} />
      <div className="row justify-content-center">
        <div className="col-lg-8">
          <h1 className="h3 mb-3">Открыть спор: {d.product.title}</h1>
          <div className="alert alert-warning d-flex gap-2">
            <i className="bi bi-exclamation-triangle-fill" />
            <div>
              <strong>Правила спора.</strong>{' '}
              {d.purchase_id ? (
                <>
                  Спор по покупке можно открыть в течение {config?.hold_days ?? 7} дней после оплаты
                  {d.days_left
                    ? ` (осталось ${d.days_left} ${plural(d.days_left, ['день', 'дня', 'дней'])})`
                    : ''}
                  , если продукт не работает или не соответствует описанию. Причина «передумал» не
                  принимается: после выдачи кода деньги не возвращаются без проверки администратором.
                </>
              ) : (
                'Спор по заказу останавливает автоматическую приёмку. Администратор изучит переписку и результат работы.'
              )}{' '}
              Пока спор открыт, деньги продавцу не переводятся.
            </div>
          </div>
          <form className="card" noValidate onSubmit={(e: FormEvent) => e.preventDefault()}>
            <div className="card-body p-4">
              <FormError error={error} />
              <fieldset className="mb-3">
                <legend className="form-label fw-semibold fs-6">
                  Причина <span className="required-mark">*</span>
                </legend>
                {d.reasons.map(([code, text]) => (
                  <div className="form-check" key={code}>
                    <input
                      className="form-check-input"
                      type="radio"
                      name="reason_type"
                      id={`r-${code}`}
                      checked={reasonType === code}
                      onChange={() => setReasonType(code)}
                    />
                    <label className="form-check-label" htmlFor={`r-${code}`}>
                      {text}
                    </label>
                  </div>
                ))}
              </fieldset>
              <label className="form-label fw-semibold" htmlFor="reason">
                Опишите проблему <span className="required-mark">*</span>
              </label>
              <textarea
                className="form-control mb-3"
                id="reason"
                rows={5}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Что именно не работает, какие шаги вы делали, что ожидали увидеть"
              />
              <ConfirmButton
                className="btn btn-danger"
                text="Открыть спор? Решение примет администратор."
                onConfirm={submit}
              >
                Открыть спор
              </ConfirmButton>
              <Link className="btn btn-link" to={d.back}>
                Отмена
              </Link>
            </div>
          </form>
        </div>
      </div>
    </>
  )
}

/** Отзыв о продукте (?purchase=) или о доработке (?order=). */
export function ReviewNewPage() {
  useTitle('Отзыв')
  const q = useTarget('reviews')
  const navigate = useNavigate()
  const toast = useToast()
  const qc = useQueryClient()
  const [rating, setRating] = useState(0)
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  if (q.isLoading) return <Loading />
  if (q.isError || !q.data) return <ErrorState error={q.error} />
  const d = q.data
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    try {
      const r = await unwrap(
        client.POST('/api/reviews', {
          body: { purchase_id: d.purchase_id, order_id: d.order_id, rating: rating || null, text },
        }),
      )
      toast.push('Спасибо за отзыв!')
      void qc.invalidateQueries()
      navigate(r.url)
    } catch (err) {
      setError(errorText(err))
    }
  }
  const label = d.purchase_id ? `Покупка №${d.purchase_id}` : `Заказ №${d.order_id}`
  return (
    <>
      <Breadcrumbs items={[{ to: d.back, label }, { label: 'Отзыв' }]} />
      <div className="row justify-content-center">
        <div className="col-lg-7">
          <h1 className="h3 mb-3">
            {d.purchase_id ? 'Отзыв о продукте' : 'Отзыв о доработке'}: {d.product.title}
          </h1>
          <form className="card" onSubmit={submit} noValidate>
            <div className="card-body p-4">
              <FormError error={error} />
              <fieldset className="mb-3">
                <legend className="form-label fw-semibold fs-6">
                  Оценка <span className="required-mark">*</span>
                </legend>
                <div className="cm-rate">
                  {[5, 4, 3, 2, 1].map((i) => (
                    <span key={i} style={{ display: 'contents' }}>
                      <input
                        type="radio"
                        name="rating"
                        id={`star${i}`}
                        value={i}
                        checked={rating === i}
                        onChange={() => setRating(i)}
                      />
                      <label htmlFor={`star${i}`} title={String(i)} aria-label={`${i} из 5`}>
                        <i className="bi bi-star-fill" />
                      </label>
                    </span>
                  ))}
                </div>
              </fieldset>
              <label className="form-label fw-semibold" htmlFor="text">
                Отзыв
              </label>
              <textarea
                className="form-control mb-3"
                id="text"
                rows={5}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Что понравилось, что можно улучшить"
              />
              <button className="btn btn-primary">Отправить отзыв</button>
            </div>
          </form>
        </div>
      </div>
    </>
  )
}
