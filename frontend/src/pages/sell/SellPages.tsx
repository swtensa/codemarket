import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router'

import { ApiError, client, unwrap, upload, type S } from '../../api/client'
import {
  Breadcrumbs,
  ConfirmButton,
  EmptyState,
  ErrorState,
  FormError,
  Loading,
  Pagination,
  SimilarityBar,
  StatusBadge,
} from '../../components/ui'
import { useTitle } from '../../hooks/misc'
import { useAuth } from '../../hooks/useAuth'
import { useToast } from '../../hooks/useToast'
import { errorText } from '../../lib/forms'
import { formatDateTime, formatMoney } from '../../lib/format'
import { CategoryFields, InfoFields, ProductTabs, Releases, SellNav, type InfoValue } from './common'

// ---------------------------------------------------------------- кабинет

export function SellDashboardPage() {
  useTitle('Продажи')
  const { state } = useLocation()
  const toast = useToast()
  const qc = useQueryClient()
  const q = useQuery({
    queryKey: ['seller-dashboard'],
    queryFn: () => unwrap(client.GET('/api/seller/dashboard')),
  })
  const [openMenu, setOpenMenu] = useState<number | null>(null)
  useEffect(() => {
    if ((state as { needGithub?: boolean } | null)?.needGithub)
      toast.push('Чтобы продавать, подключите GitHub.', 'info')
  }, [state, toast])
  const act = async (id: number, action: 'hide' | 'unhide' | 'delete') => {
    setOpenMenu(null)
    try {
      const path = { params: { path: { pk: id } } }
      const r = await unwrap(
        action === 'delete'
          ? client.DELETE('/api/seller/products/{pk}', path)
          : action === 'hide'
            ? client.POST('/api/seller/products/{pk}/hide', path)
            : client.POST('/api/seller/products/{pk}/unhide', path),
      )
      toast.push(r.message)
      void qc.invalidateQueries({ queryKey: ['seller-dashboard'] })
    } catch (e) {
      toast.push(errorText(e), 'danger')
    }
  }
  return (
    <>
      <SellNav />
      {q.isLoading ? (
        <Loading />
      ) : q.isError || !q.data ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !q.data.is_seller ? (
        <div className="card cm-hero border-0">
          <div className="row g-4 align-items-center">
            <div className="col-lg-8">
              <h2 className="h3">
                <i className="bi bi-github me-2" />
                Подключите GitHub, чтобы продавать
              </h2>
              <p className="mb-2">CodeMarket получает код ваших продуктов прямо из репозитория на GitHub:</p>
              <ul>
                <li>вы выбираете репозиторий и создаёте в нём релиз;</li>
                <li>платформа проверяет код на заимствования и передаёт модератору;</li>
                <li>
                  покупатели получают доступ только к закрытой копии с одобренными версиями, ваш рабочий
                  репозиторий они не видят;
                </li>
                <li>
                  пароли и токены не нужны: вы устанавливаете приложение CodeMarket только на нужные
                  репозитории.
                </li>
              </ul>
              <Link className="btn btn-primary btn-lg" to="/sell/github/">
                <i className="bi bi-github me-2" />
                Подключить GitHub
              </Link>
            </div>
            <div className="col-lg-4 text-center d-none d-lg-block">
              <i className="bi bi-git" style={{ fontSize: '7rem', color: 'var(--c-accent)' }} />
            </div>
          </div>
        </div>
      ) : (
        <>
          {q.data.tiles && (
            <div className="row g-3 mb-4">
              <div className="col-6 col-lg-3">
                <div className="cm-stat">
                  <div className="label">Выручка за месяц</div>
                  <div className="value">{formatMoney(q.data.tiles.revenue_month)}</div>
                </div>
              </div>
              <div className="col-6 col-lg-3">
                <div className="cm-stat">
                  <div className="label">Продажи</div>
                  <div className="value">{q.data.tiles.sales}</div>
                </div>
              </div>
              <div className="col-6 col-lg-3">
                <div className="cm-stat">
                  <div className="label">Просмотры</div>
                  <div className="value">{q.data.tiles.views}</div>
                </div>
              </div>
              <div className="col-6 col-lg-3">
                <div className="cm-stat">
                  <div className="label">Рейтинг</div>
                  <div className="value">
                    {q.data.tiles.rating ? (
                      <>
                        {Number(q.data.tiles.rating).toFixed(1).replace('.', ',')}{' '}
                        <i className="bi bi-star-fill fs-6" style={{ color: 'var(--c-warning)' }} />
                      </>
                    ) : (
                      '—'
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
          {q.data.products.length ? (
            <div className="card">
              <div className="table-responsive" style={{ overflow: 'visible' }}>
                <table className="table table-hover align-middle mb-0">
                  <thead>
                    <tr>
                      <th style={{ width: 96 }} />
                      <th>Название</th>
                      <th>Статус</th>
                      <th className="text-end">Цена</th>
                      <th className="text-end">Продажи</th>
                      <th className="text-end">Действия</th>
                    </tr>
                  </thead>
                  <tbody>
                    {q.data.products.map((p) => (
                      <tr key={p.id}>
                        <td>
                          {p.cover ? (
                            <img
                              src={p.cover}
                              alt=""
                              className="rounded"
                              style={{ width: 80, aspectRatio: '16/10', objectFit: 'cover' }}
                            />
                          ) : (
                            <div
                              className="rounded bg-light d-flex align-items-center justify-content-center text-muted"
                              style={{ width: 80, aspectRatio: '16/10' }}
                            >
                              <i className="bi bi-image" />
                            </div>
                          )}
                        </td>
                        <td>
                          <Link className="fw-semibold" to={`/p/${p.slug}/`}>
                            {p.title}
                          </Link>
                          <div className="small text-muted">
                            {p.section} / {p.category}
                          </div>
                        </td>
                        <td>
                          <StatusBadge status={p.status} label={p.status_label} />
                          {p.pending_version && (
                            <div className="small text-muted mt-1">
                              новая версия {p.pending_version} на проверке
                            </div>
                          )}
                        </td>
                        <td className="text-end text-nowrap">{formatMoney(p.price)}</td>
                        <td className="text-end">{p.sales_count}</td>
                        <td className="text-end text-nowrap">
                          <div className="dropdown">
                            <button
                              className="btn btn-sm btn-outline-primary dropdown-toggle"
                              aria-expanded={openMenu === p.id}
                              onClick={() => setOpenMenu(openMenu === p.id ? null : p.id)}
                            >
                              Действия
                            </button>
                            <ul
                              className={`dropdown-menu dropdown-menu-end ${openMenu === p.id ? 'show' : ''}`}
                              style={{ right: 0 }}
                            >
                              <li>
                                <Link className="dropdown-item" to={`/sell/products/${p.id}/edit/`}>
                                  <i className="bi bi-pencil me-2" />
                                  Редактировать
                                </Link>
                              </li>
                              <li>
                                <Link className="dropdown-item" to={`/sell/products/${p.id}/media/`}>
                                  <i className="bi bi-images me-2" />
                                  Скриншоты
                                </Link>
                              </li>
                              <li>
                                <Link className="dropdown-item" to={`/sell/products/${p.id}/versions/`}>
                                  <i className="bi bi-tags me-2" />
                                  Версии
                                </Link>
                              </li>
                              {p.status === 'published' && (
                                <li>
                                  <ConfirmButton
                                    className="dropdown-item"
                                    text={`Снять «${p.title}» с продажи? У покупателей доступ и обновления сохранятся.`}
                                    onConfirm={() => act(p.id, 'hide')}
                                  >
                                    <i className="bi bi-eye-slash me-2" />
                                    Снять с продажи
                                  </ConfirmButton>
                                </li>
                              )}
                              {p.status === 'hidden' && (
                                <li>
                                  <button className="dropdown-item" onClick={() => act(p.id, 'unhide')}>
                                    <i className="bi bi-eye me-2" />
                                    Вернуть в продажу
                                  </button>
                                </li>
                              )}
                              {!p.sales_count && (
                                <>
                                  <li>
                                    <hr className="dropdown-divider" />
                                  </li>
                                  <li>
                                    <ConfirmButton
                                      className="dropdown-item text-danger"
                                      text={`Удалить «${p.title}» без возможности восстановления?`}
                                      onConfirm={() => act(p.id, 'delete')}
                                    >
                                      <i className="bi bi-trash me-2" />
                                      Удалить
                                    </ConfirmButton>
                                  </li>
                                </>
                              )}
                            </ul>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="card">
              <EmptyState icon="bi-box-seam" title="У вас пока нет продуктов">
                <Link className="btn btn-accent mt-2" to="/sell/products/new/">
                  Создать первый продукт
                </Link>
              </EmptyState>
            </div>
          )}
        </>
      )}
    </>
  )
}

// ---------------------------------------------------------------- GitHub

export function GithubConnectPage() {
  useTitle('Подключение GitHub')
  const { user, reloadUser } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['github-info'], queryFn: () => unwrap(client.GET('/api/seller/github')) })
  const connect = async () => {
    try {
      const r = await unwrap(client.POST('/api/seller/github/connect'))
      toast.push(r.message)
      await reloadUser()
      void qc.invalidateQueries({ queryKey: ['seller-dashboard'] })
      navigate('/sell/')
    } catch (e) {
      toast.push(errorText(e), 'danger')
    }
  }
  return (
    <>
      <Breadcrumbs items={[{ to: '/sell/', label: 'Продажи' }, { label: 'Подключение GitHub' }]} />
      <div className="row justify-content-center">
        <div className="col-lg-8">
          <div className="card">
            <div className="card-body p-4">
              <h1 className="h3">
                <i className="bi bi-github me-2" />
                Подключение GitHub
              </h1>
              {user?.is_seller && (
                <div className="alert alert-success d-flex gap-2">
                  <i className="bi bi-check-circle-fill" />
                  <div>GitHub уже подключён.</div>
                </div>
              )}
              <ol className="mb-4">
                <li>
                  Нажмите кнопку ниже и установите приложение CodeMarket на репозитории с продуктами (личные
                  или организации).
                </li>
                <li>При создании продукта выберите репозиторий из списка.</li>
                <li>Создайте релиз в репозитории и нажмите «Проверить релиз» на странице версий.</li>
              </ol>
              {q.data?.mode === 'fake' ? (
                <>
                  <div className="alert alert-info d-flex gap-2">
                    <i className="bi bi-info-circle-fill" />
                    <div>
                      Включён демо-режим GitHub (<code>GITHUB_MODE=fake</code>): репозитории берутся из папки{' '}
                      <code>backend/fixtures/demo/repos</code>, интернет не нужен.
                    </div>
                  </div>
                  <button className="btn btn-primary btn-lg" onClick={connect}>
                    <i className="bi bi-github me-2" />
                    Подключить GitHub (демо)
                  </button>
                </>
              ) : q.data?.install_url ? (
                <a className="btn btn-primary btn-lg" href={q.data.install_url}>
                  <i className="bi bi-github me-2" />
                  Установить приложение на GitHub
                </a>
              ) : (
                <Loading />
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

/** GitHub возвращает пользователя после установки приложения: ?installation_id=...&state=... */
export function GithubCallbackPage() {
  useTitle('Подключение GitHub')
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const { reloadUser } = useAuth()
  const done = useRef(false)
  useEffect(() => {
    if (done.current) return
    done.current = true
    unwrap(
      client.POST('/api/seller/github/callback', {
        body: { installation_id: params.get('installation_id') ?? '', state: params.get('state') ?? '' },
      }),
    )
      .then(async (r) => {
        toast.push(r.message)
        await reloadUser()
        navigate('/sell/', { replace: true })
      })
      .catch((e) => {
        toast.push(errorText(e), 'danger')
        navigate('/sell/github/', { replace: true })
      })
  }, [params, navigate, toast, reloadUser])
  return <Loading text="Подключаем GitHub…" />
}

// ---------------------------------------------------------------- мастер продукта

const STEP_FIELDS: Record<number, string[]> = {
  1: ['repo_full_name', 'accept_seller_terms'],
  2: ['title', 'short_description', 'description', 'price'],
  3: ['category_id', 'technology_ids', 'platform_ids', 'demo_url'],
}

export function ProductWizardPage() {
  useTitle('Новый продукт')
  const navigate = useNavigate()
  const toast = useToast()
  const qc = useQueryClient()
  const repos = useQuery({
    queryKey: ['seller-repos'],
    queryFn: () => unwrap(client.GET('/api/seller/repos')),
  })
  const [step, setStep] = useState(1)
  const [repo, setRepo] = useState('')
  const [terms, setTerms] = useState(false)
  const [info, setInfo] = useState<InfoValue>({
    title: '',
    short_description: '',
    description: '',
    price: '',
  })
  const [cat, setCat] = useState({
    category_id: null as number | null,
    technology_ids: [] as number[],
    platform_ids: [] as number[],
    demo_url: '',
  })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const next = (e: FormEvent) => {
    e.preventDefault()
    const errs: Record<string, string> = {}
    if (step === 1) {
      if (!repo) errs.repo_full_name = 'Выберите репозиторий из списка.'
      if (repos.data?.need_terms && !terms) errs.accept_seller_terms = 'Без согласия создать продукт нельзя.'
    } else if (step === 2) {
      if (!info.title.trim()) errs.title = 'Обязательное поле.'
      if (!info.short_description.trim()) errs.short_description = 'Обязательное поле.'
      if (!info.description.trim()) errs.description = 'Обязательное поле.'
      const price = Number(info.price)
      if (!info.price || !Number.isFinite(price) || price < 100 || price > 500000)
        errs.price = 'Цена — от 100 до 500 000 ₽.'
    }
    setErrors(errs)
    if (Object.keys(errs).length) return
    if (step < 3) setStep(step + 1)
    else void create()
  }

  const create = async () => {
    setBusy(true)
    setError('')
    try {
      const p = await unwrap(
        client.POST('/api/seller/products', {
          body: { repo_full_name: repo, accept_seller_terms: terms, ...info, price: info.price, ...cat },
        }),
      )
      toast.push('Черновик продукта создан. Добавьте скриншоты и отправьте релиз на проверку.')
      void qc.invalidateQueries({ queryKey: ['seller-dashboard'] })
      void qc.invalidateQueries({ queryKey: ['me'] })
      navigate(`/sell/products/${p.id}/media/`)
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fields).length) {
        setErrors(err.fields)
        const first = Object.keys(err.fields)[0]
        const back = Number(Object.entries(STEP_FIELDS).find(([, f]) => f.includes(first))?.[0] ?? 3)
        setStep(back)
      } else setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  const stepClass = (n: number) => (step > n ? 'done' : step === n ? 'current' : '')
  return (
    <>
      <Breadcrumbs items={[{ to: '/sell/', label: 'Продажи' }, { label: 'Новый продукт' }]} />
      <div className="row justify-content-center">
        <div className="col-lg-9">
          <h1 className="h3 mb-3">Новый продукт</h1>
          <div className="cm-steps mb-4 fs-6">
            <span className={stepClass(1)}>1. Репозиторий</span>
            <span className={stepClass(2)}>2. Описание и цена</span>
            <span className={stepClass(3)}>3. Категории и демо</span>
            <span>4. Скриншоты и релиз</span>
          </div>
          <div className="card">
            <div className="card-body p-4">
              <form onSubmit={next} noValidate>
                <FormError error={error} />
                {step === 1 &&
                  (repos.isLoading ? (
                    <Loading />
                  ) : (
                    <>
                      {(repos.data?.error || !repos.data?.repos.length) && (
                        <div className="alert alert-warning d-flex gap-2">
                          <i className="bi bi-exclamation-triangle-fill" />
                          <div>
                            {repos.data?.error ||
                              'Приложению CodeMarket пока не доступен ни один репозиторий.'}{' '}
                            <Link to="/sell/github/">Настройте доступ</Link>.
                          </div>
                        </div>
                      )}
                      <div className="mb-3">
                        <label className="form-label fw-semibold" htmlFor="repo">
                          Репозиторий <span className="required-mark">*</span>
                        </label>
                        <select
                          id="repo"
                          className={`form-select ${errors.repo_full_name ? 'is-invalid' : ''}`}
                          value={repo}
                          onChange={(e) => setRepo(e.target.value)}
                        >
                          <option value="">— выберите —</option>
                          {repos.data?.repos.map((r) => (
                            <option key={r.full_name} value={r.full_name}>
                              {r.full_name}
                            </option>
                          ))}
                        </select>
                        {errors.repo_full_name ? (
                          <div className="cm-field-error">
                            <i className="bi bi-exclamation-circle" />
                            {errors.repo_full_name}
                          </div>
                        ) : (
                          <div className="form-text">
                            Репозитории, к которым установлено приложение CodeMarket.
                          </div>
                        )}
                      </div>
                      {repos.data?.need_terms && (
                        <>
                          <div className="form-check mb-1">
                            <input
                              className="form-check-input"
                              type="checkbox"
                              id="terms"
                              checked={terms}
                              onChange={(e) => setTerms(e.target.checked)}
                            />
                            <label className="form-check-label" htmlFor="terms">
                              Принимаю{' '}
                              <Link to="/legal/seller/" target="_blank">
                                условия для продавцов
                              </Link>{' '}
                              <span className="required-mark">*</span>
                            </label>
                          </div>
                          {errors.accept_seller_terms && (
                            <div className="cm-field-error">
                              <i className="bi bi-exclamation-circle" />
                              {errors.accept_seller_terms}
                            </div>
                          )}
                          <p className="small text-muted mt-2">
                            Также действуют{' '}
                            <Link to="/legal/terms/" target="_blank">
                              пользовательское соглашение
                            </Link>
                            ,{' '}
                            <Link to="/legal/license/" target="_blank">
                              стандартная лицензия
                            </Link>{' '}
                            и{' '}
                            <Link to="/legal/privacy/" target="_blank">
                              политика персональных данных
                            </Link>
                            .
                          </p>
                        </>
                      )}
                    </>
                  ))}
                {step === 2 && (
                  <InfoFields value={info} onChange={(v) => setInfo({ ...info, ...v })} errors={errors} />
                )}
                {step === 3 && (
                  <CategoryFields value={cat} onChange={(v) => setCat({ ...cat, ...v })} errors={errors} />
                )}
                <div className="d-flex justify-content-between mt-4">
                  {step > 1 ? (
                    <button
                      type="button"
                      className="btn btn-outline-primary"
                      onClick={() => setStep(step - 1)}
                    >
                      <i className="bi bi-arrow-left me-1" />
                      Назад
                    </button>
                  ) : (
                    <span />
                  )}
                  <button className="btn btn-primary" type="submit" disabled={busy}>
                    {step === 3 ? 'Создать черновик' : 'Далее'} <i className="bi bi-arrow-right ms-1" />
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

// ---------------------------------------------------------------- продукт: описание, скриншоты, версии

function useProductId() {
  const { id = '' } = useParams()
  return Number(id)
}

export function ProductEditPage() {
  const pk = useProductId()
  const qc = useQueryClient()
  const toast = useToast()
  const q = useQuery({
    queryKey: ['seller-product', pk],
    queryFn: () => unwrap(client.GET('/api/seller/products/{pk}', { params: { path: { pk } } })),
  })
  const [info, setInfo] = useState<InfoValue | null>(null)
  const [cat, setCat] = useState<{
    category_id: number | null
    technology_ids: number[]
    platform_ids: number[]
    demo_url: string
  } | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})
  useTitle(q.data ? `Редактирование: ${q.data.title}` : 'Редактирование')
  if (q.isLoading) return <Loading />
  if (q.isError || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const p = q.data
  const infoV = info ?? {
    title: p.title,
    short_description: p.short_description,
    description: p.description,
    price: String(Math.round(Number(p.price))),
  }
  const catV = cat ?? {
    category_id: p.category_id,
    technology_ids: p.technology_ids,
    platform_ids: p.platform_ids,
    demo_url: p.demo_url,
  }
  const save = async (e: FormEvent) => {
    e.preventDefault()
    setErrors({})
    try {
      await unwrap(
        client.PUT('/api/seller/products/{pk}', { params: { path: { pk } }, body: { ...infoV, ...catV } }),
      )
      toast.push('Изменения сохранены.')
      setInfo(null)
      setCat(null)
      void qc.invalidateQueries({ queryKey: ['seller-product', pk] })
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fields).length) setErrors(err.fields)
      else toast.push(errorText(err), 'danger')
    }
  }
  return (
    <>
      <ProductTabs product={p} />
      <div className="card">
        <div className="card-body p-4">
          <form onSubmit={save} noValidate>
            <div className="row g-3">
              <div className="col-lg-7">
                <InfoFields value={infoV} onChange={(v) => setInfo({ ...infoV, ...v })} errors={errors} />
              </div>
              <div className="col-lg-5">
                <CategoryFields value={catV} onChange={(v) => setCat({ ...catV, ...v })} errors={errors} />
                <div className="mb-3">
                  <label className="form-label fw-semibold">Репозиторий</label>
                  <input className="form-control" value={p.source_repo_full_name} disabled />
                </div>
              </div>
            </div>
            <button className="btn btn-primary" type="submit">
              Сохранить
            </button>
          </form>
        </div>
      </div>
    </>
  )
}

export function ProductMediaPage() {
  const pk = useProductId()
  const qc = useQueryClient()
  const toast = useToast()
  const fileRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const key = ['seller-media', pk]
  const q = useQuery({
    queryKey: key,
    queryFn: () => unwrap(client.GET('/api/seller/products/{pk}/media', { params: { path: { pk } } })),
  })
  useTitle('Скриншоты и релиз')
  const remove = useMutation({
    mutationFn: (sid: number) =>
      unwrap(client.DELETE('/api/seller/products/{pk}/screenshots/{sid}', { params: { path: { pk, sid } } })),
    onSuccess: (r) => {
      toast.push(r.message)
      void qc.invalidateQueries({ queryKey: key })
    },
    onError: (e) => toast.push(errorText(e), 'danger'),
  })
  if (q.isLoading) return <Loading />
  if (q.isError || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  const send = async (e: FormEvent) => {
    e.preventDefault()
    const files = fileRef.current?.files
    if (!files?.length) {
      toast.push('Выберите файлы.', 'danger')
      return
    }
    const form = new FormData()
    Array.from(files).forEach((f) => form.append('images', f))
    setBusy(true)
    try {
      await upload<S['MediaOut']>(`/api/seller/products/${pk}/screenshots`, form)
      toast.push('Скриншоты загружены.')
      if (fileRef.current) fileRef.current.value = ''
      void qc.invalidateQueries({ queryKey: key })
    } catch (err) {
      toast.push(errorText(err), 'danger')
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <ProductTabs product={d.product} />
      <div className="row g-4">
        <div className="col-lg-7">
          <div className="card">
            <div className="card-body p-4">
              <h2 className="h5">
                <i className="bi bi-images me-1" />
                Скриншоты{' '}
                <span className="text-muted fs-6">
                  {d.screenshots.length} из {d.max_screens}
                </span>
              </h2>
              {d.screenshots.length ? (
                <div className="row row-cols-2 row-cols-md-3 g-2 mb-3">
                  {d.screenshots.map((s, i) => (
                    <div className="col" key={s.id}>
                      <div className="position-relative">
                        <img
                          src={s.url}
                          className="img-fluid rounded border"
                          alt={`Скриншот ${i + 1}`}
                          style={{ aspectRatio: '16/10', objectFit: 'cover', width: '100%' }}
                        />
                        <div className="position-absolute top-0 end-0 m-1">
                          <ConfirmButton
                            className="btn btn-sm btn-danger"
                            text="Удалить скриншот?"
                            onConfirm={() => remove.mutate(s.id)}
                          >
                            <i className="bi bi-trash" aria-label="Удалить" />
                          </ConfirmButton>
                        </div>
                        {i === 0 && (
                          <span className="badge text-bg-dark position-absolute bottom-0 start-0 m-1">
                            Обложка
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-muted">Скриншотов пока нет. Первый станет обложкой в каталоге.</p>
              )}
              {d.screenshots.length < d.max_screens && (
                <form onSubmit={send}>
                  <label className="form-label fw-semibold" htmlFor="images">
                    Добавить скриншоты
                  </label>
                  <input
                    className="form-control"
                    type="file"
                    id="images"
                    multiple
                    accept=".jpg,.jpeg,.png,.webp"
                    ref={fileRef}
                  />
                  <div className="form-text">jpg, png или webp, до 3 МБ каждый.</div>
                  <button className="btn btn-primary mt-2" type="submit" disabled={busy}>
                    <i className="bi bi-upload me-1" />
                    Загрузить
                  </button>
                </form>
              )}
            </div>
          </div>
        </div>
        <div className="col-lg-5">
          <Releases
            product={d.product}
            releases={d.releases}
            error={d.release_error}
            invalidate={[key, ['seller-versions', pk]]}
          />
        </div>
      </div>
    </>
  )
}

function AppealForm({ versionId, onDone }: { versionId: number; onDone: () => void }) {
  const toast = useToast()
  const [text, setText] = useState('')
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    try {
      const r = await unwrap(
        client.POST('/api/seller/versions/{vid}/appeal', {
          params: { path: { vid: versionId } },
          body: { appeal_text: text },
        }),
      )
      toast.push(r.message)
      onDone()
    } catch (err) {
      toast.push(errorText(err), 'danger')
    }
  }
  return (
    <form onSubmit={submit}>
      <label className="form-label small fw-semibold" htmlFor={`appeal-${versionId}`}>
        Обжаловать автоматический отказ <span className="required-mark">*</span>
      </label>
      <textarea
        className="form-control form-control-sm mb-2"
        id={`appeal-${versionId}`}
        rows={2}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Например: совпадает только стандартная разметка формы, весь код написан мной"
      />
      <button className="btn btn-sm btn-primary" type="submit">
        Обжаловать
      </button>
    </form>
  )
}

export function VersionsPage() {
  const pk = useProductId()
  const qc = useQueryClient()
  const key = ['seller-versions', pk]
  const q = useQuery({
    queryKey: key,
    queryFn: () => unwrap(client.GET('/api/seller/products/{pk}/versions', { params: { path: { pk } } })),
    refetchInterval: (query) =>
      query.state.data?.versions.some((v) => v.status === 'checking') ? 15_000 : false,
  })
  useTitle(q.data ? `Версии: ${q.data.product.title}` : 'Версии')
  if (q.isLoading) return <Loading />
  if (q.isError || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  const refresh = () => void qc.invalidateQueries({ queryKey: key })
  return (
    <>
      <ProductTabs product={d.product} />
      <div className="row g-4">
        <div className="col-lg-8">
          <div className="card">
            {d.versions.length ? (
              <div className="table-responsive">
                <table className="table align-middle mb-0">
                  <thead>
                    <tr>
                      <th>Тег</th>
                      <th>Статус</th>
                      <th style={{ minWidth: 150 }}>Сходство</th>
                      <th>Получена</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.versions.map((v) => (
                      <VersionRows key={v.id} v={v} onChange={refresh} />
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState icon="bi-tags" title="Версий пока нет">
                Отправьте релиз на проверку.
              </EmptyState>
            )}
          </div>
          <p className="small text-muted mt-2">
            Сходство: <span style={{ color: 'var(--c-sage-text)' }}>до 30 % — норма</span>, 30–70 % —
            модератор проверит внимательнее, от 70 % — автоматический отказ с возможностью обжалования.
          </p>
        </div>
        <div className="col-lg-4">
          <Releases product={d.product} releases={d.releases} error={d.release_error} invalidate={[key]} />
        </div>
      </div>
    </>
  )
}

function VersionRows({ v, onChange }: { v: S['VersionOut']; onChange: () => void }) {
  return (
    <>
      <tr>
        <td className="fw-semibold">
          {v.tag_name}
          <div className="small text-muted">{v.files_count} файлов</div>
        </td>
        <td>
          <StatusBadge status={v.status} label={v.status_label} />
          {v.flagged && (
            <div className="small mt-1" style={{ color: 'var(--c-warning-text)' }}>
              <i className="bi bi-flag-fill" /> отмечена для модератора
            </div>
          )}
        </td>
        <td>
          {v.similarity !== null ? (
            <SimilarityBar value={v.similarity} />
          ) : v.status === 'checking' ? (
            <span className="small text-muted">
              <span className="spinner-border spinner-border-sm me-1" />
              Проверяется
            </span>
          ) : (
            '—'
          )}
        </td>
        <td className="small text-nowrap">{formatDateTime(v.created_at)}</td>
      </tr>
      {(v.admin_comment || v.check_error) && (
        <tr>
          <td colSpan={4} className="small bg-light">
            <i className="bi bi-chat-left-text me-1" />
            {v.admin_comment
              ? `Комментарий модератора: ${v.admin_comment}`
              : `Ошибка проверки: ${v.check_error}`}
          </td>
        </tr>
      )}
      {v.status === 'rejected_auto' && (
        <tr>
          <td colSpan={4} className="bg-light">
            {v.matches.length > 0 && (
              <>
                <div className="small fw-semibold mb-1">Совпадения с продуктами каталога:</div>
                <ul className="small mb-2">
                  {v.matches.map((m) => (
                    <li key={m.matched_version_id}>
                      «{m.product_title}» ({m.matched_tag}) — {Math.round(m.similarity * 100)}&nbsp;%
                      {m.files.length ? `: ${m.files.join(', ')}` : ''}
                    </li>
                  ))}
                </ul>
              </>
            )}
            <AppealForm versionId={v.id} onDone={onChange} />
          </td>
        </tr>
      )}
      {v.status === 'appeal' && (
        <tr>
          <td colSpan={4} className="small bg-light">
            <i className="bi bi-hourglass-split me-1" />
            Обжалование у модератора: «{v.appeal_text}»
          </td>
        </tr>
      )}
    </>
  )
}

// ---------------------------------------------------------------- заказы продавца

export function SellerOrdersPage() {
  useTitle('Заказы и вопросы')
  const [params] = useSearchParams()
  const kind = params.get('kind') ?? ''
  const page = Number(params.get('page') ?? '1') || 1
  const q = useQuery({
    queryKey: ['seller-orders', kind, page],
    queryFn: () => unwrap(client.GET('/api/seller/orders', { params: { query: { kind, page } } })),
  })
  const pill = (k: string, label: string) => (
    <li className="nav-item">
      <Link className={`nav-link ${kind === k ? 'active' : ''}`} to={k ? `?kind=${k}` : '?'}>
        {label}
      </Link>
    </li>
  )
  return (
    <>
      <SellNav />
      <ul className="nav nav-pills mb-3">
        {pill('', 'Все')}
        {pill('orders', 'Заказы')}
        {pill('question', 'Вопросы')}
      </ul>
      {q.isLoading ? (
        <Loading />
      ) : q.isError || !q.data ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data.items.length ? (
        <>
          <div className="card">
            <div className="table-responsive">
              <table className="table table-hover align-middle mb-0">
                <thead>
                  <tr>
                    <th>Заказ</th>
                    <th>Покупатель</th>
                    <th>Тип</th>
                    <th>Статус</th>
                    <th className="text-end">Цена</th>
                    <th>Крайний срок</th>
                  </tr>
                </thead>
                <tbody>
                  {q.data.items.map((o) => (
                    <tr key={o.id}>
                      <td>
                        <Link className="fw-semibold" to={`/orders/${o.id}/`}>
                          №{o.id} · {o.product.title}
                        </Link>
                        {o.unread > 0 && (
                          <span className="badge rounded-pill text-bg-danger ms-2">{o.unread}</span>
                        )}
                        <div className="small text-muted text-truncate" style={{ maxWidth: 320 }}>
                          {o.task}
                        </div>
                      </td>
                      <td className="small">{o.buyer}</td>
                      <td className="small">{o.kind_label}</td>
                      <td>
                        <StatusBadge status={o.status} label={o.status_label} />
                      </td>
                      <td className="text-end text-nowrap">{o.price ? formatMoney(o.price) : '—'}</td>
                      <td className="small text-nowrap">{formatDateTime(o.deadline)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <Pagination page={q.data.page} pages={q.data.pages} />
        </>
      ) : (
        <div className="card">
          <EmptyState icon="bi-inbox" title="Заказов и вопросов пока нет" />
        </div>
      )}
    </>
  )
}
