/* eslint-disable react-refresh/only-export-components */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, NavLink } from 'react-router'

import { client, unwrap, type S } from '../../api/client'
import { Breadcrumbs, EmptyState, StatusBadge } from '../../components/ui'
import { useAuth } from '../../hooks/useAuth'
import { useToast } from '../../hooks/useToast'
import { errorText } from '../../lib/forms'
import { formatDateTime } from '../../lib/format'

export function SellNav() {
  const { user } = useAuth()
  const tab = (to: string, label: string, end = false) => (
    <li className="nav-item">
      <NavLink end={end} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} to={to}>
        {label}
      </NavLink>
    </li>
  )
  return (
    <>
      <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
        <h1 className="h3 mb-0 me-auto">Продажи</h1>
        {user?.is_seller && (
          <Link className="btn btn-accent" to="/sell/products/new/">
            <i className="bi bi-plus-lg me-1" />
            Новый продукт
          </Link>
        )}
      </div>
      {user?.is_seller && (
        <ul className="nav nav-tabs mb-4">
          {tab('/sell/', 'Продукты', true)}
          {tab('/sell/orders/', 'Заказы и вопросы')}
          {tab('/sell/stats/', 'Статистика')}
          {tab('/balance/', 'Баланс')}
        </ul>
      )}
    </>
  )
}

export function ProductTabs({ product }: { product: S['ProductEditOut'] }) {
  const tab = (to: string, label: string) => (
    <li className="nav-item">
      <NavLink className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} to={to}>
        {label}
      </NavLink>
    </li>
  )
  return (
    <>
      <Breadcrumbs items={[{ to: '/sell/', label: 'Продажи' }, { label: product.title }]} />
      <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
        <h1 className="h3 mb-0 me-auto">{product.title}</h1>
        <StatusBadge status={product.status} label={product.status_label} />
        <Link className="btn btn-sm btn-outline-primary" to={`/p/${product.slug}/`}>
          <i className="bi bi-box-arrow-up-right me-1" />
          Страница продукта
        </Link>
      </div>
      <ul className="nav nav-tabs mb-4">
        {tab(`/sell/products/${product.id}/edit/`, 'Описание')}
        {tab(`/sell/products/${product.id}/media/`, 'Скриншоты и релиз')}
        {tab(`/sell/products/${product.id}/versions/`, 'Версии')}
      </ul>
    </>
  )
}

/** Блок «Проверить релиз»: релизы репозитория и кнопка «Отправить на проверку». */
export function Releases({
  product,
  releases,
  error,
  invalidate,
}: {
  product: S['ProductEditOut']
  releases: S['ReleaseOut'][]
  error: string
  invalidate: readonly unknown[][]
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const imp = useMutation({
    mutationFn: (tag: string) =>
      unwrap(
        client.POST('/api/seller/products/{pk}/versions/import', {
          params: { path: { pk: product.id } },
          body: { tag },
        }),
      ),
    onSuccess: (r) => {
      toast.push(r.message)
      invalidate.forEach((k) => void qc.invalidateQueries({ queryKey: k }))
    },
    onError: (e) => toast.push(errorText(e), 'danger'),
  })
  return (
    <div className="card">
      <div className="card-body p-4">
        <h2 className="h5">
          <i className="bi bi-tag me-1" />
          Проверить релиз
        </h2>
        <p className="text-muted small">
          Репозиторий: <code>{product.source_repo_full_name || 'не выбран'}</code>. Создайте релиз на GitHub и
          отправьте его на проверку на заимствования.
        </p>
        {error ? (
          <div className="alert alert-danger d-flex gap-2 mb-0">
            <i className="bi bi-exclamation-octagon-fill" />
            <div>{error}</div>
          </div>
        ) : releases.length ? (
          <ul className="list-group">
            {releases.map((r) => (
              <li key={r.tag_name} className="list-group-item d-flex align-items-center gap-2 flex-wrap">
                <span className="fw-semibold">{r.tag_name}</span>
                <span className="small text-muted">{formatDateTime(r.published_at)}</span>
                {r.imported ? (
                  <span className="ms-auto">
                    <StatusBadge status="approved" label="Получен" />
                  </span>
                ) : (
                  <button
                    className="btn btn-sm btn-accent ms-auto"
                    disabled={imp.isPending}
                    onClick={() => imp.mutate(r.tag_name)}
                  >
                    <i className="bi bi-shield-check me-1" />
                    Отправить на проверку
                  </button>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState icon="bi-tag" title="В репозитории пока нет релизов">
            Создайте релиз на GitHub и обновите страницу.
          </EmptyState>
        )}
      </div>
    </div>
  )
}

/** Подкатегория (сгруппирована по разделам), технологии, платформы, ссылка на демо. */
export function CategoryFields({
  value,
  onChange,
  errors,
}: {
  value: { category_id: number | null; technology_ids: number[]; platform_ids: number[]; demo_url: string }
  onChange: (
    v: Partial<{
      category_id: number | null
      technology_ids: number[]
      platform_ids: number[]
      demo_url: string
    }>,
  ) => void
  errors: Record<string, string>
}) {
  const refs = useQuery({
    queryKey: ['refs'],
    queryFn: () => unwrap(client.GET('/api/catalog/refs')),
    staleTime: 300_000,
  })
  const toggle = (list: number[], id: number) =>
    list.includes(id) ? list.filter((x) => x !== id) : [...list, id]
  return (
    <>
      <div className="mb-3">
        <label className="form-label fw-semibold" htmlFor="category">
          Подкатегория <span className="required-mark">*</span>
        </label>
        <select
          id="category"
          className={`form-select ${errors.category_id ? 'is-invalid' : ''}`}
          value={value.category_id ?? ''}
          onChange={(e) => onChange({ category_id: e.target.value ? Number(e.target.value) : null })}
        >
          <option value="">— выберите —</option>
          {refs.data?.sections.map((s) => (
            <optgroup key={s.id} label={s.name}>
              {s.children.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        {errors.category_id && (
          <div className="cm-field-error">
            <i className="bi bi-exclamation-circle" />
            {errors.category_id}
          </div>
        )}
      </div>
      {(['technology_ids', 'platform_ids'] as const).map((field) => (
        <div className="mb-3" key={field}>
          <div className="form-label fw-semibold">
            {field === 'technology_ids' ? 'Технологии' : 'Платформы'}
          </div>
          <div className="row row-cols-2 row-cols-md-3 g-1">
            {(field === 'technology_ids' ? refs.data?.technologies : refs.data?.platforms)?.map((t) => (
              <div className="col" key={t.id}>
                <div className="form-check">
                  <input
                    className="form-check-input"
                    type="checkbox"
                    id={`${field}-${t.id}`}
                    checked={value[field].includes(t.id)}
                    onChange={() => onChange({ [field]: toggle(value[field], t.id) })}
                  />
                  <label className="form-check-label" htmlFor={`${field}-${t.id}`}>
                    {t.name}
                  </label>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
      <div className="mb-3">
        <label className="form-label fw-semibold" htmlFor="demo_url">
          Ссылка на демо
        </label>
        <input
          id="demo_url"
          className={`form-control ${errors.demo_url ? 'is-invalid' : ''}`}
          value={value.demo_url}
          onChange={(e) => onChange({ demo_url: e.target.value })}
          placeholder="https://"
        />
        {errors.demo_url && (
          <div className="cm-field-error">
            <i className="bi bi-exclamation-circle" />
            {errors.demo_url}
          </div>
        )}
      </div>
    </>
  )
}

export type InfoValue = { title: string; short_description: string; description: string; price: string }

export function InfoFields({
  value,
  onChange,
  errors,
}: {
  value: InfoValue
  onChange: (v: Partial<InfoValue>) => void
  errors: Record<string, string>
}) {
  const err = (k: string) =>
    errors[k] ? (
      <div className="cm-field-error">
        <i className="bi bi-exclamation-circle" />
        {errors[k]}
      </div>
    ) : null
  return (
    <>
      <div className="mb-3">
        <label className="form-label fw-semibold" htmlFor="title">
          Название <span className="required-mark">*</span>
        </label>
        <input
          id="title"
          maxLength={120}
          className={`form-control ${errors.title ? 'is-invalid' : ''}`}
          value={value.title}
          onChange={(e) => onChange({ title: e.target.value })}
        />
        {err('title')}
      </div>
      <div className="mb-3">
        <label className="form-label fw-semibold" htmlFor="short">
          Краткое описание <span className="required-mark">*</span>
        </label>
        <textarea
          id="short"
          rows={2}
          maxLength={200}
          className={`form-control ${errors.short_description ? 'is-invalid' : ''}`}
          value={value.short_description}
          onChange={(e) => onChange({ short_description: e.target.value })}
        />
        {errors.short_description ? (
          err('short_description')
        ) : (
          <div className="form-text">До 200 символов.</div>
        )}
      </div>
      <div className="mb-3">
        <label className="form-label fw-semibold" htmlFor="description">
          Описание <span className="required-mark">*</span>
        </label>
        <textarea
          id="description"
          rows={8}
          className={`form-control ${errors.description ? 'is-invalid' : ''}`}
          value={value.description}
          onChange={(e) => onChange({ description: e.target.value })}
        />
        {errors.description ? (
          err('description')
        ) : (
          <div className="form-text">Что умеет продукт, как установить, что входит в комплект.</div>
        )}
      </div>
      <div className="mb-3">
        <label className="form-label fw-semibold" htmlFor="price">
          Цена, ₽ <span className="required-mark">*</span>
        </label>
        <input
          id="price"
          type="number"
          min={100}
          max={500000}
          step={1}
          className={`form-control ${errors.price ? 'is-invalid' : ''}`}
          value={value.price}
          onChange={(e) => onChange({ price: e.target.value })}
        />
        {errors.price ? err('price') : <div className="form-text">От 100 до 500 000 ₽</div>}
      </div>
    </>
  )
}
