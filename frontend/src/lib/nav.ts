import type { NavigateFunction } from 'react-router'

/** Перейти на страницу оплаты: fake-заглушка — внутри сайта, ЮKassa — внешний адрес. */
export function goToPayment(url: string, navigate: NavigateFunction) {
  if (url.startsWith('/')) navigate(url)
  else window.location.assign(url)
}
