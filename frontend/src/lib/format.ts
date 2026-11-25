/** Форматирование: «12 500 ₽», «ДД.ММ.ГГГГ ЧЧ:ММ» в местном времени площадки. */

const TZ = 'Asia/Yekaterinburg'
const NBSP = ' '

export function formatMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return ''
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) return ''
  const whole = Number.isInteger(n)
  const [int, frac] = Math.abs(n)
    .toFixed(whole ? 0 : 2)
    .split('.')
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP)
  return `${n < 0 ? '−' : ''}${grouped}${frac ? ',' + frac : ''}${NBSP}₽`
}

function parts(value: string | Date) {
  const date = typeof value === 'string' ? new Date(value) : value
  const fmt = new Intl.DateTimeFormat('ru-RU', {
    timeZone: TZ,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
  const p: Record<string, string> = {}
  for (const { type, value: v } of fmt.formatToParts(date)) p[type] = v
  return p
}

/** Дата и время: 05.11.2026 14:30 («—» для пустого значения). */
export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return '—'
  const p = parts(value)
  return `${p.day}.${p.month}.${p.year} ${p.hour === '24' ? '00' : p.hour}:${p.minute}`
}

/** Только дата: 05.11.2026. */
export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return '—'
  const p = parts(value)
  return `${p.day}.${p.month}.${p.year}`
}

/** Склонение: plural(3, ['отзыв', 'отзыва', 'отзывов']) → «отзыва». */
export function plural(n: number, forms: [string, string, string]): string {
  const a = Math.abs(n) % 100
  const b = a % 10
  if (a > 10 && a < 20) return forms[2]
  if (b > 1 && b < 5) return forms[1]
  if (b === 1) return forms[0]
  return forms[2]
}

export function percent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return '—'
  return `${value.toFixed(digits).replace('.', ',')}${NBSP}%`
}

export function similarityTone(value: number | null | undefined): 'success' | 'warning' | 'danger' {
  const v = value ?? 0
  if (v >= 0.7) return 'danger'
  if (v >= 0.3) return 'warning'
  return 'success'
}

/** Размер файла: 1,2 МБ. */
export function fileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1).replace('.', ',')}${NBSP}МБ`
  return `${Math.max(1, Math.round(bytes / 1024))}${NBSP}КБ`
}

/** Сколько осталось до срока: «2 дн. 5 ч» / «просрочено». */
export function timeLeft(seconds: number): string {
  if (seconds < 0) return 'срок прошёл'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  return days
    ? `${days}${NBSP}дн. ${hours}${NBSP}ч`
    : `${hours}${NBSP}ч ${Math.floor((seconds % 3600) / 60)}${NBSP}мин`
}
