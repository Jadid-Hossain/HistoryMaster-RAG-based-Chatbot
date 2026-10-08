import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ask, fetchSessions, fetchMessages, deleteSession, fetchCapabilities, clearSession,
} from '../api.js'

let nextTempId = -1

// Shown when the backend does not provide KB-specific suggestions.
const DEFAULT_SUGGESTIONS = [
  'What is this book about?',
  'When was Bangladesh liberated?',
  'Summarize the main topics covered in the book',
  'Who wrote this book?',
]

// Minimal, safe markdown-ish rendering: **bold**, *italic*, `code`, "- " bullets.
function renderFormatted(text) {
  const escaped = String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  return escaped
    .replace(/^-\s+/gm, '• ')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*\n]+)\*/g, '<em>$1</em>')
    .replace(/`([^`\n]+)`/g, '<code>$1</code>')
}

function formatTime(iso) {
  const d = iso ? new Date(iso) : new Date()
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function Chat({ user, onLogout }) {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState([])
  const [activeSession, setActiveSession] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [copiedId, setCopiedId] = useState(null)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    fetchSessions().then(setSessions).catch(() => {})
    fetchCapabilities()
      .then((caps) => {
        const fromKb = caps.suggested_questions || []
        setSuggestions(fromKb.length ? fromKb : DEFAULT_SUGGESTIONS)
      })
      .catch(() => setSuggestions(DEFAULT_SUGGESTIONS))
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending])

  async function newChat() {
    setActiveSession(null)
    setMessages([])
    setError('')
  }

  async function openSession(sessionId) {
    setError('')
    try {
      const data = await fetchMessages(sessionId)
      setActiveSession(sessionId)
      setMessages(data.messages)
    } catch (err) {
      setError(err.message)
    }
  }

  async function removeSession(sessionId, event) {
    event.stopPropagation()
    try {
      await deleteSession(sessionId)
      setSessions((prev) => prev.filter((s) => s.id !== sessionId))
      if (activeSession === sessionId) newChat()
    } catch (err) {
      setError(err.message)
    }
  }

  async function send(event, presetText) {
    event?.preventDefault()
    const text = (presetText ?? input).trim()
    if (!text || sending) return
    setError('')
    setInput('')
    setMessages((prev) => [
      ...prev,
      { id: nextTempId++, role: 'user', content: text, created_at: new Date().toISOString() },
    ])
    setSending(true)
    try {
      const reply = await ask(text, activeSession)
      setMessages((prev) => [
        ...prev,
        {
          id: reply.message_id,
          role: 'assistant',
          content: reply.answer,
          sources: reply.sources,
          confidence: reply.confidence,
          in_scope: reply.in_scope,
          latency_ms: reply.latency_ms,
          created_at: new Date().toISOString(),
        },
      ])
      setActiveSession(reply.session_id)
      if (!sessions.some((s) => s.id === reply.session_id)) {
        setSessions((prev) => [
          { id: reply.session_id, title: reply.session_title, message_count: 2 },
          ...prev,
        ])
      }
    } catch (err) {
      setError(err.message)
      setMessages((prev) => prev.filter((m) => m.id > 0))
    } finally {
      setSending(false)
    }
  }

  async function copyAnswer(message) {
    try {
      await navigator.clipboard.writeText(message.content)
      setCopiedId(message.id)
      setTimeout(() => setCopiedId(null), 1600)
    } catch {
      /* clipboard unavailable */
    }
  }

  function logout() {
    clearSession()
    onLogout()
  }

  return (
    <div className="chat-layout">
      {/* ---------------------------------------------------- sidebar -- */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <strong>History Master</strong>
          <small>History of Bangladesh, on demand</small>
        </div>

        <button className="btn primary full" onClick={newChat}>＋ New Chat</button>

        <div className="session-list">
          {sessions.length === 0 && <p className="muted small">No conversations yet.</p>}
          {sessions.map((s) => (
            <div
              key={s.id}
              className={activeSession === s.id ? 'session-item active' : 'session-item'}
              onClick={() => openSession(s.id)}
            >
              <span className="session-title">💬 {s.title}</span>
              <button className="session-delete" title="Delete chat" onClick={(e) => removeSession(s.id, e)}>✕</button>
            </div>
          ))}
        </div>

        <div className="sidebar-footer">
          {user?.role === 'admin' && (
            <button className="btn ghost full" onClick={() => navigate('/admin')}>
              🛡 Admin Panel
            </button>
          )}
          <div className="user-row">
            <span className="avatar">{(user?.username || '?')[0].toUpperCase()}</span>
            <div className="user-meta">
              <strong>{user?.username}</strong>
              <small>{user?.role}</small>
            </div>
            <button className="btn ghost small-btn" onClick={logout}>Logout</button>
          </div>
        </div>
      </aside>

      {/* ------------------------------------------------------- main -- */}
      <main className="chat-main">
        <header className="chat-header">
          <h2>{activeSession ? sessions.find((s) => s.id === activeSession)?.title || 'Conversation' : 'New conversation'}</h2>
        </header>

        <div className="messages" id="messages">
          {messages.length === 0 && !sending && (
            <div className="welcome">
              <div className="welcome-icon">📖</div>
              <h3>Hi {user?.username}! Ask me anything about the history of Bangladesh.</h3>
              <p>I answer strictly from the book in my knowledge base — if something is not there, I'll tell you honestly.</p>
              <div className="suggestion-grid">
                {suggestions.map((q) => (
                  <button key={q} className="suggestion" onClick={(e) => send(e, q)}>
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m) =>
            m.role === 'user' ? (
              <div key={m.id} className="row user-row-msg">
                <div className="bubble user">
                  {m.content}
                  <div className="bubble-meta" style={{ justifyContent: 'flex-end', marginTop: 4 }}>
                    <span>{formatTime(m.created_at)}</span>
                  </div>
                </div>
              </div>
            ) : (
              <div key={m.id} className="row bot-row-msg">
                <div className={`bubble bot ${m.in_scope === false ? 'fallback' : ''}`}>
                  <div
                    className="bubble-text"
                    dangerouslySetInnerHTML={{ __html: renderFormatted(m.content) }}
                  />
                  {m.sources?.length > 0 && (
                    <div className="sources">
                      <div className="sources-label">📚 Sources</div>
                      {m.sources.map((s, i) => (
                        <details key={i} className="source-item">
                          <summary>
                            <span className="source-doc">📄 {s.document}</span>
                            <span className="source-score">
                              match {(s.retrieval_score * 100).toFixed(0)}%
                            </span>
                          </summary>
                          <p className="source-snippet">{s.snippet}</p>
                        </details>
                      ))}
                    </div>
                  )}
                  <div className="bubble-meta">
                    {m.confidence != null && <span>🎯 {(m.confidence * 100).toFixed(0)}% match</span>}
                    {m.latency_ms > 0 && <span>⚡ {(m.latency_ms / 1000).toFixed(1)}s</span>}
                    {m.in_scope === false && <span>🤔 out of knowledge base</span>}
                    <span>{formatTime(m.created_at)}</span>
                    <span className="msg-actions">
                      <button
                        className="copy-btn"
                        title="Copy answer"
                        onClick={() => copyAnswer(m)}
                      >
                        {copiedId === m.id ? '✓ Copied' : '⧉ Copy'}
                      </button>
                    </span>
                  </div>
                </div>
              </div>
            )
          )}

          {sending && (
            <div className="row bot-row-msg">
              <div className="bubble bot typing">
                <span></span><span></span><span></span>
                <em>&nbsp;searching the book…</em>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {error && <div className="chat-error">⚠ {error}</div>}

        <form className="composer" onSubmit={send}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask anything about the history of Bangladesh…"
            disabled={sending}
            autoFocus
          />
          <button className="btn primary" disabled={sending || !input.trim()}>
            {sending ? '…' : 'Send ➤'}
          </button>
        </form>
      </main>
    </div>
  )
}
