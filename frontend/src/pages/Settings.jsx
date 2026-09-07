import React, { useState, useEffect } from 'react'
import { User, Bell, Shield, CreditCard, Save } from 'lucide-react'
import api from '../services/api'

const DEFAULTS = {
  profile: { name: 'Admin User', company: '' },
  notifications: { telegram_enabled: true, daily_reports: false },
  security: { session_timeout: 30 },
}

function Settings() {
  const [activeTab, setActiveTab] = useState('profile')
  const [settings, setSettings] = useState(DEFAULTS)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    const loadSettings = async () => {
      try {
        const res = await api.get('/settings')
        const data = res.data || {}
        setSettings({
          profile: {
            name: data['profile.name'] || DEFAULTS.profile.name,
            company: data['profile.company'] || DEFAULTS.profile.company,
          },
          notifications: {
            telegram_enabled: data['notifications.telegram_enabled'] === undefined
              ? DEFAULTS.notifications.telegram_enabled
              : data['notifications.telegram_enabled'] === 'true' || data['notifications.telegram_enabled'] === true,
            daily_reports: data['notifications.daily_reports'] === 'true' || data['notifications.daily_reports'] === true,
          },
          security: {
            session_timeout: parseInt(data['security.session_timeout'] || DEFAULTS.security.session_timeout, 10),
          },
        })
      } catch (e) { /* keep defaults */ }
      setLoading(false)
    }
    loadSettings()
  }, [])

  const handleSave = async () => {
    setSaving(true)
    setMessage('')
    try {
      const payload = {
        'profile.name': settings.profile.name,
        'profile.company': settings.profile.company,
        'notifications.telegram_enabled': settings.notifications.telegram_enabled,
        'security.session_timeout': settings.security.session_timeout,
      }
      for (const [key, value] of Object.entries(payload)) {
        await api.put(`/settings/${encodeURIComponent(key)}`, { value })
      }
      setMessage('Settings saved')
      setTimeout(() => setMessage(''), 2500)
    } catch (e) {
      setMessage('Failed to save settings')
    }
    setSaving(false)
  }

  const tabs = [
    { id: 'profile', name: 'Profile', icon: User },
    { id: 'notifications', name: 'Notifications', icon: Bell },
    { id: 'security', name: 'Security', icon: Shield },
    { id: 'billing', name: 'Billing', icon: CreditCard },
  ]

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
    </div>
  )

  const toggle = (group, key) =>
    setSettings(s => ({ ...s, [group]: { ...s[group], [key]: !s[group][key] } }))

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Settings</h1>
      <div className="flex flex-col lg:flex-row gap-6">
        <div className="lg:w-64">
          <nav className="space-y-1">
            {tabs.map((tab) => {
              const Icon = tab.icon
              return (
                <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                  className={`w-full flex items-center px-3 py-2 text-sm font-medium rounded-lg ${
                    activeTab === tab.id ? 'bg-blue-50 text-blue-600 dark:bg-blue-900/50'
                      : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
                  }`}>
                  <Icon className="mr-3 h-5 w-5" />{tab.name}
                </button>
              )
            })}
          </nav>
        </div>
        <div className="flex-1">
          {activeTab === 'profile' && (
            <div className="card">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Profile Settings</h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name</label>
                  <input type="text" value={settings.profile.name}
                    onChange={(e) => setSettings({ ...settings, profile: { ...settings.profile, name: e.target.value } })}
                    className="input" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Company</label>
                  <input type="text" value={settings.profile.company}
                    onChange={(e) => setSettings({ ...settings, profile: { ...settings.profile, company: e.target.value } })}
                    className="input" />
                </div>
              </div>
            </div>
          )}
          {activeTab === 'notifications' && (
            <div className="card space-y-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Notification Settings</h2>
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Telegram alerts</label>
                <button onClick={() => toggle('notifications', 'telegram_enabled')}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full ${settings.notifications.telegram_enabled ? 'bg-blue-600' : 'bg-gray-200 dark:bg-gray-700'}`}>
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${settings.notifications.telegram_enabled ? 'translate-x-6' : 'translate-x-1'}`} />
                </button>
              </div>
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Daily summary reports (not configured)</label>
                <button disabled title="Daily summary delivery is not configured"
                  className={`relative inline-flex h-6 w-11 items-center rounded-full ${settings.notifications.daily_reports ? 'bg-blue-600' : 'bg-gray-200 dark:bg-gray-700'}`}>
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${settings.notifications.daily_reports ? 'translate-x-6' : 'translate-x-1'}`} />
                </button>
              </div>
              <div className="flex items-center justify-between opacity-50">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Email alerts</label>
                <span className="text-xs text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded">Disabled (no SMTP)</span>
              </div>
              <div className="flex items-center justify-between opacity-50">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Slack alerts</label>
                <span className="text-xs text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded">Disabled</span>
              </div>
            </div>
          )}
          {activeTab === 'security' && (
            <div className="card">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Security Settings</h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Session Timeout (minutes)</label>
                  <input type="number" value={settings.security.session_timeout}
                    onChange={(e) => setSettings({ ...settings, security: { ...settings.security, session_timeout: parseInt(e.target.value) || 30 } })}
                    className="input w-32" />
                </div>
              </div>
            </div>
          )}
          {activeTab === 'billing' && (
            <div className="card">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Billing</h2>
              <div className="text-center py-8">
                <CreditCard className="mx-auto h-12 w-12 text-gray-400 mb-4" />
                <p className="text-gray-500">No billing plans configured</p>
              </div>
            </div>
          )}
          <div className="mt-6 flex items-center justify-end gap-3">
            {message && <span className="text-sm text-green-600 dark:text-green-400">{message}</span>}
            <button onClick={handleSave} disabled={saving} className="btn-primary">
              <Save className="mr-2 h-4 w-4 inline" />
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Settings
