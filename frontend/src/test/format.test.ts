import {
  formatDate,
  formatDateTime,
  formatMoney,
  percent,
  plural,
  similarityTone,
  timeLeft,
} from '../lib/format'

const NB = ' '

describe('форматирование цен и дат', () => {
  it('цена с пробелами между тысячами и знаком рубля', () => {
    expect(formatMoney('12500.00')).toBe(`12${NB}500${NB}₽`)
    expect(formatMoney(490)).toBe(`490${NB}₽`)
    expect(formatMoney('1350.50')).toBe(`1${NB}350,50${NB}₽`)
    expect(formatMoney('-600.00')).toBe(`−600${NB}₽`)
    expect(formatMoney(null)).toBe('')
    expect(formatMoney('abc')).toBe('')
  })

  it('даты в часовом поясе площадки (Екатеринбург, UTC+5)', () => {
    expect(formatDateTime('2026-11-05T09:30:00Z')).toBe('05.11.2026 14:30')
    expect(formatDate('2026-12-31T20:00:00Z')).toBe('01.01.2027')
    expect(formatDateTime(null)).toBe('—')
  })

  it('склонения, проценты, сходство, остаток срока', () => {
    expect(plural(1, ['отзыв', 'отзыва', 'отзывов'])).toBe('отзыв')
    expect(plural(3, ['отзыв', 'отзыва', 'отзывов'])).toBe('отзыва')
    expect(plural(11, ['отзыв', 'отзыва', 'отзывов'])).toBe('отзывов')
    expect(plural(21, ['день', 'дня', 'дней'])).toBe('день')
    expect(percent(25)).toBe(`25${NB}%`)
    expect(percent(12.34, 1)).toBe(`12,3${NB}%`)
    expect(percent(null)).toBe('—')
    expect(similarityTone(0.1)).toBe('success')
    expect(similarityTone(0.3)).toBe('warning')
    expect(similarityTone(0.8)).toBe('danger')
    expect(timeLeft(2 * 86400 + 5 * 3600)).toBe(`2${NB}дн. 5${NB}ч`)
    expect(timeLeft(-1)).toBe('срок прошёл')
  })
})
