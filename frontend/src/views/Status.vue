<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  ArrowPathIcon,
  CpuChipIcon,
  ChevronDownIcon,
  ExclamationTriangleIcon,
  PlayCircleIcon,
  StopCircleIcon,
} from '@heroicons/vue/24/outline'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { useAuthStore } from '@/stores/auth'
import { useSSE } from '@/composables/useSSE'
import type { BackendStatus } from '@/types'
import { logger } from '@/utils/logger'

const auth = useAuthStore()
const backend = ref<BackendStatus>({ running: false, pid: null, target: '' })
const loading = ref(true)
const actionLoading = ref<'start' | 'restart' | 'stop' | null>(null)
const error = ref('')
const lastUpdated = ref('')
const terminalRef = ref<HTMLElement | null>(null)
const isPinnedToBottom = ref(true)
const showScrollButton = ref(false)
const hasUnreadLogs = ref(false)

const statusEndpoint = ref<string | null>('/sse/status')

const backendBadge = computed(() => backend.value.running ? 'success' : 'warning')
const backendLabel = computed(() => backend.value.running ? '运行中' : '已停止')
const statusHeadline = computed(() => 'Embykeeper')
const statusDescription = computed(() => backend.value.running ? '当前正在运行。' : '当前尚未启动。')
const backendOutput = computed<string[]>(() => (backend.value?.recent_output || []).filter((line: string) => !line.startsWith('$ ')))
const activeTerminalLines = computed<string[]>(() => backendOutput.value)
const backendExitCode = computed(() => backend.value?.exit_code)
const coloredTerminalHtml = computed(() => {
  const escapeHtml = (value: string) => value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  return activeTerminalLines.value.map((line) => {
    const safe = escapeHtml(line)
    if (safe.includes(' ERROR ') || safe.startsWith('ERROR') || safe.includes('] ERROR')) {
      return `<span class="text-rose-300">${safe}</span>`
    }
    if (safe.includes(' WARNING ') || safe.startsWith('WARNING') || safe.includes('] WARNING')) {
      return `<span class="text-amber-300">${safe}</span>`
    }
    if (safe.includes(' INFO ') || safe.startsWith('INFO') || safe.includes('] INFO')) {
      return safe
        .replace(/INFO/g, '<span class="text-sky-300">INFO</span>')
        .replace(/Embykeeper/g, '<span class="text-emerald-300">Embykeeper</span>')
    }
    return safe.replace(/Embykeeper/g, '<span class="text-emerald-300">Embykeeper</span>')
  }).join('\n')
})

const updateScrollState = () => {
  const element = terminalRef.value
  if (!element) return
  const threshold = 24
  const pinned = element.scrollTop + element.clientHeight >= element.scrollHeight - threshold
  isPinnedToBottom.value = pinned
  showScrollButton.value = !pinned
  if (pinned) {
    hasUnreadLogs.value = false
  }
}

const scrollToBottom = async (behavior: ScrollBehavior = 'smooth') => {
  await nextTick()
  const element = terminalRef.value
  if (!element) return
  element.scrollTo({ top: element.scrollHeight, behavior })
  isPinnedToBottom.value = true
  showScrollButton.value = false
  hasUnreadLogs.value = false
}

const { isConnected: statusStreamConnected, retryCount: statusRetryCount, connect: connectStatusStream, disconnect: disconnectStatusStream } = useSSE(statusEndpoint, {
  onConnect: () => { void fetchStatus() },
  onEvent: (event) => {
    if (event.type !== 'status') return
    const previousLogCount = backendOutput.value.length
    backend.value = {
      ...backend.value,
      ...event.data,
    }
    lastUpdated.value = new Date().toLocaleTimeString('zh-CN')
    const currentLogCount = (event.data?.recent_output || []).filter((line: string) => !line.startsWith('$ ')).length
    if (currentLogCount > previousLogCount) {
      if (isPinnedToBottom.value) {
        scrollToBottom('auto')
      } else {
        hasUnreadLogs.value = true
        showScrollButton.value = true
      }
    }
  },
})

const fetchStatus = async () => {
  loading.value = true
  error.value = ''

  try {
    backend.value = await auth.request<BackendStatus>('/pm/status')
    lastUpdated.value = new Date().toLocaleTimeString('zh-CN')

    if (!backend.value.running) {
      error.value = backend.value.last_error || ''
      return
    }
  } catch (err) {
    logger.error('Failed to fetch status', err)
    error.value = logger.message(err, '状态信息加载失败')
  } finally {
    loading.value = false
  }
}

const handleAction = async (action: 'start' | 'restart' | 'stop') => {
  actionLoading.value = action
  try {
    await auth.request(`/pm/${action}`, { method: 'POST' })
    await fetchStatus()
  } catch (err) {
    logger.error('Action failed', err)
    await fetchStatus()
    if (!error.value) {
      error.value = logger.message(err, '操作未完成，请稍后重试')
    }
  } finally {
    actionLoading.value = null
  }
}

onMounted(async () => {
  await fetchStatus()
  connectStatusStream()
  nextTick(() => scrollToBottom('auto'))
})

onBeforeUnmount(() => {
  disconnectStatusStream()
})
</script>

<template>
  <div class="space-y-6">
    <section class="overflow-hidden rounded-[30px] border border-slate-200/80 bg-[radial-gradient(circle_at_top_left,_rgba(99,102,241,0.28),_transparent_32%),linear-gradient(135deg,_#0f172a_0%,_#111827_44%,_#1e293b_100%)] shadow-[0_28px_90px_-40px_rgba(15,23,42,0.7)]">
      <div class="space-y-5 px-4 py-5 sm:space-y-6 sm:px-6 sm:py-6 xl:px-8">
        <div class="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-primary-100 backdrop-blur-sm">
          <CpuChipIcon class="h-4 w-4" aria-hidden="true" />
          Embykeeper
        </div>

        <div class="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div class="min-w-0 space-y-4 text-white">
            <h1 class="text-3xl font-semibold tracking-tight sm:text-4xl">{{ statusHeadline }}</h1>
            <p class="max-w-2xl text-sm leading-6 text-slate-300">{{ statusDescription }}</p>
            <div class="flex flex-wrap items-center gap-3 text-sm text-slate-200">
              <UiBadge :variant="backendBadge" size="lg">{{ backendLabel }}</UiBadge>
              <span>更新时间 {{ lastUpdated || '-' }}</span>
            </div>
          </div>

          <div class="flex shrink-0 flex-wrap gap-2">
            <UiButton
              v-if="!backend.running"
              :loading="actionLoading === 'start'"
              @click="handleAction('start')"
            >
              <PlayCircleIcon class="mr-2 h-4 w-4" aria-hidden="true" />
              启动 Embykeeper
            </UiButton>
            <template v-else>
              <UiButton
                variant="secondary"
                :loading="actionLoading === 'restart'"
                @click="handleAction('restart')"
              >
                <ArrowPathIcon class="mr-2 h-4 w-4" aria-hidden="true" />
                重启 Embykeeper
              </UiButton>
              <UiButton
                variant="danger"
                :loading="actionLoading === 'stop'"
                @click="handleAction('stop')"
              >
                <StopCircleIcon class="mr-2 h-4 w-4" aria-hidden="true" />
                停止 Embykeeper
              </UiButton>
            </template>
            <UiButton variant="outline" :loading="loading" @click="fetchStatus">
              <ArrowPathIcon class="mr-2 h-4 w-4" aria-hidden="true" />
              {{ loading ? '刷新中...' : '立即刷新' }}
            </UiButton>
          </div>
        </div>
      </div>
    </section>

    <div v-if="error" class="rounded-[24px] border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-900">
      <div class="flex items-start gap-2">
        <ExclamationTriangleIcon class="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
        <span>{{ error }}</span>
      </div>
    </div>

    <section class="relative overflow-hidden rounded-[30px] bg-[#020617] shadow-[0_28px_90px_-40px_rgba(2,6,23,0.9)]">
      <div class="flex items-center justify-between border-b border-white/5 px-5 py-4 sm:px-7">
        <h2 class="text-lg font-semibold tracking-tight text-white">最近日志</h2>
        <div class="group relative flex items-center">
          <span class="relative flex h-2.5 w-2.5">
            <span v-if="statusStreamConnected" class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60"></span>
            <span :class="['relative inline-flex h-2.5 w-2.5 rounded-full transition-colors', statusStreamConnected ? 'bg-emerald-400' : 'bg-amber-400']"></span>
          </span>
          <div class="pointer-events-none invisible absolute right-0 top-full z-20 mt-2.5 whitespace-nowrap rounded-xl border border-white/10 bg-slate-900/95 px-3.5 py-2 text-xs text-slate-200 opacity-0 shadow-2xl backdrop-blur transition group-hover:visible group-hover:opacity-100">
            <template v-if="statusStreamConnected">日志实时推送已连接</template>
            <template v-else-if="statusRetryCount > 0">实时推送已断开，正在重连（第 {{ statusRetryCount }} 次）</template>
            <template v-else>正在建立实时连接…</template>
          </div>
        </div>
      </div>

      <div
        ref="terminalRef"
        class="ek-terminal relative h-[min(420px,60dvh)] min-h-56 overflow-auto px-4 py-4 sm:px-6 sm:py-6"
        @scroll="updateScrollState"
      >
        <pre
          v-if="activeTerminalLines.length"
          class="min-h-full whitespace-pre-wrap break-words font-mono text-xs leading-6 text-slate-100"
          v-html="coloredTerminalHtml"
        ></pre>

        <div v-else class="flex h-full items-center justify-center text-sm text-slate-500">
          暂无可显示的日志。
        </div>
      </div>

      <button
        v-if="showScrollButton"
        type="button"
        class="absolute bottom-5 right-5 inline-flex h-12 w-12 items-center justify-center rounded-full border border-white/10 bg-white/10 text-white shadow-[0_18px_32px_-18px_rgba(15,23,42,0.8)] backdrop-blur-md transition hover:bg-white/15"
        @click="scrollToBottom()"
      >
        <span v-if="hasUnreadLogs" class="pointer-events-none absolute inset-0 rounded-full border border-sky-300/60 ek-log-ripple"></span>
        <ChevronDownIcon class="h-5 w-5" aria-hidden="true" />
      </button>
    </section>
  </div>
</template>
