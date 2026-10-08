import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  fetchDocuments, uploadFiles, addUrl, deleteDocument, rebuildIndex, fetchStats,
  fetchUsers, clearSession,
} from '../api.js'

const FORMAT_ICONS = { pdf: '📕', docx: '📘', txt: '📄', md: '📝', html: '🌐', url: '🌐' }

export default function Admin({ user, onLogout }) {
  const navigate = useNavigate()
  const [tab, setTab] = useState('knowledge')
  const [docs, setDocs] = useState([])
  const [users, setUsers] = useState([])
  const [stats, setStats] = useState(null)
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [notice, setNotice] = useState(null)
  const [uploadResults, setUploadResults] = useState(null)
  const fileInputRef = useRef(null)

  async function refresh() {
    try {
      setDocs(await fetchDocuments())
      setStats(await fetchStats())
    } catch (err) {
      setNotice({ kind: 'err', text: err.message })
    }
  }

  useEffect(() => { refresh() }, [])

  async function showUsers() {
    try {
      setUsers(await fetchUsers())
    } catch (err) {
      setNotice({ kind: 'err', text: err.message })
    }
  }

  function switchTab(next) {
    setTab(next)
    setNotice(null)
    setUploadResults(null)
    if (next === 'users') showUsers()
  }

  async function handleFiles(fileList) {
    const files = [...fileList]
    if (!files.length) return
    setBusy(true); setUploadResults(null); setNotice(null)
    try {
      const data = await uploadFiles(files)
      setUploadResults(data.results)
      await refresh()
    } catch (err) {
      setNotice({ kind: 'err', text: err.message })
      if (err.data?.detail?.results) setUploadResults(err.data.detail.results)
    } finally {
      setBusy(false)
    }
  }

  function onFilesSelected(event) {
    // Copy to a real array FIRST: clearing input.value empties the live
    // FileList, which silently skipped the whole upload.
    const files = Array.from(event.target.files || [])
    event.target.value = ''
    handleFiles(files)
  }

  function onDrop(event) {
    event.preventDefault()
    setDragging(false)
    handleFiles(event.dataTransfer.files)
  }

  async function onAddUrl(event) {
    event.preventDefault()
    if (!url.trim()) return
    setBusy(true); setNotice(null); setUploadResults(null)
    try {
      const result = await addUrl(url.trim())
      setUploadResults([{ filename: result.filename, status: result.status, num_chunks: result.num_chunks, error: null }])
      setUrl('')
      await refresh()
    } catch (err) {
      setNotice({ kind: 'err', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  async function onDelete(doc) {
    if (!window.confirm(`Delete "${doc.filename}" and its ${doc.num_chunks} vectors from the index?`)) return
    try {
      await deleteDocument(doc.id)
      setNotice({ kind: 'ok', text: `Deleted ${doc.filename}. The vector index shrinks instantly — no retraining.` })
      await refresh()
    } catch (err) {
      setNotice({ kind: 'err', text: err.message })
    }
  }

  async function onRebuild() {
    setBusy(true); setNotice(null)
    try {
      const result = await rebuildIndex()
      setNotice({ kind: 'ok', text: `Re-indexed ${result.chunks} chunks.` })
      await refresh()
    } catch (err) {
      setNotice({ kind: 'err', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  function logout() {
    clearSession()
    onLogout()
  }

  const statCards = stats ? [
    { icon: '📚', value: stats.documents, label: 'Documents' },
    { icon: '🧩', value: stats.chunks, label: 'Vector chunks' },
    { icon: '👥', value: stats.users, label: 'Users' },
    { icon: '💬', value: stats.chat_sessions, label: 'Chat sessions' },
    { icon: '💡', value: stats.answers_generated, label: 'Answers generated' },
    { icon: '🤖', value: stats.llm_model || stats.llm_provider || '—', label: 'LLM' },
  ] : []

  return (
    <div className="admin-layout">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <strong>History Master</strong>
          <small>Admin Panel · Knowledge base control</small>
        </div>
        <button className="btn primary full" onClick={() => navigate('/chat')}>💬 Back to Chat</button>
        <div className="sidebar-footer">
          <div className="user-row">
            <span className="avatar">{user?.username?.[0]?.toUpperCase()}</span>
            <div className="user-meta"><strong>{user?.username}</strong><small>{user?.role}</small></div>
            <button className="btn ghost small-btn" onClick={logout}>Logout</button>
          </div>
        </div>
      </aside>

      <main className="admin-main">
        <header className="admin-header">
          <h1>Knowledge Base Management</h1>
          <p className="muted">Upload documents or web pages — new content is embedded instantly, no retraining needed.</p>
        </header>

        {statCards.length > 0 && (
          <section className="stats-grid">
            {statCards.map((s) => (
              <div className="stat-card" key={s.label}>
                <span className="stat-icon">{s.icon}</span>
                <span className="stat-body">
                  <span className="stat-num" title={String(s.value)}>{s.value}</span>
                  <span>{s.label}</span>
                </span>
              </div>
            ))}
          </section>
        )}

        <div className="admin-tabs">
          <button className={tab === 'knowledge' ? 'tab-btn active' : 'tab-btn'} onClick={() => switchTab('knowledge')}>
            📥 Knowledge Base
          </button>
          <button className={tab === 'users' ? 'tab-btn active' : 'tab-btn'} onClick={() => switchTab('users')}>
            👥 Users
          </button>
        </div>

        {tab === 'knowledge' && (
          <>
            <section className="panel">
              <h2>📥 Add knowledge</h2>
              <div
                className={dragging ? 'dropzone dragover' : 'dropzone'}
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                role="button"
                aria-label="Upload files"
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".pdf,.txt,.md,.docx,.html,.htm"
                  onChange={onFilesSelected}
                  disabled={busy}
                />
                <span className="dropzone-icon">{dragging ? '📥' : '📤'}</span>
                <strong>{dragging ? 'Drop the files here' : 'Click to choose files or drag & drop'}</strong>
                <span className="muted">PDF · TXT · MD · DOCX · HTML — up to 25 MB each</span>
              </div>

              <form className="url-row" onSubmit={onAddUrl}>
                <input
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://example.com/page — ingest a web page"
                  disabled={busy}
                />
                <button className="btn primary" disabled={busy || !url.trim()}>Add URL</button>
              </form>

              {uploadResults && (
                <ul className="upload-results">
                  {uploadResults.map((r, i) => (
                    <li key={i} className={r.status === 'ready' ? 'ok' : 'err'}>
                      {r.status === 'ready'
                        ? `✅ ${r.filename} — ${r.num_chunks} chunks embedded`
                        : `❌ ${r.filename} — ${r.error}`}
                    </li>
                  ))}
                </ul>
              )}
              {notice && <div className={notice.kind === 'ok' ? 'notice ok' : 'notice err'}>{notice.text}</div>}
            </section>

            <section className="panel">
              <div className="panel-head">
                <h2>📚 Documents in the knowledge base</h2>
                <button className="btn ghost" onClick={onRebuild} disabled={busy}>🔄 Re-index all</button>
              </div>
              <table className="doc-table">
                <thead>
                  <tr><th>File</th><th>Type</th><th>Chunks</th><th>Size</th><th>Uploaded by</th><th>Date</th><th></th></tr>
                </thead>
                <tbody>
                  {docs.length === 0 && (
                    <tr><td colSpan={7} className="muted">No documents yet — upload something above.</td></tr>
                  )}
                  {docs.map((d) => (
                    <tr key={d.id}>
                      <td>{FORMAT_ICONS[d.doc_type] || '📄'} {d.filename}{d.status !== 'ready' && <em className="muted"> ({d.status})</em>}</td>
                      <td><span className="type-badge">{d.doc_type}</span></td>
                      <td>{d.num_chunks}</td>
                      <td>{d.size_bytes > 1024 ? `${(d.size_bytes / 1024).toFixed(1)} KB` : `${d.size_bytes} B`}</td>
                      <td>{d.uploaded_by}</td>
                      <td>{String(d.created_at).slice(0, 16)}</td>
                      <td><button className="btn danger small-btn" onClick={() => onDelete(d)}>Delete</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </>
        )}

        {tab === 'users' && (
          <section className="panel">
            <div className="panel-head">
              <h2>👥 Registered users</h2>
              <button className="btn ghost" onClick={showUsers}>🔄 Refresh</button>
            </div>
            <table className="doc-table">
              <thead>
                <tr><th>#</th><th>Username</th><th>Role</th><th>Joined</th></tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>{u.id}</td>
                    <td>{u.username}</td>
                    <td><span className={`role-badge ${u.role}`}>{u.role}</span></td>
                    <td>{String(u.created_at).slice(0, 16)}</td>
                  </tr>
                ))}
                {users.length === 0 && <tr><td colSpan={4} className="muted">Loading…</td></tr>}
              </tbody>
            </table>
          </section>
        )}
      </main>
    </div>
  )
}
