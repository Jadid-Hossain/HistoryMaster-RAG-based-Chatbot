import { useEffect, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { getStoredUser } from './api.js'
import Login from './pages/Login.jsx'
import Chat from './pages/Chat.jsx'
import Admin from './pages/Admin.jsx'

export default function App() {
  const [user, setUser] = useState(getStoredUser())

  const requireAuth = (element) =>
    user ? element : <Navigate to="/login" replace />

  return (
    <div className="app">
      <Routes>
        <Route
          path="/login"
          element={user ? <Navigate to="/chat" replace /> : <Login onLogin={setUser} />}
        />
        <Route path="/chat" element={requireAuth(<Chat user={user} onLogout={() => setUser(null)} />)} />
        <Route
          path="/admin"
          element={requireAuth(
            user?.role === 'admin' ? <Admin user={user} onLogout={() => setUser(null)} /> : <Navigate to="/chat" replace />
          )}
        />
        <Route path="*" element={<Navigate to={user ? '/chat' : '/login'} replace />} />
      </Routes>
    </div>
  )
}
