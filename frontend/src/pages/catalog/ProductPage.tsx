import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { client, unwrap, type S } from '../../api/client'
import { Breadcrumbs, ErrorState, Loading, RichText, Stars, StatusBadge } from '../../components/ui'
import { useTitle } from '../../hooks/misc'
import { formatDate, formatDateTime, formatMoney, plural } from '../../lib/format'

function Review({ r }: { r: S['ReviewOut'] }) {
  return (
    <div className="mb-3 pb-3 border-bottom">
      <div className="d-flex justify-content-between">
        <span className="fw-semibold">{r.author}</span>
        <Stars value={r.rating} />
      </div>
      {r.text && <div className="mt-1">{r.text}</div>}
      <div className="small text-muted">{formatDate(r.created_at)}</div>
    </div>
  )
}

type Tab = 'desc' | 'versions' | 'reviews' | 'qa'

export default function ProductPage() {
  const { slug = '' } = useParams()
  const q = useQuery({
    queryKey: ['product', slug],
    queryFn: () => unwrap(client.GET('/api/catalog/products/{slug}', { params: { path: { slug } } })),
  })
  const [tab, setTab] = useState<Tab>('desc')
  const [shot, setShot] = useState(0)
  const [lightbox, setLightbox] = useState(false)
  useTitle(q.data?.title ?? 'Продукт')

  if (q.isLoading) return <Loading />
  if (q.isError || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const p = q.data
  const shots = p.screenshots
  const main = shots[Math.min(shot, shots.length - 1)]
  const reviewsTotal = p.product_reviews.length + p.order_reviews.length
  const askLink = `/orders/new/?product=${p.slug}&kind=question`

  const tabs: [Tab, string][] = [
    ['desc', 'Описание'],
    ['versions', 'Версии'],
    ['reviews', 'Отзывы'],
    ['qa', 'Вопросы'],
  ]

  return (
    <>
      <Breadcrumbs
        items={[
          { to: '/', label: 'Каталог' },
          { to: `/?section=${p.section.slug}`, label: p.section.name },
          ...(p.category.parent_id ? [{ to: `/?category=${p.category.slug}`, label: p.category.name }] : []),
          { label: p.title },
        ]}
      />
      {p.status !== 'published' && (
        <div className="alert alert-warning d-flex gap-2">
          <i className="bi bi-eye-slash-fill" />
          <div>
            Продукт не виден в каталоге. Статус: <StatusBadge status={p.status} label={p.status_label} />
          </div>
        </div>
      )}
      <div className="row g-4">
        <div className="col-lg-8">
          <h1 className="h2 mb-1">{p.title}</h1>
          <p className="text-muted mb-3">{p.short_description}</p>
          <div
            className="cm-gallery-main mb-2"
            role="button"
            aria-label="Открыть скриншот"
            onClick={() => main && setLightbox(true)}
          >
            {main ? (
              <img src={main.url} alt={`Скриншот: ${p.title}`} />
            ) : (
              <div className="h-100 d-flex align-items-center justify-content-center text-muted">
                <i className="bi bi-code-slash" style={{ fontSize: '4rem' }} />
              </div>
            )}
          </div>
          {shots.length > 1 && (
            <div className="d-flex gap-2 flex-wrap mb-4">
              {shots.map((s, i) => (
                <button
                  key={s.id}
                  type="button"
                  className={`cm-thumb ${i === shot ? 'active' : ''}`}
                  aria-label={`Скриншот ${i + 1}`}
                  onClick={() => setShot(i)}
                >
                  <img src={s.url} alt="" />
                </button>
              ))}
            </div>
          )}

          <ul className="nav nav-tabs mt-4" role="tablist">
            {tabs.map(([key, label]) => (
              <li className="nav-item" role="presentation" key={key}>
                <button
                  className={`nav-link ${tab === key ? 'active' : ''}`}
                  type="button"
                  role="tab"
                  aria-selected={tab === key}
                  onClick={() => setTab(key)}
                >
                  {label} {key === 'reviews' && <span className="text-muted">{reviewsTotal}</span>}
                </button>
              </li>
            ))}
          </ul>
          <div className="card border-top-0 rounded-top-0">
            <div className="card-body p-4">
              {tab === 'desc' && (
                <div className="cm-description">
                  <RichText text={p.description} />
                </div>
              )}
              {tab === 'versions' &&
                (p.versions.length ? (
                  <ul className="list-group list-group-flush">
                    {p.versions.map((v) => (
                      <li key={v.id} className="list-group-item px-0 d-flex justify-content-between">
                        <span className="fw-semibold">{v.tag_name}</span>
                        <span className="text-muted">{formatDateTime(v.approved_at)}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-muted mb-0">Одобренных версий пока нет.</p>
                ))}
              {tab === 'reviews' && (
                <>
                  <h2 className="h6">О продукте</h2>
                  {p.product_reviews.length ? (
                    p.product_reviews.map((r) => <Review key={r.id} r={r} />)
                  ) : (
                    <p className="text-muted">Отзывов о продукте пока нет.</p>
                  )}
                  <h2 className="h6 mt-4">О доработках</h2>
                  {p.order_reviews.length ? (
                    p.order_reviews.map((r) => <Review key={r.id} r={r} />)
                  ) : (
                    <p className="text-muted mb-0">Отзывов о доработках пока нет.</p>
                  )}
                </>
              )}
              {tab === 'qa' && (
                <>
                  {p.questions.length ? (
                    p.questions.map((qa, i) => (
                      <div key={i} className="mb-3 pb-3 border-bottom">
                        <div>
                          <i className="bi bi-question-circle me-1 text-muted" />
                          <span className="fw-semibold">Вопрос:</span> {qa.question}
                        </div>
                        {qa.answer && (
                          <div className="mt-1 ms-3">
                            <i className="bi bi-reply me-1 text-muted" />
                            <span className="fw-semibold">Ответ продавца:</span> {qa.answer}
                          </div>
                        )}
                        <div className="small text-muted ms-3">{formatDateTime(qa.created_at)}</div>
                      </div>
                    ))
                  ) : (
                    <p className="text-muted">Вопросов пока не задавали.</p>
                  )}
                  {!p.is_owner && (
                    <Link className="btn btn-outline-primary" to={askLink}>
                      <i className="bi bi-chat-dots me-1" />
                      Задать вопрос
                    </Link>
                  )}
                </>
              )}
            </div>
          </div>
        </div>

        <div className="col-lg-4">
          <div className="cm-sticky">
            <div className="card shadow-sm mb-3">
              <div className="card-body p-4">
                <div className="cm-price fs-2 mb-3">{formatMoney(p.price)}</div>
                {p.is_owner ? (
                  <>
                    <Link className="btn btn-primary w-100 mb-2" to={`/sell/products/${p.id}/edit/`}>
                      <i className="bi bi-pencil me-1" />
                      Редактировать
                    </Link>
                    <Link className="btn btn-outline-primary w-100" to={`/sell/products/${p.id}/versions/`}>
                      Версии
                    </Link>
                  </>
                ) : p.purchase_id ? (
                  <Link className="btn btn-sage w-100 mb-2" to={`/me/purchases/${p.purchase_id}/`}>
                    <i className="bi bi-box-arrow-in-right me-1" />
                    Перейти к покупке
                  </Link>
                ) : p.status === 'published' ? (
                  <>
                    <Link className="btn btn-accent w-100 mb-2" to={`/buy/${p.slug}/`}>
                      <i className="bi bi-bag me-1" />
                      Купить
                    </Link>
                    <Link
                      className="btn btn-cream w-100 mb-2"
                      to={`/orders/new/?product=${p.slug}&kind=with_purchase`}
                    >
                      <i className="bi bi-tools me-1" />
                      Купить с доработкой
                    </Link>
                    <Link className="btn btn-outline-primary w-100 mb-2" to={askLink}>
                      <i className="bi bi-chat-dots me-1" />
                      Задать вопрос
                    </Link>
                  </>
                ) : null}
                {p.demo_url && (
                  <a
                    className="btn btn-link w-100"
                    href={p.demo_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <i className="bi bi-box-arrow-up-right me-1" />
                    Открыть демо
                  </a>
                )}
                <div className="alert alert-success small mt-3 mb-0 d-flex gap-2">
                  <i className="bi bi-shield-check" />
                  <div>
                    <strong>Проверено на заимствования.</strong> Код сравнён с каталогом, совпадений выше
                    порога нет.
                  </div>
                </div>
              </div>
            </div>

            <div className="card mb-3">
              <div className="card-body">
                <div className="small text-muted">Продавец</div>
                <div className="fw-bold fs-5">{p.seller.username}</div>
                <div className="small">
                  {p.seller.rating ? (
                    <>
                      <Stars value={p.seller.rating} /> {Number(p.seller.rating).toFixed(1).replace('.', ',')}{' '}
                      · {p.seller.reviews} {plural(p.seller.reviews, ['отзыв', 'отзыва', 'отзывов'])}
                    </>
                  ) : (
                    <span className="text-muted">пока без отзывов</span>
                  )}
                </div>
                <div className="small text-muted">
                  {p.seller.sales} {plural(p.seller.sales, ['продажа', 'продажи', 'продаж'])}
                </div>
              </div>
            </div>

            <div className="card">
              <div className="card-body small">
                <dl className="row mb-0">
                  <dt className="col-5 text-muted fw-normal">Раздел</dt>
                  <dd className="col-7">
                    {p.section.name} / {p.category.name}
                  </dd>
                  <dt className="col-5 text-muted fw-normal">Технологии</dt>
                  <dd className="col-7">
                    {p.technologies.length
                      ? p.technologies.map((t) => (
                          <span key={t.id} className="cm-tag me-1 mb-1">
                            {t.name}
                          </span>
                        ))
                      : '—'}
                  </dd>
                  <dt className="col-5 text-muted fw-normal">Платформы</dt>
                  <dd className="col-7">
                    {p.platforms.length ? p.platforms.map((x) => x.name).join(', ') : '—'}
                  </dd>
                  <dt className="col-5 text-muted fw-normal">Версия</dt>
                  <dd className="col-7">
                    {p.current_version
                      ? `${p.current_version.tag_name} от ${formatDate(p.current_version.approved_at)}`
                      : '—'}
                  </dd>
                  <dt className="col-5 text-muted fw-normal">Рейтинг</dt>
                  <dd className="col-7 mb-0">
                    <Stars value={p.rating_avg} /> {p.rating_count}
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </div>
      </div>

      {lightbox && main && (
        <>
          <div
            className="modal fade show d-block"
            tabIndex={-1}
            aria-label="Просмотр скриншота"
            onClick={() => setLightbox(false)}
          >
            <div className="modal-dialog modal-xl modal-dialog-centered">
              <div className="modal-content bg-transparent border-0">
                <button
                  type="button"
                  className="btn-close btn-close-white ms-auto mb-2"
                  aria-label="Закрыть"
                  onClick={() => setLightbox(false)}
                />
                <img src={main.url} className="img-fluid rounded" alt="Скриншот" />
              </div>
            </div>
          </div>
          <div className="modal-backdrop fade show" />
        </>
      )}
    </>
  )
}
