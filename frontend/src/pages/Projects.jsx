import MonitoringPanel from '../components/MonitoringPanel'
import { useAuth } from '../context/AuthContext'
import { checkedFetch as fetch } from '../services/checkedFetch'
import React, { useState, useEffect } from 'react'
import {
  Plus, Search, Filter, Globe, Server, Activity, X, RefreshCw,
  KeyRound, Eye, Database, Terminal, CheckCircle2, AlertTriangle, Info, Bug, ScanSearch
} from 'lucide-react'

function Projects() {
  const { user } = useAuth()
  const isAdmin = ['admin', 'owner'].includes(user?.role)
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [showModal, setShowModal] = useState(false)
  const [detail, setDetail] = useState(null)
  const [newProject, setNewProject] = useState(emptyProject())

  function emptyProject() {
    return {
      project_name: '', domain: '', server_host: '', ssh_username: '',
      ssh_port: 22, project_path: '', health_check_url: '', application_type: 'wordpress',
      connection_type: 'ssh', monitoring_enabled: true, check_interval: 300
    }
  }

  const authHeaders = () => {
    const token = localStorage.getItem('token')
    return token ? { 'Authorization': `Bearer ${token}` } : {}
  }

  const fetchProjects = async () => {
    try {
      const response = await fetch('/api/v1/projects', { headers: authHeaders() })
      const data = await response.json()
      setProjects(data)
    } catch (error) {
      console.error('Failed to fetch projects:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchProjects() }, [])

  const handleCreateProject = async (e) => {
    e.preventDefault()
    try {
      const response = await fetch('/api/v1/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ ...newProject, client_id: '00000000-0000-0000-0000-000000000001' })
      })
      if (response.ok) {
        setShowModal(false)
        setNewProject(emptyProject())
        fetchProjects()
      }
    } catch (error) {
      console.error('Failed to create project:', error)
    }
  }

  const filteredProjects = projects.filter(project =>
    project.project_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    project.domain?.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const getStatusColor = (status) => {
    switch (status) {
      case 'HEALTHY': return 'bg-green-100 text-green-800'
      case 'DEGRADED': return 'bg-yellow-100 text-yellow-800'
      case 'DOWN': return 'bg-red-100 text-red-800'
      default: return 'bg-gray-100 text-gray-800'
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
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Projects</h1>
        <button hidden={!isAdmin} onClick={() => setShowModal(true)} className="btn-primary">
          <Plus className="mr-2 h-4 w-4 inline" /> Add Project
        </button>
      </div>

      <div className="card">
        <div className="flex items-center space-x-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={20} />
            <input type="text" placeholder="Search projects..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700" />
          </div>
        </div>
      </div>

      {filteredProjects.length === 0 ? (
        <div className="card text-center py-12">
          <Globe className="mx-auto h-12 w-12 text-gray-400 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">No projects yet</h3>
          <p className="text-gray-500 mb-4">Get started by adding your first project</p>
          <button hidden={!isAdmin} onClick={() => setShowModal(true)} className="btn-primary">
            <Plus className="mr-2 h-4 w-4 inline" /> Add Project
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {filteredProjects.map((project) => (
            <div key={project.project_id} className="card hover:shadow-lg transition-shadow">
              <div className="flex items-start justify-between">
                <div className="flex items-center">
                  <div className="p-3 bg-blue-100 dark:bg-blue-900 rounded-lg">
                    <Globe className="h-6 w-6 text-blue-600 dark:text-blue-400" />
                  </div>
                  <div className="ml-4">
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{project.project_name}</h3>
                    <p className="text-sm text-gray-500">{project.domain || 'No domain'}</p>
                  </div>
                </div>
              </div>

              <div className="mt-4 space-y-1.5 text-sm text-gray-600 dark:text-gray-400">
                <div className="flex items-center"><Server className="mr-2 h-4 w-4" />{project.server_host || 'No server'}</div>
                <div className="flex items-center"><Activity className="mr-2 h-4 w-4" />{project.application_type}</div>
              </div>

              <div className="mt-4 flex items-center justify-between">
                <span className={`px-2 py-1 text-xs font-semibold rounded-full ${getStatusColor(project.current_status)}`}>
                  {project.current_status || 'UNKNOWN'}
                </span>
                <button onClick={() => setDetail(project)}
                  className="text-blue-600 hover:text-blue-700 text-sm font-medium inline-flex items-center">
                  <Eye className="mr-1 h-4 w-4" /> Details
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add Project Modal */}
      {showModal && (
        <Modal onClose={() => setShowModal(false)} title="Add New Project">
          <form onSubmit={handleCreateProject} className="space-y-4">
            <Field label="Project Name"><input required type="text"
              value={newProject.project_name}
              onChange={(e) => setNewProject({ ...newProject, project_name: e.target.value })} className="input" placeholder="My cPanel Site" /></Field>
            <Field label="Domain / URL"><input type="text"
              value={newProject.domain}
              onChange={(e) => setNewProject({ ...newProject, domain: e.target.value })} className="input" placeholder="example.com" /></Field>
            <Field label="Health Check URL (optional)"><input type="text"
              value={newProject.health_check_url}
              onChange={(e) => setNewProject({ ...newProject, health_check_url: e.target.value })} className="input" placeholder="https://example.com/health" /></Field>

            <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">SSH Access (for server stats/logs/git)</p>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Server Host"><input type="text"
                  value={newProject.server_host}
                  onChange={(e) => setNewProject({ ...newProject, server_host: e.target.value })} className="input" placeholder="server.example.com" /></Field>
                <Field label="SSH Port"><input type="number"
                  value={newProject.ssh_port}
                  onChange={(e) => setNewProject({ ...newProject, ssh_port: parseInt(e.target.value) || 22 })} className="input" /></Field>
                <Field label="SSH Username"><input type="text"
                  value={newProject.ssh_username}
                  onChange={(e) => setNewProject({ ...newProject, ssh_username: e.target.value })} className="input" placeholder="cpaneluser" /></Field>
              </div>
              <Field label="Project Path (e.g. /home/user/domains/site/public_html)"><input type="text"
                value={newProject.project_path}
                onChange={(e) => setNewProject({ ...newProject, project_path: e.target.value })} className="input" placeholder="/home/user/domains/site" /></Field>
            </div>

            <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Connection & Monitoring</p>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Connection Type">
                  <select value={newProject.connection_type}
                    onChange={(e) => setNewProject({ ...newProject, connection_type: e.target.value })} className="input">
                    <option value="ssh">SSH</option>
                    <option value="sftp">SFTP</option>
                  </select>
                </Field>
                <Field label="Check Interval (seconds)">
                  <input type="number"
                    value={newProject.check_interval}
                    onChange={(e) => setNewProject({ ...newProject, check_interval: parseInt(e.target.value) || 300 })} className="input" />
                </Field>
              </div>
              <div className="mt-3 flex items-center justify-between">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Monitoring enabled</label>
                <button type="button" onClick={() => setNewProject({ ...newProject, monitoring_enabled: !newProject.monitoring_enabled })}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full ${newProject.monitoring_enabled ? 'bg-blue-600' : 'bg-gray-200 dark:bg-gray-700'}`}>
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${newProject.monitoring_enabled ? 'translate-x-6' : 'translate-x-1'}`} />
                </button>
              </div>
            </div>

            <Field label="Application Type">
              <select value={newProject.application_type}
                onChange={(e) => setNewProject({ ...newProject, application_type: e.target.value })} className="input">
                <option value="wordpress">WordPress</option>
                <option value="php">PHP</option>
                <option value="laravel">Laravel</option>
                <option value="nodejs">Node.js</option>
                <option value="python">Python</option>
                <option value="static">Static Site</option>
                <option value="api">API Service</option>
                <option value="other">Other</option>
              </select>
            </Field>

            <div className="flex justify-end space-x-3 mt-6">
              <button type="button" onClick={() => setShowModal(false)} className="btn-secondary">Cancel</button>
              <button type="submit" className="btn-primary">Create Project</button>
            </div>
          </form>
        </Modal>
      )}

      {detail && <ProjectDetail project={detail} authHeaders={authHeaders} onClose={() => setDetail(null)}
        onRefresh={fetchProjects} />}
    </div>
  )
}

function Modal({ title, onClose, children, wide }) {
  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-start justify-center min-h-screen px-4 pt-10 pb-20 text-center sm:block sm:p-0">
        <div className="fixed inset-0 transition-opacity bg-gray-500 bg-opacity-75" onClick={onClose} />
        <div className={`inline-block w-full ${wide ? 'max-w-3xl' : 'max-w-md'} p-6 my-8 overflow-hidden text-left align-middle transition-all transform bg-white dark:bg-gray-800 shadow-xl rounded-lg`}>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h3>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={20} /></button>
          </div>
          {children}
        </div>
      </div>
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{label}</label>
      {children}
    </div>
  )
}

function StatBox({ label, value }) {
  return (
    <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3 text-center">
      <div className="text-sm text-gray-500">{label}</div>
      <div className="text-lg font-semibold text-gray-900 dark:text-white">{value}</div>
    </div>
  )
}

function FieldRow({ label, value }) {
  return (
    <div className="flex items-center justify-between border-b border-gray-100 dark:border-gray-700/60 py-1.5">
      <span className="text-gray-500">{label}</span>
      <span className="font-medium text-gray-900 dark:text-white text-right break-words">{value || '—'}</span>
    </div>
  )
}

function ProjectDetail({ project, authHeaders, onClose, onRefresh }) {
  const { user } = useAuth()
  const isAdmin = ['admin', 'owner'].includes(user?.role)
  const [tab, setTab] = useState('health')
  const [health, setHealth] = useState(null)
  const [stats, setStats] = useState(null)
  const [logs, setLogs] = useState([])
  const [errors, setErrors] = useState([])
  const [scanMsg, setScanMsg] = useState('')
  const [busy, setBusy] = useState('')
  const [lastChecked, setLastChecked] = useState(null)
  const [message, setMessage] = useState('')
  const [creds, setCreds] = useState([])
  const [credForm, setCredForm] = useState({ credential_type: 'ssh', host: '', port: 22, username: '', key_path: '', password: '' })

  const pid = project.project_id

  const load = async () => {
    setCreds(await safeGet(`/api/v1/projects/${pid}/credentials`))
    if (tab === 'health' || tab === 'stats') {
      const h = await safeGet(`/api/v1/projects/${pid}/health`)
      if (h) { setHealth(h); setLastChecked(new Date()) }
    }
    if (tab === 'stats') {
      const s = await safeGet(`/api/v1/projects/${pid}/server-stats`)
      if (s) setStats(s)
    }
    if (tab === 'logs') {
      const l = await safeGet(`/api/v1/projects/${pid}/logs?lines=50`)
      if (l) setLogs(l)
    }
    if (tab === 'errors') {
      const e = await safeGet(`/api/v1/projects/${pid}/errors?lines=100`)
      if (e) setErrors(e)
    }
  }

  const runErrorScan = async () => {
    if (busy) return
    setBusy('Scanning...')
    setScanMsg('')
    try {
      const r = await fetch(`/api/v1/projects/${pid}/scan-errors`, { method: 'POST', headers: authHeaders() })
      const res = await r.json()
      if (res && res.success) {
        if (!res.found) setScanMsg('No application error log found (logs may not be enabled for this site).')
        else if (res.created > 0) setScanMsg(`Detected ${res.created} new error(s). Incidents created.`)
        else setScanMsg(`No new errors. ${res.entries} recent error line(s) already known.`)
      }
      const e = await safeGet(`/api/v1/projects/${pid}/errors?lines=100`)
      if (e) setErrors(e)
    } catch { setScanMsg('Scan failed.') }
    setBusy('')
  }

  const safeGet = async (url) => {
    try { const r = await fetch(url, { headers: authHeaders() }); return await r.json() } catch { return null }
  }

  useEffect(() => { load(); }, [tab, pid])

  const switchTab = (t) => { setTab(t); }

  const runHealthCheck = async () => {
    if (busy) return
    setBusy('Checking...')
    try {
      const r = await fetch(`/api/v1/projects/${pid}/health`, { headers: authHeaders() })
      const h = await r.json()
      setHealth(h)
      setLastChecked(new Date())
      if (h && h.status !== 'HEALTHY' && h.status !== 'DEGRADED') {
        setMessage('Health check failed')
        setTimeout(() => setMessage(''), 4000)
      }
    } catch (e) {
      setHealth(null)
      setMessage('Health check failed')
      setTimeout(() => setMessage(''), 4000)
    }
    setBusy('')
  }

  const runConnectionTest = async () => {
    setBusy('Testing connection...')
    try {
      const r = await fetch(`/api/v1/projects/${pid}/test-connection`, { method: 'POST', headers: authHeaders() })
      const d = await r.json()
      setMessage(d.success ? `Connected: ${d.os_info || ''}` : `Failed: ${d.message || ''}`)
    } catch (e) { setMessage(e.message) }
    finally { setBusy('') }
  }


  const saveCredential = async () => {
    setBusy('Saving credential...')
    try {
      const body = { ...credForm }
      if (body.password === '') delete body.password
      const r = await fetch(`/api/v1/projects/${pid}/credentials`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify(body)
      })
      if (r.ok) {
        setCredForm({ credential_type: 'ssh', host: '', port: 22, username: '', key_path: '', password: '' })
        setCreds(await safeGet(`/api/v1/projects/${pid}/credentials`))
      } else { alert('Failed to save credential') }
    } catch { alert('Failed to save credential') }
    setBusy('')
  }

  const removeCredential = async (cid) => {
    await fetch(`/api/v1/projects/${pid}/credentials/${cid}`, { method: 'DELETE', headers: authHeaders() })
    setCreds(await safeGet(`/api/v1/projects/${pid}/credentials`))
  }

  const tabs = [
    { id: 'health', label: 'Health', icon: Activity },
    { id: 'overview', label: 'Overview', icon: Info },
    { id: 'stats', label: 'Server Stats', icon: Server },
    { id: 'credentials', label: 'SSH Credentials', icon: KeyRound },
    { id: 'logs', label: 'Logs', icon: Terminal },
    { id: 'errors', label: 'Errors', icon: Bug },
  ].filter(tab => isAdmin || ['health', 'overview'].includes(tab.id))

  return (
    <Modal onClose={onClose} title={project.project_name} wide>
      <div className="flex space-x-1 border-b border-gray-200 dark:border-gray-700 mb-4">
        {tabs.map(t => (
          <button key={t.id} onClick={() => switchTab(t.id)}
            className={`px-3 py-2 text-sm font-medium ${tab === t.id ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}>
            <t.icon className="inline mr-1 h-4 w-4" />{t.label}
          </button>
        ))}
      </div>

      {tab === 'health' && isAdmin && <MonitoringPanel projectId={pid} />}
      {tab === 'health' && (
        <div>
          <div className="grid grid-cols-4 gap-3 mb-4">
            <StatBox label="Status" value={health?.status || '—'} />
            <StatBox label="HTTP" value={health?.http_status_code ?? '—'} />
            <StatBox label="Response" value={health?.response_time_ms ? `${health.response_time_ms}ms` : '—'} />
            <StatBox label="SSL" value={health?.ssl_days_remaining != null ? `${health.ssl_days_remaining}d` : '—'} />
          </div>
          <div className="flex items-center justify-between flex-wrap gap-3">
            {message && <span className="text-sm text-red-600 dark:text-red-400">{message}</span>}
            {!message && lastChecked && (
              <span className="text-sm text-gray-500">Last checked: {lastChecked.toLocaleTimeString()}</span>
            )}
            <button onClick={runHealthCheck} disabled={!!busy} className="btn-secondary inline-flex items-center">
              {busy === 'Checking...'
                ? <><RefreshCw className="mr-1 h-4 w-4 animate-spin" /> Checking...</>
                : <><RefreshCw className="mr-1 h-4 w-4" /> Run Health Check</>}
            </button>
          </div>
        </div>
      )}

      {tab === 'overview' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <FieldRow label="Project Name" value={project.project_name} />
          <FieldRow label="Domain" value={project.domain} />
          <FieldRow label="Server Host" value={project.server_host} />
          <FieldRow label="SSH Username" value={project.ssh_username} />
          <FieldRow label="SSH Port" value={project.ssh_port} />
          <FieldRow label="Connection Type" value={project.connection_type} />
          <FieldRow label="Project Path" value={project.project_path} />
          <FieldRow label="Health Check URL" value={project.health_check_url} />
          <FieldRow label="Application Type" value={project.application_type} />
          <FieldRow label="Framework" value={project.framework} />
          <FieldRow label="Environment" value={project.environment} />
          <FieldRow label="Check Interval" value={project.check_interval ? `${project.check_interval}s` : ''} />
          <FieldRow label="Monitoring Enabled" value={project.monitoring_enabled ? 'Yes' : 'No'} />
          <FieldRow label="Status" value={project.current_status} />
          <FieldRow label="Created" value={project.created_at ? new Date(project.created_at).toLocaleString() : ''} />
          <FieldRow label="Last Check" value={project.last_check_at ? new Date(project.last_check_at).toLocaleString() : ''} />
        </div>
      )}

      {tab === 'stats' && stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <StatBox label="CPU" value={`${stats.cpu_percent}%`} />
          <StatBox label="Memory" value={`${stats.memory_percent}%`} />
          <StatBox label="Disk" value={`${stats.disk_percent}%`} />
          <StatBox label="Load" value={stats.load_average?.join(' ') || '—'} />
          <StatBox label="Uptime" value={stats.uptime ? `${Math.round(stats.uptime / 86400)}d` : '—'} />
        </div>
      )}
      {tab === 'stats' && !stats && <p className="text-gray-500 text-sm">Add SSH credentials and open Server Stats to load live metrics.</p>}

      {tab === 'credentials' && (
        <div className="space-y-4">
          {creds.length > 0 && (
            <div className="space-y-2">
              {creds.map(c => (
                <div key={c.credential_id} className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-semibold text-gray-900 dark:text-white">{c.name} <span className="text-gray-400 font-normal">({c.type})</span></span>
                    <button onClick={() => removeCredential(c.credential_id)} className="text-red-500 text-xs font-medium">Delete</button>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 text-sm">
                    <FieldRow label="Host" value={c.host} />
                    <FieldRow label="Port" value={c.port} />
                    <FieldRow label="Username" value={c.username} />
                    <FieldRow label="Auth Method" value={c.has_password ? 'Password' : c.has_private_key ? 'Private key' : c.key_path ? 'Key file' : '—'} />
                    <FieldRow label="Key File Path" value={c.key_path} />
                  </div>
                </div>
              ))}
            </div>
          )}
          {creds.length === 0 && (
            <p className="text-sm text-gray-500">No SSH credentials stored yet. Add one below.</p>
          )}
          <div className="border-t border-gray-200 dark:border-gray-700 pt-3 space-y-3">
            <p className="text-sm font-medium">Add SSH credential</p>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Host"><input value={credForm.host} onChange={e => setCredForm({ ...credForm, host: e.target.value })} className="input" placeholder="server.example.com" /></Field>
              <Field label="Port"><input type="number" value={credForm.port} onChange={e => setCredForm({ ...credForm, port: parseInt(e.target.value) || 22 })} className="input" /></Field>
              <Field label="Username"><input value={credForm.username} onChange={e => setCredForm({ ...credForm, username: e.target.value })} className="input" placeholder="cpaneluser" /></Field>
              <Field label="Key file path (in agent)"><input value={credForm.key_path} onChange={e => setCredForm({ ...credForm, key_path: e.target.value })} className="input" placeholder="/keys/directadmin_deploy" /></Field>
            </div>
            <Field label="Password (alternative)"><input type="password" value={credForm.password} onChange={e => setCredForm({ ...credForm, password: e.target.value })} className="input" placeholder="or SSH password" /></Field>
            <div className="flex gap-3">
              <button onClick={saveCredential} disabled={!!busy} className="btn-primary inline-flex items-center"><KeyRound className="mr-1 h-4 w-4" /> Save Credential</button>
              <button onClick={runConnectionTest} disabled={!!busy} className="btn-secondary inline-flex items-center"><CheckCircle2 className="mr-1 h-4 w-4" /> Test Connection</button>
            </div>
            {busy && <p className="text-sm text-blue-600">{busy}</p>}
          </div>
        </div>
      )}

      {tab === 'logs' && (
        <div className="bg-black text-green-400 rounded-lg p-3 font-mono text-xs max-h-72 overflow-auto space-y-1">
          {logs.length === 0 ? <p className="text-gray-500">No log entries found (or logs not accessible via SSH).</p>
            : logs.map((l, i) => <div key={i}><span className="text-blue-300">[{l.level}]</span> {l.message}</div>)}
        </div>
      )}

      {tab === 'errors' && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            {scanMsg && <p className="text-sm text-gray-500">{scanMsg}</p>}
            <button onClick={runErrorScan} disabled={!!busy} className="btn-secondary inline-flex items-center ml-auto">
              {busy === 'Scanning...' ? <><ScanSearch className="mr-1 h-4 w-4 animate-spin" /> Scanning...</>
                : <><ScanSearch className="mr-1 h-4 w-4" /> Scan for Errors</>}
            </button>
          </div>
          <div className="bg-red-950/40 rounded-lg p-3 font-mono text-xs max-h-72 overflow-auto space-y-1">
            {errors.length === 0 ? (
              <p className="text-gray-400">No application errors detected. This site is static HTML (no PHP/error log) or errors have not been logged.</p>
            ) : errors.map((l, i) => (
              <div key={i} className="flex"><AlertTriangle className="mr-2 h-3.5 w-3.5 text-red-400 shrink-0 mt-0.5" /><span className="text-red-200 break-all">{l.message}</span></div>
            ))}
          </div>
        </div>
      )}
    </Modal>
  )
}

export default Projects
