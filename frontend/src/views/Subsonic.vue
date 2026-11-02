<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowPathIcon, ChevronDownIcon, MagnifyingGlassIcon, MusicalNoteIcon, PencilSquareIcon, PlusIcon, TrashIcon } from '@heroicons/vue/24/outline'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiCard from '@/components/ui/UiCard.vue'
import UiDrawer from '@/components/ui/UiDrawer.vue'
import UiSelect, { type UiSelectOption } from '@/components/ui/UiSelect.vue'
import UiScheduleIntervalOverride from '@/components/ui/UiScheduleIntervalOverride.vue'
import UiScheduleTimeOverride from '@/components/ui/UiScheduleTimeOverride.vue'
import UiTimeline from '@/components/ui/UiTimeline.vue'
import Switch from '@/components/Switch.vue'
import { useSSE } from '@/composables/useSSE'
import { useAuthStore } from '@/stores/auth'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { formatScheduleConcurrency, formatScheduleInterval, formatScheduleTimeRange } from '@/utils/schedulerDisplay'
import { logger } from '@/utils/logger'

type SubsonicRunItem = {
  id: string
  description?: string | null
  status?: string | null
  status_code?: number | null
  status_info?: string | null
  duration?: number | null
  start_time?: string | null
  end_time?: string | null
  parent_ids?: string[]
  child_count?: number
}

type SubsonicRunLog = {
  level?: string | null
  message: string
  time?: string | null
}

type SubsonicAccountItem = {
  id: string
  url: string
  username: string
  name?: string | null
  enabled: boolean
  use_proxy: boolean
  time: number | number[]
  interval_days?: string | null
  time_range?: string | null
  run_history?: SubsonicRunItem[]
}

type SubsonicForm = {
  url: string
  username: string
  password: string
  name: string
  enabled: boolean
  use_proxy: boolean
  time_start: number
  time_end: number
  interval_days: string
  time_range: string
}

const auth = useAuthStore()
const accounts = ref<SubsonicAccountItem[]>([])
const summary = ref({ total: 0, enabled: 0, use_proxy: 0, concurrency: 1, time_range: '', interval_days: '', module_enabled: true })
const loading = ref(true)
const saving = ref(false)
const moduleSaving = ref(false)
const deleting = ref<string | null>(null)
const search = ref('')
const statusFilter = ref<'all' | 'enabled' | 'disabled'>('all')
const featureFilter = ref<'all' | 'use_proxy' | 'interval_days' | 'time_range'>('all')
const drawerOpen = ref(false)
const detailOpen = ref(false)
const detailTab = ref<'history' | 'test'>('history')
const detailLoading = ref(false)
const historyLoading = ref(false)
const runDetailLoading = ref(false)
let accountDetailRequestVersion = 0
const detailError = ref('')
const selectedRunId = ref('')
const selectedRun = ref<SubsonicRunItem | null>(null)
const selectedRunLogs = ref<SubsonicRunLog[]>([])
const currentAccount = ref<SubsonicAccountItem | null>(null)
const formMode = ref<'create' | 'edit'>('create')
const formError = ref('')
const formTestActive = ref(false)
const formErrorElement = ref<HTMLElement | null>(null)
const pageError = ref('')
const testStarting = ref(false)
const testRunId = ref('')
const testRun = ref<SubsonicRunItem | null>(null)
const testRunLogs = ref<SubsonicRunLog[]>([])
const testLogsEndpoint = ref<string | null>(null)
const testError = ref('')
const form = ref<SubsonicForm>({
  url: '',
  username: '',
  password: '',
  name: '',
  enabled: true,
  use_proxy: true,
  time_start: 300,
  time_end: 600,
  interval_days: '',
  time_range: '',
})

const { model: drawerModel } = useUnsavedChanges(drawerOpen, () => form.value, saving)

const filteredAccounts = computed(() => {
  const keyword = search.value.trim().toLowerCase()

  return accounts.value.filter((account) => {
    if (statusFilter.value === 'enabled' && !account.enabled) return false
    if (statusFilter.value === 'disabled' && account.enabled) return false
    if (featureFilter.value !== 'all' && !account[featureFilter.value]) return false

    if (!keyword) return true

    return [account.username, account.url, account.name]
      .some((value) => String(value || '').toLowerCase().includes(keyword))
  })
})

const drawerTitle = computed(() => formMode.value === 'create' ? '新增 Subsonic 账号' : '编辑 Subsonic 账号')
const currentAccountKey = computed(() => currentAccount.value?.id || '')
const accountKey = (account: SubsonicAccountItem) => account.id
const statusFilterOptions: UiSelectOption[] = [
  { label: '全部状态', value: 'all' },
  { label: '仅启用', value: 'enabled' },
  { label: '仅停用', value: 'disabled' },
]
const featureFilterOptions: UiSelectOption[] = [
  { label: '全部特性', value: 'all' },
  { label: '使用代理', value: 'use_proxy' },
  { label: '单独间隔', value: 'interval_days' },
  { label: '单独时段', value: 'time_range' },
]
const summaryDisplay = computed(() => ({
  timeRange: formatScheduleTimeRange(summary.value.time_range),
  interval: formatScheduleInterval(summary.value.interval_days),
  concurrency: formatScheduleConcurrency(summary.value.concurrency),
}))
const detailTabs = [
  { key: 'history' as const, label: '运行记录' },
  { key: 'test' as const, label: '测试' },
]
const selectedRunTimeline = computed(() => mapRunLogsToTimeline(selectedRunLogs.value))
const accountDetailItems = computed(() => {
  if (!currentAccount.value) {
    return []
  }

  return [
    { label: '显示名称', value: currentAccount.value.name || '-' },
    { label: '播放时长', value: Array.isArray(currentAccount.value.time) ? `${currentAccount.value.time[0]} - ${currentAccount.value.time[1]} 秒` : '-' },
    { label: '单独间隔', value: formatScheduleInterval(currentAccount.value.interval_days) },
    { label: '单独时段', value: formatScheduleTimeRange(currentAccount.value.time_range) },
  ]
})

const applyForm = (account?: SubsonicAccountItem | null) => {
  const time = typeof account?.time === 'number' ? [account.time, account.time]
    : Array.isArray(account?.time) && account.time.length >= 2 ? account.time : [300, 600]
  form.value = {
    url: account?.url || '',
    username: account?.username || '',
    password: '',
    name: account?.name || '',
    enabled: account?.enabled ?? true,
    use_proxy: account?.use_proxy ?? true,
    time_start: Number(time[0] || 300),
    time_end: Number(time[1] || 600),
    interval_days: account?.interval_days || '',
    time_range: account?.time_range || '',
  }
}

const fetchAccounts = async () => {
  loading.value = true
  pageError.value = ''
  try {
    const data = await auth.request('/subsonic/accounts')
    accounts.value = data.accounts || []
    summary.value = data.summary || summary.value
  } catch (error) {
    logger.error('Failed to fetch subsonic accounts', error)
    pageError.value = logger.message(error, '账号列表加载失败')
  } finally {
    loading.value = false
  }
}

const saveSubsonicModuleSetting = async (enabled: boolean) => {
  moduleSaving.value = true
  pageError.value = ''
  try {
    await auth.request('/subsonic/settings', {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    })
    await fetchAccounts()
  } catch (error) {
    logger.error('Failed to save subsonic module setting', error)
    pageError.value = logger.message(error, '全局保活设置保存失败')
    await fetchAccounts()
  } finally {
    moduleSaving.value = false
  }
}

const openCreateDrawer = () => {
  formMode.value = 'create'
  currentAccount.value = null
  formError.value = ''
  applyForm(null)
  stopTestPolling()
  disconnectTestLogsStream()
  testLogsEndpoint.value = null
  formTestActive.value = false
  resetTestState()
  drawerOpen.value = true
}

const openEditDrawer = (account: SubsonicAccountItem) => {
  formMode.value = 'edit'
  currentAccount.value = account
  formError.value = ''
  applyForm(account)
  stopTestPolling()
  disconnectTestLogsStream()
  testLogsEndpoint.value = null
  formTestActive.value = false
  resetTestState()
  drawerOpen.value = true
}

const openDetailDrawer = async (account: SubsonicAccountItem) => {
  const requestVersion = ++accountDetailRequestVersion
  const accountKeyAtRequest = accountKey(account)
  currentAccount.value = account
  detailTab.value = 'history'
  detailOpen.value = true
  detailLoading.value = true
  detailError.value = ''
  resetRunDetail()
  resetTestState()
  stopTestPolling()
  pageError.value = ''

  try {
    const data = await auth.request(`/subsonic/accounts/detail?key=${encodeURIComponent(accountKeyAtRequest)}`)
    if (requestVersion !== accountDetailRequestVersion || currentAccountKey.value !== accountKeyAtRequest) return
    currentAccount.value = data.account
    if (currentAccount.value?.run_history?.[0]?.id) {
      await loadRunDetail(currentAccount.value.run_history[0].id)
    }
  } catch (error) {
    if (requestVersion !== accountDetailRequestVersion || currentAccountKey.value !== accountKeyAtRequest) return
    logger.error('Failed to fetch subsonic account detail', error)
    detailError.value = logger.message(error, '账号详情加载失败')
  } finally {
    if (requestVersion === accountDetailRequestVersion) detailLoading.value = false
  }
}

const refreshCurrentAccount = async (preferredRunId?: string) => {
  if (!currentAccountKey.value) return

  const accountKeyAtRequest = currentAccountKey.value
  const requestVersion = ++accountDetailRequestVersion
  const encodedKey = encodeURIComponent(accountKeyAtRequest)
  historyLoading.value = true
  detailError.value = ''

  try {
    const [accountData, runsData] = await Promise.all([
      auth.request(`/subsonic/accounts/detail?key=${encodedKey}`),
      auth.request(`/subsonic/accounts/runs?key=${encodedKey}&limit=20`),
    ])

    if (requestVersion !== accountDetailRequestVersion || currentAccountKey.value !== accountKeyAtRequest) return

    currentAccount.value = {
      ...accountData.account,
      run_history: runsData.runs || [],
    }

    const nextRunId = preferredRunId || selectedRunId.value || currentAccount.value.run_history?.[0]?.id
    if (nextRunId) {
      await loadRunDetail(nextRunId)
    } else {
      resetRunDetail()
    }
  } catch (error) {
    if (requestVersion !== accountDetailRequestVersion || currentAccountKey.value !== accountKeyAtRequest) return
    logger.error('Failed to refresh subsonic account detail', error)
    detailError.value = logger.message(error, '账号详情刷新失败')
  } finally {
    if (requestVersion === accountDetailRequestVersion) historyLoading.value = false
  }
}

const loadRunDetail = async (runId: string) => {
  const accountKeyAtStart = currentAccountKey.value
  selectedRunId.value = runId
  runDetailLoading.value = true
  detailError.value = ''

  try {
    const data = await fetchRunBundle(runId)
    if (!detailOpen.value || currentAccountKey.value !== accountKeyAtStart || selectedRunId.value !== runId) return
    selectedRun.value = data.run
    selectedRunLogs.value = data.logs
  } catch (error) {
    if (!detailOpen.value || currentAccountKey.value !== accountKeyAtStart || selectedRunId.value !== runId) return
    logger.error('Failed to fetch subsonic run detail', error)
    detailError.value = logger.message(error, '运行记录详情加载失败')
  } finally {
    runDetailLoading.value = false
  }
}

const toggleRunDetail = async (runId: string) => {
  if (selectedRunId.value === runId && !runDetailLoading.value) {
    resetRunDetail()
    return
  }

  await loadRunDetail(runId)
}

const validateForm = () => {
  const errors: string[] = []

  if (!form.value.url.trim()) {
    errors.push('请输入服务地址')
  }

  if (!form.value.username.trim()) {
    errors.push('请输入用户名')
  }

  if (formMode.value === 'create' && !form.value.password) {
    errors.push('创建账号时必须填写密码')
  }

  if (form.value.time_start <= 0 || form.value.time_end <= 0 || form.value.time_end < form.value.time_start) {
    errors.push('播放时长范围无效')
  }

  if (errors.length) {
    formError.value = errors[0]
    scrollFormErrorIntoView()
    return false
  }

  return true
}

const scrollFormErrorIntoView = async () => {
  await nextTick()
  formErrorElement.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const buildFormPayload = () => {
  return {
    url: form.value.url,
    username: form.value.username,
    password: form.value.password,
    name: form.value.name || null,
    enabled: form.value.enabled,
    use_proxy: form.value.use_proxy,
    time: [form.value.time_start, form.value.time_end],
    interval_days: form.value.interval_days || null,
    time_range: form.value.time_range || null,
  }
}

const submitForm = async () => {
  if (!validateForm()) return

  saving.value = true
  formError.value = ''

  const payload = buildFormPayload()

  try {
    if (formMode.value === 'create') {
      await auth.request('/subsonic/accounts', { method: 'POST', body: JSON.stringify(payload) })
    } else {
      await auth.request(`/subsonic/accounts?key=${encodeURIComponent(currentAccountKey.value)}`, { method: 'PUT', body: JSON.stringify(payload) })
    }
    drawerOpen.value = false
    await fetchAccounts()
  } catch (error) {
    logger.error('Failed to save subsonic account', error)
    formError.value = logger.message(error, '保存账号失败')
  } finally {
    saving.value = false
  }
}

const resetRunDetail = () => {
  selectedRunId.value = ''
  selectedRun.value = null
  selectedRunLogs.value = []
}

const resetTestState = () => {
  testRunId.value = ''
  testRun.value = null
  testRunLogs.value = []
  testError.value = ''
}

const sameRunLog = (left: SubsonicRunLog | null | undefined, right: SubsonicRunLog | null | undefined) => {
  if (!left || !right) return false

  return left.time === right.time
    && left.level === right.level
    && left.message === right.message
}

const appendTestRunLog = (item: SubsonicRunLog) => {
  if (testRunLogs.value.some((log) => sameRunLog(log, item))) {
    return
  }

  testRunLogs.value = [item, ...testRunLogs.value]
}

let testPollTimer: number | null = null

const stopTestPolling = () => {
  if (testPollTimer !== null) {
    window.clearInterval(testPollTimer)
    testPollTimer = null
  }
}

const {
  isConnected: testLogsConnected,
  connect: connectTestLogsStream,
  disconnect: disconnectTestLogsStream,
} = useSSE(testLogsEndpoint, {
  onEvent: (event) => {
    if (event.type !== 'message' || !testRunId.value) return

    const item = event.data as SubsonicRunLog & { run_id?: string | null }
    if (item.run_id !== testRunId.value) return

    appendTestRunLog({
      level: item.level,
      message: item.message,
      time: item.time,
    })
  },
  onError: (streamError) => {
    if (((detailOpen.value && detailTab.value === 'test') || formTestActive.value) && testRunId.value) {
      logger.error('Failed to stream test logs', streamError)
    }
  },
})

const syncTestLogsStream = () => {
  const nextEndpoint = ((detailOpen.value && detailTab.value === 'test') || formTestActive.value) && testRunId.value
    ? `/runinfo/logs/stream?include_children=true&keyword=${encodeURIComponent(testRunId.value)}`
    : null

  if (!nextEndpoint) {
    if (testLogsEndpoint.value) {
      disconnectTestLogsStream()
      testLogsEndpoint.value = null
    }
    return
  }

  if (testLogsEndpoint.value !== nextEndpoint) {
    disconnectTestLogsStream()
    testLogsEndpoint.value = nextEndpoint
    connectTestLogsStream()
    return
  }

  if (!testLogsConnected.value) {
    connectTestLogsStream()
  }
}

const fetchRunBundle = async (runId: string) => {
  const [runData, logData] = await Promise.all([
    auth.request(`/runinfo/${runId}`),
    auth.request(`/runinfo/${runId}/logs?limit=200&include_children=true`),
  ])

  return {
    run: runData.run as SubsonicRunItem,
    logs: (logData.logs || []) as SubsonicRunLog[],
  }
}

const refreshTestRun = async (silent = false) => {
  if (!testRunId.value) return

  if (!silent) {
    testError.value = ''
  }

  try {
    const runData = await auth.request(`/runinfo/${testRunId.value}`)
    testRun.value = runData.run as SubsonicRunItem

    if (!isActiveRun(testRun.value?.status)) {
      stopTestPolling()
      await refreshCurrentAccount(testRunId.value)
    }
  } catch (error) {
    logger.error('Failed to refresh test run', error)
    if (!silent) {
      testError.value = logger.message(error, '测试日志加载失败')
    }
  }
}

const startTestPolling = () => {
  stopTestPolling()
  if (!testRunId.value) return

  testPollTimer = window.setInterval(() => {
    refreshTestRun(true)
  }, 2000)
}

const startFormTestRun = async () => {
  if (!validateForm()) return

  formTestActive.value = true
  testStarting.value = true
  testError.value = ''
  stopTestPolling()

  try {
    const key = formMode.value === 'edit' && currentAccountKey.value
      ? `?key=${encodeURIComponent(currentAccountKey.value)}`
      : ''
    const data = await auth.request(`/subsonic/accounts/test-run${key}`, {
      method: 'POST',
      body: JSON.stringify(buildFormPayload()),
    })
    testRunId.value = data.run_id || ''

    if (!testRunId.value) {
      throw new Error('测试任务已提交，但暂时还没有可读取的运行记录')
    }

    const bundle = await fetchRunBundle(testRunId.value)
    testRun.value = bundle.run
    testRunLogs.value = bundle.logs
    syncTestLogsStream()
    await refreshTestRun()
    if (isActiveRun(testRun.value?.status)) {
      startTestPolling()
    }
  } catch (error) {
    logger.error('Failed to start subsonic account config test run', error)
    testError.value = logger.message(error, '启动测试失败')
  } finally {
    testStarting.value = false
  }
}

const startAccountTestRun = async () => {
  if (!currentAccountKey.value) return

  testStarting.value = true
  testError.value = ''
  detailTab.value = 'test'
  stopTestPolling()

  try {
    const encodedKey = encodeURIComponent(currentAccountKey.value)
    const data = await auth.request(`/subsonic/accounts/test-run?key=${encodedKey}`, { method: 'POST' })
    testRunId.value = data.run_id || ''

    if (!testRunId.value) {
      await refreshCurrentAccount()
      const fallbackRun = currentAccount.value?.run_history?.find((run) => isActiveRun(run.status)) || currentAccount.value?.run_history?.[0]
      testRunId.value = fallbackRun?.id || ''
    }

    if (!testRunId.value) {
      throw new Error('测试任务已提交，但暂时还没有可读取的运行记录')
    }

    const bundle = await fetchRunBundle(testRunId.value)
    testRun.value = bundle.run
    testRunLogs.value = bundle.logs
    syncTestLogsStream()
    await refreshTestRun()
    if (isActiveRun(testRun.value?.status)) {
      startTestPolling()
    }
  } catch (error) {
    logger.error('Failed to start subsonic account test run', error)
    testError.value = logger.message(error, '启动测试失败')
  } finally {
    testStarting.value = false
  }
}

const isActiveRun = (status?: string | null) => ['PENDING', 'INITIALIZING', 'RUNNING'].includes(String(status || ''))

const runStatusVariant = (status?: string | null) => {
  if (status === 'SUCCESS') return 'success'
  if (status === 'RUNNING' || status === 'INITIALIZING') return 'info'
  if (status === 'PENDING') return 'warning'
  if (status === 'FAIL' || status === 'FAILED' || status === 'ERROR') return 'error'
  return 'default'
}

const formatDateTime = (value?: string | null) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('zh-CN')
}

const formatRunDuration = (value?: number | null) => {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-'
  if (value < 60) return `${value.toFixed(1)} 秒`

  const minutes = Math.floor(value / 60)
  const seconds = Math.round(value % 60)
  return `${minutes} 分 ${seconds} 秒`
}

const mapRunLogsToTimeline = (items: SubsonicRunLog[]) => {
  return items.map((log) => ({
    time: formatDateTime(log.time),
    title: log.message,
    description: log.level || 'INFO',
    type:
      log.level === 'ERROR'
        ? 'error'
        : log.level === 'WARNING'
          ? 'warning'
          : log.level === 'SUCCESS'
            ? 'success'
            : 'default',
  }))
}

const testRunTimeline = computed(() => mapRunLogsToTimeline(testRunLogs.value))

const deleteAccount = async (account: SubsonicAccountItem) => {
  const key = accountKey(account)
  deleting.value = key
  pageError.value = ''
  try {
    await auth.request(`/subsonic/accounts?key=${encodeURIComponent(key)}`, { method: 'DELETE' })
    if (currentAccountKey.value === key) {
      currentAccount.value = null
      detailOpen.value = false
    }
    await fetchAccounts()
  } catch (error) {
    logger.error('Failed to delete subsonic account', error)
    pageError.value = logger.message(error, '删除账号失败')
  } finally {
    deleting.value = null
  }
}

onMounted(() => {
  fetchAccounts()
})

watch(detailOpen, (open) => {
  if (!open) {
    accountDetailRequestVersion++
    stopTestPolling()
    disconnectTestLogsStream()
    testLogsEndpoint.value = null
    detailLoading.value = false
    historyLoading.value = false
    runDetailLoading.value = false
    detailError.value = ''
    resetRunDetail()
    resetTestState()
    detailTab.value = 'history'
  }
})

watch(drawerOpen, (open) => {
  if (!open) {
    stopTestPolling()
    disconnectTestLogsStream()
    testLogsEndpoint.value = null
    formTestActive.value = false
    resetTestState()
  }
})

onBeforeUnmount(() => {
  stopTestPolling()
  disconnectTestLogsStream()
})

watch([drawerOpen, detailOpen, detailTab, testRunId, formTestActive], () => {
  syncTestLogsStream()
})
</script>

<template>
  <div class="space-y-8">
    <section class="overflow-hidden rounded-[30px] border border-orange-200/70 bg-gradient-to-br from-orange-50 via-white to-amber-50 shadow-[0_24px_80px_-40px_rgba(217,119,6,0.28)]">
      <div class="px-4 py-5 sm:px-6 sm:py-6 xl:px-8">
        <div class="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
        <div class="space-y-3">
          <div class="inline-flex items-center gap-2 rounded-full bg-orange-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-orange-700 ring-1 ring-orange-200">
            <MusicalNoteIcon class="h-4 w-4" aria-hidden="true" />
            Subsonic
          </div>
          <div>
            <h1 class="text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">Subsonic</h1>
            <p class="mt-2 max-w-2xl text-sm leading-6 text-slate-600">管理账号与全局播放调度策略。</p>
          </div>
        </div>
        <div class="inline-flex items-center gap-3 self-start rounded-full border border-white/80 bg-white/85 px-4 py-2 shadow-sm ring-1 ring-orange-100 sm:mt-1 sm:self-auto">
          <span class="text-sm font-medium text-slate-900">启用</span>
          <Switch :model-value="summary.module_enabled" :disabled="moduleSaving" size="sm" @change="saveSubsonicModuleSetting" />
        </div>
        </div>
        <div class="mt-6 rounded-[24px] border border-white/80 bg-white/80 px-5 py-4 shadow-sm ring-1 ring-orange-100">
          <p class="text-xs uppercase tracking-[0.18em] text-slate-400">运行时间</p>
          <div class="mt-4 grid gap-3 sm:grid-cols-3 sm:gap-4">
            <div>
              <p class="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">时段</p>
              <p class="mt-1 text-sm font-semibold text-slate-950">{{ summaryDisplay.timeRange }}</p>
            </div>
            <div>
              <p class="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">间隔</p>
              <p class="mt-1 text-sm font-semibold text-slate-950">{{ summaryDisplay.interval }}</p>
            </div>
            <div>
              <p class="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">并发</p>
              <p class="mt-1 text-sm font-semibold text-slate-950">{{ summaryDisplay.concurrency }}</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <UiCard class="overflow-hidden border-slate-200/70 bg-white/90">
      <template #header>
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 class="text-lg font-semibold tracking-tight text-slate-950">账号列表</h2>
            <p class="mt-1 text-sm text-slate-500">按账号查看播放时长、代理与调度覆盖。</p>
          </div>
          <div class="flex shrink-0 flex-wrap items-center gap-2">
            <div class="inline-flex items-center rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-500 ring-1 ring-slate-200">
              共 {{ filteredAccounts.length }} / {{ accounts.length }} 个账号
            </div>
            <UiButton size="sm" @click="openCreateDrawer">
              <PlusIcon class="mr-2 h-4 w-4" />
              新增账号
            </UiButton>
          </div>
        </div>
      </template>

      <div class="min-w-0 rounded-[26px] border border-slate-200/70 bg-slate-50/80 p-3 sm:p-4">
        <div class="mb-5 grid min-w-0 grid-cols-2 gap-3 lg:grid-cols-[minmax(0,1fr)_180px_200px]">
          <div class="relative col-span-2 min-w-0 lg:col-span-1">
            <label for="subsonic-search" class="sr-only">搜索账号</label>
            <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
              <MagnifyingGlassIcon class="h-5 w-5 text-gray-400" />
            </div>
            <input id="subsonic-search" v-model="search" type="text" placeholder="搜索用户名、域名" class="block w-full rounded-[18px] border-0 bg-white py-3 pl-10 pr-4 text-slate-900 ring-1 ring-inset ring-slate-200 placeholder:text-slate-400 focus:ring-2 focus:ring-primary-600" />
          </div>
          <UiSelect v-model="statusFilter" :options="statusFilterOptions" aria-label="筛选账号状态" class="min-w-0 w-full" />
          <UiSelect v-model="featureFilter" :options="featureFilterOptions" aria-label="筛选账号特性" class="min-w-0 w-full" />
        </div>

        <div v-if="pageError" class="mb-4 rounded-[20px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {{ pageError }}
        </div>

        <div v-if="loading" class="rounded-[24px] border border-dashed border-slate-300 bg-white/70 px-6 py-16 text-center">
          <div class="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-orange-50 text-orange-500 ring-1 ring-orange-100">
            <div class="h-7 w-7 animate-spin rounded-full border-2 border-orange-200 border-t-orange-500"></div>
          </div>
          <p class="mt-5 text-base font-medium text-slate-700">正在加载 Subsonic 账号</p>
          <p class="mt-2 text-sm text-slate-500">请稍候，列表准备好后会直接显示在这里。</p>
        </div>

        <div v-else-if="filteredAccounts.length === 0" class="rounded-[24px] border border-dashed border-slate-300 bg-white/70 px-6 py-16 text-center">
          <MusicalNoteIcon class="mx-auto mb-4 h-16 w-16 text-orange-200" />
          <p class="text-base font-medium text-slate-700">没有符合条件的 Subsonic 账号</p>
          <p class="mt-2 text-sm text-slate-500">调整筛选条件或新增账号后再试。</p>
        </div>

        <div v-else class="grid grid-cols-1 gap-4 md:grid-cols-2 2xl:grid-cols-3">
          <UiCard v-for="account in filteredAccounts" :key="accountKey(account)" hover>
            <div class="mb-4 flex items-start justify-between gap-4">
              <div class="flex min-w-0 flex-1 items-center gap-3">
                <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-[20px] bg-gradient-to-br from-orange-500 to-amber-500 shadow-lg shadow-orange-500/20">
                  <MusicalNoteIcon class="h-6 w-6 text-white" />
                </div>
                <div class="min-w-0 flex-1">
                  <div class="break-words font-semibold text-slate-900">{{ account.username }}</div>
                  <div class="mt-0.5 truncate text-xs text-slate-500">{{ account.url }}</div>
                </div>
              </div>
              <UiBadge :variant="account.enabled ? 'success' : 'default'">
                {{ account.enabled ? '启用' : '停用' }}
              </UiBadge>
            </div>

            <div class="flex flex-wrap gap-2">
              <UiBadge :variant="account.use_proxy ? 'info' : 'default'">代理</UiBadge>
              <UiBadge :variant="account.interval_days ? 'warning' : 'default'">单独间隔</UiBadge>
              <UiBadge :variant="account.time_range ? 'success' : 'default'">单独时段</UiBadge>
            </div>

            <div class="mt-5 flex flex-wrap gap-2">
              <UiButton size="sm" variant="ghost" @click="openDetailDrawer(account)">查看</UiButton>
              <UiButton size="sm" variant="secondary" @click="openEditDrawer(account)">
                <PencilSquareIcon class="mr-2 h-4 w-4" />
                编辑
              </UiButton>
              <UiButton size="sm" variant="danger" :loading="deleting === accountKey(account)" @click="deleteAccount(account)">
                <TrashIcon class="mr-2 h-4 w-4" />
                删除
              </UiButton>
            </div>
          </UiCard>
        </div>
      </div>
    </UiCard>

    <UiDrawer v-model="drawerModel" :title="drawerTitle">
      <div class="space-y-6">
        <div v-if="formError" ref="formErrorElement" class="rounded-[20px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {{ formError }}
        </div>

        <UiCard>
          <div class="grid gap-4 sm:grid-cols-2">
            <label class="space-y-2 text-sm text-slate-600 sm:col-span-2">
              <span class="font-medium text-slate-900">服务地址</span>
              <input v-model="form.url" type="text" placeholder="https://demo.example.com" class="block w-full rounded-[18px] border-0 bg-slate-50 px-4 py-3 text-slate-900 ring-1 ring-inset ring-slate-200 focus:ring-2 focus:ring-primary-600" />
            </label>
            <label class="space-y-2 text-sm text-slate-600">
              <span class="font-medium text-slate-900">用户名</span>
              <input v-model="form.username" type="text" class="block w-full rounded-[18px] border-0 bg-slate-50 px-4 py-3 text-slate-900 ring-1 ring-inset ring-slate-200 focus:ring-2 focus:ring-primary-600" />
            </label>
            <label class="space-y-2 text-sm text-slate-600">
              <span class="font-medium text-slate-900">密码</span>
              <input v-model="form.password" type="password" :placeholder="formMode === 'edit' ? '留空则保持原密码' : ''" class="block w-full rounded-[18px] border-0 bg-slate-50 px-4 py-3 text-slate-900 ring-1 ring-inset ring-slate-200 focus:ring-2 focus:ring-primary-600" />
            </label>
            <label class="space-y-2 text-sm text-slate-600 sm:col-span-2">
              <span class="font-medium text-slate-900">显示名称</span>
              <input v-model="form.name" type="text" placeholder="可选" class="block w-full rounded-[18px] border-0 bg-slate-50 px-4 py-3 text-slate-900 ring-1 ring-inset ring-slate-200 focus:ring-2 focus:ring-primary-600" />
            </label>
          </div>
        </UiCard>

        <UiCard>
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="flex items-center justify-between gap-3 rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <span>启用账号</span>
              <input v-model="form.enabled" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-600" />
            </label>
            <label class="flex items-center justify-between gap-3 rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <span>使用代理</span>
              <input v-model="form.use_proxy" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-600" />
            </label>
          </div>
        </UiCard>

        <UiCard>
          <h3 class="text-base font-semibold text-slate-950">播放与调度</h3>
          <div class="mt-4 space-y-6">
            <div class="space-y-4">
              <div class="space-y-1.5">
                <p class="text-sm font-medium text-slate-900">播放时长随机范围</p>
                <p class="text-xs leading-5 text-slate-400">系统会在这个秒数区间内随机选择本次需要补足的播放时长。</p>
              </div>
              <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:items-end">
                <label class="space-y-2 text-sm text-slate-600">
                  <span class="text-xs font-medium text-slate-500">起始时长</span>
                  <input v-model.number="form.time_start" type="number" min="1" class="block w-full rounded-[16px] border-0 bg-white px-4 py-3 text-sm text-slate-900 ring-1 ring-inset ring-slate-200 focus:ring-2 focus:ring-primary-600" />
                </label>
                <div class="pb-3 text-center text-lg font-semibold text-slate-300">~</div>
                <label class="space-y-2 text-sm text-slate-600">
                  <span class="text-xs font-medium text-slate-500">结束时长</span>
                  <input v-model.number="form.time_end" type="number" min="1" class="block w-full rounded-[16px] border-0 bg-white px-4 py-3 text-sm text-slate-900 ring-1 ring-inset ring-slate-200 focus:ring-2 focus:ring-primary-600" />
                </label>
              </div>
            </div>
            <div class="border-t border-slate-200 pt-5">
              <UiScheduleIntervalOverride v-model="form.interval_days" variant="plain" label="单独间隔天数" helper-text="可让当前账号沿用全局间隔，或单独指定固定天数 / 区间天数。" :global-value="summary.interval_days" />
            </div>
            <div class="border-t border-slate-200 pt-5">
              <UiScheduleTimeOverride v-model="form.time_range" variant="plain" label="单独执行时段" helper-text="可让当前账号沿用全局时段，或单独指定每天固定时间 / 时间范围。" :global-value="summary.time_range" />
            </div>
          </div>
        </UiCard>

        <div v-if="formTestActive" class="rounded-[20px] border border-slate-200 bg-slate-50/70 p-4">
          <div class="flex items-center justify-between gap-3">
            <div class="flex items-center gap-2">
              <h4 class="text-sm font-semibold text-slate-900">连接测试</h4>
              <ArrowPathIcon v-if="testLogsConnected" class="h-4 w-4 animate-spin text-emerald-500" />
            </div>
            <UiBadge v-if="testRun" :variant="runStatusVariant(testRun.status)">{{ testRun.status || 'UNKNOWN' }}</UiBadge>
          </div>

          <div v-if="testError" class="mt-3 rounded-[16px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            {{ testError }}
          </div>

          <div v-if="testRun" class="mt-3">
            <p class="break-all text-xs text-slate-500">任务 {{ testRun.id }}</p>
            <p v-if="testRun.status_info" class="mt-1 text-sm text-slate-600">{{ testRun.status_info }}</p>
          </div>

          <div v-if="testRunTimeline.length" class="mt-3">
            <UiTimeline :items="testRunTimeline" />
          </div>

          <div v-else-if="!testRun && !testError" class="mt-3 rounded-[16px] border border-dashed border-slate-200 bg-white/70 px-4 py-6 text-center text-sm text-slate-500">
            点击下方「测试配置」按钮，会立即检查账号能否正常登录并访问站点，结果会实时显示在这里。
          </div>
        </div>

      </div>
      <template #footer>
        <div class="flex flex-wrap justify-end gap-2">
          <UiButton variant="outline" :loading="testStarting" @click="startFormTestRun">
            测试配置
          </UiButton>
          <UiButton variant="outline" @click="drawerModel = false">取消</UiButton>
          <UiButton :loading="saving" @click="submitForm">保存账号</UiButton>
        </div>
      </template>
    </UiDrawer>

    <UiDrawer v-model="detailOpen" title="账号详情">
      <div v-if="currentAccount" class="space-y-5">
        <div class="rounded-[20px] border border-slate-200/80 bg-slate-50/70 p-4">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                <h3 class="text-base font-semibold text-slate-950">{{ currentAccount.username }}</h3>
                <UiBadge :variant="currentAccount.enabled ? 'success' : 'default'">
                  {{ currentAccount.enabled ? '启用' : '停用' }}
                </UiBadge>
                <span class="mx-0.5 h-3.5 w-px bg-slate-300/70"></span>
                <span class="flex flex-wrap items-center gap-1">
                  <UiBadge size="sm" :variant="currentAccount.use_proxy ? 'info' : 'default'">代理</UiBadge>
                  <UiBadge size="sm" :variant="currentAccount.interval_days ? 'warning' : 'default'">单独间隔</UiBadge>
                  <UiBadge size="sm" :variant="currentAccount.time_range ? 'success' : 'default'">单独时段</UiBadge>
                </span>
              </div>
              <p class="mt-1 break-all text-sm text-slate-500">{{ currentAccount.url }}</p>
            </div>
            <UiButton size="sm" variant="secondary" class="shrink-0" @click="openEditDrawer(currentAccount)">
              <PencilSquareIcon class="mr-1.5 h-4 w-4" />
              编辑
            </UiButton>
          </div>

          <div class="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5">
            <div v-for="item in accountDetailItems" :key="item.label" class="flex items-baseline justify-between gap-2 rounded-[12px] border border-slate-200/80 bg-white px-3 py-1.5">
              <p class="shrink-0 text-xs text-slate-400">{{ item.label }}</p>
              <p class="truncate text-sm font-medium text-slate-900">{{ item.value }}</p>
            </div>
          </div>
        </div>

        <div class="rounded-[20px] border border-slate-200 bg-slate-50 p-1">
          <div class="grid grid-cols-2 gap-1">
            <button
              v-for="tab in detailTabs"
              :key="tab.key"
              type="button"
              class="rounded-[16px] px-3 py-2 text-sm font-medium transition"
              :class="detailTab === tab.key ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
              @click="detailTab = tab.key"
            >
              {{ tab.label }}
            </button>
          </div>
        </div>

        <div v-if="detailError" class="rounded-[20px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {{ detailError }}
        </div>

        <div v-if="detailLoading" class="rounded-[24px] border border-dashed border-slate-300 bg-white/70 px-6 py-12 text-center">
          <div class="mx-auto h-10 w-10 animate-spin rounded-full border-2 border-emerald-200 border-t-emerald-500"></div>
          <p class="mt-4 text-sm text-slate-500">正在加载账号详情</p>
        </div>

        <template v-else>
          <div v-if="detailTab === 'history'">
            <UiCard padding="sm">
              <div class="flex items-center justify-between gap-3">
                <div>
                  <h4 class="text-base font-semibold text-slate-950">运行记录</h4>
                  <p class="mt-0.5 text-sm text-slate-500">查看该账号最近的保活执行和每次运行的详细日志。</p>
                </div>
                <UiButton size="sm" variant="secondary" :loading="historyLoading" @click="refreshCurrentAccount()">
                  刷新
                </UiButton>
              </div>

              <div v-if="historyLoading && !(currentAccount.run_history || []).length" class="mt-4 space-y-2.5">
                <div v-for="index in 3" :key="index" class="h-16 animate-pulse rounded-[16px] bg-slate-100"></div>
              </div>

              <div v-else-if="!(currentAccount.run_history || []).length" class="mt-4 rounded-[16px] border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
                还没有这个账号的运行记录。
              </div>

              <div v-else class="mt-4 space-y-2.5">
                <div v-for="run in currentAccount.run_history" :key="run.id">
                  <button
                    type="button"
                    class="w-full rounded-[16px] border px-3.5 py-3 text-left transition"
                    :class="selectedRunId === run.id ? 'border-emerald-300 bg-emerald-50/70' : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'"
                    @click="toggleRunDetail(run.id)"
                  >
                    <div class="flex items-start justify-between gap-3">
                      <div class="min-w-0">
                        <div class="flex flex-wrap items-center gap-2">
                          <p class="text-sm font-semibold text-slate-900">{{ run.description || 'Subsonic 保活任务' }}</p>
                          <UiBadge :variant="runStatusVariant(run.status)">{{ run.status || 'UNKNOWN' }}</UiBadge>
                        </div>
                        <p class="mt-1.5 text-xs text-slate-500">开始于 {{ formatDateTime(run.start_time) }}</p>
                        <p v-if="run.status_info" class="mt-1 text-sm text-slate-600">{{ run.status_info }}</p>
                      </div>
                      <div class="flex shrink-0 items-start gap-2 text-right text-xs text-slate-500">
                        <div>
                          <p>耗时 {{ formatRunDuration(run.duration) }}</p>
                          <p class="mt-1">ID {{ run.id }}</p>
                        </div>
                        <ChevronDownIcon class="mt-0.5 h-4 w-4 text-slate-400 transition" :class="selectedRunId === run.id ? 'rotate-180' : ''" aria-hidden="true" />
                      </div>
                    </div>
                  </button>

                  <div
                    v-if="selectedRunId === run.id && (runDetailLoading || selectedRun)"
                    class="mt-2 rounded-[16px] border border-slate-200 bg-slate-50/70 px-3.5 py-3.5"
                  >
                    <div v-if="runDetailLoading" class="rounded-[14px] border border-dashed border-slate-200 bg-white px-4 py-6 text-center text-sm text-slate-500">
                      正在加载运行详情
                    </div>

                    <template v-else-if="selectedRun">
                      <div v-if="selectedRunTimeline.length">
                        <UiTimeline :items="selectedRunTimeline" />
                      </div>
                      <div v-else class="rounded-[14px] border border-dashed border-slate-200 bg-white px-4 py-6 text-center text-sm text-slate-500">
                        这条运行记录暂时没有日志。
                      </div>
                    </template>
                  </div>
                </div>
              </div>
            </UiCard>
          </div>

          <div v-else>
            <UiCard padding="sm">
              <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div class="flex items-center gap-2">
                  <h4 class="text-base font-semibold text-slate-950">测试运行</h4>
                  <ArrowPathIcon v-if="testLogsConnected" class="h-4 w-4 animate-spin text-emerald-500" />
                </div>
                <UiButton :loading="testStarting" @click="startAccountTestRun">
                  立刻运行
                </UiButton>
              </div>

              <div v-if="testError" class="mt-4 rounded-[16px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                {{ testError }}
              </div>

              <div v-if="testRun" class="mt-4 grid grid-cols-2 gap-2">
                <div class="rounded-[14px] border border-slate-200/80 bg-slate-50 px-3 py-2.5">
                  <p class="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-400">当前测试任务</p>
                  <p class="mt-1 break-all text-sm font-medium text-slate-900">{{ testRun.id }}</p>
                </div>
                <div class="rounded-[14px] border border-slate-200/80 bg-slate-50 px-3 py-2.5">
                  <p class="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-400">状态</p>
                  <div class="mt-1 flex items-center gap-2">
                    <UiBadge :variant="runStatusVariant(testRun.status)">{{ testRun.status || 'UNKNOWN' }}</UiBadge>
                    <span class="text-sm text-slate-600">{{ testRun.status_info || '执行中' }}</span>
                  </div>
                </div>
              </div>

              <div v-else class="mt-4 rounded-[16px] border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
                点击上方按钮后，会在这里显示本次测试任务和日志。
              </div>

              <div v-if="testRun || testRunTimeline.length" class="mt-4">
                <div v-if="testRunTimeline.length">
                  <UiTimeline :items="testRunTimeline" />
                </div>

                <div v-else class="rounded-[16px] border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
                  还没有测试日志。
                </div>
              </div>
            </UiCard>
          </div>
        </template>
      </div>
    </UiDrawer>
  </div>
</template>