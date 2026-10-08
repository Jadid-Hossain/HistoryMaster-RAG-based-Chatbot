const TOKEN_KEY = 'knowbot_token'
const USER_KEY = 'knowbot_user'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
  } catch {
    return null
  }
}

export function storeSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

async function request(path, { method = 'GET', body, formData, headers = {} } = {}) {
  const finalHeaders = { ...headers }
  const token = getToken()
  if (token) finalHeaders['Authorization'] = `Bearer ${token}`
  if (body !== undefined) finalHeaders['Content-Type'] = 'application/json'

  let response
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: finalHeaders,
      body: formData ? formData : body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new Error('Cannot reach the server. Is the backend running on port 8000?')
  }

  if (response.status === 401 && getToken()) {
    clearSession()
    window.location.hash = '#/login'
    throw new Error('Session expired. Please log in again.')
  }

  let data = null
  try {
    data = await response.json()
  } catch {
    /* non-JSON error body */
  }

  if (!response.ok) {
    const detail = data?.detail
    const message =
      typeof detail === 'string'
        ? detail
        : detail?.message || (data ? JSON.stringify(data).slice(0, 300) : `HTTP ${response.status}`)
    const error = new Error(message)
    error.status = response.status
    error.data = data
    throw error
  }
  return data
}

// ---------------------------------------------------------------- auth ----
export const login = (username, password) =>
  request('/auth/login', { method: 'POST', body: { username, password } })

export const register = (username, password) =>
  request('/auth/register', { method: 'POST', body: { username, password } })

export const fetchMe = () => request('/auth/me')

export const fetchUsers = () => request('/auth/users')

// ---------------------------------------------------------------- chat ----
export const ask = (message, sessionId) =>
  request('/chat/ask', { method: 'POST', body: { message, session_id: sessionId } })

export const fetchSessions = () => request('/chat/sessions')

export const fetchMessages = (sessionId) => request(`/chat/sessions/${sessionId}/messages`)

export const deleteSession = (sessionId) =>
  request(`/chat/sessions/${sessionId}`, { method: 'DELETE' })

export const fetchCapabilities = () => request('/chat/capabilities')

// ------------------------------------------------------------------ kb ----
export const fetchDocuments = () => request('/kb/documents')

export const uploadFiles = (fileList) => {
  const formData = new FormData()
  for (const file of fileList) formData.append('files', file)
  return request('/kb/documents', { method: 'POST', formData })
}

export const addUrl = (url) => request('/kb/url', { method: 'POST', body: { url } })

export const deleteDocument = (id) => request(`/kb/documents/${id}`, { method: 'DELETE' })

export const rebuildIndex = () => request('/kb/rebuild', { method: 'POST' })

export const fetchStats = () => request('/kb/stats')

// -------------------------------------------------------------- system ----
export const fetchHealth = () => request('/health')
