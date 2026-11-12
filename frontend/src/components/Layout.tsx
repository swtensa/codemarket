import { useState, type FormEvent } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate, useSearchParams } from 'react-router'

import { useUnreadCount } from '../hooks/misc'
import { useAuth } from '../hooks/useAuth'
import { useToast } from '../hooks/useToast'

function SearchForm({ className, mobile }: { className?: string; mobile?: boolean }) {
  const [params] = useSearchParams()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const [q, setQ] = useState(pathname === '/' ? (params.get('q') ?? '') : '')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    navigate(q.trim() ? `/?q=${encodeURIComponent(q.trim())}` : '/')
  }
  return (
    <form className={className} role="search" onSubmit={submit}>
      {mobile ? (
        <input
          className="form-control"
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Поиск"
          aria-label="Поиск"
        />
      ) : (
        <div className="input-group">
          <span className="input-group-text bg-transparent border-0 text-white">
            <i className="bi bi-search" />
          </span>
          <input
            className="form-control"
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Поиск шаблонов, ботов, скриптов"
            aria-label="Поиск"
          />
        </div>
      )}
    </form>
  )
}

export function Header() {
  const { user, logout } = useAuth()
  const unread = useUnreadCount()
  const { pathname, search } = useLocation()
  const navigate = useNavigate()
  const toast = useToast()
  const [menu, setMenu] = useState(false)
  const [userMenu, setUserMenu] = useState(false)
  const [mobileSearch, setMobileSearch] = useState(false)
  const next = encodeURIComponent(pathname + search)
  const close = () => {
    setMenu(false)
    setUserMenu(false)
  }
  return (
    <header className="cm-header">
      <nav className="navbar navbar-expand-lg py-2" data-bs-theme="dark">
        <div className="container-xl gap-2">
          <Link className="cm-logo me-2" to="/" aria-label="CodeMarket, на главную" onClick={close}>
            Code<span>Market</span>
          </Link>
          <button
            className="btn btn-link text-white d-lg-none ms-auto px-2"
            type="button"
            aria-label="Поиск"
            onClick={() => setMobileSearch((v) => !v)}
          >
            <i className="bi bi-search fs-5" />
          </button>
          <button
            className="navbar-toggler border-0 px-2"
            type="button"
            aria-expanded={menu}
            aria-label="Меню"
            onClick={() => setMenu((v) => !v)}
          >
            <span className="navbar-toggler-icon" />
          </button>
          <div className={`collapse navbar-collapse ${menu ? 'show' : ''}`}>
            <SearchForm className="d-none d-lg-flex flex-grow-1 mx-lg-4" />
            <ul className="navbar-nav ms-auto align-items-lg-center gap-lg-2">
              <li className="nav-item">
                <Link className="nav-link fw-semibold" to="/sell/" onClick={close}>
                  <i className="bi bi-shop me-1" />
                  Продавать
                </Link>
              </li>
              {user ? (
                <>
                  <li className="nav-item">
                    <Link
                      className="nav-link cm-bell"
                      to="/notifications/"
                      aria-label={`Уведомления: ${unread} непрочитанных`}
                      onClick={close}
                    >
                      <i className="bi bi-bell" />
                      {unread > 0 && <span className="badge rounded-pill">{unread}</span>}
                    </Link>
                  </li>
                  <li className="nav-item dropdown">
                    <button
                      className="nav-link dropdown-toggle btn btn-link"
                      type="button"
                      aria-expanded={userMenu}
                      onClick={() => setUserMenu((v) => !v)}
                    >
                      <i className="bi bi-person-circle me-1" />
                      {user.username}
                    </button>
                    <ul
                      className={`dropdown-menu dropdown-menu-end ${userMenu ? 'show' : ''}`}
                      data-bs-theme="light"
                    >
                      <li>
                        <Link className="dropdown-item" to="/me/purchases/" onClick={close}>
                          <i className="bi bi-bag me-2" />
                          Покупки
                        </Link>
                      </li>
                      <li>
                        <Link className="dropdown-item" to="/me/orders/" onClick={close}>
                          <i className="bi bi-chat-square-text me-2" />
                          Заказы
                        </Link>
                      </li>
                      {user.is_seller && (
                        <li>
                          <Link className="dropdown-item" to="/sell/" onClick={close}>
                            <i className="bi bi-shop me-2" />
                            Продажи
                          </Link>
                        </li>
                      )}
                      <li>
                        <Link className="dropdown-item" to="/balance/" onClick={close}>
                          <i className="bi bi-wallet2 me-2" />
                          Баланс
                        </Link>
                      </li>
                      <li>
                        <Link className="dropdown-item" to="/me/profile/" onClick={close}>
                          <i className="bi bi-person me-2" />
                          Профиль
                        </Link>
                      </li>
                      {user.is_staff && (
                        <>
                          <li>
                            <hr className="dropdown-divider" />
                          </li>
                          <li>
                            <Link className="dropdown-item" to="/moderation/" onClick={close}>
                              <i className="bi bi-shield-check me-2" />
                              Модерация
                            </Link>
                          </li>
                        </>
                      )}
                      <li>
                        <hr className="dropdown-divider" />
                      </li>
                      <li>
                        <button
                          className="dropdown-item"
                          type="button"
                          onClick={async () => {
                            close()
                            await logout()
                            toast.push('Вы вышли из аккаунта.', 'info')
                            navigate('/')
                          }}
                        >
                          <i className="bi bi-box-arrow-right me-2" />
                          Выйти
                        </button>
                      </li>
                    </ul>
                  </li>
                </>
              ) : (
                <>
                  <li className="nav-item">
                    <Link
                      className="btn btn-cream btn-sm px-3"
                      to={`/accounts/login/?next=${next}`}
                      onClick={close}
                    >
                      Войти
                    </Link>
                  </li>
                  <li className="nav-item">
                    <NavLink className="nav-link" to="/accounts/register/" onClick={close}>
                      Регистрация
                    </NavLink>
                  </li>
                </>
              )}
            </ul>
          </div>
        </div>
      </nav>
      {mobileSearch && <SearchForm className="container-xl pb-2 d-lg-none" mobile />}
    </header>
  )
}

export function Footer() {
  return (
    <footer className="cm-footer cm-on-dark">
      <div className="container-xl py-4">
        <div className="row g-4">
          <div className="col-md-4">
            <div className="cm-logo mb-2">
              Code<span>Market</span>
            </div>
            <p className="small mb-0">
              Площадка готового кода с доработкой от автора. Учебный проект, НИУ ВШЭ Пермь.
            </p>
          </div>
          <div className="col-6 col-md-4">
            <div className="fw-bold mb-2">Документы</div>
            <ul className="list-unstyled small mb-0">
              <li>
                <Link to="/legal/terms/">Пользовательское соглашение</Link>
              </li>
              <li>
                <Link to="/legal/terms/#refunds">Правила возврата</Link>
              </li>
              <li>
                <Link to="/legal/seller/">Условия для продавцов</Link>
              </li>
              <li>
                <Link to="/legal/license/">Лицензия на продукт</Link>
              </li>
              <li>
                <Link to="/legal/privacy/">Политика персональных данных</Link>
              </li>
            </ul>
          </div>
          <div className="col-6 col-md-4">
            <div className="fw-bold mb-2">Контакты</div>
            <ul className="list-unstyled small mb-0">
              <li>
                <i className="bi bi-envelope me-1" />
                support@codemarket.example
              </li>
              <li>
                <i className="bi bi-telephone me-1" />
                +7 (342) 000-00-00
              </li>
              <li>
                <i className="bi bi-geo-alt me-1" />
                Пермь, ул. Студенческая, 1
              </li>
            </ul>
          </div>
        </div>
        <div className="small mt-4">
          © {new Date().getFullYear()} CodeMarket. Учебный проект, не является публичной офертой.
        </div>
      </div>
    </footer>
  )
}

/** Каркас страницы: шапка, содержимое, подвал. Заблокированного пользователя отправляет на страницу с причиной. */
export function Layout() {
  const { blockedReason } = useAuth()
  const { pathname } = useLocation()
  return (
    <>
      <a className="visually-hidden-focusable" href="#main">
        Перейти к содержимому
      </a>
      <Header />
      <main id="main">
        <div className="container-xl pt-3 pb-4">
          {blockedReason && pathname !== '/accounts/blocked/' ? (
            <div className="alert alert-danger d-flex gap-2" role="alert">
              <i className="bi bi-slash-circle" />
              <div>{blockedReason}</div>
            </div>
          ) : null}
          <Outlet />
        </div>
      </main>
      <Footer />
    </>
  )
}
