import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { client, unwrap } from '../../api/client'
import { Filters, filtersToParams, hasFilters, readFilters } from '../../components/Filters'
import { ProductCard, ProductCardSkeleton } from '../../components/ProductCard'
import { ErrorState, Pagination } from '../../components/ui'
import { useTitle } from '../../hooks/misc'
import { plural } from '../../lib/format'

/** Главная = каталог: поиск, фильтры и сортировка в адресной строке, страницы по 12. */
export default function CatalogPage() {
  const [params, setParams] = useSearchParams()
  const [showFilters, setShowFilters] = useState(false)
  const q = params.get('q') ?? ''
  const sort = params.get('sort') ?? 'new'
  const page = Number(params.get('page') ?? '1') || 1
  useTitle(q ? `Поиск «${q}»` : 'Каталог')

  const refs = useQuery({
    queryKey: ['refs'],
    queryFn: () => unwrap(client.GET('/api/catalog/refs')),
    staleTime: 300_000,
  })
  const query = {
    q,
    section: params.get('section') ?? '',
    category: params.get('category') ?? '',
    price_min: params.get('price_min') ?? undefined,
    price_max: params.get('price_max') ?? undefined,
    tech: params.getAll('tech'),
    platform: params.getAll('platform'),
    rating: params.get('rating') ?? undefined,
    sort,
    page,
  }
  const products = useQuery({
    queryKey: ['catalog', params.toString()],
    queryFn: () => unwrap(client.GET('/api/catalog/products', { params: { query } })),
    placeholderData: keepPreviousData,
  })

  const filters = readFilters(params)
  const currentSection =
    filters.section ||
    refs.data?.sections.find((s) => s.children.some((c) => c.slug === filters.category))?.slug ||
    ''
  const apply = (next: URLSearchParams) => {
    setParams(next)
    setShowFilters(false)
    document.getElementById('catalog')?.scrollIntoView({ behavior: 'smooth' })
  }
  const reset = () => apply(new URLSearchParams())

  return (
    <>
      {!hasFilters(params) && page === 1 && (
        <section className="cm-hero mb-4">
          <div className="row align-items-center g-3">
            <div className="col-lg-8">
              <h1 className="mb-2">Готовый код с доработкой от автора</h1>
              <p className="lead mb-3">
                Шаблоны сайтов, модули, боты и скрипты. Каждая версия проверяется на заимствования, а оплата
                доработки удерживается до приёмки работы.
              </p>
              <a className="btn btn-primary me-2 mb-2" href="#catalog">
                Смотреть каталог
              </a>
              <Link className="btn btn-accent mb-2" to="/sell/">
                Начать продавать
              </Link>
            </div>
            <div className="col-lg-4 d-none d-lg-block text-center">
              <i
                className="bi bi-shield-lock"
                style={{ fontSize: '7rem', color: 'var(--c-primary)', opacity: 0.85 }}
              />
            </div>
          </div>
        </section>
      )}

      <div className="row g-3 mb-4">
        {refs.data?.sections.map((s) => (
          <div key={s.slug} className="col-6 col-lg-3">
            <Link
              className={`cm-section-tile ${currentSection === s.slug ? 'active' : ''}`}
              to={`/?section=${s.slug}`}
            >
              <i className={`bi ${s.icon || 'bi-grid'}`} />
              <div>
                <div className="fw-bold">{s.name}</div>
                <div className="small text-muted">
                  {s.product_count} {plural(s.product_count, ['продукт', 'продукта', 'продуктов'])}
                </div>
              </div>
            </Link>
          </div>
        ))}
      </div>

      <div className="row g-4" id="catalog">
        <aside className="col-lg-3">
          <div
            className={`offcanvas-lg offcanvas-start ${showFilters ? 'show' : ''}`}
            tabIndex={-1}
            aria-labelledby="cmFiltersLabel"
          >
            <div className="offcanvas-header">
              <h2 className="offcanvas-title h5" id="cmFiltersLabel">
                Фильтры
              </h2>
              <button
                type="button"
                className="btn-close"
                aria-label="Закрыть"
                onClick={() => setShowFilters(false)}
              />
            </div>
            <div className="offcanvas-body">
              {refs.data && (
                <Filters
                  key={params.toString()}
                  refs={refs.data}
                  value={filters}
                  onApply={(f) => apply(filtersToParams(f, { q, sort }))}
                  onReset={reset}
                />
              )}
            </div>
          </div>
          {showFilters && (
            <div className="offcanvas-backdrop fade show d-lg-none" onClick={() => setShowFilters(false)} />
          )}
        </aside>

        <section className="col-lg-9">
          <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
            <button
              className="btn btn-outline-primary btn-sm d-lg-none"
              type="button"
              onClick={() => setShowFilters(true)}
            >
              <i className="bi bi-funnel me-1" />
              Фильтры
            </button>
            <div className="fw-semibold">Найдено {products.data?.total ?? '…'}</div>
            {q && <span className="text-muted">по запросу «{q}»</span>}
            <div className="ms-auto d-flex align-items-center gap-2">
              <label htmlFor="sort" className="small text-muted text-nowrap">
                Сортировка
              </label>
              <select
                className="form-select form-select-sm"
                id="sort"
                value={sort}
                onChange={(e) => {
                  const p = new URLSearchParams(params)
                  p.delete('page')
                  if (e.target.value === 'new') p.delete('sort')
                  else p.set('sort', e.target.value)
                  setParams(p)
                }}
              >
                {(refs.data?.sorts ?? [{ key: 'new', label: 'Новые' }]).map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {products.isError ? (
            <ErrorState error={products.error} onRetry={() => products.refetch()} />
          ) : products.isLoading || !products.data ? (
            <div className="row row-cols-1 row-cols-md-2 row-cols-xl-3 g-3">
              {Array.from({ length: 6 }, (_, i) => (
                <div className="col" key={i}>
                  <ProductCardSkeleton />
                </div>
              ))}
            </div>
          ) : products.data.items.length ? (
            <>
              <div className="row row-cols-1 row-cols-md-2 row-cols-xl-3 g-3">
                {products.data.items.map((p) => (
                  <div className="col" key={p.id}>
                    <ProductCard p={p} />
                  </div>
                ))}
              </div>
              <Pagination page={products.data.page} pages={products.data.pages} />
            </>
          ) : (
            <div className="cm-empty card">
              <i className="bi bi-search" />
              <p className="fs-5 mb-3">Ничего не нашлось, попробуйте убрать часть фильтров</p>
              <div>
                <button className="btn btn-primary" type="button" onClick={reset}>
                  Сбросить фильтры
                </button>
              </div>
            </div>
          )}
        </section>
      </div>
    </>
  )
}
