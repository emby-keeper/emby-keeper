<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import {
  CheckCircleIcon,
  Cog6ToothIcon,
  InformationCircleIcon,
} from '@heroicons/vue/24/outline'
import UiButton from '@/components/ui/UiButton.vue'
import UiCard from '@/components/ui/UiCard.vue'
import UiSelect, { type UiSelectOption } from '@/components/ui/UiSelect.vue'
import UiSiteScopeSelector from '@/components/ui/UiSiteScopeSelector.vue'
import UiTooltip from '@/components/ui/UiTooltip.vue'
import { useAuthStore } from '@/stores/auth'
import { logger } from '@/utils/logger'

const auth = useAuthStore()

type SectionKey = 'basic' | 'notifier' | 'scheduler' | 'network'
type SaveState = 'idle' | 'saved' | 'error'
type TelegramNotifierAccount = {
  phone: string
  masked_phone: string
  enabled: boolean
}

const sectionOrder: SectionKey[] = ['basic', 'notifier', 'scheduler', 'network']
const sectionTitleMap: Record<SectionKey, string> = {
  basic: '基础运行',
  notifier: '通知设置',
  scheduler: '任务调度',
  network: '网络代理',
}

const loading = reactive({ basic: false, notifier: false, scheduler: false, network: false })
const saving = reactive({ basic: false, notifier: false, scheduler: false, network: false })
const loadError = reactive({ basic: '', notifier: '', scheduler: '', network: '' })
const notifierAccounts = ref<TelegramNotifierAccount[]>([])
const notifierAccountError = ref('')
const saveState = reactive({
  basic: 'idle' as SaveState,
  notifier: 'idle' as SaveState,
  scheduler: 'idle' as SaveState,
  network: 'idle' as SaveState,
})
const sectionSnapshot = reactive({ basic: '', notifier: '', scheduler: '', network: '' })
const saveStateTimer: Partial<Record<SectionKey, number>> = {}

const basicForm = reactive({ nofail: true, debug_cron: false })

const notifierForm = reactive({
  notifier_enabled: false,
  notifier_account: '1',
  notifier_immediately: false,
  notifier_once: false,
  notifier_method: 'telegram',
  notifier_apprise_uri: '',
})

const schedulerForm = reactive({
  checkiner_time_range: '<11:00AM,11:00PM>',
  checkiner_interval_days: '1',
  checkiner_timeout: 120,
  checkiner_retries: 4,
  checkiner_concurrency: 1,
  checkiner_random_start: 60,
  emby_time_range: '<11:00AM,11:00PM>',
  emby_interval_days: '<7,12>',
  emby_concurrency: 1,
  subsonic_time_range: '<11:00AM,11:00PM>',
  subsonic_interval_days: '<7,12>',
  subsonic_concurrency: 1,
  registrar_concurrency: 1,
  site_checkiner: null as string[] | null,
  site_monitor: null as string[] | null,
  site_messager: null as string[] | null,
  site_registrar: null as string[] | null,
})

const sitesLoading = ref(false)
const siteNames = ref<{ checkiner: string[], monitor: string[], messager: string[], registrar: string[] }>({
  checkiner: [],
  monitor: [],
  messager: [],
  registrar: [],
})
const allSiteNames = ref<{ checkiner: string[], monitor: string[], messager: string[], registrar: string[] }>({
  checkiner: [],
  monitor: [],
  messager: [],
  registrar: [],
})
const siteDisplayNames = ref<{ checkiner: Record<string, string>, monitor: Record<string, string>, messager: Record<string, string>, registrar: Record<string, string> }>({
  checkiner: {},
  monitor: {},
  messager: {},
  registrar: {},
})
const customSiteNames = ref<{ checkiner: string[], monitor: string[], messager: string[], registrar: string[] }>({
  checkiner: [],
  monitor: [],
  messager: [],
  registrar: [],
})

const loadSiteNames = async () => {
  sitesLoading.value = true
  try {
    const data = await auth.request<{
      sites: Record<string, string[]>,
      all_sites: Record<string, string[]>,
      custom: Record<string, string[]>,
      display_names: Record<string, Record<string, string>>,
    }>('/telegram/sites')
    siteNames.value = {
      checkiner: data.sites?.checkiner || [],
      monitor: data.sites?.monitor || [],
      messager: data.sites?.messager || [],
      registrar: data.sites?.registrar || [],
    }
    allSiteNames.value = {
      checkiner: data.all_sites?.checkiner || [],
      monitor: data.all_sites?.monitor || [],
      messager: data.all_sites?.messager || [],
      registrar: data.all_sites?.registrar || [],
    }
    customSiteNames.value = {
      checkiner: data.custom?.checkiner || [],
      monitor: data.custom?.monitor || [],
      messager: data.custom?.messager || [],
      registrar: data.custom?.registrar || [],
    }
    const displayNames = data.display_names || {}
    siteDisplayNames.value = {
      checkiner: displayNames.checkiner || {},
      monitor: displayNames.monitor || {},
      messager: displayNames.messager || {},
      registrar: displayNames.registrar || {},
    }
  } catch (err) {
    logger.error('Failed to load telegram sites', err)
  } finally {
    sitesLoading.value = false
  }
}

const schedulerTimeForm = reactive({
  checkiner_start: '11:00',
  checkiner_end: '23:00',
  emby_start: '11:00',
  emby_end: '23:00',
  subsonic_start: '11:00',
  subsonic_end: '23:00',
})

const schedulerTimeMode = reactive({
  checkiner: 'range' as 'single' | 'range',
  emby: 'range' as 'single' | 'range',
  subsonic: 'range' as 'single' | 'range',
})

const schedulerIntervalForm = reactive({
  checkiner_single: '1',
  checkiner_start: '1',
  checkiner_end: '1',
  emby_single: '7',
  emby_start: '7',
  emby_end: '12',
  subsonic_single: '7',
  subsonic_start: '7',
  subsonic_end: '12',
})

const schedulerIntervalMode = reactive({
  checkiner: 'single' as 'single' | 'range',
  emby: 'range' as 'single' | 'range',
  subsonic: 'range' as 'single' | 'range',
})

const networkForm = reactive({
  telegram_use_proxy: true,
  proxy: {
    enabled: false,
    scheme: 'http',
    hostname: '127.0.0.1',
    port: 7890 as number | null,
    username: '',
    password: '',
  },
})

const notifierSummary = computed(() => {
  if (!notifierForm.notifier_enabled) return '日志推送关闭'
  return notifierForm.notifier_method === 'apprise'
    ? 'Apprise 推送已启用'
    : `Telegram 推送账号 ${selectedNotifierAccountLabel.value}`
})

const notifierAccountOptions = computed<UiSelectOption[]>(() => {
  const options = notifierAccounts.value.map((account) => ({
    label: account.masked_phone || account.phone,
    value: account.phone,
    description: account.enabled ? account.phone : `${account.phone} · 已停用`,
  }))

  const current = notifierForm.notifier_account.trim()
  if (!current || options.some((option) => option.value === current)) {
    return options
  }

  if (/^\d+$/.test(current)) {
    const account = notifierAccounts.value[Number(current) - 1]
    if (account) {
      return [{
        label: account.masked_phone || account.phone,
        value: current,
        description: `当前配置：${account.phone}`,
      }, ...options]
    }
  }

  return [{ label: current, value: current, description: '当前配置' }, ...options]
})

const selectedNotifierAccountLabel = computed(() => {
  const current = notifierForm.notifier_account.trim()
  if (!current) return '未选择'
  const matched = notifierAccountOptions.value.find((option) => option.value === current)
  return matched?.label || current
})

const notifierAccountPlaceholder = computed(() => {
  if (notifierForm.notifier_method !== 'telegram') return '仅 Telegram 方式需要选择账号'
  return notifierAccounts.value.length ? '选择一个 Telegram 账号' : '请先到 Telegram 页面添加账号'
})

const proxySummary = computed(() => {
  if (!networkForm.proxy.enabled || !networkForm.proxy.hostname || !networkForm.proxy.port) {
    return '未启用统一代理'
  }
  return `${networkForm.proxy.scheme}://${networkForm.proxy.hostname}:${networkForm.proxy.port}`
})

const formFieldClass = 'block w-full rounded-[16px] border-0 bg-white px-4 py-3 text-sm text-slate-900 ring-1 ring-inset ring-slate-200 focus:ring-2 focus:ring-primary-600'
const formLabelClass = 'space-y-2 text-sm text-slate-600'
const helperTextClass = 'text-xs leading-5 text-slate-400'
const schedulerPanelClass = 'rounded-[24px] border border-slate-200 bg-slate-50 p-5'
const schedulerTimeBlockClass = 'space-y-4 rounded-[20px] border border-slate-200 bg-white px-4 py-4 shadow-[0_8px_20px_-18px_rgba(15,23,42,0.18)] sm:col-span-2'
const schedulerIntervalBlockClass = 'space-y-4 rounded-[20px] border border-slate-200 bg-white px-4 py-4 shadow-[0_8px_20px_-18px_rgba(15,23,42,0.18)] sm:col-span-2'
const notifierMethodOptions = [
  { label: 'Telegram', value: 'telegram', description: '通过 Telegram 发送消息通知' },
  { label: 'Apprise', value: 'apprise', description: '通过 Apprise 聚合通知渠道发送消息' },
]
const proxySchemeOptions = [
  { label: 'SOCKS5', value: 'socks5' },
  { label: 'HTTP', value: 'http' },
]

const tooltipButtonClass = 'inline-flex h-6 w-6 -m-1 items-center justify-center rounded-full text-slate-400 transition hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 focus-visible:ring-offset-2'

const normalizeClockValue = (value: string): string | null => {
  const trimmed = value.trim()
  if (!trimmed) return null

  const matched = trimmed.match(/^(\d{1,2})(?::(\d{2}))?\s*([AaPp][Mm])?$/)
  if (!matched) return null

  let hour = Number(matched[1])
  const minute = Number(matched[2] ?? '00')
  const meridiem = matched[3]?.toUpperCase()

  if (Number.isNaN(hour) || Number.isNaN(minute) || minute < 0 || minute > 59) return null

  if (meridiem) {
    if (hour < 1 || hour > 12) return null
    if (hour === 12) hour = meridiem === 'AM' ? 0 : 12
    else if (meridiem === 'PM') hour += 12
  } else if (hour < 0 || hour > 23) {
    return null
  }

  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
}

const parseTimeRangeValue = (value: string, fallbackStart = '11:00', fallbackEnd = '23:00') => {
  const trimmed = String(value || '').trim()
  if (!trimmed) {
    return { mode: 'range' as const, start: fallbackStart, end: fallbackEnd }
  }

  const rangeMatch = trimmed.match(/^<\s*(.*?)\s*,\s*(.*?)\s*>$/)
  if (rangeMatch) {
    return {
      mode: 'range' as const,
      start: normalizeClockValue(rangeMatch[1]) || fallbackStart,
      end: normalizeClockValue(rangeMatch[2]) || fallbackEnd,
    }
  }

  const single = normalizeClockValue(trimmed)
  if (single) {
    return { mode: 'single' as const, start: single, end: single }
  }

  return { mode: 'range' as const, start: fallbackStart, end: fallbackEnd }
}

const formatTimeRangeValue = (mode: 'single' | 'range', start: string, end: string) => {
  return mode === 'single' ? start : `<${start},${end}>`
}

const normalizeIntervalValue = (value: string): string | null => {
  const trimmed = String(value || '').trim()
  if (!trimmed) return null
  if (!/^\d+$/.test(trimmed)) return null
  const numeric = Number(trimmed)
  if (!Number.isInteger(numeric) || numeric <= 0) return null
  return String(numeric)
}

const parseIntervalValue = (
  value: string,
  fallbackMode: 'single' | 'range',
  fallbackSingle: string,
  fallbackStart: string,
  fallbackEnd: string,
) => {
  const trimmed = String(value || '').trim()
  if (!trimmed) {
    return {
      mode: fallbackMode,
      single: fallbackSingle,
      start: fallbackStart,
      end: fallbackEnd,
    }
  }

  const rangeMatch = trimmed.match(/^<\s*(\d+)\s*,\s*(\d+)\s*>$/)
  if (rangeMatch) {
    return {
      mode: 'range' as const,
      single: rangeMatch[1],
      start: rangeMatch[1],
      end: rangeMatch[2],
    }
  }

  const single = normalizeIntervalValue(trimmed)
  if (single) {
    return {
      mode: 'single' as const,
      single,
      start: single,
      end: single,
    }
  }

  return {
    mode: fallbackMode,
    single: fallbackSingle,
    start: fallbackStart,
    end: fallbackEnd,
  }
}

const formatIntervalValue = (mode: 'single' | 'range', single: string, start: string, end: string) => {
  return mode === 'single' ? single : `<${start},${end}>`
}

const buildSchedulerPayload = () => ({
  ...schedulerForm,
  checkiner_time_range: formatTimeRangeValue(schedulerTimeMode.checkiner, schedulerTimeForm.checkiner_start, schedulerTimeForm.checkiner_end),
  checkiner_interval_days: formatIntervalValue(schedulerIntervalMode.checkiner, schedulerIntervalForm.checkiner_single, schedulerIntervalForm.checkiner_start, schedulerIntervalForm.checkiner_end),
  emby_time_range: formatTimeRangeValue(schedulerTimeMode.emby, schedulerTimeForm.emby_start, schedulerTimeForm.emby_end),
  emby_interval_days: formatIntervalValue(schedulerIntervalMode.emby, schedulerIntervalForm.emby_single, schedulerIntervalForm.emby_start, schedulerIntervalForm.emby_end),
  subsonic_time_range: formatTimeRangeValue(schedulerTimeMode.subsonic, schedulerTimeForm.subsonic_start, schedulerTimeForm.subsonic_end),
  subsonic_interval_days: formatIntervalValue(schedulerIntervalMode.subsonic, schedulerIntervalForm.subsonic_single, schedulerIntervalForm.subsonic_start, schedulerIntervalForm.subsonic_end),
})

const buildSectionPayload = (section: SectionKey) => {
  if (section === 'basic') return { ...basicForm }
  if (section === 'notifier') return { ...notifierForm }
  if (section === 'scheduler') return buildSchedulerPayload()
  return {
    telegram_use_proxy: networkForm.telegram_use_proxy,
    proxy: { ...networkForm.proxy },
  }
}

const serializeSection = (section: SectionKey) => JSON.stringify(buildSectionPayload(section))

const captureSectionSnapshot = (section: SectionKey) => {
  sectionSnapshot[section] = serializeSection(section)
}

const clearSaveStateTimer = (section: SectionKey) => {
  const timer = saveStateTimer[section]
  if (timer !== undefined) {
    window.clearTimeout(timer)
    delete saveStateTimer[section]
  }
}

const setSaveState = (section: SectionKey, next: SaveState, resetAfter = 0) => {
  clearSaveStateTimer(section)
  saveState[section] = next
  if (resetAfter > 0) {
    saveStateTimer[section] = window.setTimeout(() => {
      if (saveState[section] === next) saveState[section] = 'idle'
      delete saveStateTimer[section]
    }, resetAfter)
  }
}

const sectionDirty = {
  basic: computed(() => serializeSection('basic') !== sectionSnapshot.basic),
  notifier: computed(() => serializeSection('notifier') !== sectionSnapshot.notifier),
  scheduler: computed(() => serializeSection('scheduler') !== sectionSnapshot.scheduler),
  network: computed(() => serializeSection('network') !== sectionSnapshot.network),
}

const dirtySections = computed(() => sectionOrder.filter((section) => sectionDirty[section].value))
const hasDirtySections = computed(() => dirtySections.value.length > 0)
const dirtySectionCount = computed(() => dirtySections.value.length)
const isAnySectionSaving = computed(() => sectionOrder.some((section) => saving[section]))
const hasSaveError = computed(() => dirtySections.value.some((section) => saveState[section] === 'error'))
const dirtySectionSummary = computed(() => dirtySections.value.map((section) => sectionTitleMap[section]).join('、'))
const saveBarLabel = computed(() => {
  if (isAnySectionSaving.value) return '保存中'
  if (hasSaveError.value) return '重新保存'
  return '保存修改'
})

const isSectionDirty = (section: SectionKey) => sectionDirty[section].value

const getSaveButtonVariant = (section: SectionKey) => {
  if (isSectionDirty(section)) {
    return saveState[section] === 'error' ? 'danger' : 'primary'
  }
  return 'secondary'
}

const isSaveButtonDisabled = (section: SectionKey) => !isSectionDirty(section) || saving[section]

const showSavedState = (section: SectionKey) => !isSectionDirty(section) && saveState[section] === 'saved'

const getSaveButtonLabel = (section: SectionKey) => {
  if (showSavedState(section)) return '已保存'
  if (saveState[section] === 'error' && isSectionDirty(section)) return '重试'
  return '保存'
}

const syncSchedulerTimeForm = () => {
  const checkiner = parseTimeRangeValue(schedulerForm.checkiner_time_range)
  schedulerTimeMode.checkiner = checkiner.mode
  schedulerTimeForm.checkiner_start = checkiner.start
  schedulerTimeForm.checkiner_end = checkiner.end

  const emby = parseTimeRangeValue(schedulerForm.emby_time_range)
  schedulerTimeMode.emby = emby.mode
  schedulerTimeForm.emby_start = emby.start
  schedulerTimeForm.emby_end = emby.end

  const subsonic = parseTimeRangeValue(schedulerForm.subsonic_time_range)
  schedulerTimeMode.subsonic = subsonic.mode
  schedulerTimeForm.subsonic_start = subsonic.start
  schedulerTimeForm.subsonic_end = subsonic.end
}

const syncSchedulerIntervalForm = () => {
  const checkiner = parseIntervalValue(schedulerForm.checkiner_interval_days, 'single', '1', '1', '1')
  schedulerIntervalMode.checkiner = checkiner.mode
  schedulerIntervalForm.checkiner_single = checkiner.single
  schedulerIntervalForm.checkiner_start = checkiner.start
  schedulerIntervalForm.checkiner_end = checkiner.end

  const emby = parseIntervalValue(schedulerForm.emby_interval_days, 'range', '7', '7', '12')
  schedulerIntervalMode.emby = emby.mode
  schedulerIntervalForm.emby_single = emby.single
  schedulerIntervalForm.emby_start = emby.start
  schedulerIntervalForm.emby_end = emby.end

  const subsonic = parseIntervalValue(schedulerForm.subsonic_interval_days, 'range', '7', '7', '12')
  schedulerIntervalMode.subsonic = subsonic.mode
  schedulerIntervalForm.subsonic_single = subsonic.single
  schedulerIntervalForm.subsonic_start = subsonic.start
  schedulerIntervalForm.subsonic_end = subsonic.end
}

const normalizeNotifierAccountValue = () => {
  const current = notifierForm.notifier_account.trim()
  if (!/^\d+$/.test(current)) return

  const account = notifierAccounts.value[Number(current) - 1]
  if (!account?.phone) return

  notifierForm.notifier_account = account.phone
  if (!loading.notifier) {
    captureSectionSnapshot('notifier')
  }
}

const restoreSectionFromSnapshot = (section: SectionKey) => {
  const rawSnapshot = sectionSnapshot[section]
  if (!rawSnapshot) return

  const snapshot = JSON.parse(rawSnapshot)

  if (section === 'basic') {
    Object.assign(basicForm, snapshot)
    setSaveState(section, 'idle')
    return
  }

  if (section === 'notifier') {
    Object.assign(notifierForm, snapshot)
    normalizeNotifierAccountValue()
    setSaveState(section, 'idle')
    return
  }

  if (section === 'scheduler') {
    Object.assign(schedulerForm, snapshot)
    syncSchedulerTimeForm()
    syncSchedulerIntervalForm()
    setSaveState(section, 'idle')
    return
  }

  Object.assign(networkForm, snapshot)
  setSaveState(section, 'idle')
}

const loadSection = async (section: SectionKey) => {
  loading[section] = true
  loadError[section] = ''
  setSaveState(section, 'idle')
  try {
    const data = await auth.request(`/settings/${section}`)
    if (section === 'basic') Object.assign(basicForm, data)
    if (section === 'notifier') {
      Object.assign(notifierForm, data)
      normalizeNotifierAccountValue()
    }
    if (section === 'scheduler') {
      Object.assign(schedulerForm, data)
      syncSchedulerTimeForm()
      syncSchedulerIntervalForm()
    }
    if (section === 'network') Object.assign(networkForm, data)
    captureSectionSnapshot(section)
  } catch (err) {
    logger.error(`Failed to load ${section} settings`, err)
    loadError[section] = '加载失败'
  } finally {
    loading[section] = false
  }
}

const loadNotifierAccounts = async () => {
  notifierAccountError.value = ''
  try {
    const data = await auth.request<{ accounts: TelegramNotifierAccount[] }>('/telegram/accounts')
    notifierAccounts.value = Array.isArray(data.accounts) ? data.accounts : []
    normalizeNotifierAccountValue()
  } catch (err) {
    logger.error('Failed to load notifier accounts', err)
    notifierAccounts.value = []
    notifierAccountError.value = logger.message(err, 'Telegram 账号列表加载失败')
  }
}

const saveSection = async (section: SectionKey) => {
  if (!isSectionDirty(section)) return true

  saving[section] = true
  setSaveState(section, 'idle')
  try {
    const payload = buildSectionPayload(section)
    await auth.request(`/settings/${section}`, { method: 'POST', body: JSON.stringify(payload) })
    captureSectionSnapshot(section)
    setSaveState(section, 'saved', 1800)
    return true
  } catch (err) {
    logger.error(`Failed to save ${section} settings`, err)
    setSaveState(section, 'error')
    return false
  } finally {
    saving[section] = false
  }
}

const saveAllDirtySections = async () => {
  for (const section of dirtySections.value) {
    const success = await saveSection(section)
    if (!success) break
  }
}

const revertAllDirtySections = () => {
  for (const section of dirtySections.value) {
    restoreSectionFromSnapshot(section)
  }
}

syncSchedulerTimeForm()
syncSchedulerIntervalForm()
captureSectionSnapshot('basic')
captureSectionSnapshot('notifier')
captureSectionSnapshot('scheduler')
captureSectionSnapshot('network')
Promise.all([
  loadSection('basic'),
  loadSection('notifier'),
  loadSection('scheduler'),
  loadSection('network'),
  loadNotifierAccounts(),
  loadSiteNames(),
])
</script>

<template>
  <div class="space-y-8" :class="{ 'pb-44 sm:pb-28': hasDirtySections }">
    <section class="overflow-hidden rounded-[30px] border border-slate-200/80 bg-gradient-to-br from-white via-slate-50 to-slate-100 shadow-[0_20px_60px_-32px_rgba(15,23,42,0.35)]">
      <div class="flex min-w-0 flex-col gap-4 px-4 py-5 sm:px-6 sm:py-6 xl:px-8">
        <div class="max-w-2xl space-y-2">
          <p class="text-xs font-semibold uppercase tracking-[0.22em] text-primary-600">System Settings</p>
          <div>
            <h1 class="text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">系统设置</h1>
            <p class="mt-2 text-sm leading-6 text-slate-600">调整系统运行、通知、任务调度和网络代理等全局设置。</p>
          </div>
        </div>
      </div>
    </section>

    <section class="grid min-w-0 grid-cols-1 gap-6 2xl:grid-cols-2">
      <section id="basic" class="scroll-mt-6">
      <UiCard class="h-full overflow-hidden border-slate-200/70 bg-white/90">
        <template #header>
          <div class="flex items-center justify-between gap-4">
            <div>
              <h2 class="text-lg font-semibold tracking-tight text-slate-950">基础运行</h2>
              <p class="mt-1 text-sm text-slate-500">控制失败行为和调试计划任务。</p>
              <p v-if="loadError.basic" class="mt-2 text-sm font-medium text-rose-600">{{ loadError.basic }}</p>
            </div>
            <UiButton size="md" class="min-w-[88px]" :variant="getSaveButtonVariant('basic')" :disabled="isSaveButtonDisabled('basic')" :loading="saving.basic" @click="saveSection('basic')">
              <CheckCircleIcon v-if="showSavedState('basic')" class="h-4 w-4" />
              <span v-else>{{ getSaveButtonLabel('basic') }}</span>
            </UiButton>
          </div>
        </template>
        <div class="space-y-4">
          <label class="flex items-start justify-between gap-4 rounded-[20px] border border-slate-200 bg-slate-50 px-4 py-4">
            <div>
              <p class="text-sm font-medium text-slate-900">失败不中断</p>
              <p class="mt-1 text-sm text-slate-500">任务报错后继续执行后续流程。</p>
            </div>
            <input v-model="basicForm.nofail" type="checkbox" class="mt-1 h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-600" />
          </label>
          <label class="flex items-start justify-between gap-4 rounded-[20px] border border-slate-200 bg-slate-50 px-4 py-4">
            <div>
              <p class="text-sm font-medium text-slate-900">调试计划任务</p>
              <p class="mt-1 text-sm text-slate-500">缩短计划任务触发时间，用于排查调度问题。</p>
            </div>
            <input v-model="basicForm.debug_cron" type="checkbox" class="mt-1 h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-600" />
          </label>
        </div>
      </UiCard>
      </section>

      <section id="notifier" class="scroll-mt-6">
      <UiCard class="relative z-10 h-full overflow-visible border-slate-200/70 bg-white/90 focus-within:z-30">
        <template #header>
          <div class="flex items-center justify-between gap-4">
            <div>
              <h2 class="text-lg font-semibold tracking-tight text-slate-950">通知设置</h2>
              <p class="mt-1 text-sm text-slate-500">{{ notifierSummary }}</p>
              <p v-if="loadError.notifier" class="mt-2 text-sm font-medium text-rose-600">{{ loadError.notifier }}</p>
            </div>
            <UiButton size="md" class="min-w-[88px]" :variant="getSaveButtonVariant('notifier')" :disabled="isSaveButtonDisabled('notifier')" :loading="saving.notifier" @click="saveSection('notifier')">
              <CheckCircleIcon v-if="showSavedState('notifier')" class="h-4 w-4" />
              <span v-else>{{ getSaveButtonLabel('notifier') }}</span>
            </UiButton>
          </div>
        </template>
        <div class="space-y-4">
          <label class="flex items-center justify-between gap-3 rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
            <span>启用通知</span>
            <input v-model="notifierForm.notifier_enabled" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-600" />
          </label>
          <div class="grid gap-4 sm:grid-cols-2">
            <UiSelect v-model="notifierForm.notifier_method" label="通知方式" :options="notifierMethodOptions" />
            <div class="space-y-2 text-sm text-slate-600">
              <UiSelect
                v-model="notifierForm.notifier_account"
                label="通知账号"
                :options="notifierAccountOptions"
                :disabled="notifierForm.notifier_method !== 'telegram'"
                :placeholder="notifierAccountPlaceholder"
              />
              <p v-if="notifierAccountError" class="text-xs leading-5 text-rose-600">{{ notifierAccountError }}</p>
            </div>
            <label v-if="notifierForm.notifier_method === 'apprise'" class="space-y-2 text-sm text-slate-600 sm:col-span-2">
              <span class="font-medium text-slate-900">Apprise 地址</span>
              <input v-model="notifierForm.notifier_apprise_uri" type="text" class="block w-full rounded-[18px] border-0 bg-slate-50 px-4 py-3 text-slate-900 ring-1 ring-inset ring-slate-200 focus:ring-2 focus:ring-primary-600" placeholder="tgram://token/chatid" />
            </label>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="flex items-center justify-between gap-3 rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <span class="flex items-center gap-1.5">
                <span>即时推送</span>
                <UiTooltip text="开启后会立刻推送；关闭后会按机器人设置的时间推送。" width-class="w-64">
                  <button type="button" :class="tooltipButtonClass" aria-label="查看即时推送说明">
                    <InformationCircleIcon class="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </UiTooltip>
              </span>
              <input v-model="notifierForm.notifier_immediately" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-600" />
            </label>
            <label class="flex items-center justify-between gap-3 rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <span class="flex items-center gap-1.5">
                <span>首次运行也推送</span>
                <UiTooltip text="开启后，程序启动后立刻执行的那一轮签到或保活也会发送通知；关闭后，这一轮不会推送。" width-class="w-80">
                  <button type="button" :class="tooltipButtonClass" aria-label="查看首次运行推送说明">
                    <InformationCircleIcon class="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </UiTooltip>
              </span>
              <input v-model="notifierForm.notifier_once" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-600" />
            </label>
          </div>
        </div>
      </UiCard>
      </section>

      <section id="scheduler" class="scroll-mt-6 2xl:col-span-2">
      <UiCard class="relative z-10 overflow-hidden border-slate-200/70 bg-white/90 focus-within:z-20">
        <template #header>
          <div class="flex items-center justify-between gap-4">
            <div>
              <h2 class="text-lg font-semibold tracking-tight text-slate-950">任务调度</h2>
              <p class="mt-1 text-sm text-slate-500">设置各类任务的执行时段、频率与并发数量。</p>
              <p v-if="loadError.scheduler" class="mt-2 text-sm font-medium text-rose-600">{{ loadError.scheduler }}</p>
            </div>
            <UiButton size="md" class="min-w-[88px]" :variant="getSaveButtonVariant('scheduler')" :disabled="isSaveButtonDisabled('scheduler')" :loading="saving.scheduler" @click="saveSection('scheduler')">
              <CheckCircleIcon v-if="showSavedState('scheduler')" class="h-4 w-4" />
              <span v-else>{{ getSaveButtonLabel('scheduler') }}</span>
            </UiButton>
          </div>
        </template>
        <div class="space-y-4">
          <div class="grid gap-5">
            <div :class="schedulerPanelClass">
              <div class="mb-4">
                <h3 class="text-base font-semibold text-slate-950">签到任务</h3>
                <p class="mt-1 text-sm text-slate-500">控制签到任务的执行时段、超时时间和并发。</p>
              </div>
              <div class="grid gap-4 sm:grid-cols-2">
                <div :class="schedulerTimeBlockClass">
                  <div class="space-y-1.5">
                    <p class="text-sm font-medium text-slate-900">执行时段</p>
                    <p class="text-xs leading-5 text-slate-400">选择每天固定执行时间，或限定任务可执行的时间范围。</p>
                  </div>
                  <div>
                    <div class="inline-flex rounded-[14px] bg-white p-1 ring-1 ring-inset ring-slate-200">
                      <button
                        type="button"
                        class="rounded-[10px] px-3 py-1.5 text-xs font-medium transition"
                        :class="schedulerTimeMode.checkiner === 'single' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-700'"
                        @click="schedulerTimeMode.checkiner = 'single'"
                      >
                        单个时间
                      </button>
                      <button
                        type="button"
                        class="rounded-[10px] px-3 py-1.5 text-xs font-medium transition"
                        :class="schedulerTimeMode.checkiner === 'range' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-700'"
                        @click="schedulerTimeMode.checkiner = 'range'"
                      >
                        时间范围
                      </button>
                    </div>
                  </div>
                  <div class="grid gap-4 sm:grid-cols-2">
                    <label :class="formLabelClass">
                      <span class="text-xs font-medium text-slate-500">{{ schedulerTimeMode.checkiner === 'single' ? '执行时间' : '开始时间' }}</span>
                      <input v-model="schedulerTimeForm.checkiner_start" type="time" :class="formFieldClass" />
                    </label>
                    <label v-if="schedulerTimeMode.checkiner === 'range'" :class="formLabelClass">
                      <span class="text-xs font-medium text-slate-500">结束时间</span>
                      <input v-model="schedulerTimeForm.checkiner_end" type="time" :class="formFieldClass" />
                    </label>
                  </div>
                  <p :class="helperTextClass">{{ schedulerTimeMode.checkiner === 'single' ? '系统会在每天这个时间安排签到任务。' : '系统会在这个时间范围内安排签到任务。' }}</p>
                </div>
                <div :class="schedulerIntervalBlockClass">
                  <div class="space-y-1.5">
                    <p class="text-sm font-medium text-slate-900">间隔天数</p>
                    <p class="text-xs leading-5 text-slate-400">选择固定天数，或让系统在一个天数区间内随机安排。</p>
                  </div>
                  <div>
                    <div class="inline-flex rounded-[14px] bg-white p-1 ring-1 ring-inset ring-slate-200">
                      <button
                        type="button"
                        class="rounded-[10px] px-3 py-1.5 text-xs font-medium transition"
                        :class="schedulerIntervalMode.checkiner === 'single' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-700'"
                        @click="schedulerIntervalMode.checkiner = 'single'"
                      >
                        固定天数
                      </button>
                      <button
                        type="button"
                        class="rounded-[10px] px-3 py-1.5 text-xs font-medium transition"
                        :class="schedulerIntervalMode.checkiner === 'range' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-700'"
                        @click="schedulerIntervalMode.checkiner = 'range'"
                      >
                        区间天数
                      </button>
                    </div>
                  </div>
                  <div class="grid gap-4 sm:grid-cols-2">
                    <label :class="formLabelClass">
                      <span class="text-xs font-medium text-slate-500">{{ schedulerIntervalMode.checkiner === 'single' ? '间隔天数' : '最小天数' }}</span>
                      <input v-model="schedulerIntervalForm.checkiner_single" v-if="schedulerIntervalMode.checkiner === 'single'" type="number" min="1" step="1" :class="formFieldClass" />
                      <input v-model="schedulerIntervalForm.checkiner_start" v-else type="number" min="1" step="1" :class="formFieldClass" />
                    </label>
                    <label v-if="schedulerIntervalMode.checkiner === 'range'" :class="formLabelClass">
                      <span class="text-xs font-medium text-slate-500">最大天数</span>
                      <input v-model="schedulerIntervalForm.checkiner_end" type="number" min="1" step="1" :class="formFieldClass" />
                    </label>
                  </div>
                  <p :class="helperTextClass">{{ schedulerIntervalMode.checkiner === 'single' ? '系统会按固定天数间隔安排任务。' : '系统会在这个天数区间内随机安排任务。' }}</p>
                </div>
                <label :class="formLabelClass">
                  <span class="font-medium text-slate-900">超时时间（秒）</span>
                  <input v-model.number="schedulerForm.checkiner_timeout" type="number" min="1" :class="formFieldClass" />
                  <p :class="helperTextClass">单次签到超过该时间后会判定为超时。</p>
                </label>
                <label :class="formLabelClass">
                  <span class="font-medium text-slate-900">重试次数</span>
                  <input v-model.number="schedulerForm.checkiner_retries" type="number" min="0" :class="formFieldClass" />
                  <p :class="helperTextClass">任务失败后最多自动重试的次数。</p>
                </label>
                <label :class="`${formLabelClass} sm:col-span-2`">
                  <span class="font-medium text-slate-900">并发数量</span>
                  <input v-model.number="schedulerForm.checkiner_concurrency" type="number" min="1" :class="formFieldClass" />
                  <p :class="helperTextClass">同时执行的签到任务数量。</p>
                </label>
                <label :class="formLabelClass">
                  <span class="font-medium text-slate-900">随机延迟（秒）</span>
                  <input v-model.number="schedulerForm.checkiner_random_start" type="number" min="0" :class="formFieldClass" />
                  <p :class="helperTextClass">启动前额外等待的随机秒数。</p>
                </label>
              </div>
            </div>

            <div :class="schedulerPanelClass">
              <div class="mb-4">
                <h3 class="text-base font-semibold text-slate-950">Emby 任务</h3>
                <p class="mt-1 text-sm text-slate-500">控制 Emby 保活任务的时段、间隔和并发。</p>
              </div>
              <div class="grid gap-4 sm:grid-cols-2">
                <div :class="schedulerTimeBlockClass">
                  <div class="space-y-1.5">
                    <p class="text-sm font-medium text-slate-900">执行时段</p>
                    <p class="text-xs leading-5 text-slate-400">选择每天固定执行时间，或限定任务可执行的时间范围。</p>
                  </div>
                  <div>
                    <div class="inline-flex rounded-[14px] bg-white p-1 ring-1 ring-inset ring-slate-200">
                      <button
                        type="button"
                        class="rounded-[10px] px-3 py-1.5 text-xs font-medium transition"
                        :class="schedulerTimeMode.emby === 'single' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-700'"
                        @click="schedulerTimeMode.emby = 'single'"
                      >
                        单个时间
                      </button>
                      <button
                        type="button"
                        class="rounded-[10px] px-3 py-1.5 text-xs font-medium transition"
                        :class="schedulerTimeMode.emby === 'range' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-700'"
                        @click="schedulerTimeMode.emby = 'range'"
                      >
                        时间范围
                      </button>
                    </div>
                  </div>
                  <div class="grid gap-4 sm:grid-cols-2">
                    <label :class="formLabelClass">
                      <span class="text-xs font-medium text-slate-500">{{ schedulerTimeMode.emby === 'single' ? '执行时间' : '开始时间' }}</span>
                      <input v-model="schedulerTimeForm.emby_start" type="time" :class="formFieldClass" />
                    </label>
                    <label v-if="schedulerTimeMode.emby === 'range'" :class="formLabelClass">
                      <span class="text-xs font-medium text-slate-500">结束时间</span>
                      <input v-model="schedulerTimeForm.emby_end" type="time" :class="formFieldClass" />
                    </label>
                  </div>
                  <p :class="helperTextClass">{{ schedulerTimeMode.emby === 'single' ? '系统会在每天这个时间安排 Emby 保活任务。' : '系统会在这个时间范围内安排 Emby 保活任务。' }}</p>
                </div>
                <div :class="schedulerIntervalBlockClass">
                  <div class="space-y-1.5">
                    <p class="text-sm font-medium text-slate-900">间隔天数</p>
                    <p class="text-xs leading-5 text-slate-400">选择固定天数，或让系统在一个天数区间内随机安排。</p>
                  </div>
                  <div>
                    <div class="inline-flex rounded-[14px] bg-white p-1 ring-1 ring-inset ring-slate-200">
                      <button
                        type="button"
                        class="rounded-[10px] px-3 py-1.5 text-xs font-medium transition"
                        :class="schedulerIntervalMode.emby === 'single' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-700'"
                        @click="schedulerIntervalMode.emby = 'single'"
                      >
                        固定天数
                      </button>
                      <button
                        type="button"
                        class="rounded-[10px] px-3 py-1.5 text-xs font-medium transition"
                        :class="schedulerIntervalMode.emby === 'range' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-700'"
                        @click="schedulerIntervalMode.emby = 'range'"
                      >
                        区间天数
                      </button>
                    </div>
                  </div>
                  <div class="grid gap-4 sm:grid-cols-2">
                    <label :class="formLabelClass">
                      <span class="text-xs font-medium text-slate-500">{{ schedulerIntervalMode.emby === 'single' ? '间隔天数' : '最小天数' }}</span>
                      <input v-model="schedulerIntervalForm.emby_single" v-if="schedulerIntervalMode.emby === 'single'" type="number" min="1" step="1" :class="formFieldClass" />
                      <input v-model="schedulerIntervalForm.emby_start" v-else type="number" min="1" step="1" :class="formFieldClass" />
                    </label>
                    <label v-if="schedulerIntervalMode.emby === 'range'" :class="formLabelClass">
                      <span class="text-xs font-medium text-slate-500">最大天数</span>
                      <input v-model="schedulerIntervalForm.emby_end" type="number" min="1" step="1" :class="formFieldClass" />
                    </label>
                  </div>
                  <p :class="helperTextClass">{{ schedulerIntervalMode.emby === 'single' ? '系统会按固定天数间隔安排 Emby 保活任务。' : '系统会在这个天数区间内随机安排 Emby 保活任务。' }}</p>
                </div>
                <label :class="`${formLabelClass} sm:col-span-2`">
                  <span class="font-medium text-slate-900">并发数量</span>
                  <input v-model.number="schedulerForm.emby_concurrency" type="number" min="1" :class="formFieldClass" />
                  <p :class="helperTextClass">同时执行的 Emby 任务数量。</p>
                </label>
              </div>
            </div>

            <div :class="schedulerPanelClass">
              <div class="mb-4">
                <h3 class="text-base font-semibold text-slate-950">Subsonic 任务</h3>
                <p class="mt-1 text-sm text-slate-500">控制 Subsonic 保活任务的时段、间隔和并发。</p>
              </div>
              <div class="grid gap-4 sm:grid-cols-2">
                <div :class="schedulerTimeBlockClass">
                  <div class="space-y-1.5">
                    <p class="text-sm font-medium text-slate-900">执行时段</p>
                    <p class="text-xs leading-5 text-slate-400">选择每天固定执行时间，或限定任务可执行的时间范围。</p>
                  </div>
                  <div>
                    <div class="inline-flex rounded-[14px] bg-white p-1 ring-1 ring-inset ring-slate-200">
                      <button
                        type="button"
                        class="rounded-[10px] px-3 py-1.5 text-xs font-medium transition"
                        :class="schedulerTimeMode.subsonic === 'single' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-700'"
                        @click="schedulerTimeMode.subsonic = 'single'"
                      >
                        单个时间
                      </button>
                      <button
                        type="button"
                        class="rounded-[10px] px-3 py-1.5 text-xs font-medium transition"
                        :class="schedulerTimeMode.subsonic === 'range' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-700'"
                        @click="schedulerTimeMode.subsonic = 'range'"
                      >
                        时间范围
                      </button>
                    </div>
                  </div>
                  <div class="grid gap-4 sm:grid-cols-2">
                    <label :class="formLabelClass">
                      <span class="text-xs font-medium text-slate-500">{{ schedulerTimeMode.subsonic === 'single' ? '执行时间' : '开始时间' }}</span>
                      <input v-model="schedulerTimeForm.subsonic_start" type="time" :class="formFieldClass" />
                    </label>
                    <label v-if="schedulerTimeMode.subsonic === 'range'" :class="formLabelClass">
                      <span class="text-xs font-medium text-slate-500">结束时间</span>
                      <input v-model="schedulerTimeForm.subsonic_end" type="time" :class="formFieldClass" />
                    </label>
                  </div>
                  <p :class="helperTextClass">{{ schedulerTimeMode.subsonic === 'single' ? '系统会在每天这个时间安排 Subsonic 保活任务。' : '系统会在这个时间范围内安排 Subsonic 保活任务。' }}</p>
                </div>
                <div :class="schedulerIntervalBlockClass">
                  <div class="space-y-1.5">
                    <p class="text-sm font-medium text-slate-900">间隔天数</p>
                    <p class="text-xs leading-5 text-slate-400">选择固定天数，或让系统在一个天数区间内随机安排。</p>
                  </div>
                  <div>
                    <div class="inline-flex rounded-[14px] bg-white p-1 ring-1 ring-inset ring-slate-200">
                      <button
                        type="button"
                        class="rounded-[10px] px-3 py-1.5 text-xs font-medium transition"
                        :class="schedulerIntervalMode.subsonic === 'single' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-700'"
                        @click="schedulerIntervalMode.subsonic = 'single'"
                      >
                        固定天数
                      </button>
                      <button
                        type="button"
                        class="rounded-[10px] px-3 py-1.5 text-xs font-medium transition"
                        :class="schedulerIntervalMode.subsonic === 'range' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-700'"
                        @click="schedulerIntervalMode.subsonic = 'range'"
                      >
                        区间天数
                      </button>
                    </div>
                  </div>
                  <div class="grid gap-4 sm:grid-cols-2">
                    <label :class="formLabelClass">
                      <span class="text-xs font-medium text-slate-500">{{ schedulerIntervalMode.subsonic === 'single' ? '间隔天数' : '最小天数' }}</span>
                      <input v-model="schedulerIntervalForm.subsonic_single" v-if="schedulerIntervalMode.subsonic === 'single'" type="number" min="1" step="1" :class="formFieldClass" />
                      <input v-model="schedulerIntervalForm.subsonic_start" v-else type="number" min="1" step="1" :class="formFieldClass" />
                    </label>
                    <label v-if="schedulerIntervalMode.subsonic === 'range'" :class="formLabelClass">
                      <span class="text-xs font-medium text-slate-500">最大天数</span>
                      <input v-model="schedulerIntervalForm.subsonic_end" type="number" min="1" step="1" :class="formFieldClass" />
                    </label>
                  </div>
                  <p :class="helperTextClass">{{ schedulerIntervalMode.subsonic === 'single' ? '系统会按固定天数间隔安排 Subsonic 保活任务。' : '系统会在这个天数区间内随机安排 Subsonic 保活任务。' }}</p>
                </div>
                <label :class="`${formLabelClass} sm:col-span-2`">
                  <span class="font-medium text-slate-900">并发数量</span>
                  <input v-model.number="schedulerForm.subsonic_concurrency" type="number" min="1" :class="formFieldClass" />
                  <p :class="helperTextClass">同时执行的 Subsonic 任务数量。</p>
                </label>
              </div>
            </div>

            <div :class="schedulerPanelClass">
              <div class="mb-4">
                <h3 class="text-base font-semibold text-slate-950">注册任务</h3>
                <p class="mt-1 text-sm text-slate-500">控制注册任务的并发数量。</p>
              </div>
              <div class="grid gap-4">
                <label :class="formLabelClass">
                  <span class="font-medium text-slate-900">并发数量</span>
                  <input v-model.number="schedulerForm.registrar_concurrency" type="number" min="1" :class="formFieldClass" />
                  <p :class="helperTextClass">同时执行的注册任务数量。</p>
                </label>
              </div>
            </div>

            <div :class="schedulerPanelClass">
              <div class="mb-4 flex items-start justify-between gap-3">
                <div>
                  <h3 class="text-base font-semibold text-slate-950">站点范围</h3>
                  <p class="mt-1 text-sm text-slate-500">系统默认的站点范围，账号未单独指定时会沿用这里的设置。</p>
                </div>
                <UiButton size="sm" variant="secondary" :loading="sitesLoading" @click="loadSiteNames">
                  刷新站点
                </UiButton>
              </div>
              <div class="grid gap-5">
                <UiSiteScopeSelector
                  v-model="schedulerForm.site_checkiner"
                  label="签到站点"
                  helper-text="参与签到任务的站点。"
                  :sites="siteNames.checkiner"
                  :all-sites="allSiteNames.checkiner"
                  :extra-sites="customSiteNames.checkiner"
                  :display-names="siteDisplayNames.checkiner"
                  site-type="checkiner"
                />
                <div class="border-t border-slate-200 pt-5">
                  <UiSiteScopeSelector
                    v-model="schedulerForm.site_monitor"
                    label="监控站点"
                    helper-text="参与监控任务的站点。"
                    :sites="siteNames.monitor"
                    :all-sites="allSiteNames.monitor"
                    :extra-sites="customSiteNames.monitor"
                    :display-names="siteDisplayNames.monitor"
                    site-type="monitor"
                  />
                </div>
                <div class="border-t border-slate-200 pt-5">
                  <UiSiteScopeSelector
                    v-model="schedulerForm.site_messager"
                    label="水群站点"
                    helper-text="参与水群任务的站点。"
                    :sites="siteNames.messager"
                    :all-sites="allSiteNames.messager"
                    :extra-sites="customSiteNames.messager"
                    :display-names="siteDisplayNames.messager"
                    site-type="messager"
                  />
                </div>
                <div class="border-t border-slate-200 pt-5">
                  <UiSiteScopeSelector
                    v-model="schedulerForm.site_registrar"
                    label="抢注站点"
                    helper-text="参与抢注任务的站点。"
                    :sites="siteNames.registrar"
                    :all-sites="allSiteNames.registrar"
                    :extra-sites="customSiteNames.registrar"
                    :display-names="siteDisplayNames.registrar"
                    site-type="registrar"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </UiCard>
      </section>

      <section id="network" class="scroll-mt-6 2xl:col-span-2">
      <UiCard class="overflow-hidden border-slate-200/70 bg-white/90">
        <template #header>
          <div class="flex items-center justify-between gap-4">
            <div>
              <h2 class="text-lg font-semibold tracking-tight text-slate-950">网络代理</h2>
              <p class="mt-1 break-all text-sm text-slate-500">{{ proxySummary }}</p>
              <p v-if="loadError.network" class="mt-2 text-sm font-medium text-rose-600">{{ loadError.network }}</p>
            </div>
            <UiButton size="md" class="min-w-[88px]" :variant="getSaveButtonVariant('network')" :disabled="isSaveButtonDisabled('network')" :loading="saving.network" @click="saveSection('network')">
              <CheckCircleIcon v-if="showSavedState('network')" class="h-4 w-4" />
              <span v-else>{{ getSaveButtonLabel('network') }}</span>
            </UiButton>
          </div>
        </template>
        <div class="space-y-4">
          <label class="flex items-center justify-between gap-3 rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
            <span>启用代理</span>
            <input v-model="networkForm.proxy.enabled" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-600" />
          </label>
          <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <UiSelect v-model="networkForm.proxy.scheme" label="协议" :options="proxySchemeOptions" :disabled="!networkForm.proxy.enabled" />
            <label class="space-y-2 text-sm text-slate-600 xl:col-span-2">
              <span class="font-medium text-slate-900">主机</span>
              <input v-model="networkForm.proxy.hostname" :disabled="!networkForm.proxy.enabled" type="text" class="block w-full rounded-[18px] border-0 bg-slate-50 px-4 py-3 text-slate-900 ring-1 ring-inset ring-slate-200 disabled:bg-slate-100 focus:ring-2 focus:ring-primary-600" placeholder="127.0.0.1" />
            </label>
            <label class="space-y-2 text-sm text-slate-600">
              <span class="font-medium text-slate-900">端口</span>
              <input v-model.number="networkForm.proxy.port" :disabled="!networkForm.proxy.enabled" type="number" min="1" class="block w-full rounded-[18px] border-0 bg-slate-50 px-4 py-3 text-slate-900 ring-1 ring-inset ring-slate-200 disabled:bg-slate-100 focus:ring-2 focus:ring-primary-600" placeholder="7890" />
            </label>
            <label class="space-y-2 text-sm text-slate-600 xl:col-span-2">
              <span class="font-medium text-slate-900">用户名</span>
              <input v-model="networkForm.proxy.username" :disabled="!networkForm.proxy.enabled" type="text" class="block w-full rounded-[18px] border-0 bg-slate-50 px-4 py-3 text-slate-900 ring-1 ring-inset ring-slate-200 disabled:bg-slate-100 focus:ring-2 focus:ring-primary-600" placeholder="可选" />
            </label>
            <label class="space-y-2 text-sm text-slate-600 xl:col-span-2">
              <span class="font-medium text-slate-900">密码</span>
              <input v-model="networkForm.proxy.password" :disabled="!networkForm.proxy.enabled" type="password" class="block w-full rounded-[18px] border-0 bg-slate-50 px-4 py-3 text-slate-900 ring-1 ring-inset ring-slate-200 disabled:bg-slate-100 focus:ring-2 focus:ring-primary-600" placeholder="可选" />
            </label>
          </div>
          <div class="border-t border-slate-200/80 pt-4">
            <label class="flex items-center justify-between gap-3 rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <span>Telegram 连接使用代理</span>
              <input v-model="networkForm.telegram_use_proxy" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-600" />
            </label>
          </div>
        </div>
      </UiCard>
      </section>
    </section>

    <transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="translate-y-4 opacity-0"
      enter-to-class="translate-y-0 opacity-100"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="translate-y-0 opacity-100"
      leave-to-class="translate-y-4 opacity-0"
    >
        <div v-if="hasDirtySections" class="pointer-events-none fixed inset-x-0 bottom-[max(0.75rem,env(safe-area-inset-bottom))] z-40 flex justify-center px-3 xl:left-72">
        <div class="pointer-events-auto flex w-full max-w-3xl flex-col gap-3 rounded-[24px] border border-primary-200 bg-white/95 px-4 py-3 shadow-[0_24px_60px_-24px_rgba(37,99,235,0.35)] backdrop-blur sm:flex-row sm:items-center sm:justify-between sm:gap-4 sm:px-6">
          <div class="min-w-0">
            <p class="text-sm font-semibold text-slate-950">有 {{ dirtySectionCount }} 项设置尚未保存</p>
            <p class="mt-1 truncate text-sm text-slate-500">已修改：{{ dirtySectionSummary }}</p>
          </div>
          <div class="flex shrink-0 flex-wrap items-center justify-end gap-2">
            <UiButton size="md" variant="outline" :disabled="isAnySectionSaving" @click="revertAllDirtySections">
              撤销修改
            </UiButton>
            <UiButton
              size="md"
              class="min-w-[112px]"
              :variant="hasSaveError ? 'danger' : 'primary'"
              :loading="isAnySectionSaving"
              @click="saveAllDirtySections"
            >
              {{ saveBarLabel }}
            </UiButton>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>
