import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, Navigate, useNavigate } from 'react-router'
import { z } from 'zod'

import { client, unwrap } from '../../api/client'
import { Field, FormError } from '../../components/ui'
import { useTitle } from '../../hooks/misc'
import { useAuth } from '../../hooks/useAuth'
import { useToast } from '../../hooks/useToast'
import { applyServerErrors } from '../../lib/forms'

/** Правила как на сервере: показываем ошибку сразу, сервер всё равно проверит ещё раз. */
export const registerSchema = z
  .object({
    email: z
      .string()
      .trim()
      .min(1, 'Обязательное поле.')
      .email('Введите правильный адрес электронной почты.'),
    username: z
      .string()
      .trim()
      .regex(
        /^[A-Za-z0-9_]{3,30}$/,
        'Имя пользователя: 3–30 символов, латинские буквы, цифры и знак подчёркивания.',
      ),
    password1: z
      .string()
      .min(8, 'Пароль слишком короткий: не короче 8 символов.')
      .refine((v) => /[A-Za-zА-Яа-яЁё]/.test(v) && /\d/.test(v), 'Пароль должен содержать буквы и цифры.'),
    password2: z.string(),
    accept_terms: z.boolean().refine((v) => v, 'Без согласия регистрация невозможна.'),
  })
  .refine((d) => d.password1 === d.password2, { path: ['password2'], message: 'Пароли не совпадают.' })

type Form = z.infer<typeof registerSchema>
const FIELDS = ['email', 'username', 'password1', 'password2', 'accept_terms'] as const

export default function RegisterPage() {
  useTitle('Регистрация')
  const { user, setUser } = useAuth()
  const navigate = useNavigate()
  const toast = useToast()
  const [formError, setFormError] = useState('')
  const { register, handleSubmit, setError, formState } = useForm<Form>({
    resolver: zodResolver(registerSchema),
    defaultValues: { email: '', username: '', password1: '', password2: '', accept_terms: false },
  })
  if (user) return <Navigate to="/" replace />
  const e = formState.errors

  const onSubmit = handleSubmit(async (data) => {
    setFormError('')
    try {
      const u = await unwrap(client.POST('/api/auth/register', { body: data }))
      setUser(u)
      toast.push('Добро пожаловать в CodeMarket!')
      navigate('/')
    } catch (err) {
      setFormError(applyServerErrors(err, setError, FIELDS))
    }
  })

  return (
    <div className="row justify-content-center py-3">
      <div className="col-sm-10 col-md-7 col-lg-5">
        <div className="card shadow-sm">
          <div className="card-body p-4">
            <h1 className="h4 mb-3">Регистрация</h1>
            <form onSubmit={onSubmit} noValidate>
              <FormError error={formError} />
              <Field label="Email" id="email" required error={e.email?.message}>
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  className={`form-control ${e.email ? 'is-invalid' : ''}`}
                  {...register('email')}
                />
              </Field>
              <Field
                label="Имя пользователя"
                id="username"
                required
                error={e.username?.message}
                help="3–30 символов: латинские буквы, цифры, «_»."
              >
                <input
                  id="username"
                  className={`form-control ${e.username ? 'is-invalid' : ''}`}
                  {...register('username')}
                />
              </Field>
              <Field
                label="Пароль"
                id="password1"
                required
                error={e.password1?.message}
                help="Не короче 8 символов, буквы и цифры."
              >
                <input
                  id="password1"
                  type="password"
                  autoComplete="new-password"
                  className={`form-control ${e.password1 ? 'is-invalid' : ''}`}
                  {...register('password1')}
                />
              </Field>
              <Field label="Повтор пароля" id="password2" required error={e.password2?.message}>
                <input
                  id="password2"
                  type="password"
                  autoComplete="new-password"
                  className={`form-control ${e.password2 ? 'is-invalid' : ''}`}
                  {...register('password2')}
                />
              </Field>
              <div className="mb-3">
                <div className="form-check">
                  <input
                    id="accept_terms"
                    type="checkbox"
                    className={`form-check-input ${e.accept_terms ? 'is-invalid' : ''}`}
                    {...register('accept_terms')}
                  />
                  <label className="form-check-label" htmlFor="accept_terms">
                    Принимаю{' '}
                    <Link to="/legal/terms/" target="_blank">
                      пользовательское соглашение
                    </Link>{' '}
                    и{' '}
                    <Link to="/legal/privacy/" target="_blank">
                      политику обработки персональных данных
                    </Link>
                    <span className="required-mark"> *</span>
                  </label>
                </div>
                {e.accept_terms && (
                  <div className="cm-field-error">
                    <i className="bi bi-exclamation-circle" aria-hidden="true" />
                    {e.accept_terms.message}
                  </div>
                )}
              </div>
              <button className="btn btn-accent w-100" type="submit" disabled={formState.isSubmitting}>
                Зарегистрироваться
              </button>
            </form>
            <p className="mt-3 mb-0 text-center">
              Уже есть аккаунт? <Link to="/accounts/login/">Войти</Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
