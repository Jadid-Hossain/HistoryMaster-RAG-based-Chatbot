import { useState } from 'react'
import { login, register, storeSession } from '../api.js'

const FEATURES = [
  {
    icon: '📚',
    title: 'Answers grounded in the book',
    text: 'Every answer is retrieved from A History of Bangladesh - never invented.',
  },
  {
    icon: '🎯',
    title: 'Sources with every answer',
    text: 'See exactly which passage each answer came from, with a match score.',
  },
  {
    icon: '🤔',
    title: 'Honest about the unknown',
    text: 'Ask something outside the book and it will tell you it does not know.',
  },
]

export default function Login({ onLogin }) {
  const [mode, setMode] = useState('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setError('')
    if (mode === 'register' && password !== confirm) {
      setError('Passwords do not match.')
      return
    }
    setBusy(true)
    try {
      const data =
        mode === 'login'
          ? await login(username.trim(), password)
          : await register(username.trim(), password)
      storeSession(data.access_token, { username: data.username, role: data.role })
      onLogin({ username: data.username, role: data.role })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-hero">
        <div className="hero-brand">Retrieval-Augmented Generation</div>
        <h1>History Master</h1>
        <p className="hero-sub">
          An AI assistant for the history of Bangladesh. It reads the book, finds the
          relevant passages, and answers your questions - with the source always shown.
        </p>
        {FEATURES.map((f) => (
          <div className="login-feature" key={f.title}>
            <span className="f-icon">{f.icon}</span>
            <div>
              <strong>{f.title}</strong>
              <span>{f.text}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="login-side">
        <div className="login-card">
          <div className="login-logo">
            <h1>
              History <span>Master</span>
            </h1>
            <p className="tagline">Ask anything about the history of Bangladesh</p>
          </div>

          <div className="mode-tabs">
            <button
              type="button"
              className={mode === 'login' ? 'tab active' : 'tab'}
              onClick={() => { setMode('login'); setError('') }}
            >
              Sign In
            </button>
            <button
              type="button"
              className={mode === 'register' ? 'tab active' : 'tab'}
              onClick={() => { setMode('register'); setError('') }}
            >
              Create Account
            </button>
          </div>

          <form onSubmit={submit} className="login-form">
            <label>
              Username
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="your.username"
                autoComplete="username"
                required
                minLength={3}
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                required
                minLength={6}
              />
            </label>
            {mode === 'register' && (
              <label>
                Confirm Password
                <input
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="new-password"
                  required
                  minLength={6}
                />
              </label>
            )}

            {error && <div className="form-error">⚠ {error}</div>}

            <button className="btn primary full" disabled={busy}>
              {busy ? 'Please wait…' : mode === 'login' ? 'Sign In' : 'Create Account & Sign In'}
            </button>
          </form>

          {mode === 'login' && (
            <div className="demo-hint">
              <strong>Demo accounts</strong>
              <span>👤 user / user123 &nbsp;·&nbsp; 🛡 admin / admin123</span>
            </div>
          )}
        </div>
        <p className="login-footer">Powered by Gemini · Chroma Vector DB · LangChain</p>
      </div>
    </div>
  )
}
