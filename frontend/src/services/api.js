import axios from 'axios'

const API_BASE_URL = '/api/v1'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }
    if (error.response?.status === 429) {
      console.error('Rate limit exceeded')
    }
    window.dispatchEvent(new CustomEvent('api-error', { detail: typeof error.response?.data?.detail === 'string' ? error.response.data.detail : 'Request failed. Please try again.' }))
    return Promise.reject(error)
  }
)

export const projectService = {
  list: () => api.get('/projects'),
  get: (id) => api.get(`/projects/${id}`),
  create: (data) => api.post('/projects', data),
  update: (id, data) => api.put(`/projects/${id}`, data),
  delete: (id) => api.delete(`/projects/${id}`),
  health: (id) => api.get(`/projects/${id}/health`),
  logs: (id, params) => api.get(`/projects/${id}/logs`, { params }),
}

export const incidentService = {
  list: (params) => api.get('/incidents', { params }),
  get: (id) => api.get(`/incidents/${id}`),
  create: (data) => api.post('/incidents', data),
  approve: (id) => api.post(`/incidents/${id}/approve`),
  reject: (id, reason) => api.post(`/incidents/${id}/reject`, { reason }),
}

export const scanService = {
  trigger: () => api.post('/trigger-scan'),
}

export const analyticsService = {
  dashboard: () => api.get('/analytics/dashboard'),
  incidentTrends: (params) => api.get('/analytics/incident-trends', { params }),
  healthTrends: (id, params) => api.get(`/analytics/health-trends/${id}`, { params }),
  remediationStats: (params) => api.get('/analytics/remediation-stats', { params }),
  clientSummary: (id, params) => api.get(`/analytics/client-summary/${id}`, { params }),
}

export const reportService = {
  incident: (params) => api.get('/reports/incident', { params }),
  uptime: (id, params) => api.get(`/reports/uptime/${id}`, { params }),
  performance: (id, params) => api.get(`/reports/performance/${id}`, { params }),
  executiveSummary: (id, params) => api.get(`/reports/executive-summary/${id}`, { params }),
}

export const clientService = {
  list: (params) => api.get('/clients', { params }),
  get: (id) => api.get(`/clients/${id}`),
  create: (data) => api.post('/clients', null, { params: data }),
  update: (id, data) => api.put(`/clients/${id}`, null, { params: data }),
  delete: (id) => api.delete(`/clients/${id}`),
  usage: (id) => api.get(`/clients/${id}/usage`),
  billing: (id) => api.get(`/clients/${id}/billing`),
}

export const userService = {
  list: (params) => api.get('/users', { params }),
  get: (id) => api.get(`/users/${id}`),
  create: (data) => api.post('/users', data),
  update: (id, data) => api.put(`/users/${id}`, null, { params: data }),
  delete: (id) => api.delete(`/users/${id}`),
}

export const authService = {
  login: (email, password) => api.post('/auth/login', { email, password }),
  createApiKey: (data) => api.post('/auth/api-keys', data),
  revokeApiKey: (id) => api.post(`/auth/api-keys/${id}/revoke`),
}

export default api
