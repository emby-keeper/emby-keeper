import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('ek_token') || '')
  const showLogin = ref(true)

  const headers = computed<Record<string, string>>(() => {
    const result: Record<string, string> = {}
    if (token.value) result.Authorization = `Bearer ${token.value}`
    return result
  })

  const isLoggedIn = computed(() => !!token.value && !showLogin.value)

  async function checkAuth() {
    try {
      const res = await fetch('/api/auth/me', {
        credentials: 'include',
        headers: headers.value,
      })

      showLogin.value = res.status === 401

      if (res.ok && !token.value) {
        localStorage.removeItem('ek_token')
      }

      return !showLogin.value
    } catch {
      showLogin.value = true
      return false
    }
  }

  async function login(password: string) {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password })
    })
    if (!res.ok) throw new Error('login failed')
    const data = await res.json()
    token.value = data.token || ''
    if (token.value) localStorage.setItem('ek_token', token.value)
    showLogin.value = false
  }

  async function logout() {
    await fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'include',
      headers: headers.value,
    }).catch(() => undefined)
    token.value = ''
    localStorage.removeItem('ek_token')
    showLogin.value = true
  }

  async function request<T = unknown>(path: string, options: RequestInit = {}): Promise<T> {
    const url = path.startsWith('http') ? path : `/api${path.startsWith('/') ? path : '/' + path}`

    const mergedHeaders: Record<string, string> = {
      ...(options.headers as Record<string, string> || {}),
    }

    if (token.value) {
      mergedHeaders['Authorization'] = `Bearer ${token.value}`
    }

    if (options.body && typeof options.body === 'string') {
      mergedHeaders['Content-Type'] = 'application/json'
    }

    const res = await fetch(url, {
      ...options,
      credentials: 'include',
      headers: mergedHeaders,
    })

    if (res.status === 401) {
      await logout()
      throw new Error('Unauthorized')
    }

    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(error.detail || res.statusText)
    }

    const contentType = res.headers.get('content-type') || ''
    if (!contentType.includes('application/json')) {
      return undefined as T
    }

    const text = await res.text()
    if (!text) {
      return undefined as T
    }

    return JSON.parse(text) as T
  }

  return {
    token,
    showLogin,
    headers,
    isLoggedIn,
    checkAuth,
    login,
    logout,
    request,
  }
})
