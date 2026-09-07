import React, { useState, useEffect } from 'react'
import { Plus, Search, Users, Mail, Building2, Phone } from 'lucide-react'
import api from '../services/api'

function Clients() {
  const [clients, setClients] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [showModal, setShowModal] = useState(false)
  const [newClient, setNewClient] = useState({
    client_name: '', contact_email: '', company_name: '', phone: '', plan: 'starter',
  })

  useEffect(() => { fetchClients() }, [])

  const fetchClients = async () => {
    try {
      const res = await api.get('/clients')
      setClients(res.data)
    } catch (e) { console.error('Failed to fetch clients:', e) }
    setLoading(false)
  }

  const handleCreate = async (e) => {
    e.preventDefault()
    try {
      await api.post('/clients', null, { params: newClient })
      setShowModal(false)
      setNewClient({ client_name: '', contact_email: '', company_name: '', phone: '', plan: 'starter' })
      fetchClients()
    } catch (e) { console.error('Failed to create client:', e) }
  }

  const filtered = clients.filter(c =>
    c.client_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    c.company?.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const getPlanColor = (plan) => {
    switch (plan) {
      case 'enterprise': return 'bg-purple-100 text-purple-800'
      case 'professional': return 'bg-blue-100 text-blue-800'
      default: return 'bg-gray-100 text-gray-800'
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
    </div>
  )

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Clients</h1>
        <button onClick={() => setShowModal(true)} className="btn-primary">
          <Plus className="mr-2 h-4 w-4 inline" />Add Client
        </button>
      </div>

      <div className="card">
        <div className="flex items-center space-x-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={20} />
            <input type="text" placeholder="Search clients..." value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700" />
          </div>
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="card text-center py-12">
          <Users className="mx-auto h-12 w-12 text-gray-400 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">No clients yet</h3>
          <p className="text-gray-500 mb-4">Add your first client to get started</p>
          <button onClick={() => setShowModal(true)} className="btn-primary">
            <Plus className="mr-2 h-4 w-4 inline" />Add Client
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((client) => (
            <div key={client.client_id} className="card hover:shadow-lg transition-shadow">
              <div className="flex items-start justify-between">
                <div className="flex items-center">
                  <div className="p-3 bg-green-100 dark:bg-green-900 rounded-lg">
                    <Users className="h-6 w-6 text-green-600 dark:text-green-400" />
                  </div>
                  <div className="ml-4">
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{client.client_name}</h3>
                    {client.company && <p className="text-sm text-gray-500">{client.company}</p>}
                  </div>
                </div>
              </div>
              <div className="mt-4 space-y-2">
                {client.email && (
                  <div className="flex items-center text-sm text-gray-600 dark:text-gray-400">
                    <Mail className="mr-2 h-4 w-4" />{client.email}
                  </div>
                )}
                {client.phone && (
                  <div className="flex items-center text-sm text-gray-600 dark:text-gray-400">
                    <Phone className="mr-2 h-4 w-4" />{client.phone}
                  </div>
                )}
              </div>
              <div className="mt-4 flex items-center justify-between">
                <span className={`px-2 py-1 text-xs font-semibold rounded-full ${getPlanColor(client.settings?.plan || 'starter')}`}>
                  {client.settings?.plan || 'starter'}
                </span>
                <span className={`text-xs font-medium ${client.status === 'active' ? 'text-green-600' : 'text-gray-500'}`}>
                  {client.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {showModal && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:block sm:p-0">
            <div className="fixed inset-0 transition-opacity bg-gray-500 bg-opacity-75" onClick={() => setShowModal(false)} />
            <div className="inline-block w-full max-w-md p-6 my-8 overflow-hidden text-left align-middle transition-all transform bg-white dark:bg-gray-800 shadow-xl rounded-lg">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Add New Client</h3>
              <form onSubmit={handleCreate} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Client Name</label>
                  <input type="text" required value={newClient.client_name}
                    onChange={(e) => setNewClient({ ...newClient, client_name: e.target.value })}
                    className="input" placeholder="Acme Corp" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Contact Email</label>
                  <input type="email" required value={newClient.contact_email}
                    onChange={(e) => setNewClient({ ...newClient, contact_email: e.target.value })}
                    className="input" placeholder="contact@acme.com" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Company</label>
                  <input type="text" value={newClient.company_name}
                    onChange={(e) => setNewClient({ ...newClient, company_name: e.target.value })}
                    className="input" placeholder="Acme Inc" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Phone</label>
                  <input type="text" value={newClient.phone}
                    onChange={(e) => setNewClient({ ...newClient, phone: e.target.value })}
                    className="input" placeholder="+1 234 567 890" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Plan</label>
                  <select value={newClient.plan}
                    onChange={(e) => setNewClient({ ...newClient, plan: e.target.value })}
                    className="input">
                    <option value="starter">Starter</option>
                    <option value="professional">Professional</option>
                    <option value="enterprise">Enterprise</option>
                  </select>
                </div>
                <div className="flex justify-end space-x-3 mt-6">
                  <button type="button" onClick={() => setShowModal(false)} className="btn-secondary">Cancel</button>
                  <button type="submit" className="btn-primary">Create Client</button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Clients
