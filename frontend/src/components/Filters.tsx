/* eslint-disable react-refresh/only-export-components */
import { useState, type FormEvent } from 'react'

import type { S } from '../api/client'

/** Значения фильтров каталога из адресной строки (?section=…&category=…&tech=…&platform=…). */
export type FilterState = {
  section: string
  category: string
  price_min: string
  price_max: string
  tech: string[]
  platform: string[]
  rating: string
}

export function readFilters(params: URLSearchParams): FilterState {
  return {
    section: params.get('section') ?? '',
    category: params.get('category') ?? '',
    price_min: params.get('price_min') ?? '',
    price_max: params.get('price_max') ?? '',
    tech: params.getAll('tech'),
    platform: params.getAll('platform'),
    rating: params.get('rating') ?? '',
  }
}

/** Собрать параметры адреса: фильтры + сохранённые q и sort; пустые значения не попадают в адрес. */
export function filtersToParams(f: FilterState, keep: { q?: string; sort?: string } = {}): URLSearchParams {
  const p = new URLSearchParams()
  if (keep.q) p.set('q', keep.q)
  if (f.category) p.set('category', f.category)
  else if (f.section) p.set('section', f.section)
  if (f.price_min) p.set('price_min', f.price_min)
  if (f.price_max) p.set('price_max', f.price_max)
  f.tech.forEach((t) => p.append('tech', t))
  f.platform.forEach((t) => p.append('platform', t))
  if (f.rating) p.set('rating', f.rating)
  if (keep.sort && keep.sort !== 'new') p.set('sort', keep.sort)
  return p
}

export function hasFilters(params: URLSearchParams): boolean {
  return ['q', 'section', 'category', 'price_min', 'price_max', 'tech', 'platform', 'rating'].some((k) =>
    params.has(k),
  )
}

function toggle(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((x) => x !== value) : [...list, value]
}

export function Filters({
  refs,
  value,
  onApply,
  onReset,
}: {
  refs: S['CatalogRefs']
  value: FilterState
  onApply: (f: FilterState) => void
  onReset: () => void
}) {
  const [f, setF] = useState<FilterState>(value)
  const submit = (e: FormEvent) => {
    e.preventDefault()
    onApply(f)
  }
  return (
    <form className="card w-100" onSubmit={submit} aria-label="Фильтры каталога">
      <div className="card-body">
        <div className="mb-3">
          <div className="fw-bold mb-2">Раздел</div>
          <div className="form-check">
            <input
              className="form-check-input"
              type="radio"
              name="section"
              id="sec-all"
              checked={!f.section && !f.category}
              onChange={() => setF({ ...f, section: '', category: '' })}
            />
            <label className="form-check-label" htmlFor="sec-all">
              Все
            </label>
          </div>
          {refs.sections.map((s) => (
            <div key={s.slug}>
              <div className="form-check">
                <input
                  className="form-check-input"
                  type="radio"
                  name="section"
                  id={`sec-${s.slug}`}
                  checked={f.section === s.slug && !f.category}
                  onChange={() => setF({ ...f, section: s.slug, category: '' })}
                />
                <label className="form-check-label" htmlFor={`sec-${s.slug}`}>
                  {s.name}
                </label>
              </div>
              <div className="ms-4">
                {s.children.map((c) => (
                  <div key={c.slug} className="form-check small">
                    <input
                      className="form-check-input"
                      type="radio"
                      name="category"
                      id={`cat-${c.slug}`}
                      checked={f.category === c.slug}
                      onChange={() => setF({ ...f, category: c.slug, section: '' })}
                    />
                    <label className="form-check-label" htmlFor={`cat-${c.slug}`}>
                      {c.name}
                    </label>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="mb-3">
          <div className="fw-bold mb-2">Цена, ₽</div>
          <div className="d-flex gap-2">
            <input
              className="form-control form-control-sm"
              type="number"
              min={0}
              placeholder="от"
              aria-label="Цена от"
              value={f.price_min}
              onChange={(e) => setF({ ...f, price_min: e.target.value })}
            />
            <input
              className="form-control form-control-sm"
              type="number"
              min={0}
              placeholder="до"
              aria-label="Цена до"
              value={f.price_max}
              onChange={(e) => setF({ ...f, price_max: e.target.value })}
            />
          </div>
        </div>
        <div className="mb-3">
          <div className="fw-bold mb-2">Технологии</div>
          {refs.technologies.map((t) => (
            <div key={t.slug} className="form-check small">
              <input
                className="form-check-input"
                type="checkbox"
                id={`tech-${t.slug}`}
                checked={f.tech.includes(t.slug)}
                onChange={() => setF({ ...f, tech: toggle(f.tech, t.slug) })}
              />
              <label className="form-check-label" htmlFor={`tech-${t.slug}`}>
                {t.name}
              </label>
            </div>
          ))}
        </div>
        <div className="mb-3">
          <div className="fw-bold mb-2">Платформы</div>
          {refs.platforms.map((p) => (
            <div key={p.slug} className="form-check small">
              <input
                className="form-check-input"
                type="checkbox"
                id={`pl-${p.slug}`}
                checked={f.platform.includes(p.slug)}
                onChange={() => setF({ ...f, platform: toggle(f.platform, p.slug) })}
              />
              <label className="form-check-label" htmlFor={`pl-${p.slug}`}>
                {p.name}
              </label>
            </div>
          ))}
        </div>
        <div className="mb-3">
          <label className="fw-bold mb-2 d-block" htmlFor="rating">
            Рейтинг от
          </label>
          <select
            id="rating"
            className="form-select form-select-sm"
            value={f.rating}
            onChange={(e) => setF({ ...f, rating: e.target.value })}
          >
            <option value="">любой</option>
            <option value="4.5">4,5 и выше</option>
            <option value="4">4 и выше</option>
            <option value="3">3 и выше</option>
          </select>
        </div>
        <button className="btn btn-primary w-100 mb-2" type="submit">
          Показать
        </button>
        <button className="btn btn-outline-primary w-100" type="button" onClick={onReset}>
          Сбросить фильтры
        </button>
      </div>
    </form>
  )
}
