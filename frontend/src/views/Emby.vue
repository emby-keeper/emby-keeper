<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot } from '@headlessui/vue'
import { ArrowPathIcon, CheckCircleIcon, ChevronDownIcon, InformationCircleIcon, MagnifyingGlassIcon, PencilSquareIcon, PlusIcon, TrashIcon, TvIcon, XCircleIcon } from '@heroicons/vue/24/outline'
import UiCard from '@/components/ui/UiCard.vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDrawer from '@/components/ui/UiDrawer.vue'
import UiSelect, { type UiSelectOption } from '@/components/ui/UiSelect.vue'
import UiScheduleIntervalOverride from '@/components/ui/UiScheduleIntervalOverride.vue'
import UiScheduleTimeOverride from '@/components/ui/UiScheduleTimeOverride.vue'
import UiTimeline from '@/components/ui/UiTimeline.vue'
import UiTooltip from '@/components/ui/UiTooltip.vue'
import Switch from '@/components/Switch.vue'
import { useSSE } from '@/composables/useSSE'
import { useAuthStore } from '@/stores/auth'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { formatScheduleConcurrency, formatScheduleInterval, formatScheduleTimeRange } from '@/utils/schedulerDisplay'
import { logger } from '@/utils/logger'

type EmbyRunItem = {
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

type EmbyRunLog = {
  level?: string | null
  message: string
  time?: string | null
}

type EmbyDeviceCache = {
  client?: string | null
  device?: string | null
  device_id?: string | null
  client_version?: string | null
  useragent?: string | null
}

type EmbyAccountItem = {
  id: string
  url: string
  username: string
  name?: string | null
  site_title?: string | null
  card_title?: string | null
  card_subtitle?: string | null
  hostname?: string | null
  enabled: boolean
  allow_stream: boolean
  use_proxy: boolean
  cf_challenge: boolean
  allow_multiple: boolean
  play_id?: string | null
  time: number | number[]
  interval_days?: string | null
  time_range?: string | null
  watch_history?: Array<{ status: 'success' | 'failed', time: string }>
  device_cache?: EmbyDeviceCache | null
  run_history?: EmbyRunItem[]
}

type EmbyForm = {
  url: string
  username: string
  password: string
  name: string
  enabled: boolean
  use_proxy: boolean
  allow_stream: boolean
  cf_challenge: boolean
  allow_multiple: boolean
  play_id: string
  time_start: number
  time_end: number
  interval_days: string
  time_range: string
}

const auth = useAuthStore()
const accounts = ref<EmbyAccountItem[]>([])
const summary = ref({ total: 0, enabled: 0, use_proxy: 0, allow_stream: 0, cf_challenge: 0, concurrency: 1, time_range: '', interval_days: '', module_enabled: true })
const loading = ref(true)
const saving = ref(false)
const moduleSaving = ref(false)
const deleting = ref<string | null>(null)
const deleteDialogOpen = ref(false)
const pendingDeleteAccount = ref<EmbyAccountItem | null>(null)
const search = ref('')
const statusFilter = ref<'all' | 'enabled' | 'disabled'>('all')
const featureFilter = ref<'all' | 'use_proxy' | 'allow_stream' | 'cf_challenge' | 'allow_multiple'>('all')
const drawerOpen = ref(false)
const detailOpen = ref(false)
const currentAccount = ref<EmbyAccountItem | null>(null)
const detailTab = ref<'history' | 'device' | 'test'>('history')
const detailLoading = ref(false)
const historyLoading = ref(false)
const runDetailLoading = ref(false)
let accountDetailRequestVersion = 0
const detailError = ref('')
const selectedRunId = ref('')
const selectedRun = ref<EmbyRunItem | null>(null)
const selectedRunLogs = ref<EmbyRunLog[]>([])
const testStarting = ref(false)
const testRunId = ref('')
const testRun = ref<EmbyRunItem | null>(null)
const testRunLogs = ref<EmbyRunLog[]>([])
const testLogsEndpoint = ref<string | null>(null)
const testError = ref('')
const formMode = ref<'create' | 'edit'>('create')
const formError = ref('')
const formTestActive = ref(false)
const formErrorElement = ref<HTMLElement | null>(null)
const pageError = ref('')
const probeStarting = ref(false)
const probeResult = ref<{ success: boolean; message: string } | null>(null)
const form = ref<EmbyForm>({
  url: '',
  username: '',
  password: '',
  name: '',
  enabled: true,
  use_proxy: true,
  allow_stream: false,
  cf_challenge: true,
  allow_multiple: true,
  play_id: '',
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

    return [account.username, account.url, account.name, account.play_id]
      .some((value) => String(value || '').toLowerCase().includes(keyword))
  })
})

const drawerTitle = computed(() => formMode.value === 'create' ? '新增 Emby 账号' : '编辑 Emby 账号')
const currentAccountKey = computed(() => currentAccount.value?.id || '')
const statusFilterOptions: UiSelectOption[] = [
  { label: '全部状态', value: 'all' },
  { label: '仅启用', value: 'enabled' },
  { label: '仅停用', value: 'disabled' },
]
const featureFilterOptions: UiSelectOption[] = [
  { label: '全部特性', value: 'all' },
  { label: '使用代理', value: 'use_proxy' },
  { label: '允许流播放', value: 'allow_stream' },
  { label: 'CF 检测', value: 'cf_challenge' },
  { label: '允许多开', value: 'allow_multiple' },
]
const summaryDisplay = computed(() => ({
  timeRange: formatScheduleTimeRange(summary.value.time_range),
  interval: formatScheduleInterval(summary.value.interval_days),
  concurrency: formatScheduleConcurrency(summary.value.concurrency),
}))
const detailTabs = [
  { key: 'history' as const, label: '运行记录' },
  { key: 'device' as const, label: '缓存设备' },
  { key: 'test' as const, label: '测试' },
]
const deviceEntries = computed(() => {
  const device = currentAccount.value?.device_cache
  if (!device) return []

  return [
    { label: '客户端', value: device.client },
    { label: '设备名', value: device.device },
    { label: '设备 ID', value: device.device_id },
    { label: '版本', value: device.client_version },
    { label: 'User-Agent', value: device.useragent },
  ].filter((item) => item.value)
})
const selectedRunTimeline = computed(() => mapRunLogsToTimeline(selectedRunLogs.value))
const testRunTimeline = computed(() => mapRunLogsToTimeline(testRunLogs.value))
const accountDetailItems = computed(() => {
  if (!currentAccount.value) {
    return []
  }

  return [
    { label: '用户名', value: currentAccount.value.username },
    { label: '播放时长', value: Array.isArray(currentAccount.value.time) ? `${currentAccount.value.time[0]} - ${currentAccount.value.time[1]} 秒` : '-' },
    { label: '单独间隔', value: formatScheduleInterval(currentAccount.value.interval_days) },
    { label: '单独时段', value: formatScheduleTimeRange(currentAccount.value.time_range) },
    { label: '指定播放 ID', value: currentAccount.value.play_id || '-' },
  ]
})

const accountMetaChips = (account: EmbyAccountItem) => {
  return [
    formatScheduleTimeRange(account.time_range),
    formatScheduleInterval(account.interval_days),
  ].filter((item) => item && item !== '-')
}

const formatAbsoluteTime = (value?: string | null) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const formatRelativeTime = (value?: string | null) => {
  if (!value) return '暂无记录'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '暂无记录'

  const diff = Date.now() - date.getTime()
  if (diff < 0) {
    return formatAbsoluteTime(value)
  }

  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  if (hours < 24) return `${hours} 小时前`
  if (days === 1) return '昨天'
  if (days < 7) return `${days} 天前`
  return formatAbsoluteTime(value)
}

const formatHistoryStatus = (status?: 'success' | 'failed') => {
  return status === 'success' ? '成功' : '失败'
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

const runStatusVariant = (status?: string | null) => {
  if (status === 'SUCCESS') return 'success'
  if (status === 'RUNNING' || status === 'INITIALIZING') return 'info'
  if (status === 'PENDING') return 'warning'
  if (status === 'FAIL' || status === 'FAILED' || status === 'ERROR') return 'error'
  return 'default'
}

const isActiveRun = (status?: string | null) => ['PENDING', 'INITIALIZING', 'RUNNING'].includes(String(status || ''))

const mapRunLogsToTimeline = (items: EmbyRunLog[]) => {
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

const displayHostname = (account: EmbyAccountItem) => {
  const source = account.hostname || account.url
  try {
    const urlObj = new URL(source.startsWith('http') ? source : `http://${source}`)
    return urlObj.hostname
  } catch {
    return source.replace(/^https?:\/\//, '').split('/')[0].split(':')[0]
  }
}

const accountKey = (account: EmbyAccountItem) => account.id

const openDeleteDialog = (account: EmbyAccountItem) => {
  pendingDeleteAccount.value = account
  deleteDialogOpen.value = true
}

const closeDeleteDialog = (force = false) => {
  if (deleting.value && !force) return
  deleteDialogOpen.value = false
  pendingDeleteAccount.value = null
}

const applyForm = (account?: EmbyAccountItem | null) => {
  const time = typeof account?.time === 'number' ? [account.time, account.time]
    : Array.isArray(account?.time) && account.time.length >= 2 ? account.time : [300, 600]
  form.value = {
    url: account?.url || '',
    username: account?.username || '',
    password: '',
    name: account?.name || '',
    enabled: account?.enabled ?? true,
    use_proxy: account?.use_proxy ?? true,
    allow_stream: account?.allow_stream ?? false,
    cf_challenge: account?.cf_challenge ?? true,
    allow_multiple: account?.allow_multiple ?? true,
    play_id: account?.play_id || '',
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
    const data = await auth.request('/emby/accounts')
    accounts.value = data.accounts || []
    summary.value = data.summary || summary.value
  } catch (error) {
    logger.error('Failed to fetch accounts', error)
    pageError.value = logger.message(error, '账号列表加载失败')
  } finally {
    loading.value = false
  }
}

const saveEmbyModuleSetting = async (enabled: boolean) => {
  moduleSaving.value = true
  pageError.value = ''
  try {
    await auth.request('/emby/settings', {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    })
    await fetchAccounts()
  } catch (error) {
    logger.error('Failed to save emby module setting', error)
    pageError.value = logger.message(error, '全局保活设置保存失败')
    await fetchAccounts()
  } finally {
    moduleSaving.value = false
  }
}

const buildAccountUpdatePayload = (account: EmbyAccountItem, enabled = account.enabled) => {
  const time = typeof account.time === 'number' ? [account.time, account.time]
    : Array.isArray(account.time) && account.time.length >= 2 ? account.time : [300, 600]

  return {
    url: account.url,
    username: account.username,
    password: '',
    name: account.name || null,
    enabled,
    use_proxy: account.use_proxy,
    allow_stream: account.allow_stream,
    cf_challenge: account.cf_challenge,
    allow_multiple: account.allow_multiple,
    play_id: account.play_id || null,
    time: [Number(time[0] || 300), Number(time[1] || 600)],
    interval_days: account.interval_days || null,
    time_range: account.time_range || null,
  }
}

const openCreateDrawer = () => {
  formMode.value = 'create'
  formError.value = ''
  currentAccount.value = null
  applyForm(null)
  stopTestPolling()
  disconnectTestLogsStream()
  testLogsEndpoint.value = null
  formTestActive.value = false
  probeResult.value = null
  resetTestState()
  drawerOpen.value = true
}

const openEditDrawer = (account: EmbyAccountItem) => {
  formMode.value = 'edit'
  formError.value = ''
  currentAccount.value = account
  applyForm(account)
  stopTestPolling()
  disconnectTestLogsStream()
  testLogsEndpoint.value = null
  formTestActive.value = false
  probeResult.value = null
  resetTestState()
  detailOpen.value = false
  drawerOpen.value = true
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

const sameRunLog = (left: EmbyRunLog | null | undefined, right: EmbyRunLog | null | undefined) => {
  if (!left || !right) return false

  return left.time === right.time
    && left.level === right.level
    && left.message === right.message
}

const appendTestRunLog = (item: EmbyRunLog) => {
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

    const item = event.data as EmbyRunLog & { run_id?: string | null }
    if (item.run_id !== testRunId.value) return

    appendTestRunLog({
      level: item.level,
      message: item.message,
      time: item.time,
    })
  },
  onError: (streamError) => {
    if ((detailOpen.value && detailTab.value === 'test' || formTestActive.value) && testRunId.value) {
      logger.error('Failed to stream test logs', streamError)
    }
  },
})

const syncTestLogsStream = () => {
  const nextEndpoint = (detailOpen.value && detailTab.value === 'test' || formTestActive.value) && testRunId.value
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
    run: runData.run as EmbyRunItem,
    logs: (logData.logs || []) as EmbyRunLog[],
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
    const [accountData, runsData, deviceData] = await Promise.all([
      auth.request(`/emby/accounts/detail?key=${encodedKey}`),
      auth.request(`/emby/accounts/runs?key=${encodedKey}&limit=20`),
      auth.request(`/emby/accounts/device?key=${encodedKey}`),
    ])

    if (requestVersion !== accountDetailRequestVersion || currentAccountKey.value !== accountKeyAtRequest) return

    currentAccount.value = {
      ...accountData.account,
      run_history: runsData.runs || [],
      device_cache: deviceData.device || null,
    }

    const nextRunId = preferredRunId || selectedRunId.value || currentAccount.value.run_history?.[0]?.id
    if (nextRunId) {
      await loadRunDetail(nextRunId)
    } else {
      resetRunDetail()
    }
  } catch (error) {
    if (requestVersion !== accountDetailRequestVersion || currentAccountKey.value !== accountKeyAtRequest) return
    logger.error('Failed to refresh emby account detail', error)
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
    logger.error('Failed to fetch run detail', error)
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

const refreshTestRun = async (silent = false) => {
  if (!testRunId.value) return

  if (!silent) {
    testError.value = ''
  }

  try {
    const runData = await auth.request(`/runinfo/${testRunId.value}`)
    testRun.value = runData.run as EmbyRunItem

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

const openDetailDrawer = async (account: EmbyAccountItem) => {
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
    const data = await auth.request(`/emby/accounts/detail?key=${encodeURIComponent(accountKeyAtRequest)}`)
    if (requestVersion !== accountDetailRequestVersion || currentAccountKey.value !== accountKeyAtRequest) return
    currentAccount.value = data.account
    if (currentAccount.value?.run_history?.[0]?.id) {
      await loadRunDetail(currentAccount.value.run_history[0].id)
    }
  } catch (error) {
    if (requestVersion !== accountDetailRequestVersion || currentAccountKey.value !== accountKeyAtRequest) return
    logger.error('Failed to fetch emby account detail', error)
    detailError.value = logger.message(error, '账号详情加载失败')
  } finally {
    if (requestVersion === accountDetailRequestVersion) detailLoading.value = false
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
    const data = await auth.request(`/emby/accounts/test-run?key=${encodedKey}`, { method: 'POST' })
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
    logger.error('Failed to start emby account test run', error)
    testError.value = logger.message(error, '启动测试失败')
  } finally {
    testStarting.value = false
  }
}

const submitForm = async () => {
  if (!validateForm()) return

  saving.value = true
  formError.value = ''

  const payload = buildFormPayload()

  try {
    if (formMode.value === 'create') {
      await auth.request('/emby/accounts', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
    } else {
      await auth.request(`/emby/accounts?key=${encodeURIComponent(currentAccountKey.value)}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      })
    }

    drawerOpen.value = false
    await fetchAccounts()
  } catch (error) {
    logger.error('Failed to save emby account', error)
    formError.value = logger.message(error, '保存账号失败')
  } finally {
    saving.value = false
  }
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
    allow_stream: form.value.allow_stream,
    cf_challenge: form.value.cf_challenge,
    allow_multiple: form.value.allow_multiple,
    play_id: form.value.play_id || null,
    time: [form.value.time_start, form.value.time_end],
    interval_days: form.value.interval_days || null,
    time_range: form.value.time_range || null,
  }
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
    const data = await auth.request(`/emby/accounts/test-run${key}`, {
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
    logger.error('Failed to start emby account config test run', error)
    testError.value = logger.message(error, '启动测试失败')
  } finally {
    testStarting.value = false
  }
}

const testPlayId = async () => {
  const playId = form.value.play_id.trim()

  if (!form.value.url.trim() || !form.value.username.trim()) {
    probeResult.value = { success: false, message: '请先填写服务地址和用户名' }
    return
  }

  if (!playId) {
    probeResult.value = { success: false, message: '请先填写播放 ID' }
    return
  }

  probeStarting.value = true
  probeResult.value = null

  try {
    const query = formMode.value === 'edit' && currentAccountKey.value
      ? `?key=${encodeURIComponent(currentAccountKey.value)}`
      : ''
    const data = await auth.request(`/emby/accounts/probe-item${query}`, {
      method: 'POST',
      body: JSON.stringify({
        url: form.value.url,
        username: form.value.username,
        password: form.value.password,
        name: form.value.name || null,
        use_proxy: form.value.use_proxy,
        cf_challenge: form.value.cf_challenge,
        play_id: playId,
      }),
    })

    const item = data.item || {}
    const parts: string[] = []

    if (item.name) parts.push(String(item.name))
    if (item.series && item.series !== item.name) parts.push(`来自《${item.series}》`)
    if (item.duration_seconds) parts.push(`时长约 ${Math.max(1, Math.round(item.duration_seconds / 60))} 分钟`)

    probeResult.value = {
      success: true,
      message: parts.length ? `播放 ID 可用：${parts.join(' · ')}` : '播放 ID 可用，已成功获取视频项目。',
    }
  } catch (error) {
    logger.error('Failed to probe emby play id', error)
    probeResult.value = { success: false, message: logger.message(error, '测试播放 ID 失败') }
  } finally {
    probeStarting.value = false
  }
}

const deleteAccount = async (account: EmbyAccountItem) => {
  const key = accountKey(account)
  deleting.value = key
  pageError.value = ''

  try {
    await auth.request(`/emby/accounts?key=${encodeURIComponent(key)}`, { method: 'DELETE' })
    if (currentAccountKey.value === key) {
      currentAccount.value = null
      detailOpen.value = false
      stopTestPolling()
    }
    await fetchAccounts()
    closeDeleteDialog(true)
  } catch (error) {
    logger.error('Failed to delete emby account', error)
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
    probeResult.value = null
    resetTestState()
  }
})

onBeforeUnmount(() => {
  stopTestPolling()
  disconnectTestLogsStream()
})

watch([detailOpen, detailTab, testRunId, formTestActive], () => {
  syncTestLogsStream()
})
</script>

<template>
  <div class="space-y-8">
    <section class="overflow-hidden rounded-[30px] border border-emerald-200/70 bg-gradient-to-br from-emerald-50 via-white to-teal-50 shadow-[0_24px_80px_-40px_rgba(5,150,105,0.32)]">
      <div class="px-4 py-5 sm:px-6 sm:py-6 xl:px-8">
        <div class="space-y-5">
          <div class="inline-flex items-center gap-2 rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-emerald-700 ring-1 ring-emerald-200">
            <TvIcon class="h-4 w-4" aria-hidden="true" />
            Emby
          </div>
          <div class="flex flex-col gap-4 md:flex-row md:items-center md:justify-between md:gap-6">
            <div>
              <h1 class="text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">Emby 保活</h1>
              <p class="mt-2 max-w-2xl text-sm leading-6 text-slate-600">管理账号与全局调度策略。</p>
            </div>
            <div class="inline-flex items-center gap-3 self-start rounded-full border border-white/80 bg-white/85 px-4 py-2 shadow-sm ring-1 ring-emerald-100 md:self-center">
              <span class="text-sm font-medium text-slate-900">启用</span>
              <Switch :model-value="summary.module_enabled" :disabled="moduleSaving" size="sm" @change="saveEmbyModuleSetting" />
            </div>
          </div>
        </div>
        <div class="mt-6 rounded-[24px] border border-white/80 bg-white/80 px-5 py-4 shadow-sm ring-1 ring-emerald-100">
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
            <p class="mt-1 text-sm text-slate-500">按账号查看保活相关选项。</p>
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
        <label for="emby-search" class="sr-only">搜索账号</label>
        <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
          <MagnifyingGlassIcon class="h-5 w-5 text-gray-400" />
        </div>
        <input id="emby-search" v-model="search" type="text" placeholder="搜索用户名、域名、播放 ID" class="block w-full rounded-[18px] border-0 bg-white py-3 pl-10 pr-4 text-slate-900 ring-1 ring-inset ring-slate-200 placeholder:text-slate-400 focus:ring-2 focus:ring-primary-600" />
      </div>
      <UiSelect v-model="statusFilter" :options="statusFilterOptions" aria-label="筛选账号状态" class="min-w-0 w-full" />
      <UiSelect v-model="featureFilter" :options="featureFilterOptions" aria-label="筛选账号特性" class="min-w-0 w-full" />
    </div>

    <div v-if="pageError" class="mb-4 rounded-[20px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
      {{ pageError }}
    </div>

    <div v-if="loading" class="rounded-[24px] border border-dashed border-slate-300 bg-white/70 px-6 py-16 text-center">
      <div class="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-50 text-emerald-500 ring-1 ring-emerald-100">
        <div class="h-7 w-7 animate-spin rounded-full border-2 border-emerald-200 border-t-emerald-500"></div>
      </div>
      <p class="mt-5 text-base font-medium text-slate-700">正在加载 Emby 账号</p>
      <p class="mt-2 text-sm text-slate-500">请稍候，列表准备好后会直接显示在这里。</p>
    </div>

    <div v-else-if="filteredAccounts.length === 0" class="rounded-[24px] border border-dashed border-slate-300 bg-white/70 px-6 py-16 text-center">
      <TvIcon class="mx-auto mb-4 h-16 w-16 text-emerald-200" />
      <p class="text-base font-medium text-slate-700">没有符合条件的 Emby 账号</p>
      <p class="mt-2 text-sm text-slate-500">调整筛选条件或新增账号后再试。</p>
    </div>

    <div v-else class="grid grid-cols-1 gap-4 md:grid-cols-2 2xl:grid-cols-3">
      <UiCard v-for="account in filteredAccounts" :key="accountKey(account)" hover padding="none">
        <div
          class="h-full min-w-0 p-4 sm:p-5"
          role="button"
          tabindex="0"
          @click="openDetailDrawer(account)"
          @keydown.enter.prevent="openDetailDrawer(account)"
          @keydown.space.prevent="openDetailDrawer(account)"
        >
          <div class="mb-4 flex items-center justify-between gap-4">
            <div class="flex min-w-0 items-center gap-3">
              <div class="flex h-12 w-12 items-center justify-center rounded-[20px] bg-gradient-to-br from-emerald-500 to-teal-500 shadow-lg shadow-emerald-500/20">
                <TvIcon class="w-6 h-6 text-white" />
              </div>
              <div class="min-w-0">
                <div class="truncate font-semibold text-slate-900">{{ displayHostname(account) }}</div>
                <div class="mt-0.5 truncate text-xs text-slate-500">{{ account.card_subtitle || account.username }}</div>
              </div>
            </div>
          </div>

          <div class="mt-4 border-t border-slate-100 pt-4">
            <div v-if="account.watch_history?.length" class="space-y-2.5 rounded-xl bg-slate-50/50 px-3 py-3">
              <div
                v-for="(record, index) in account.watch_history.slice(0, 2)"
                :key="`${accountKey(account)}-${record.time}-${index}`"
                class="flex items-center justify-between gap-3 text-sm"
              >
                <div class="flex min-w-0 items-center gap-2">
                  <CheckCircleIcon v-if="record.status === 'success'" class="h-4 w-4 shrink-0 text-emerald-500" />
                  <XCircleIcon v-else class="h-4 w-4 shrink-0 text-rose-500" />
                  <span class="font-medium text-slate-700">{{ formatRelativeTime(record.time) }}</span>
                </div>
                <span class="text-xs text-slate-400">{{ formatAbsoluteTime(record.time) }}</span>
              </div>
            </div>
            <div v-else class="rounded-xl bg-slate-50/50 px-3 py-3">
              <p class="text-sm text-slate-400">暂无保活记录</p>
            </div>

            <div v-if="accountMetaChips(account).length" class="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
              <span
                v-for="chip in accountMetaChips(account)"
                :key="`${accountKey(account)}-${chip}`"
                class="rounded-[10px] bg-slate-100/80 px-2 py-0.5"
              >
                {{ chip }}
              </span>
            </div>
          </div>

          <div class="mt-5 flex flex-wrap gap-2" @click.stop>
            <UiButton size="sm" variant="ghost" @click.stop="openDetailDrawer(account)">
              保活记录
            </UiButton>
            <UiButton size="sm" variant="secondary" @click.stop="openEditDrawer(account)">
              <PencilSquareIcon class="mr-2 h-4 w-4" />
              编辑
            </UiButton>
            <UiButton size="sm" variant="danger" :loading="deleting === accountKey(account)" @click.stop="openDeleteDialog(account)">
              <TrashIcon class="mr-2 h-4 w-4" />
              删除
            </UiButton>
          </div>
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
          <h3 class="text-base font-semibold text-slate-950">账号行为</h3>
          <div class="mt-4 grid gap-3 sm:grid-cols-2">
            <label class="flex items-center justify-between gap-3 rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <span class="flex items-center gap-1.5">
                <span>启用账号</span>
                <UiTooltip text="关闭后，这个账号不会参与定时保活，也不会被自动登录或播放。" width-class="w-64">
                  <button type="button" class="inline-flex h-4 w-4 items-center justify-center rounded-full text-slate-400 transition hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 focus-visible:ring-offset-2" aria-label="查看启用账号说明">
                    <InformationCircleIcon class="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </UiTooltip>
              </span>
              <input v-model="form.enabled" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-600" />
            </label>
            <label class="flex items-center justify-between gap-3 rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <span class="flex items-center gap-1.5">
                <span>使用代理</span>
                <UiTooltip text="开启后，这个账号会优先使用当前配置的代理；关闭后将直接连接站点。" width-class="w-64">
                  <button type="button" class="inline-flex h-4 w-4 items-center justify-center rounded-full text-slate-400 transition hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 focus-visible:ring-offset-2" aria-label="查看使用代理说明">
                    <InformationCircleIcon class="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </UiTooltip>
              </span>
              <input v-model="form.use_proxy" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-600" />
            </label>
            <label class="flex items-center justify-between gap-3 rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <span class="flex items-center gap-1.5">
                <span>允许流播放</span>
                <UiTooltip width-class="w-72">
                  <button type="button" class="inline-flex h-4 w-4 items-center justify-center rounded-full text-slate-400 transition hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 focus-visible:ring-offset-2" aria-label="查看允许流播放说明">
                    <InformationCircleIcon class="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                  <template #content>
                    <div class="space-y-2">
                      <p class="font-medium text-slate-800">用于处理没有时长信息的视频。</p>
                      <p>开启后，这类视频仍可被播放，系统会按一段估算时长继续保活。</p>
                      <p>关闭后，这类视频会被跳过，改选其他能获取时长的视频。</p>
                    </div>
                  </template>
                </UiTooltip>
              </span>
              <input v-model="form.allow_stream" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-600" />
            </label>
            <label class="flex items-center justify-between gap-3 rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <span class="flex items-center gap-1.5">
                <span>CF 检测</span>
                <UiTooltip width-class="w-80">
                  <button type="button" class="inline-flex h-4 w-4 items-center justify-center rounded-full text-slate-400 transition hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 focus-visible:ring-offset-2" aria-label="查看 CF 检测说明">
                    <InformationCircleIcon class="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                  <template #content>
                    <div class="space-y-2">
                      <div class="flex items-center gap-2">
                        <span class="font-medium text-slate-800">尝试处理 Cloudflare 验证。</span>
                        <UiBadge variant="warning" size="sm">PRIME</UiBadge>
                      </div>
                      <p>遇到站点前的 Cloudflare 检测时，开启后才会尝试使用在线服务解析验证码。</p>
                      <p>关闭后，遇到这类校验通常会直接失败。</p>
                    </div>
                  </template>
                </UiTooltip>
              </span>
              <input v-model="form.cf_challenge" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-600" />
            </label>
            <label class="flex items-center justify-between gap-3 rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 sm:col-span-2">
              <span class="flex items-center gap-1.5">
                <span>允许多开 / 多视频补足时长</span>
                <UiTooltip width-class="w-72">
                  <button type="button" class="inline-flex h-4 w-4 items-center justify-center rounded-full text-slate-400 transition hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 focus-visible:ring-offset-2" aria-label="查看允许多开说明">
                    <InformationCircleIcon class="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                  <template #content>
                    <div class="space-y-2">
                      <p class="font-medium text-slate-800">决定是否可以拆成多个视频补足时长。</p>
                      <p>开启后，单个视频时长不够时，会继续播放别的视频直到达到目标时长。</p>
                      <p>关闭后，只会寻找单个时长足够的视频；如果都不够，任务可能失败。</p>
                    </div>
                  </template>
                </UiTooltip>
              </span>
              <input v-model="form.allow_multiple" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-600" />
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
            <div class="border-t border-slate-200 pt-5">
              <div class="space-y-2 text-sm text-slate-600">
                <div class="flex items-center justify-between gap-3">
                  <span class="font-medium text-slate-900">指定播放 ID</span>
                  <UiButton size="sm" variant="secondary" :loading="probeStarting" @click="testPlayId">
                    测试
                  </UiButton>
                </div>
                <input v-model="form.play_id" type="text" placeholder="可选，指定固定视频 ID" class="block w-full rounded-[18px] border-0 bg-white px-4 py-3 text-slate-900 ring-1 ring-inset ring-slate-200 focus:ring-2 focus:ring-primary-600" />
                <p v-if="probeResult" class="text-xs leading-5" :class="probeResult.success ? 'text-emerald-600' : 'text-amber-600'">
                  {{ probeResult.message }}
                </p>
                <p v-else class="text-xs leading-5 text-slate-400">填写后点「测试」，会立即登录并检查该视频 ID 是否存在且可播放。</p>
              </div>
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
                <h3 class="text-base font-semibold text-slate-950">{{ displayHostname(currentAccount) }}</h3>
                <UiBadge :variant="currentAccount.enabled ? 'success' : 'default'">
                  {{ currentAccount.enabled ? '启用' : '停用' }}
                </UiBadge>
                <span class="mx-0.5 h-3.5 w-px bg-slate-300/70"></span>
                <span class="flex flex-wrap items-center gap-1">
                  <UiBadge size="sm" :variant="currentAccount.use_proxy ? 'info' : 'default'">代理</UiBadge>
                  <UiBadge size="sm" :variant="currentAccount.allow_stream ? 'warning' : 'default'">流播放</UiBadge>
                  <UiBadge size="sm" :variant="currentAccount.cf_challenge ? 'success' : 'default'">CF 检测</UiBadge>
                  <UiBadge size="sm" :variant="currentAccount.allow_multiple ? 'info' : 'default'">多开</UiBadge>
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
          <div class="grid grid-cols-3 gap-1">
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
                          <p class="text-sm font-semibold text-slate-900">{{ run.description || 'Emby 保活任务' }}</p>
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

          <div v-else-if="detailTab === 'device'">
            <UiCard padding="sm">
              <div class="flex items-center justify-between gap-3">
                <div>
                  <h4 class="text-base font-semibold text-slate-950">缓存的设备数据</h4>
                  <p class="mt-0.5 text-sm text-slate-500">用于模拟客户端环境的设备信息，来源于最近一次成功初始化时缓存的值。</p>
                </div>
                <UiButton size="sm" variant="secondary" :loading="historyLoading" @click="refreshCurrentAccount()">
                  刷新
                </UiButton>
              </div>

              <div v-if="!deviceEntries.length" class="mt-4 rounded-[16px] border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
                还没有缓存到设备数据，先运行一次后通常会在这里看到。
              </div>

              <div v-else class="mt-4 grid gap-2">
                <div v-for="item in deviceEntries" :key="item.label" class="rounded-[14px] border border-slate-200/80 bg-slate-50 px-3 py-2.5">
                  <p class="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-400">{{ item.label }}</p>
                  <p class="mt-1 break-all text-sm font-medium text-slate-900">{{ item.value }}</p>
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

    <TransitionRoot as="template" :show="deleteDialogOpen">
      <Dialog as="div" class="relative z-50" @close="closeDeleteDialog">
        <TransitionChild
          as="template"
          enter="ease-out duration-200"
          enter-from="opacity-0"
          enter-to="opacity-100"
          leave="ease-in duration-150"
          leave-from="opacity-100"
          leave-to="opacity-0"
        >
          <div class="fixed inset-0 bg-slate-950/30 backdrop-blur-sm" />
        </TransitionChild>

        <div class="fixed inset-0 overflow-y-auto p-4 sm:p-6">
          <div class="flex min-h-full items-center justify-center">
            <TransitionChild
              as="template"
              enter="ease-out duration-200"
              enter-from="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
              enter-to="opacity-100 translate-y-0 sm:scale-100"
              leave="ease-in duration-150"
              leave-from="opacity-100 translate-y-0 sm:scale-100"
              leave-to="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
            >
              <DialogPanel class="w-full max-w-md overflow-hidden rounded-[28px] border border-rose-100 bg-white shadow-[0_30px_80px_-35px_rgba(15,23,42,0.45)]">
                <div class="bg-gradient-to-r from-rose-50 via-white to-amber-50 px-6 py-5">
                  <div class="flex items-start gap-4">
                    <div class="flex h-12 w-12 items-center justify-center rounded-[18px] bg-rose-100 text-rose-600 ring-1 ring-rose-200">
                      <TrashIcon class="h-6 w-6" />
                    </div>
                    <div class="min-w-0 flex-1">
                      <DialogTitle class="text-lg font-semibold text-slate-950">删除这个 Emby 账号？</DialogTitle>
                      <p class="mt-2 text-sm leading-6 text-slate-600">删除后，这个账号会从当前配置中移除，后续不会再参与保活。</p>
                    </div>
                  </div>
                </div>

                <div class="space-y-4 px-6 py-5">
                  <div class="rounded-[20px] border border-slate-200 bg-slate-50 px-4 py-4 text-sm">
                    <p class="font-medium text-slate-900">{{ pendingDeleteAccount ? displayHostname(pendingDeleteAccount) : '-' }}</p>
                    <p class="mt-1 text-slate-500">{{ pendingDeleteAccount?.card_subtitle || pendingDeleteAccount?.username }}</p>
                    <p class="mt-2 break-all text-xs text-slate-400">{{ pendingDeleteAccount?.url }}</p>
                  </div>

                  <div class="flex justify-end gap-3">
                    <UiButton variant="outline" :disabled="Boolean(deleting)" @click="closeDeleteDialog">取消</UiButton>
                    <UiButton
                      variant="danger"
                      :loading="pendingDeleteAccount ? deleting === accountKey(pendingDeleteAccount) : false"
                      @click="pendingDeleteAccount && deleteAccount(pendingDeleteAccount)"
                    >
                      确认删除
                    </UiButton>
                  </div>
                </div>
              </DialogPanel>
            </TransitionChild>
          </div>
        </div>
      </Dialog>
    </TransitionRoot>
  </div>
</template>
