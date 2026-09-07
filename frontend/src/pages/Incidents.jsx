import { useAuth } from '../context/AuthContext'
import { checkedFetch as fetch } from '../services/checkedFetch'
import React, { useState, useEffect } from 'react'
import {
  AlertTriangle, Search, Filter, CheckCircle, Clock, XCircle,
  ChevronDown, Eye, RefreshCw, ThumbsUp, ThumbsDown, Check, X, Loader
} from 'lucide-react'

function Incidents() {
  const { user } = useAuth()
  const isAdmin = ['admin', 'owner'].includes(user?.role)
  const [incidents, setIncidents] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [severityFilter, setSeverityFilter] = useState('all')
  const [detail, setDetail] = useState(null)

  const authHeaders = () => {
    const token = localStorage.getItem('token')
    return token ? { 'Authorization': `Bearer ${token}` } : {}
  }

  const fetchIncidents = async () => {
    try {
      const response = await fetch('/api/v1/incidents', { headers: authHeaders() })
      const data = await response.json()
      setIncidents(data)
    } catch (error) {
      console.error('Failed to fetch incidents:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchIncidents() }, [])

  const act = async (id, action) => {
    try {
      await fetch(`/api/v1/incidents/${id}/${action}`, { method: 'POST', headers: authHeaders() })
      fetchIncidents()
      if (detail) { setDetail(d => d && d.incident_id === id ? { ...d } : d); loadDetail(id) }
    } catch (e) { console.error(e) }
  }

  const loadDetail = async (id) => {
    const r = await fetch(`/api/v1/incidents/${id}`, { headers: authHeaders() })
    const inc = await r.json()
    const d = await fetch(`/api/v1/incidents/${id}/diagnosis`, { headers: authHeaders() })
    inc.diagnosis = await d.json()
    setDetail(inc)
  }

  const openDetail = async (inc) => { await loadDetail(inc.incident_id) }

  const filteredIncidents = incidents.filter(incident => {
    const matchesSearch =
      (incident.error_signature || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
      (incident.category || '').toLowerCase().includes(searchTerm.toLowerCase())
    const matchesStatus = statusFilter === 'all' || incident.status === statusFilter
    const matchesSeverity = severityFilter === 'all' || incident.severity === severityFilter
    return matchesSearch && matchesStatus && matchesSeverity
  })

  const sevColor = (s) => ({ CRITICAL: 'bg-red-100 text-red-800', HIGH: 'bg-orange-100 text-orange-800', MEDIUM: 'bg-yellow-100 text-yellow-800', LOW: 'bg-green-100 text-green-800' }[s] || 'bg-gray-100 text-gray-800')
  const stColor = (s) => ({ OPEN: 'bg-red-100 text-red-800', INVESTIGATING: 'bg-yellow-100 text-yellow-800', RESOLVED: 'bg-green-100 text-green-800', APPROVED: 'bg-blue-100 text-blue-800', IGNORED: 'bg-gray-100 text-gray-800' }[s] || 'bg-gray-100 text-gray-800')

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
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Incidents</h1>
        <div className="flex items-center space-x-2 text-sm text-gray-500">
          <span className="px-2 py-1 bg-red-100 text-red-800 rounded-full">{incidents.filter(i => i.status === 'OPEN').length} Open</span>
        </div>
      </div>

      <div className="card">
        <div className="flex flex-wrap items-center gap-4">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={20} />
            <input type="text" placeholder="Search incidents..." value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700" />
          </div>
          <Select value={statusFilter} onChange={setStatusFilter} options={[['all','All Status'],['OPEN','Open'],['INVESTIGATING','In Progress'],['APPROVED','Approved'],['IGNORED','Ignored'],['RESOLVED','Resolved']]} />
          <Select value={severityFilter} onChange={setSeverityFilter} options={[['all','All Severity'],['CRITICAL','Critical'],['HIGH','High'],['MEDIUM','Medium'],['LOW','Low']]} />
        </div>
      </div>

      {filteredIncidents.length === 0 ? (
        <div className="card text-center py-12">
          <CheckCircle className="mx-auto h-12 w-12 text-green-500 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">No incidents found</h3>
          <p className="text-gray-500">{incidents.length === 0 ? 'No incidents have been recorded yet' : 'No incidents match your filters'}</p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredIncidents.map((incident) => (
            <div key={incident.incident_id} className="card">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{incident.error_signature || 'Unknown Error'}</h3>
                  <p className="text-sm text-gray-500 mt-1">{incident.category} {incident.affected_component && `• ${incident.affected_component}`}</p>
                </div>
                <div className="flex items-center space-x-2">
                  <span className={`px-2 py-1 text-xs font-semibold rounded-full ${sevColor(incident.severity)}`}>{incident.severity}</span>
                  <span className={`px-2 py-1 text-xs font-semibold rounded-full ${stColor(incident.status)}`}>{incident.status}</span>
                </div>
              </div>
              <div className="mt-3 flex items-center justify-between text-sm text-gray-500">
                <span>Occurrences: {incident.occurrence_count || 1} • First seen: {incident.first_seen ? new Date(incident.first_seen).toLocaleString() : ''}</span>
                <div className="flex items-center space-x-2">
                  {isAdmin && ['OPEN', 'INVESTIGATING', 'AWAITING_APPROVAL'].includes(incident.status) && (
                    <>
                      <button onClick={() => act(incident.incident_id, 'approve')} className="inline-flex items-center text-xs font-medium text-blue-600 hover:text-blue-700"><ThumbsUp className="mr-1 h-3.5 w-3.5" />Approve</button>
                      <button onClick={() => act(incident.incident_id, 'reject')} className="inline-flex items-center text-xs font-medium text-gray-500 hover:text-gray-700"><ThumbsDown className="mr-1 h-3.5 w-3.5" />Reject</button>
                    </>
                  )}
                  {isAdmin && incident.status !== 'RESOLVED' && incident.status !== 'IGNORED' && (
                    <button onClick={() => act(incident.incident_id, 'resolve')} className="inline-flex items-center text-xs font-medium text-green-600 hover:text-green-700"><Check className="mr-1 h-3.5 w-3.5" />Resolve</button>
                  )}
                  <button onClick={() => openDetail(incident)} className="inline-flex items-center text-xs font-medium text-blue-600 hover:text-blue-700"><Eye className="mr-1 h-3.5 w-3.5" />Details</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {detail && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex items-start justify-center min-h-screen px-4 pt-10 pb-20">
            <div className="fixed inset-0 bg-gray-500 bg-opacity-75" onClick={() => setDetail(null)} />
            <div className="relative inline-block w-full max-w-2xl p-6 bg-white dark:bg-gray-800 rounded-lg shadow-xl">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Incident Details</h3>
                <button onClick={() => setDetail(null)} className="text-gray-400 hover:text-gray-600"><X size={20} /></button>
              </div>
              <div className="space-y-2 text-sm">
                <Row k="Category" v={detail.category} />
                <Row k="Severity" v={detail.severity} />
                <Row k="Status" v={detail.status} />
                <Row k="Component" v={detail.affected_component} />
                <Row k="Error" v={detail.error_signature} />
                <Row k="First seen" v={detail.first_seen ? new Date(detail.first_seen).toLocaleString() : ''} />
              </div>
              {detail.diagnosis && detail.diagnosis.diagnosis_id && (
                <div className="mt-4 border-t border-gray-200 dark:border-gray-700 pt-4 space-y-2 text-sm">
                  <div className="font-semibold flex items-center gap-2"><Loader className="h-4 w-4" /> AI Diagnosis ({detail.diagnosis.model_used})</div>
                  <Row k="Root cause" v={detail.diagnosis.root_cause} />
                  <Row k="Proposed fix" v={detail.diagnosis.proposed_fix} />
                  <Row k="Risk" v={detail.diagnosis.risk_level} />
                  <Row k="Confidence" v={detail.diagnosis.confidence != null ? `${Math.round(detail.diagnosis.confidence * 100)}%` : ''} />
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function Row({ k, v }) {
  return (
    <div className="flex">
      <span className="w-32 shrink-0 text-gray-500">{k}</span>
      <span className="text-gray-800 dark:text-gray-200 break-words">{v || '—'}</span>
    </div>
  )
}

function Select({ value, onChange, options }) {
  return (
    <div className="relative">
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="appearance-none pl-3 pr-10 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700">
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
      <ChevronDown className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 pointer-events-none" size={16} />
    </div>
  )
}

export default Incidents
