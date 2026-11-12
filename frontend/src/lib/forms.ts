import type { FieldValues, Path, UseFormSetError } from 'react-hook-form'

import { ApiError } from '../api/client'

/** Разложить ошибки сервера по полям формы; вернуть общий текст ошибки (если поле не найдено). */
export function applyServerErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  fields: readonly string[],
): string {
  if (!(error instanceof ApiError)) return 'Что-то пошло не так. Попробуйте ещё раз.'
  let rest = ''
  for (const [name, text] of Object.entries(error.fields)) {
    if (fields.includes(name)) setError(name as Path<T>, { type: 'server', message: text })
    else rest ||= text
  }
  if (!Object.keys(error.fields).length) return error.message
  return rest
}

export function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Что-то пошло не так. Попробуйте ещё раз.'
}

/** Безопасный адрес возврата после входа: только внутренние пути. */
export function safeNext(next: string | null): string {
  if (!next || !next.startsWith('/') || next.startsWith('//')) return '/'
  return next
}
