// Keep fetch-based pages consistent with the shared API client's error handling.
export async function checkedFetch(url, options = {}) {
  const response = await globalThis.fetch(url, options)
  if (response.ok) return response
  let message = `Request failed (${response.status})`
  try {
    const body = await response.clone().json()
    if (typeof body.detail === 'string') message = body.detail
  } catch { /* use the HTTP status */ }
  if (response.status === 401) {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    window.location.assign('/login')
  }
  window.dispatchEvent(new CustomEvent('api-error', { detail: message }))
  throw new Error(message)
}
