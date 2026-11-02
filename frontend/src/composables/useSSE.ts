import { ref, onUnmounted, type Ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { SSE_BASE_RETRY_DELAY_MS, SSE_MAX_RETRY_DELAY_MS, SSE_CONNECT_TIMEOUT_MS } from '@/utils/constants'
import { logger } from '@/utils/logger'

export interface SSEEvent<T = unknown> {
  type: string
  data: T
}

export interface UseSSEOptions<T = unknown> {
  onEvent?: (event: SSEEvent<T>) => void
  onConnect?: () => void
  onDisconnect?: () => void
  onError?: (error: Error) => void
}

export function useSSE<T = unknown>(endpoint: Ref<string | null>, options: UseSSEOptions<T> = {}) {
  const authStore = useAuthStore()

  const isConnected = ref(false)
  const retryCount = ref(0)
  const lastEvent = ref<SSEEvent<T> | null>(null)
  const error = ref<Error | null>(null)

  let abortController: AbortController | null = null
  let connectionGeneration = 0
  let currentRetryDelay = SSE_BASE_RETRY_DELAY_MS
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let shouldReconnect = true

  const clearReconnectTimer = () => {
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  const resetBackoff = () => {
    currentRetryDelay = SSE_BASE_RETRY_DELAY_MS
    retryCount.value = 0
    clearReconnectTimer()
  }

  const scheduleReconnect = () => {
    if (!shouldReconnect || reconnectTimer !== null || !endpoint.value) {
      return
    }

    const delay = currentRetryDelay
    retryCount.value++
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      if (shouldReconnect && endpoint.value) {
        connect()
      }
    }, delay)

    currentRetryDelay = Math.min(currentRetryDelay * 2, SSE_MAX_RETRY_DELAY_MS)
  }

  const handleEvent = (eventType: string, data: T) => {
    const event: SSEEvent<T> = { type: eventType, data }
    lastEvent.value = event
    options.onEvent?.(event)
  }

  const connect = async () => {
    if (!endpoint.value) return

    disconnect({ keepRetryState: true })
    shouldReconnect = true
    clearReconnectTimer()
    const generation = ++connectionGeneration
    const controller = new AbortController()
    abortController = controller
    let connectTimedOut = false
    const connectTimer = setTimeout(() => {
      connectTimedOut = true
      controller.abort()
    }, SSE_CONNECT_TIMEOUT_MS)

    try {
      const url = endpoint.value.startsWith('http')
        ? endpoint.value
        : `/api${endpoint.value.startsWith('/') ? endpoint.value : '/' + endpoint.value}`

      const headers: Record<string, string> = {
        'Accept': 'text/event-stream',
      }

      if (authStore.token) {
        headers.Authorization = `Bearer ${authStore.token}`
      }

      const response = await fetch(url, {
        credentials: 'include',
        headers,
        signal: controller.signal,
      })

      clearTimeout(connectTimer)
      if (generation !== connectionGeneration) {
        await response.body?.cancel()
        return
      }

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      if (!response.body) {
        throw new Error('No response body')
      }

      isConnected.value = true
      error.value = null
      currentRetryDelay = SSE_BASE_RETRY_DELAY_MS
      retryCount.value = 0
      options.onConnect?.()

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = ''

      while (true) {
        const { done, value } = await reader.read()

        if (generation !== connectionGeneration) {
          await reader.cancel().catch(() => undefined)
          return
        }

        if (done) {
          break
        }

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          const trimmed = line.trim()

          if (!trimmed) {
            currentEvent = ''
            continue
          }

          if (trimmed.startsWith('event:')) {
            currentEvent = trimmed.slice(6).trim()
          } else if (trimmed.startsWith('data:')) {
            try {
              const data = JSON.parse(trimmed.slice(5).trim()) as T
              handleEvent(currentEvent || 'message', data)
            } catch (err) {
              logger.warn('SSE JSON parse failed, skipping event', err)
            }
          }
        }
      }

      if (generation !== connectionGeneration) return
      isConnected.value = false
      options.onDisconnect?.()

      if (shouldReconnect) {
        scheduleReconnect()
      }

    } catch (err: unknown) {
      if (generation !== connectionGeneration) return
      if (err instanceof Error && err.name === 'AbortError' && !connectTimedOut) {
        return
      }

      const sseError = err instanceof Error ? err : new Error(String(err))
      logger.error('SSE connection error', sseError)
      error.value = sseError
      isConnected.value = false
      options.onError?.(sseError)
      options.onDisconnect?.()

      scheduleReconnect()
    } finally {
      clearTimeout(connectTimer)
      if (abortController === controller) abortController = null
    }
  }

  const disconnect = (opts?: { keepRetryState?: boolean }) => {
    connectionGeneration++
    if (abortController) {
      abortController.abort()
      abortController = null
      isConnected.value = false
    }
    if (opts?.keepRetryState) {
      clearReconnectTimer()
    } else {
      shouldReconnect = false
      resetBackoff()
    }
  }

  onUnmounted(() => {
    disconnect()
  })

  return {
    isConnected,
    retryCount,
    lastEvent,
    error,
    connect,
    disconnect,
    resetBackoff,
  }
}
