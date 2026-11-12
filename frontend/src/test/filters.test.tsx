import { fireEvent, render, screen } from '@testing-library/react'

import type { S } from '../api/client'
import { Filters, filtersToParams, hasFilters, readFilters } from '../components/Filters'

const refs: S['CatalogRefs'] = {
  sections: [
    {
      id: 1,
      name: 'Сайты',
      slug: 'sites',
      icon: 'bi-window',
      position: 0,
      product_count: 3,
      children: [{ id: 5, name: 'Лендинг', slug: 'landing', icon: '', parent_id: 1, position: 0 }],
    },
    { id: 2, name: 'Боты', slug: 'bots', icon: 'bi-robot', position: 1, product_count: 2, children: [] },
  ],
  technologies: [
    { id: 1, name: 'Python', slug: 'python' },
    { id: 2, name: 'JavaScript', slug: 'javascript' },
  ],
  platforms: [{ id: 1, name: 'Telegram', slug: 'telegram' }],
  sorts: [{ key: 'new', label: 'Новые' }],
}

describe('фильтры каталога', () => {
  it('читают параметры адресной строки', () => {
    const f = readFilters(
      new URLSearchParams('section=bots&tech=python&tech=javascript&price_min=100&rating=4'),
    )
    expect(f).toEqual({
      section: 'bots',
      category: '',
      price_min: '100',
      price_max: '',
      tech: ['python', 'javascript'],
      platform: [],
      rating: '4',
    })
    expect(hasFilters(new URLSearchParams('sort=cheap'))).toBe(false)
    expect(hasFilters(new URLSearchParams('q=бот'))).toBe(true)
  })

  it('собирают адрес: подкатегория важнее раздела, пустые значения не попадают, q и sort сохраняются', () => {
    const p = filtersToParams(
      {
        section: 'sites',
        category: 'landing',
        price_min: '',
        price_max: '5000',
        tech: ['python'],
        platform: [],
        rating: '',
      },
      { q: 'кофе', sort: 'cheap' },
    )
    expect(p.toString()).toBe(
      'q=%D0%BA%D0%BE%D1%84%D0%B5&category=landing&price_max=5000&tech=python&sort=cheap',
    )
    expect(filtersToParams(readFilters(new URLSearchParams()), { sort: 'new' }).toString()).toBe('')
  })

  it('форма отдаёт выбранные значения и сбрасывает их', () => {
    const onApply = vi.fn()
    const onReset = vi.fn()
    render(
      <Filters refs={refs} value={readFilters(new URLSearchParams())} onApply={onApply} onReset={onReset} />,
    )
    fireEvent.click(screen.getByLabelText('Лендинг'))
    fireEvent.click(screen.getByLabelText('Python'))
    fireEvent.click(screen.getByLabelText('Telegram'))
    fireEvent.change(screen.getByLabelText('Цена до'), { target: { value: '3000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Показать' }))
    expect(onApply).toHaveBeenCalledWith({
      section: '',
      category: 'landing',
      price_min: '',
      price_max: '3000',
      tech: ['python'],
      platform: ['telegram'],
      rating: '',
    })
    // выбор раздела снимает подкатегорию
    fireEvent.click(screen.getByLabelText('Боты'))
    fireEvent.click(screen.getByRole('button', { name: 'Показать' }))
    expect(onApply.mock.calls[1][0]).toMatchObject({ section: 'bots', category: '' })
    fireEvent.click(screen.getByRole('button', { name: 'Сбросить фильтры' }))
    expect(onReset).toHaveBeenCalled()
  })
})
