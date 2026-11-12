import { Link } from 'react-router'

import type { S } from '../api/client'
import { formatMoney } from '../lib/format'
import { Stars } from './ui'

export function ProductCard({ p }: { p: S['ProductCard'] }) {
  const rating = Number(p.rating_avg)
  return (
    <Link className="cm-product-card" to={`/p/${p.slug}/`}>
      <div className="cm-cover">
        {p.cover ? (
          <img src={p.cover} alt={p.title} loading="lazy" />
        ) : (
          <div className="h-100 d-flex align-items-center justify-content-center text-muted">
            <i className="bi bi-code-slash fs-1" />
          </div>
        )}
        <span className="cm-section-badge">{p.section_name}</span>
      </div>
      <div className="p-3 d-flex flex-column flex-grow-1">
        <h3 className="h6 fw-bold cm-clamp-2 mb-1">{p.title}</h3>
        <p className="small text-muted cm-clamp-2 mb-2">{p.short_description}</p>
        <div className="d-flex flex-wrap gap-1 mb-3">
          {p.technologies.map((t) => (
            <span key={t} className="cm-tag">
              {t}
            </span>
          ))}
        </div>
        <div className="mt-auto d-flex align-items-end justify-content-between">
          <div>
            <div className="cm-price fs-5">{formatMoney(p.price)}</div>
            <div className="small text-muted">
              <Stars value={rating} />{' '}
              {p.rating_count ? `${rating.toFixed(1).replace('.', ',')} · ${p.rating_count}` : 'нет отзывов'}
            </div>
          </div>
          <span className="cm-verified" title="Код проверен на заимствования">
            <i className="bi bi-shield-check" /> Проверено
          </span>
        </div>
      </div>
    </Link>
  )
}

/** Скелетон карточки, пока каталог загружается. */
export function ProductCardSkeleton() {
  return (
    <div className="cm-product-card placeholder-glow" aria-hidden="true">
      <div className="cm-cover placeholder w-100" />
      <div className="p-3">
        <span className="placeholder col-9 mb-2" />
        <span className="placeholder col-12 placeholder-sm" />
        <span className="placeholder col-7 placeholder-sm mb-3" />
        <span className="placeholder col-4 placeholder-lg" />
      </div>
    </div>
  )
}
