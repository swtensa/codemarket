/**
 * Клиент API на fetch с типами из OpenAPI сервера (npm run gen:api → src/api/schema.d.ts).
 * Изменяющие запросы передают заголовок X-CSRF-Token из cookie csrf_token (double submit).
 * При 401 клиент один раз обновляет токены через /api/auth/refresh и повторяет запрос.
 */
import createClient, { type Middleware } from 'openapi-fetch'

import type { components, paths } from './schema'

export type S = components['schemas']

const SAFE = new Set(['GET', 'HEAD', 'OPTIONS'])

export function csrfToken(): string {
  const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : ''
}

let refreshing: Promise<boolean> | null = null

/** Обновить пару токенов по refresh-cookie; параллельные запросы ждут одно обновление. */
export function refreshTokens(): Promise<boolean> {
  if (!refreshing) {
    refreshing = fetch('/api/auth/refresh', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-CSRF-Token': csrfToken() },
    })
      .then((r) => r.ok)
      .catch(() => false)
      .finally(() => {
        setTimeout(() => (refreshing = null), 0)
      })
  }
  return refreshing
}

const NO_RETRY = ['/api/auth/refresh', '/api/auth/login', '/api/auth/register', '/api/auth/logout']

const auth: Middleware = {
  onRequest({ request }) {
    if (!SAFE.has(request.method)) request.headers.set('X-CSRF-Token', csrfToken())
    return request
  },
  async onResponse({ request, response }) {
    const path = new URL(request.url).pathname
    if (response.status !== 401 || NO_RETRY.includes(path)) return response
    if (!(await refreshTokens())) return response
    const retry = new Request(request, { headers: new Headers(request.headers) })
    if (!SAFE.has(retry.method)) retry.headers.set('X-CSRF-Token', csrfToken())
    return fetch(retry)
  },
}

export const client = createClient<paths>({ baseUrl: '', credentials: 'same-origin' })
client.use(auth)

/** Ошибка API: текст для пользователя и ошибки отдельных полей. */
export class ApiError extends Error {
  status: number
  fields: Record<string, string>
  constructor(status: number, message: string, fields: Record<string, string> = {}) {
    super(message)
    this.status = status
    this.fields = fields
  }
}

type ErrBody = { detail?: unknown; fields?: Record<string, string> } | undefined

export function toApiError(status: number, body: ErrBody): ApiError {
  const fields = body?.fields ?? {}
  let message = 'Что-то пошло не так. Попробуйте ещё раз.'
  if (typeof body?.detail === 'string') message = body.detail
  else if (Object.keys(fields).length) message = Object.values(fields)[0]
  else if (status === 404) message = 'Не найдено'
  else if (status === 403) message = 'Доступ запрещён'
  else if (status === 401) message = 'Войдите, чтобы продолжить'
  return new ApiError(status, message, fields)
}

/** Развернуть ответ openapi-fetch: данные или исключение ApiError. */
export async function unwrap<T>(
  promise: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let result
  try {
    result = await promise
  } catch {
    throw new ApiError(0, 'Нет связи с сервером. Проверьте, что он запущен.')
  }
  const { data, error, response } = result
  if (!response.ok) throw toApiError(response.status, error as ErrBody)
  return data as T
}

/** Отправка multipart/form-data (скриншоты, вложения чата) с CSRF и повтором после refresh. */
export async function upload<T>(url: string, form: FormData, method = 'POST'): Promise<T> {
  const send = () =>
    fetch(url, {
      method,
      body: form,
      credentials: 'same-origin',
      headers: { 'X-CSRF-Token': csrfToken() },
    })
  let response: Response
  try {
    response = await send()
    if (response.status === 401 && (await refreshTokens())) response = await send()
  } catch {
    throw new ApiError(0, 'Нет связи с сервером. Проверьте, что он запущен.')
  }
  const body = await response.json().catch(() => undefined)
  if (!response.ok) throw toApiError(response.status, body)
  return body as T
}
