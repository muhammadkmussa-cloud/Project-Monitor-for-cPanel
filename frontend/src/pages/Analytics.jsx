import { Line } from 'react-chartjs-2'
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend } from 'chart.js'
ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend)
import { useAuth } from '../context/AuthContext'
import { checkedFetch as fetch } from '../services/checkedFetch'
import React, { useState, useEffect } from 'react'
import { 
  BarChart3, 
  TrendingUp, 
  Activity,
  Download
} from 'lucide-react'

function Analytics() {
  const { user } = useAuth()
  const isAdmin = ['admin', 'owner'].includes(user?.role)
  const [dashboardData, setDashboardData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [timeRange, setTimeRange] = useState('7d')
  const [projects, setProjects] = useState([])
  const [selectedProject, setSelectedProject] = useState('')
  const [incidentTrend, setIncidentTrend] = useState([])
  const [healthTrend, setHealthTrend] = useState([])
  const [remediation, setRemediation] = useState(null)

  useEffect(() => {
    fetchAnalytics()
  }, [timeRange, selectedProject])

  const fetchAnalytics = async () => {
    try {
      const token = localStorage.getItem('token')
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {}
      const response = await fetch('/api/v1/analytics/dashboard', { headers })
      const data = await response.json()
      setDashboardData(data)
      const days = parseInt(timeRange, 10)
      const [projectResponse, incidentResponse, remediationResponse] = await Promise.all([
        fetch('/api/v1/projects', { headers }),
        fetch(`/api/v1/analytics/incident-trends?days=${days}`, { headers }),
        fetch(`/api/v1/analytics/remediation-stats?days=${days}`, { headers }),
      ])
      const projectData = await projectResponse.json()
      setProjects(projectData)
      if (!selectedProject && projectData.length) setSelectedProject(projectData[0].project_id)
      setIncidentTrend((await incidentResponse.json()).daily_trend || [])
      setRemediation(await remediationResponse.json())
      if (selectedProject) {
        const trend = await fetch(`/api/v1/analytics/health-trends/${selectedProject}?days=${days}`, { headers })
        setHealthTrend((await trend.json()).response_time_trend || [])
      }
    } catch (error) {
      console.error('Failed to fetch analytics:', error)
    } finally {
      setLoading(false)
    }
  }

  const exportReport = async (format) => {
    try {
      const token = localStorage.getItem('token')
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {}
      const response = await fetch(`/api/v1/reports/executive-summary/${projects.find(p => p.project_id === selectedProject)?.client_id || user.client_id}?days=${timeRange === '7d' ? 7 : timeRange === '30d' ? 30 : 90}`, { headers })
      const data = await response.json()
      
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `report-${new Date().toISOString().split('T')[0]}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      console.error('Failed to export report:', error)
    }
  }

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
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Analytics</h1>
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <select
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value)}
              className="appearance-none pl-3 pr-10 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700"
            >
              <option value="7d">Last 7 days</option>
              <option value="30d">Last 30 days</option>
              <option value="90d">Last 90 days</option>
            </select>
          </div>
          <button hidden={!isAdmin} onClick={() => exportReport('json')} className="btn-secondary">
            <Download className="mr-2 h-4 w-4 inline" />
            Export Report
          </button>
        </div>
      </div>

      {/* Overview Cards */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <div className="card">
          <div className="flex items-center">
            <div className="p-3 bg-blue-100 dark:bg-blue-900 rounded-lg">
              <Activity className="h-6 w-6 text-blue-600 dark:text-blue-400" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Avg Uptime</p>
              <p className="text-2xl font-semibold text-gray-900 dark:text-white">
                {dashboardData?.overview?.avg_uptime_percent == null ? '—' : `${dashboardData.overview.avg_uptime_percent}%`}
              </p>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center">
            <div className="p-3 bg-green-100 dark:bg-green-900 rounded-lg">
              <TrendingUp className="h-6 w-6 text-green-600 dark:text-green-400" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Projects</p>
              <p className="text-2xl font-semibold text-gray-900 dark:text-white">
                {dashboardData?.overview?.total_projects || 0}
              </p>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center">
            <div className="p-3 bg-yellow-100 dark:bg-yellow-900 rounded-lg">
              <BarChart3 className="h-6 w-6 text-yellow-600 dark:text-yellow-400" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Incidents Today</p>
              <p className="text-2xl font-semibold text-gray-900 dark:text-white">
                {dashboardData?.overview?.total_incidents_today || 0}
              </p>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center">
            <div className="p-3 bg-purple-100 dark:bg-purple-900 rounded-lg">
              <Activity className="h-6 w-6 text-purple-600 dark:text-purple-400" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Health Checks</p>
              <p className="text-2xl font-semibold text-gray-900 dark:text-white">
                {dashboardData?.overview?.total_health_checks_today || 0}
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <label className="mr-3" htmlFor="analytics-project">Project</label>
        <select id="analytics-project" className="input" value={selectedProject} onChange={e => setSelectedProject(e.target.value)}>
          {!projects.length && <option value="">No projects</option>}
          {projects.map(p => <option key={p.project_id} value={p.project_id}>{p.project_name}</option>)}
        </select>
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Trend title="Incident Trends" labels={incidentTrend.map(x => x.date)} values={incidentTrend.map(x => x.count)} />
        <Trend title="Response Time (ms)" labels={healthTrend.map(x => x.date)} values={healthTrend.map(x => x.response_time_ms)} />
        <Trend title="Healthy Checks (%)" labels={healthTrend.map(x => x.date)} values={healthTrend.map(x => x.healthy_percent)} />
        <div className="card">
          <h2 className="text-lg font-semibold mb-4">Remediation Results</h2>
          <p>Completed: {remediation?.successful ?? '—'}</p>
          <p>Failed: {remediation?.failed ?? '—'}</p>
          <p>Rolled back: {remediation?.rolled_back ?? '—'}</p>
        </div>
      </div>

      {/* System Health */}
      <div className="card">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">System Health</h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {Object.entries(dashboardData?.system_health || {}).map(([service, status]) => (
            <div key={service} className="text-center p-4 bg-gray-50 dark:bg-gray-700 rounded-lg">
              <div className={`mx-auto h-3 w-3 rounded-full mb-2 ${
                status === 'healthy' ? 'bg-green-500' : 'bg-red-500'
              }`} />
              <p className="text-sm font-medium text-gray-900 dark:text-white capitalize">
                {service.replace(/_/g, ' ')}
              </p>
              <p className={`text-xs ${
                status === 'healthy' ? 'text-green-600' : 'text-red-600'
              }`}>
                {status}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default Analytics

function Trend({ title, labels, values }) {
  return <div className="card"><h2 className="text-lg font-semibold mb-4">{title}</h2>
    <div className="h-64">{labels.length ? <Line data={{ labels, datasets: [{ label: title, data: values, borderColor: '#2563eb', tension: 0.15 }] }}
      options={{ maintainAspectRatio: false, scales: { y: { beginAtZero: true } } }} /> : <p className="text-gray-500">No recorded data for this period.</p>}</div>
  </div>
}
