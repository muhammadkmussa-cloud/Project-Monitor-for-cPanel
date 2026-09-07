import { useAuth } from '../context/AuthContext'
import { checkedFetch as fetch } from '../services/checkedFetch'
import React, { useState, useEffect, useCallback } from 'react'
import { 
  FolderOpen, 
  AlertTriangle, 
  CheckCircle, 
  Activity,
  TrendingUp,
  Clock,
  RefreshCw,
  Play,
  XCircle,
  Zap
} from 'lucide-react'

function Dashboard() {
  const { user } = useAuth()
  const isAdmin = ['admin', 'owner'].includes(user?.role)
  const [stats, setStats] = useState({
    totalProjects: 0,
    activeIncidents: 0,
    resolvedToday: 0,
    uptime: '—'
  })
  const [incidents, setIncidents] = useState([])
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [scanMessage, setScanMessage] = useState('')
  const [actionLoading, setActionLoading] = useState(null)

  const fetchDashboardData = useCallback(async () => {
    try {
      const token = localStorage.getItem('token')
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {}
      const [analyticsRes, incidentsRes] = await Promise.all([
        fetch('/api/v1/analytics/dashboard', { headers }),
        fetch('/api/v1/incidents?limit=20', { headers })
      ])
      
      const analyticsData = await analyticsRes.json()
      const incidentsData = await incidentsRes.json()
      
      setStats({
        totalProjects: analyticsData.overview?.total_projects || 0,
        activeIncidents: analyticsData.overview?.open_incidents || 0,
        resolvedToday: analyticsData.overview?.resolved_incidents_today || 0,
        uptime: analyticsData.overview?.avg_uptime_percent ?? '—'
      })
      setIncidents(Array.isArray(incidentsData) ? incidentsData : [])
    } catch (error) {
      console.error('Failed to fetch dashboard data:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchDashboardData()
    const interval = setInterval(fetchDashboardData, 30000)
    return () => clearInterval(interval)
  }, [fetchDashboardData])

  const handleTriggerScan = async () => {
    setScanning(true)
    setScanMessage('')
    try {
      const token = localStorage.getItem('token')
      const headers = { 'Content-Type': 'application/json', ...(token ? { 'Authorization': `Bearer ${token}` } : {}) }
      const res = await fetch('/api/v1/trigger-scan', { method: 'POST', headers })
      const data = await res.json()
      setScanMessage(data.message || 'Scan triggered!')
      setTimeout(() => {
        fetchDashboardData()
        setScanMessage('')
      }, 5000)
    } catch (error) {
      setScanMessage('Failed to trigger scan')
    } finally {
      setScanning(false)
    }
  }

  const handleApprove = async (incidentId) => {
    setActionLoading(incidentId)
    try {
      const token = localStorage.getItem('token')
      const headers = { 'Content-Type': 'application/json', ...(token ? { 'Authorization': `Bearer ${token}` } : {}) }
      await fetch(`/api/v1/incidents/${incidentId}/approve`, { method: 'POST', headers })
      fetchDashboardData()
    } catch (error) {
      console.error('Failed to approve:', error)
    } finally {
      setActionLoading(null)
    }
  }

  const handleReject = async (incidentId) => {
    setActionLoading(incidentId)
    try {
      const token = localStorage.getItem('token')
      const headers = { 'Content-Type': 'application/json', ...(token ? { 'Authorization': `Bearer ${token}` } : {}) }
      await fetch(`/api/v1/incidents/${incidentId}/reject`, { 
        method: 'POST',
        headers,
        body: JSON.stringify({ reason: 'Rejected from dashboard' })
      })
      fetchDashboardData()
    } catch (error) {
      console.error('Failed to reject:', error)
    } finally {
      setActionLoading(null)
    }
  }

  const statCards = [
    { name: 'Total Projects', value: stats.totalProjects, icon: FolderOpen, color: 'bg-blue-500' },
    { name: 'Active Incidents', value: stats.activeIncidents, icon: AlertTriangle, color: 'bg-red-500' },
    { name: 'Resolved Today', value: stats.resolvedToday, icon: CheckCircle, color: 'bg-green-500' },
    { name: 'Uptime', value: stats.uptime === '—' ? '—' : `${stats.uptime}%`, icon: Activity, color: 'bg-purple-500' },
  ]

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
        <div className="flex items-center space-x-4">
          <button
            onClick={handleTriggerScan}
            disabled={scanning || !isAdmin}
            className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {scanning ? (
              <>
                <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                Scanning...
              </>
            ) : (
              <>
                <Play className="mr-2 h-4 w-4" />
                Run Health Check
              </>
            )}
          </button>
          <div className="flex items-center space-x-2 text-sm text-gray-500">
            <Clock size={16} />
            <span>Last updated: {new Date().toLocaleTimeString()}</span>
          </div>
        </div>
      </div>

      {scanMessage && (
        <div className="bg-blue-50 border border-blue-200 text-blue-700 px-4 py-3 rounded-lg flex items-center">
          <Zap className="mr-2 h-4 w-4" />
          {scanMessage}
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {statCards.map((stat) => {
          const Icon = stat.icon
          return (
            <div key={stat.name} className="card">
              <div className="flex items-center">
                <div className={`${stat.color} p-3 rounded-lg`}>
                  <Icon className="h-6 w-6 text-white" />
                </div>
                <div className="ml-4">
                  <p className="text-sm font-medium text-gray-500 dark:text-gray-400">{stat.name}</p>
                  <p className="text-2xl font-semibold text-gray-900 dark:text-white">{stat.value}</p>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* No Projects Empty State */}
      {stats.totalProjects === 0 && (
        <div className="card text-center py-12">
          <FolderOpen className="mx-auto h-12 w-12 text-gray-400 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">No projects yet</h3>
          <p className="text-gray-500 mb-4">Create your first project to get started.</p>
          <a href="/projects" className="btn-primary inline-flex items-center">
            <FolderOpen className="mr-2 h-4 w-4" />
            Add Project
          </a>
        </div>
      )}

      {/* Incidents Table */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Incidents</h2>
          <a href="/incidents" className="text-blue-600 hover:text-blue-700 text-sm font-medium">
            View all
          </a>
        </div>
        
        {incidents.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <CheckCircle className="mx-auto h-12 w-12 text-green-500 mb-4" />
            <p>No incidents found</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead>
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Incident
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Severity
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Created
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {incidents.map((incident) => (
                  <tr key={incident.incident_id}>
                    <td className="px-4 py-4 whitespace-nowrap">
                      <div className="text-sm font-medium text-gray-900 dark:text-white">
                        {incident.error_signature || incident.category || 'Unknown'}
                      </div>
                      <div className="text-sm text-gray-500">{incident.affected_component}</div>
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap">
                      <span className={`px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${
                        incident.severity === 'CRITICAL' ? 'bg-red-100 text-red-800' :
                        incident.severity === 'HIGH' ? 'bg-orange-100 text-orange-800' :
                        incident.severity === 'MEDIUM' ? 'bg-yellow-100 text-yellow-800' :
                        'bg-green-100 text-green-800'
                      }`}>
                        {incident.severity}
                      </span>
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap">
                      <span className={`px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${
                        incident.status === 'OPEN' ? 'bg-red-100 text-red-800' :
                        incident.status === 'INVESTIGATING' ? 'bg-yellow-100 text-yellow-800' :
                        incident.status === 'RESOLVED' ? 'bg-green-100 text-green-800' :
                        incident.status === 'REJECTED' ? 'bg-gray-100 text-gray-800' :
                        'bg-blue-100 text-blue-800'
                      }`}>
                        {incident.status}
                      </span>
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(incident.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap text-sm font-medium">
                      {incident.status === 'OPEN' && (
                        <div className="flex space-x-2">
                          <button
                            onClick={() => handleApprove(incident.incident_id)}
                            disabled={!isAdmin || actionLoading === incident.incident_id}
                            className="text-green-600 hover:text-green-900 disabled:opacity-50"
                            title="Approve fix"
                          >
                            <CheckCircle className="h-5 w-5" />
                          </button>
                          <button
                            onClick={() => handleReject(incident.incident_id)}
                            disabled={!isAdmin || actionLoading === incident.incident_id}
                            className="text-red-600 hover:text-red-900 disabled:opacity-50"
                            title="Reject fix"
                          >
                            <XCircle className="h-5 w-5" />
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Quick Actions */}
      <div className="card">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <button 
            onClick={handleTriggerScan}
            disabled={scanning || !isAdmin}
            className="btn-primary flex items-center justify-center"
          >
            <Play className="mr-2 h-4 w-4" />
            {scanning ? 'Scanning...' : 'Run Health Check'}
          </button>
          <a href="/projects" className="btn-secondary flex items-center justify-center">
            <FolderOpen className="mr-2 h-4 w-4" />
            Add Project
          </a>
          <a href="/analytics" className="btn-secondary flex items-center justify-center">
            <TrendingUp className="mr-2 h-4 w-4" />
            View Analytics
          </a>
          <a href="/incidents" className="btn-secondary flex items-center justify-center">
            <AlertTriangle className="mr-2 h-4 w-4" />
            View Incidents
          </a>
        </div>
      </div>
    </div>
  )
}

export default Dashboard
