import type { paths, components } from './client-generated'

const API_BASE = '/api/v1'

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<{ data: T | null; error: { detail: string } | null }> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'An error occurred' }))
    return { data: null, error: { detail: errorData.detail || `HTTP ${response.status}` } }
  }

  const data = await response.json().catch(() => null)
  return { data, error: null }
}

export const api = {
  get: <T>(path: string, params?: Record<string, string | number | boolean | undefined>) => {
    const searchParams = new URLSearchParams()
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          searchParams.append(key, String(value))
        }
      })
    }
    const query = searchParams.toString()
    return request<T>(`${path}${query ? `?${query}` : ''}`, { method: 'GET' })
  },
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}

export type { paths }
export type schemas = components['schemas']