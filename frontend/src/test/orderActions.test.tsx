import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'

import { OrderActions } from '../components/OrderActions'

function order(status: string, actions: string[], extra = {}) {
  return {
    id: 7,
    status,
    kind: 'customization',
    price: '1500.00',
    days: 3,
    revisions: 0,
    max_revisions: 2,
    payment_amount: '1500.00',
    actions,
    ...extra,
  }
}

function setup(status: string, actions: string[], extra = {}) {
  const onAction = vi.fn()
  render(
    <MemoryRouter>
      <OrderActions order={order(status, actions, extra)} onAction={onAction} />
    </MemoryRouter>,
  )
  return onAction
}

const BUTTONS = [
  'Отправить предложение',
  'Согласиться и оплатить',
  'Оплатить',
  'Сдать работу',
  'Принять работу',
  'Отказаться от заказа',
  'Отменить',
]

function visible() {
  return BUTTONS.filter((b) => screen.queryAllByRole('button', { name: new RegExp(`^${b}`) }).length > 0)
}

describe('карточка действий заказа', () => {
  it('продавец в статусе «Новый»: предложение и отмена', () => {
    setup('new', ['offer', 'cancel'])
    expect(visible()).toEqual(['Отправить предложение', 'Отменить'])
    expect(screen.getByText('Предложить цену и срок')).toBeInTheDocument()
  })

  it('покупатель видит предложение: согласиться и оплатить сумму', () => {
    const onAction = setup('offer', ['accept_offer', 'cancel'], { payment_amount: '2500.00' })
    expect(visible()).toEqual(['Согласиться и оплатить', 'Отменить'])
    fireEvent.click(screen.getByRole('button', { name: /Согласиться и оплатить 2\s500/ }))
    expect(onAction).toHaveBeenCalledWith({ type: 'accept_offer' })
  })

  it('продавец в работе: сдать или отказаться; в «Сдан» у покупателя — принять и вернуть', () => {
    setup('in_work', ['submit', 'refuse'])
    expect(visible()).toEqual(['Сдать работу', 'Отказаться от заказа'])
  })

  it('возврат на доработку показывает счётчик и требует подтверждения', () => {
    const onAction = setup('submitted', ['accept', 'revision', 'dispute'], { revisions: 1 })
    expect(screen.getByRole('button', { name: 'Вернуть на доработку (2 из 2)' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Открыть спор/ })).toHaveAttribute(
      'href',
      '/disputes/new/?order=7',
    )
    fireEvent.change(screen.getByLabelText(/Что исправить/), { target: { value: 'Поправьте отступы' } })
    fireEvent.click(screen.getByRole('button', { name: /Вернуть на доработку/ }))
    expect(onAction).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }))
    expect(onAction).toHaveBeenCalledWith({ type: 'revision', comment: 'Поправьте отступы' })
  })

  it('без доступных действий карточка не показывается', () => {
    const { container } = render(
      <MemoryRouter>
        <OrderActions order={order('accepted', [])} onAction={() => undefined} />
      </MemoryRouter>,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('предложение отправляет цену и срок', () => {
    const onAction = setup('offer', ['offer', 'cancel'], { price: '700.00', days: 7 })
    expect(screen.getByText('Изменить предложение')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/Цена, ₽/), { target: { value: '900' } })
    fireEvent.click(screen.getByRole('button', { name: 'Отправить предложение' }))
    expect(onAction).toHaveBeenCalledWith({ type: 'offer', price: '900', days: '7' })
  })
})
