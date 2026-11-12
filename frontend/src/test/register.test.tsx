import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'

import { AuthProvider } from '../hooks/useAuth'
import { ToastProvider } from '../hooks/useToast'
import RegisterPage from '../pages/auth/RegisterPage'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function renderPage(registerResponse: Response) {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      calls.push(url)
      if (url.endsWith('/api/auth/me')) return json(null)
      if (url.endsWith('/api/auth/config')) return json({ hold_days: 7 })
      return registerResponse.clone()
    }),
  )
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ToastProvider>
        <AuthProvider>
          <MemoryRouter>
            <RegisterPage />
          </MemoryRouter>
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>,
  )
  return calls
}

function fill(values: Record<string, string>) {
  for (const [label, value] of Object.entries(values)) {
    fireEvent.change(screen.getByLabelText(new RegExp(`^${label}`)), { target: { value } })
  }
}

afterEach(() => vi.unstubAllGlobals())

describe('форма регистрации', () => {
  it('показывает ошибки под полями до отправки, запрос не уходит', async () => {
    const calls = renderPage(json({}))
    fill({ Email: 'не-почта', 'Имя пользователя': 'ab', Пароль: 'short', 'Повтор пароля': 'other' })
    fireEvent.click(screen.getByRole('button', { name: 'Зарегистрироваться' }))
    expect(await screen.findByText('Введите правильный адрес электронной почты.')).toBeInTheDocument()
    expect(screen.getByText(/3–30 символов, латинские буквы/)).toBeInTheDocument()
    expect(screen.getByText('Пароль слишком короткий: не короче 8 символов.')).toBeInTheDocument()
    expect(screen.getByText('Пароли не совпадают.')).toBeInTheDocument()
    expect(screen.getByText('Без согласия регистрация невозможна.')).toBeInTheDocument()
    expect(calls.some((u) => u.includes('/register'))).toBe(false)
  })

  it('ошибка сервера показывается под своим полем', async () => {
    renderPage(
      json(
        {
          detail: 'Пользователь с таким email уже есть.',
          fields: { email: 'Пользователь с таким email уже есть.' },
        },
        422,
      ),
    )
    fill({
      Email: 'anna@test.ru',
      'Имя пользователя': 'anna_1',
      Пароль: 'secret123',
      'Повтор пароля': 'secret123',
    })
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Зарегистрироваться' }))
    await waitFor(() => expect(screen.getByText('Пользователь с таким email уже есть.')).toBeInTheDocument())
    expect(screen.getByLabelText(/^Email/)).toHaveClass('is-invalid')
  })
})
