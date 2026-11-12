import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, Navigate, useNavigate, useParams, useSearchParams } from 'react-router'

import { ApiError, client, unwrap } from '../../api/client'
import { Field, FormError } from '../../components/ui'
import { useTitle } from '../../hooks/misc'
import { useAuth } from '../../hooks/useAuth'
import { useToast } from '../../hooks/useToast'
import { errorText, safeNext } from '../../lib/forms'

export function AuthCard({ children }: { children: ReactNode }) {
  return (
    <div className="row justify-content-center py-3">
      <div className="col-sm-10 col-md-7 col-lg-5">
        <div className="card shadow-sm">
          <div className="card-body p-4">{children}</div>
        </div>
      </div>
    </div>
  )
}

type Errors = Record<string, string>

function fieldsOf(err: unknown): [string, Errors] {
  if (err instanceof ApiError) return [Object.keys(err.fields).length ? '' : err.message, err.fields]
  return [errorText(err), {}]
}

export function LoginPage() {
  useTitle('Вход')
  const { user, setUser } = useAuth()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const next = safeNext(params.get('next'))
  if (user) return <Navigate to={next} replace />

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const u = await unwrap(client.POST('/api/auth/login', { body: { email, password } }))
      setUser(u)
      navigate(next, { replace: true })
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <AuthCard>
      <h1 className="h4 mb-3">Вход</h1>
      <form onSubmit={submit} noValidate>
        <FormError error={error} />
        <Field label="Email" id="email" required>
          <input
            id="email"
            type="email"
            autoComplete="email"
            autoFocus
            className="form-control"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        <Field label="Пароль" id="password" required>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            className="form-control"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <button className="btn btn-primary w-100" type="submit" disabled={busy}>
          Войти
        </button>
      </form>
      <div className="d-flex justify-content-between mt-3 small">
        <Link to="/accounts/password/reset/">Забыли пароль?</Link>
        <Link to="/accounts/register/">Регистрация</Link>
      </div>
    </AuthCard>
  )
}

export function PasswordResetPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')
  useTitle(sent ? 'Письмо отправлено' : 'Восстановление пароля')
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    try {
      await unwrap(client.POST('/api/auth/password/reset', { body: { email } }))
      setSent(true)
    } catch (err) {
      setError(errorText(err))
    }
  }
  if (sent) {
    return (
      <AuthCard>
        <h1 className="h4 mb-3">Проверьте почту</h1>
        <p className="mb-0">
          Если такой email зарегистрирован, мы отправили на него ссылку для смены пароля. В режиме разработки
          письмо выводится в консоль сервера.
        </p>
      </AuthCard>
    )
  }
  return (
    <AuthCard>
      <h1 className="h4 mb-3">Восстановление пароля</h1>
      <p className="text-muted">Укажите email, мы пришлём ссылку для смены пароля.</p>
      <form onSubmit={submit} noValidate>
        <FormError error={error} />
        <Field label="Email" id="email" required>
          <input
            id="email"
            type="email"
            className="form-control"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        <button className="btn btn-primary w-100" type="submit">
          Отправить ссылку
        </button>
      </form>
    </AuthCard>
  )
}

function PasswordPair({
  errors,
  p1,
  p2,
  set1,
  set2,
}: {
  errors: Errors
  p1: string
  p2: string
  set1: (v: string) => void
  set2: (v: string) => void
}) {
  return (
    <>
      <Field
        label="Новый пароль"
        id="new_password1"
        required
        error={errors.new_password1}
        help="Не короче 8 символов, буквы и цифры."
      >
        <input
          id="new_password1"
          type="password"
          autoComplete="new-password"
          className="form-control"
          value={p1}
          onChange={(e) => set1(e.target.value)}
        />
      </Field>
      <Field label="Повтор нового пароля" id="new_password2" required error={errors.new_password2}>
        <input
          id="new_password2"
          type="password"
          autoComplete="new-password"
          className="form-control"
          value={p2}
          onChange={(e) => set2(e.target.value)}
        />
      </Field>
    </>
  )
}

export function PasswordResetConfirmPage() {
  useTitle('Новый пароль')
  const { token = '' } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const [p1, setP1] = useState('')
  const [p2, setP2] = useState('')
  const [errors, setErrors] = useState<Errors>({})
  const [error, setError] = useState('')
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    try {
      const res = await unwrap(
        client.POST('/api/auth/password/reset/confirm', {
          body: { token, new_password1: p1, new_password2: p2 },
        }),
      )
      toast.push(res.message)
      navigate('/accounts/login/')
    } catch (err) {
      const [text, fields] = fieldsOf(err)
      setError(text)
      setErrors(fields)
    }
  }
  return (
    <AuthCard>
      <h1 className="h4 mb-3">Новый пароль</h1>
      <form onSubmit={submit} noValidate>
        {error && (
          <div className="alert alert-danger d-flex gap-2">
            <i className="bi bi-exclamation-octagon-fill" aria-hidden="true" />
            <div>
              {error} <Link to="/accounts/password/reset/">Запросить новую</Link>.
            </div>
          </div>
        )}
        <PasswordPair errors={errors} p1={p1} p2={p2} set1={setP1} set2={setP2} />
        <button className="btn btn-primary w-100" type="submit">
          Сохранить пароль
        </button>
      </form>
    </AuthCard>
  )
}

export function PasswordChangePage() {
  useTitle('Смена пароля')
  const navigate = useNavigate()
  const toast = useToast()
  const [old, setOld] = useState('')
  const [p1, setP1] = useState('')
  const [p2, setP2] = useState('')
  const [errors, setErrors] = useState<Errors>({})
  const [error, setError] = useState('')
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    try {
      const res = await unwrap(
        client.POST('/api/auth/password/change', {
          body: { old_password: old, new_password1: p1, new_password2: p2 },
        }),
      )
      toast.push(res.message)
      navigate('/me/profile/')
    } catch (err) {
      const [text, fields] = fieldsOf(err)
      setError(text)
      setErrors(fields)
    }
  }
  return (
    <AuthCard>
      <h1 className="h4 mb-3">Смена пароля</h1>
      <form onSubmit={submit} noValidate>
        <FormError error={error} />
        <Field label="Старый пароль" id="old_password" required error={errors.old_password}>
          <input
            id="old_password"
            type="password"
            autoComplete="current-password"
            className="form-control"
            value={old}
            onChange={(e) => setOld(e.target.value)}
          />
        </Field>
        <PasswordPair errors={errors} p1={p1} p2={p2} set1={setP1} set2={setP2} />
        <button className="btn btn-primary w-100" type="submit">
          Сменить пароль
        </button>
      </form>
    </AuthCard>
  )
}

export function BlockedPage() {
  useTitle('Аккаунт заблокирован')
  const { blockedReason } = useAuth()
  const reason = blockedReason.replace(/^Аккаунт заблокирован\. Причина: /, '') || 'не указана'
  return (
    <AuthCard>
      <div className="alert alert-danger d-flex gap-2 mb-0">
        <i className="bi bi-slash-circle-fill" aria-hidden="true" />
        <div>
          <strong>Аккаунт заблокирован.</strong>
          <br />
          Причина: {reason}
          <br />
          Если это ошибка, напишите в поддержку: support@codemarket.example
        </div>
      </div>
    </AuthCard>
  )
}
