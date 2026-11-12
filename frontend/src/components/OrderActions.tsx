import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'

import type { S } from '../api/client'
import { formatMoney } from '../lib/format'
import { ConfirmButton } from './ui'

export type OrderAction =
  | { type: 'offer'; price: string; days: string }
  | { type: 'accept_offer' | 'pay' | 'submit' | 'accept' | 'cancel_overdue' | 'cancel' }
  | { type: 'revision'; comment: string }
  | { type: 'refuse'; reason: string }

type Props = {
  order: Pick<
    S['OrderDetail'],
    'id' | 'status' | 'kind' | 'price' | 'days' | 'revisions' | 'max_revisions' | 'payment_amount' | 'actions'
  >
  onAction: (a: OrderAction) => void
  busy?: boolean
}

/** Карточка действий заказа: показываются только кнопки, разрешённые сервером для текущего статуса и роли. */
export function OrderActions({ order, onAction, busy }: Props) {
  const acts = order.actions
  const [price, setPrice] = useState(order.price ? String(Math.round(Number(order.price))) : '')
  const [days, setDays] = useState(order.days ? String(order.days) : '')
  const [comment, setComment] = useState('')
  const [reason, setReason] = useState('')
  if (!acts.length) return null
  const amount = formatMoney(order.payment_amount ?? order.price)

  return (
    <div className="card">
      <div className="card-body d-grid gap-2">
        {acts.includes('offer') && (
          <form
            className="border rounded p-3"
            onSubmit={(e: FormEvent) => {
              e.preventDefault()
              onAction({ type: 'offer', price, days })
            }}
          >
            <div className="fw-semibold mb-2">
              {order.status === 'offer' ? 'Изменить предложение' : 'Предложить цену и срок'}
            </div>
            <div className="row g-2">
              <div className="col-6">
                <label className="form-label small" htmlFor="price">
                  Цена, ₽ <span className="required-mark">*</span>
                </label>
                <input
                  className="form-control"
                  type="number"
                  min={300}
                  step={1}
                  id="price"
                  required
                  value={price}
                  onChange={(e) => setPrice(e.target.value)}
                />
              </div>
              <div className="col-6">
                <label className="form-label small" htmlFor="days">
                  Срок, дней <span className="required-mark">*</span>
                </label>
                <input
                  className="form-control"
                  type="number"
                  min={1}
                  max={60}
                  id="days"
                  required
                  value={days}
                  onChange={(e) => setDays(e.target.value)}
                />
              </div>
            </div>
            <div className="form-text">Цена от 300 ₽, срок от 1 до 60 дней. Комиссия площадки 10 %.</div>
            <button className="btn btn-primary w-100 mt-2" disabled={busy}>
              Отправить предложение
            </button>
          </form>
        )}
        {acts.includes('accept_offer') && (
          <button
            className="btn btn-accent w-100"
            disabled={busy}
            onClick={() => onAction({ type: 'accept_offer' })}
          >
            Согласиться и оплатить {amount}
          </button>
        )}
        {acts.includes('pay') && (
          <button className="btn btn-accent w-100" disabled={busy} onClick={() => onAction({ type: 'pay' })}>
            <i className="bi bi-credit-card me-1" />
            Оплатить {amount}
          </button>
        )}
        {acts.includes('submit') && (
          <ConfirmButton
            className="btn btn-sage w-100"
            disabled={busy}
            text="Сдать работу покупателю? Перед этим отправьте сообщение с отметкой «Результат»."
            onConfirm={() => onAction({ type: 'submit' })}
          >
            <i className="bi bi-send-check me-1" />
            Сдать работу
          </ConfirmButton>
        )}
        {acts.includes('accept') && (
          <ConfirmButton
            className="btn btn-accent w-100"
            disabled={busy}
            text="Принять работу? Продавец получит оплату, вернуть заказ на доработку будет нельзя."
            onConfirm={() => onAction({ type: 'accept' })}
          >
            <i className="bi bi-check2-circle me-1" />
            Принять работу
          </ConfirmButton>
        )}
        {acts.includes('revision') && (
          <div className="border rounded p-3">
            <label className="form-label small fw-semibold" htmlFor="comment">
              Что исправить <span className="required-mark">*</span>
            </label>
            <textarea
              className="form-control mb-2"
              id="comment"
              rows={2}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
            />
            <ConfirmButton
              className="btn btn-outline-primary w-100"
              disabled={busy}
              text="Вернуть работу на доработку? Срок продлится на 3 дня."
              onConfirm={() => onAction({ type: 'revision', comment })}
            >
              Вернуть на доработку ({order.revisions + 1} из {order.max_revisions})
            </ConfirmButton>
          </div>
        )}
        {acts.includes('review') && (
          <Link className="btn btn-outline-primary" to={`/reviews/new/?order=${order.id}`}>
            <i className="bi bi-star me-1" />
            Оставить отзыв о доработке
          </Link>
        )}
        {acts.includes('refuse') && (
          <div className="border rounded p-3">
            <label className="form-label small fw-semibold" htmlFor="reason">
              Причина отказа <span className="required-mark">*</span>
            </label>
            <input
              className="form-control mb-2"
              id="reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <ConfirmButton
              className="btn btn-outline-danger w-100"
              disabled={busy}
              text="Отказаться от заказа? Покупателю будет возвращена вся оплата доработки."
              onConfirm={() => onAction({ type: 'refuse', reason })}
            >
              Отказаться от заказа
            </ConfirmButton>
          </div>
        )}
        {acts.includes('cancel_overdue') && (
          <ConfirmButton
            className="btn btn-outline-danger w-100"
            disabled={busy}
            text="Срок прошёл. Отменить заказ с полным возвратом оплаты доработки?"
            onConfirm={() => onAction({ type: 'cancel_overdue' })}
          >
            Отменить: срок прошёл
          </ConfirmButton>
        )}
        {acts.includes('dispute') && (
          <Link className="btn btn-outline-danger" to={`/disputes/new/?order=${order.id}`}>
            <i className="bi bi-exclamation-octagon me-1" />
            Открыть спор
          </Link>
        )}
        {acts.includes('cancel') && (
          <ConfirmButton
            className="btn btn-outline-danger w-100"
            disabled={busy}
            text={`Отменить ${order.kind === 'question' ? 'вопрос' : 'заказ'}?`}
            onConfirm={() => onAction({ type: 'cancel' })}
          >
            Отменить
          </ConfirmButton>
        )}
      </div>
    </div>
  )
}
