import React, { createContext, useContext, useState, useEffect } from 'react'
import api from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(localStorage.getItem('token'))
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    if (!token) { setLoading(false); return }
    api.get('/auth/me').then(({ data }) => {
      if (active) {
        setUser(data)
        localStorage.setItem('user', JSON.stringify(data))
      }
    }).catch(() => {
      if (active) { setUser(null); setToken(null); localStorage.removeItem('token'); localStorage.removeItem('user') }
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])


  const login = async (email, password) => {
    const res = await api.post('/auth/login', { email, password })
    const { token: newToken, user: userData } = res.data
    localStorage.setItem('token', newToken)
    localStorage.setItem('user', JSON.stringify(userData))
    setToken(newToken)
    setUser(userData)
    return userData
  }

  const logout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    setToken(null)
    setUser(null)
    delete api.defaults.headers.common['Authorization']
  }



  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
