import { useEffect, useState } from 'react'

export default function App() {
  const [status, setStatus] = useState('…')
  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then((d: { status: string }) => setStatus(d.status))
      .catch(() => setStatus('нет связи с сервером'))
  }, [])
  return (
    <main className="container py-5">
      <h1 className="fw-bold">CodeMarket</h1>
      <p className="text-secondary">Сервер: {status}</p>
    </main>
  )
}
