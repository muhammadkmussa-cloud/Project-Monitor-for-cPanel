import React, { useState, useEffect } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { 
  LayoutDashboard, 
  FolderOpen, 
  AlertTriangle, 
  BarChart3, 
  Settings,
  Users,
  Menu,
  X,
  Bell,
  Search,
  LogOut
} from 'lucide-react'

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Projects', href: '/projects', icon: FolderOpen },
  { name: 'Incidents', href: '/incidents', icon: AlertTriangle },
  { name: 'Analytics', href: '/analytics', icon: BarChart3 },
  { name: 'Clients', href: '/clients', icon: Users },
  { name: 'Settings', href: '/settings', icon: Settings },
]

function Layout({ children }) {
  const [apiError, setApiError] = useState('')
  useEffect(() => {
    const handler = event => setApiError(event.detail)
    window.addEventListener('api-error', handler)
    return () => window.removeEventListener('api-error', handler)
  }, [])
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const { user, logout } = useAuth()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const navLinks = navigation.map(item => {
    if (['Clients', 'Settings'].includes(item.name) && !['admin', 'owner'].includes(user?.role)) return null
    return item
  }).filter(Boolean)

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900">
      {apiError && <div role="alert" className="fixed bottom-4 right-4 z-[100] max-w-lg rounded bg-red-700 p-4 text-white shadow-lg">
        {apiError}<button className="ml-4 underline" onClick={() => setApiError('')}>Dismiss</button>
      </div>}
      {/* Mobile sidebar */}
      <div className={`fixed inset-0 z-50 lg:hidden ${sidebarOpen ? 'block' : 'hidden'}`}>
        <div className="fixed inset-0 bg-gray-600 bg-opacity-75" onClick={() => setSidebarOpen(false)} />
        <div className="fixed inset-y-0 left-0 flex flex-col w-64 bg-white dark:bg-gray-800">
          <div className="flex items-center justify-between h-16 px-4 border-b dark:border-gray-700">
            <span className="text-xl font-bold text-blue-600">Project Monitor</span>
            <button onClick={() => setSidebarOpen(false)} className="text-gray-500 hover:text-gray-700">
              <X size={24} />
            </button>
          </div>
          <nav className="flex-1 px-4 py-4 space-y-1">
            {navLinks.map((item) => {
              const Icon = item.icon
              const isActive = location.pathname === item.href
              return (
                <Link
                  key={item.name}
                  to={item.href}
                  className={`flex items-center px-3 py-2 text-sm font-medium rounded-lg ${
                    isActive 
                      ? 'bg-blue-50 text-blue-600 dark:bg-blue-900/50' 
                      : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
                  }`}
                  onClick={() => setSidebarOpen(false)}
                >
                  <Icon className="mr-3 h-5 w-5" />
                  {item.name}
                </Link>
              )
            })}
          </nav>
          <div className="px-4 py-4 border-t dark:border-gray-700">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-400 truncate">{user?.email}</span>
              <button onClick={handleLogout} className="text-gray-500 hover:text-red-600" title="Logout">
                <LogOut size={18} />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Desktop sidebar */}
      <div className="hidden lg:fixed lg:inset-y-0 lg:flex lg:w-64 lg:flex-col">
        <div className="flex flex-col flex-grow bg-white dark:bg-gray-800 border-r dark:border-gray-700">
          <div className="flex items-center h-16 px-4 border-b dark:border-gray-700">
            <span className="text-xl font-bold text-blue-600">Project Monitor</span>
          </div>
          <nav className="flex-1 px-4 py-4 space-y-1">
            {navLinks.map((item) => {
              const Icon = item.icon
              const isActive = location.pathname === item.href
              return (
                <Link
                  key={item.name}
                  to={item.href}
                  className={`flex items-center px-3 py-2 text-sm font-medium rounded-lg ${
                    isActive 
                      ? 'bg-blue-50 text-blue-600 dark:bg-blue-900/50' 
                      : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
                  }`}
                >
                  <Icon className="mr-3 h-5 w-5" />
                  {item.name}
                </Link>
              )
            })}
          </nav>
          <div className="px-4 py-4 border-t dark:border-gray-700">
            <div className="flex items-center justify-between">
              <div className="flex items-center min-w-0">
                <div className="h-8 w-8 bg-blue-600 rounded-full flex items-center justify-center text-white font-medium text-sm flex-shrink-0">
                  {user?.name?.[0]?.toUpperCase() || 'U'}
                </div>
                <div className="ml-3 min-w-0">
                  <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{user?.name}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{user?.email}</p>
                </div>
              </div>
              <button onClick={handleLogout} className="text-gray-500 hover:text-red-600 flex-shrink-0" title="Logout">
                <LogOut size={18} />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="lg:pl-64 flex flex-col flex-1">
        {/* Top bar */}
        <div className="sticky top-0 z-40 flex items-center h-16 px-4 bg-white dark:bg-gray-800 border-b dark:border-gray-700">
          <button
            onClick={() => setSidebarOpen(true)}
            className="lg:hidden text-gray-500 hover:text-gray-700"
          >
            <Menu size={24} />
          </button>
          
          <div className="flex-1 flex items-center px-4">
            <div className="relative w-full max-w-md">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={20} />
              <input
                type="text"
                placeholder="Search..."
                className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700"
              />
            </div>
          </div>

          <div className="flex items-center space-x-4">
            <button className="relative text-gray-500 hover:text-gray-700">
              <Bell size={24} />
              <span className="absolute -top-1 -right-1 h-4 w-4 bg-red-500 rounded-full text-xs text-white flex items-center justify-center">
                3
              </span>
            </button>
          </div>
        </div>

        {/* Page content */}
        <main className="flex-1 p-6">
          {children}
        </main>
      </div>
    </div>
  )
}

export default Layout
