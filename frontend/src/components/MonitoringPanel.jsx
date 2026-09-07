import React, { useEffect, useState } from 'react'
import api from '../services/api'

export default function MonitoringPanel({ projectId }) {
  const [ready, setReady] = useState(false)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState(null)
  const [config, setConfig] = useState({})
  const [contracts, setContracts] = useState('[]')
  const [message, setMessage] = useState('')
  const load = async (initial = false) => {
    try {
      const { data } = await api.get(`/projects/${projectId}/monitoring-status`)
      setStatus(data)
      if (initial) setConfig(data.config)
    } catch { setMessage('Monitoring status could not be loaded.') }
  }
  useEffect(() => {
    let cancelled = false
    setReady(false)
    setStatus(null)
    setConfig({})
    api.get(`/projects/${projectId}/monitoring-status`).then(({ data }) => {
      if (!cancelled) { setStatus(data); setConfig(data.config); setContracts(JSON.stringify(data.config.application?.checks || [],null,2)); setReady(true) }
    }).catch(() => { if (!cancelled) setMessage('Monitoring settings could not be loaded. Reopen this project to retry.') })
    return () => { cancelled = true }
  }, [projectId])
  const save = async () => {
    if (!ready || saving) return
    setSaving(true)
    try { await api.put(`/projects/${projectId}/monitoring-config`, {...config,application:{enabled:false,interval:300,...config.application,checks:JSON.parse(contracts)}}); setMessage('Monitoring schedule saved.'); await load() }
    catch { setMessage('Could not save monitoring settings.') }
    finally { setSaving(false) }
  }
  return <section className="mt-5 p-4 border rounded-lg space-y-3">
    <h3 className="font-semibold">Automatic monitoring</h3>
    <p>Scheduler: {status?.scheduler?.stale ? 'Needs attention' : status ? 'Running' : 'Loading…'}</p>
    {['http', 'logs', 'resources'].map(kind => <div key={kind} className="flex items-center gap-3">
      <label><input type="checkbox" checked={config[kind]?.enabled ?? true} onChange={e => setConfig(c => ({...c, [kind]: {...c[kind], enabled: e.target.checked, interval: c[kind]?.interval ?? (kind === 'logs' ? 600 : 300)}}))} /> {kind === 'http' ? 'Website' : kind === 'logs' ? 'Application logs' : 'Server resources'}</label>
      <label>Every <input className="input w-24" type="number" min="30" max="86400" value={config[kind]?.interval ?? (kind === 'logs' ? 600 : 300)} onChange={e => setConfig(c => ({...c, [kind]: {...c[kind], enabled: c[kind]?.enabled ?? true, interval: Number(e.target.value)}}))} /> seconds</label>
    </div>)}
    <fieldset className="space-y-2"><legend>Incident policy</legend>
      {[['failure_checks','Consecutive failures',2],['recovery_checks','Healthy checks before recovery',2],['escalate_after','Escalate after failures',5]].map(([key,label,value]) => <label key={key} className="block">{label} <input className="input w-20" type="number" min="1" max={key === 'escalate_after' ? 100 : 10} value={config.policy?.[key] ?? value} onChange={e => setConfig(c => ({...c,policy:{failure_checks:2,recovery_checks:2,escalate_after:5,...c.policy,[key]:Number(e.target.value)}}))} /></label>)}
      <p className="text-sm">Confirmed outages and near-expired certificates alert immediately. Brief slowdowns require consecutive failures.</p>
      {[['warning_ms','Slow response warning (ms)',2000],['critical_ms','Critical response (ms)',5000],['ssl_warning_days','Certificate warning (days)',30],['ssl_critical_days','Certificate critical (days)',7]].map(([key,label,value]) => <label key={key} className="block">{label} <input className="input w-24" type="number" min="0" value={config.http?.[key] ?? value} onChange={e => setConfig(c => ({...c,http:{enabled:true,interval:300,...c.http,[key]:Number(e.target.value)}}))} /></label>)}
    </fieldset>
    <fieldset className="space-y-2"><legend>Resource thresholds (%)</legend>
      {['cpu','memory','disk','inodes'].map(metric => <div key={metric} className="flex gap-3 items-center">
        <span>{metric}</span>{['warning','critical'].map(level => <label key={level}>{level} <input className="input w-20" type="number" min="0" max="100" value={config.resources?.thresholds?.[metric]?.[level] ?? (level === 'warning' ? (metric === 'disk' ? 75 : 80) : metric === 'disk' ? 90 : 95)} onChange={e => setConfig(c => ({...c,resources:{enabled:true,interval:300,...c.resources,thresholds:{...c.resources?.thresholds,[metric]:{warning:metric === 'disk' ? 75 : 80,critical:metric === 'disk' ? 90 : 95,...c.resources?.thresholds?.[metric],[level]:Number(e.target.value)}}}}))} /></label>)}
      </div>)}
    </fieldset>
    <fieldset className="space-y-2"><legend>Application checks</legend>
      <label><input type="checkbox" checked={config.application?.enabled ?? false} onChange={e => setConfig(c => ({...c,application:{interval:300,...c.application,enabled:e.target.checked}}))} /> Enable application contracts</label>
      <label>Every <input className="input w-24" type="number" min="30" max="86400" value={config.application?.interval ?? 300} onChange={e => setConfig(c => ({...c,application:{enabled:false,...c.application,interval:Number(e.target.value)}}))} /> seconds</label>
      <p className="text-sm">Use JSON assertions for database/cache/queue health. Login journeys with POST require a staging project and explicit permission.</p>
      <label><input type="checkbox" checked={config.application?.allow_mutations ?? false} onChange={e => setConfig(c => ({...c,application:{enabled:false,interval:300,...c.application,allow_mutations:e.target.checked}}))} /> Allow requests that change staging data</label>
      <label>Check definitions (JSON)<textarea className="input w-full font-mono" rows="6" value={contracts} onChange={e => setContracts(e.target.value)} placeholder={'[{"name":"Database health","path":"/health","json_equals":{"database":"healthy"}}]'} /></label>
    </fieldset>
    <button className="btn-primary" disabled={!ready || saving} onClick={save}>Save monitoring</button> <button className="btn-secondary" onClick={() => load()}>Refresh status</button>
    {message && <p role="status">{message}</p>}
    {status?.checks?.map(check => <div key={check.check_kind} className="text-sm border-t pt-2">
      <strong>{check.check_kind}</strong> · {!check.enabled ? 'Disabled' : check.stale ? 'Overdue' : check.last_error ? 'Check unavailable' : 'Scheduled'}
      <p>Last completed: {check.last_completed_at ? new Date(check.last_completed_at).toLocaleString() : 'Not yet run'}</p>
      {check.last_error && <p className="text-red-600">{check.last_error}</p>}
    </div>)}
  </section>
}
