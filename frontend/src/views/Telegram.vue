<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ChatBubbleLeftRightIcon, ChevronDownIcon, InformationCircleIcon, MagnifyingGlassIcon, PencilSquareIcon, PlusIcon, TrashIcon } from '@heroicons/vue/24/outline'
import UiCard from '@/components/ui/UiCard.vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDrawer from '@/components/ui/UiDrawer.vue'
import UiSelect, { type UiSelectOption } from '@/components/ui/UiSelect.vue'
import UiSiteScopeSelector from '@/components/ui/UiSiteScopeSelector.vue'
import Switch from '@/components/Switch.vue'
import UiTooltip from '@/components/ui/UiTooltip.vue'
import { useAuthStore } from '@/stores/auth'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { logger } from '@/utils/logger'

type TelegramSiteConfig = {
  checkiner?: string[] | null
  monitor?: string[] | null
  messager?: string[] | null
  registrar?: string[] | null
}

type TelegramAccountItem = {
  phone: string
  masked_phone: string
  enabled: boolean
  checkiner: boolean
  monitor: boolean
  messager: boolean
  registrar: boolean
  api_id?: string | null
  api_hash?: string | null
  session?: string | null
  site?: TelegramSiteConfig | null
  site_override?: boolean
  checkiner_config_override?: boolean
  registrar_config_override?: boolean
  last_checkin_status?: 'success' | 'partial_failed' | 'failed' | null
  last_checkin_time?: string | null
}

type TelegramForm = {
  phone: string
  enabled: boolean
  checkiner: boolean
  monitor: boolean
  messager: boolean
  registrar: boolean
  api_id: string
  api_hash: string
  session: string
  site_checkiner: string[] | null
  site_monitor: string[] | null
  site_messager: string[] | null
  site_registrar: string[] | null
}

const auth = useAuthStore()
const accounts = ref<TelegramAccountItem[]>([])
const summary = ref({
  total: 0,
  enabled: 0,
  checkiner: 0,
  monitor: 0,
  messager: 0,
  registrar: 0,
  use_proxy: true,
  checkiner_enabled: true,
  monitor_enabled: true,
  messager_enabled: true,
  registrar_enabled: true,
})
const loading = ref(true)
const saving = ref(false)
const moduleSaving = ref(false)
const deleting = ref<string | null>(null)
const search = ref('')
const statusFilter = ref<'all' | 'enabled' | 'disabled'>('all')
const checkinResultFilter = ref<'all' | 'success' | 'partial_failed' | 'failed'>('all')
const drawerOpen = ref(false)
const detailOpen = ref(false)
const currentAccount = ref<TelegramAccountItem | null>(null)
const formMode = ref<'create' | 'edit'>('create')
const formError = ref('')
const formErrorElement = ref<HTMLElement | null>(null)
const pageError = ref('')
const testStarting = ref(false)
const testSubmitting = ref(false)
const testSubmitted = ref(false)
const testResult = ref<{ success: boolean, message: string } | null>(null)
const testLoginId = ref('')
const testCode = ref('')
const testPhase = ref<'idle' | 'code' | 'password' | 'done'>('idle')
const testPolling = ref(false)
let testPollTimer: ReturnType<typeof setInterval> | null = null
const connectionInfoOpen = ref(false)
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
const form = ref<TelegramForm>({
  phone: '',
  enabled: true,
  checkiner: true,
  monitor: false,
  messager: false,
  registrar: false,
  api_id: '',
  api_hash: '',
  session: '',
  site_checkiner: null,
  site_monitor: null,
  site_messager: null,
  site_registrar: null,
})

const { model: drawerModel } = useUnsavedChanges(drawerOpen, () => form.value, saving)

const filteredAccounts = computed(() => {
  const keyword = search.value.trim().toLowerCase()

  return accounts.value.filter((account) => {
    if (statusFilter.value === 'enabled' && !account.enabled) return false
    if (statusFilter.value === 'disabled' && account.enabled) return false

    if (checkinResultFilter.value !== 'all' && account.last_checkin_status !== checkinResultFilter.value) return false

    if (!keyword) return true

    return [account.phone, account.masked_phone, account.api_id, account.api_hash]
      .some((value) => String(value || '').toLowerCase().includes(keyword))
  })
})

const drawerTitle = computed(() => formMode.value === 'create' ? '新增 Telegram 账号' : '编辑 Telegram 账号')
const statusFilterOptions: UiSelectOption[] = [
  { label: '全部状态', value: 'all' },
  { label: '仅启用', value: 'enabled' },
  { label: '仅停用', value: 'disabled' },
]
const checkinResultFilterOptions: UiSelectOption[] = [
  { label: '全部签到状态', value: 'all' },
  { label: '成功', value: 'success' },
  { label: '部分失败', value: 'partial_failed' },
  { label: '全部失败', value: 'failed' },
]

const accountDetailItems = computed(() => {
  if (!currentAccount.value) {
    return []
  }

  return [
    { label: '手机号', value: currentAccount.value.phone },
    { label: '状态', value: currentAccount.value.enabled ? '启用' : '停用' },
    { label: 'API ID', value: currentAccount.value.api_id || '-' },
    { label: 'API Hash', value: currentAccount.value.api_hash || '-' },
    { label: '会话串', value: currentAccount.value.session ? '已填写' : '未填写' },
    {
      label: '上次签到状态',
      value: currentAccount.value.last_checkin_status === 'success'
        ? '成功'
        : currentAccount.value.last_checkin_status === 'partial_failed'
          ? '部分失败'
          : currentAccount.value.last_checkin_status === 'failed'
            ? '全部失败'
            : '-',
    },
    { label: '单独站点设置', value: currentAccount.value.site_override ? '已设置' : '未设置' },
    { label: '单独签到设置', value: currentAccount.value.checkiner_config_override ? '已设置' : '未设置' },
    { label: '单独抢注设置', value: currentAccount.value.registrar_config_override ? '已设置' : '未设置' },
  ]
})

const applyForm = (account?: TelegramAccountItem | null) => {
  form.value = {
    phone: account?.phone || '',
    enabled: account?.enabled ?? true,
    checkiner: account?.checkiner ?? true,
    monitor: account?.monitor ?? false,
    messager: account?.messager ?? false,
    registrar: account?.registrar ?? false,
    api_id: account?.api_id || '',
    api_hash: account?.api_hash || '',
    session: account?.session || '',
    site_checkiner: account?.site?.checkiner ?? null,
    site_monitor: account?.site?.monitor ?? null,
    site_messager: account?.site?.messager ?? null,
    site_registrar: account?.site?.registrar ?? null,
  }
  connectionInfoOpen.value = Boolean(account?.api_id || account?.api_hash || account?.session)
}

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
  } catch (error) {
    logger.error('Failed to load telegram sites', error)
  } finally {
    sitesLoading.value = false
  }
}

const syncConnectionInfoOpen = (event: Event) => {
  connectionInfoOpen.value = (event.currentTarget as HTMLDetailsElement).open
}

const fetchAccounts = async () => {
  loading.value = true
  pageError.value = ''
  try {
    const data = await auth.request('/telegram/accounts')
    accounts.value = data.accounts || []
    summary.value = data.summary || summary.value
  } catch (error) {
    logger.error('Failed to fetch accounts', error)
    pageError.value = logger.message(error, '账号列表加载失败')
  } finally {
    loading.value = false
  }
}

const saveTelegramModuleSettings = async (nextSummary = summary.value) => {
  moduleSaving.value = true
  pageError.value = ''
  try {
    await auth.request('/telegram/settings', {
      method: 'POST',
      body: JSON.stringify({
        checkiner_enabled: nextSummary.checkiner_enabled,
        monitor_enabled: nextSummary.monitor_enabled,
        messager_enabled: nextSummary.messager_enabled,
        registrar_enabled: nextSummary.registrar_enabled,
      }),
    })
    await fetchAccounts()
  } catch (error) {
    logger.error('Failed to save telegram module settings', error)
    pageError.value = logger.message(error, '模块设置保存失败')
    await fetchAccounts()
  } finally {
    moduleSaving.value = false
  }
}

const updateTelegramModule = (
  key: 'checkiner_enabled' | 'monitor_enabled' | 'messager_enabled' | 'registrar_enabled',
  checked: boolean,
) => {
  const nextSummary = { ...summary.value, [key]: checked }
  summary.value = nextSummary
  saveTelegramModuleSettings(nextSummary)
}

const openCreateDrawer = () => {
  formMode.value = 'create'
  formError.value = ''
  testResult.value = null
  resetTestState()
  applyForm(null)
  drawerOpen.value = true
}

const openEditDrawer = (account: TelegramAccountItem) => {
  formMode.value = 'edit'
  formError.value = ''
  testResult.value = null
  resetTestState()
  currentAccount.value = account
  applyForm(account)
  drawerOpen.value = true
}

const openDetailDrawer = async (account: TelegramAccountItem) => {
  pageError.value = ''
  try {
    const data = await auth.request(`/telegram/accounts/${encodeURIComponent(account.phone)}`)
    currentAccount.value = data.account
    detailOpen.value = true
  } catch (error) {
    logger.error('Failed to fetch account detail', error)
    pageError.value = logger.message(error, '账号详情加载失败')
  }
}

const validateForm = () => {
  const errors: string[] = []

  if (!form.value.phone.trim()) {
    errors.push('请输入手机号')
  }

  if (!form.value.checkiner && !form.value.monitor && !form.value.messager && !form.value.registrar) {
    errors.push('至少启用一个功能开关')
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

const resetTestState = () => {
  if (testPollTimer) {
    clearInterval(testPollTimer)
    testPollTimer = null
  }
  testLoginId.value = ''
  testCode.value = ''
  testPhase.value = 'idle'
  testPolling.value = false
  testStarting.value = false
  testSubmitting.value = false
  testSubmitted.value = false
}

const buildSitePayload = () => {
  const site: Record<string, string[]> = {}
  if (form.value.site_checkiner !== null) site.checkiner = form.value.site_checkiner
  if (form.value.site_monitor !== null) site.monitor = form.value.site_monitor
  if (form.value.site_messager !== null) site.messager = form.value.site_messager
  if (form.value.site_registrar !== null) site.registrar = form.value.site_registrar
  return Object.keys(site).length ? site : null
}

const buildFormPayload = () => {
  return {
    phone: form.value.phone,
    enabled: form.value.enabled,
    checkiner: form.value.checkiner,
    monitor: form.value.monitor,
    messager: form.value.messager,
    registrar: form.value.registrar,
    api_id: form.value.api_id || null,
    api_hash: form.value.api_hash || null,
    session: form.value.session || null,
    site: buildSitePayload(),
  }
}

const submitForm = async () => {
  if (!validateForm()) return

  saving.value = true
  formError.value = ''

  const payload = buildFormPayload()

  try {
    if (formMode.value === 'create') {
      await auth.request('/telegram/accounts', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
    } else {
      await auth.request(`/telegram/accounts/${encodeURIComponent(currentAccount.value?.phone || form.value.phone)}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      })
    }

    drawerOpen.value = false
    currentAccount.value = null
    await fetchAccounts()
  } catch (error) {
    logger.error('Failed to save telegram account', error)
    formError.value = logger.message(error, '保存账号失败')
  } finally {
    saving.value = false
  }
}

const pollTestResult = async () => {
  if (!testLoginId.value) return
  try {
    const data = await auth.request(`/telegram/accounts/test/result?login_id=${testLoginId.value}`)
    if (data.state === 'connecting') {
      testResult.value = { success: false, message: data.message || '正在连接 Telegram 服务器…' }
    } else if (data.state === 'waiting_code') {
      testPhase.value = 'code'
      testResult.value = { success: false, message: data.message || '验证码已发送到手机上的 Telegram，请查收后输入。' }
      testStarting.value = false
      if (!testSubmitted.value) {
        stopTestPolling()
      }
    } else if (data.state === 'need_password') {
      const passwordSubmitted = testSubmitted.value && testPhase.value === 'password'
      testPhase.value = 'password'
      testResult.value = { success: false, message: data.message || '该账号启用了两步验证，请输入密码。' }
      testStarting.value = false
      if (!passwordSubmitted) {
        testSubmitted.value = false
        stopTestPolling()
      }
    } else if (data.state === 'code_error') {
      testResult.value = { success: false, message: data.message || '验证码错误，请重新输入。' }
      testSubmitted.value = false
      stopTestPolling()
    } else if (data.state === 'password_error') {
      testResult.value = { success: false, message: data.message || '密码错误，请重新输入。' }
      testSubmitted.value = false
      stopTestPolling()
    } else if (data.state === 'done') {
      testPhase.value = 'done'
      testResult.value = { success: Boolean(data.success), message: data.message || (data.success ? '连接成功' : '连接失败') }
      if (data.success && data.session) {
        form.value.session = data.session
      }
      testSubmitted.value = false
      stopTestPolling()
    } else if (data.state === 'failed') {
      testPhase.value = 'done'
      testResult.value = { success: false, message: data.message || '登录失败' }
      testSubmitted.value = false
      stopTestPolling()
    }
  } catch (error) {
    logger.error('Failed to poll telegram test result', error)
    testSubmitted.value = false
    stopTestPolling()
    testResult.value = { success: false, message: logger.message(error, '测试失败') }
  }
}

const stopTestPolling = () => {
  if (testPollTimer) {
    clearInterval(testPollTimer)
    testPollTimer = null
  }
  testPolling.value = false
  testStarting.value = false
  testSubmitting.value = false
  testSubmitted.value = false
}

const startTestPolling = () => {
  testPolling.value = true
  if (testPollTimer) clearInterval(testPollTimer)
  testPollTimer = setInterval(pollTestResult, 2000)
}

const submitTestCode = async () => {
  if (!testCode.value.trim()) {
    testResult.value = { success: false, message: '请输入验证码或密码。' }
    return
  }
  testSubmitting.value = true
  testSubmitted.value = true
  testResult.value = null
  try {
    await auth.request(`/telegram/accounts/test/code?login_id=${testLoginId.value}&code=${encodeURIComponent(testCode.value.trim())}&kind=${testPhase.value === 'password' ? 'password' : 'code'}`, {
      method: 'POST',
    })
    testCode.value = ''
    startTestPolling()
  } catch (error) {
    logger.error('Failed to submit telegram test code', error)
    testSubmitting.value = false
    testSubmitted.value = false
    testResult.value = { success: false, message: logger.message(error, '提交失败') }
  }
}

const startFormTestRun = async () => {
  if (!validateForm()) return

  resetTestState()
  testStarting.value = true
  testResult.value = null

  try {
    const data = await auth.request('/telegram/accounts/test', {
      method: 'POST',
      body: JSON.stringify(buildFormPayload()),
    })
    if (data.needs_code && data.login_id) {
      testLoginId.value = data.login_id
      testPhase.value = 'idle'
      testResult.value = { success: false, message: '正在连接 Telegram 服务器…' }
      startTestPolling()
      return
    }
    testStarting.value = false
    testResult.value = {
      success: Boolean(data.success),
      message: data.message || (data.success ? '连接成功' : '连接失败'),
    }
  } catch (error) {
    logger.error('Failed to test telegram account', error)
    testStarting.value = false
    testResult.value = { success: false, message: logger.message(error, '测试失败') }
  }
}

const deleteAccount = async (account: TelegramAccountItem) => {
  deleting.value = account.phone
  pageError.value = ''

  try {
    await auth.request(`/telegram/accounts/${encodeURIComponent(account.phone)}`, { method: 'DELETE' })
    if (currentAccount.value?.phone === account.phone) {
      currentAccount.value = null
      detailOpen.value = false
    }
    await fetchAccounts()
  } catch (error) {
    logger.error('Failed to delete telegram account', error)
    pageError.value = logger.message(error, '删除账号失败')
  } finally {
    deleting.value = null
  }
}

onMounted(() => {
  fetchAccounts()
  loadSiteNames()
})

watch(drawerOpen, (open) => {
  if (!open) {
    resetTestState()
  }
})

onBeforeUnmount(() => {
  resetTestState()
})
</script>

<template>
  <div class="space-y-8">
    <section class="overflow-hidden rounded-[30px] border border-sky-200/70 bg-gradient-to-br from-sky-50 via-white to-cyan-50 shadow-[0_24px_80px_-40px_rgba(14,116,144,0.35)]">
      <div class="px-4 py-5 sm:px-6 sm:py-6 xl:px-8">
        <div class="space-y-3">
          <div class="inline-flex items-center gap-2 rounded-full bg-sky-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-sky-700 ring-1 ring-sky-200">
            <ChatBubbleLeftRightIcon class="h-4 w-4" aria-hidden="true" />
            Telegram
          </div>
          <div>
            <h1 class="text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">Telegram 账号</h1>
            <p class="mt-2 max-w-2xl text-sm leading-6 text-slate-600">管理签到、监控、水群和抢注相关的 Telegram 账号。</p>
          </div>
        </div>
        <div class="mt-6 rounded-[24px] border border-white/80 bg-white/80 px-5 py-4 shadow-sm ring-1 ring-sky-100">
            <div class="grid gap-3 md:grid-cols-2">
              <div class="flex items-center justify-between gap-3 rounded-[18px] bg-white px-4 py-3 ring-1 ring-slate-200">
                <div>
                  <p class="text-sm font-medium text-slate-900">签到</p>
                  <p class="mt-1 text-xs text-slate-500">控制 Telegram 签到任务是否执行</p>
                </div>
                <Switch :model-value="summary.checkiner_enabled" :disabled="moduleSaving" size="sm" @change="updateTelegramModule('checkiner_enabled', $event)" />
              </div>
              <div class="flex items-center justify-between gap-3 rounded-[18px] bg-white px-4 py-3 ring-1 ring-slate-200">
                <div>
                  <p class="text-sm font-medium text-slate-900">监控</p>
                  <p class="mt-1 text-xs text-slate-500">控制监控消息与自动处理逻辑</p>
                </div>
                <Switch :model-value="summary.monitor_enabled" :disabled="moduleSaving" size="sm" @change="updateTelegramModule('monitor_enabled', $event)" />
              </div>
              <div class="flex items-center justify-between gap-3 rounded-[18px] bg-white px-4 py-3 ring-1 ring-slate-200">
                <div>
                  <p class="text-sm font-medium text-slate-900">水群</p>
                  <p class="mt-1 text-xs text-slate-500">控制消息发送任务是否参与调度</p>
                </div>
                <Switch :model-value="summary.messager_enabled" :disabled="moduleSaving" size="sm" @change="updateTelegramModule('messager_enabled', $event)" />
              </div>
              <div class="flex items-center justify-between gap-3 rounded-[18px] bg-white px-4 py-3 ring-1 ring-slate-200">
                <div>
                  <p class="text-sm font-medium text-slate-900">抢注</p>
                  <p class="mt-1 text-xs text-slate-500">控制账号抢注任务是否启用</p>
                </div>
                <Switch :model-value="summary.registrar_enabled" :disabled="moduleSaving" size="sm" @change="updateTelegramModule('registrar_enabled', $event)" />
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
            <p class="mt-1 text-sm text-slate-500">按账号查看当前启用模块。</p>
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

    <div class="mb-5 grid min-w-0 grid-cols-2 gap-3 lg:grid-cols-[minmax(0,1fr)_180px_180px]">
      <div class="relative col-span-2 min-w-0 lg:col-span-1">
        <label for="telegram-search" class="sr-only">搜索账号</label>
        <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
          <MagnifyingGlassIcon class="h-5 w-5 text-gray-400" />
        </div>
        <input id="telegram-search" v-model="search" type="text" placeholder="搜索手机号、API ID" class="block w-full rounded-[18px] border-0 bg-white py-3 pl-10 pr-4 text-slate-900 ring-1 ring-inset ring-slate-200 placeholder:text-slate-400 focus:ring-2 focus:ring-primary-600" />
      </div>
      <UiSelect v-model="statusFilter" :options="statusFilterOptions" aria-label="筛选账号状态" class="min-w-0 w-full" />
      <UiSelect v-model="checkinResultFilter" :options="checkinResultFilterOptions" aria-label="筛选签到结果" class="min-w-0 w-full" />
    </div>

    <div v-if="pageError" class="mb-4 rounded-[20px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
      {{ pageError }}
    </div>

    <div v-if="loading" class="rounded-[24px] border border-dashed border-slate-300 bg-white/70 px-6 py-16 text-center">
      <div class="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-sky-50 text-sky-500 ring-1 ring-sky-100">
        <div class="h-7 w-7 animate-spin rounded-full border-2 border-sky-200 border-t-sky-500"></div>
      </div>
      <p class="mt-5 text-base font-medium text-slate-700">正在加载 Telegram 账号</p>
      <p class="mt-2 text-sm text-slate-500">请稍候，列表准备好后会直接显示在这里。</p>
    </div>

    <div v-else-if="filteredAccounts.length === 0" class="rounded-[24px] border border-dashed border-slate-300 bg-white/70 px-6 py-16 text-center">
      <ChatBubbleLeftRightIcon class="mx-auto mb-4 h-16 w-16 text-sky-200" />
      <p class="text-base font-medium text-slate-700">没有符合条件的 Telegram 账号</p>
      <p class="mt-2 text-sm text-slate-500">调整筛选条件或新增账号后再试。</p>
    </div>

    <div v-else class="grid grid-cols-1 gap-4 md:grid-cols-2 2xl:grid-cols-3">
      <UiCard v-for="account in filteredAccounts" :key="account.phone" hover>
        <div class="flex items-start justify-between gap-4 mb-4">
          <div class="flex min-w-0 flex-1 items-center gap-3">
            <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-[20px] bg-gradient-to-br from-sky-500 to-cyan-500 shadow-lg shadow-sky-500/20">
              <ChatBubbleLeftRightIcon class="w-6 h-6 text-white" />
            </div>
            <div>
              <div class="break-all font-semibold text-slate-900">{{ account.masked_phone || account.phone }}</div>
              <div class="mt-0.5 text-xs text-slate-500">Telegram</div>
            </div>
          </div>
          <UiBadge :variant="account.enabled ? 'success' : 'default'">
            {{ account.enabled ? '启用' : '停用' }}
          </UiBadge>
        </div>

        <div class="flex flex-wrap gap-2">
          <UiBadge :variant="account.checkiner ? 'success' : 'default'">签到</UiBadge>
          <UiBadge :variant="account.monitor ? 'info' : 'default'">监控</UiBadge>
          <UiBadge :variant="account.messager ? 'warning' : 'default'">水群</UiBadge>
          <UiBadge :variant="account.registrar ? 'error' : 'default'">抢注</UiBadge>
          <UiBadge
            v-if="account.last_checkin_status"
            :variant="account.last_checkin_status === 'success' ? 'success' : account.last_checkin_status === 'partial_failed' ? 'warning' : 'error'"
          >
            {{ account.last_checkin_status === 'success' ? '签到成功' : account.last_checkin_status === 'partial_failed' ? '部分失败' : '全部失败' }}
          </UiBadge>
        </div>

        <div class="mt-5 flex flex-wrap gap-2">
          <UiButton size="sm" variant="ghost" @click="openDetailDrawer(account)">
            查看
          </UiButton>
          <UiButton size="sm" variant="secondary" @click="openEditDrawer(account)">
            <PencilSquareIcon class="mr-2 h-4 w-4" />
            编辑
          </UiButton>
          <UiButton size="sm" variant="danger" :loading="deleting === account.phone" @click="deleteAccount(account)">
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
              <span class="flex items-center gap-1.5 font-medium text-slate-900">
                <span>手机号</span>
                <UiTooltip text="用于识别这个 Telegram 账号，请填写带国家区号的完整手机号，例如 +86 13800000000。" width-class="w-72">
                  <button type="button" class="inline-flex h-4 w-4 items-center justify-center rounded-full text-slate-400 transition hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 focus-visible:ring-offset-2" aria-label="查看手机号填写说明">
                    <InformationCircleIcon class="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </UiTooltip>
              </span>
              <input v-model="form.phone" type="text" placeholder="+8613800000000" class="block w-full rounded-[18px] border-0 bg-slate-50 px-4 py-3 text-slate-900 ring-1 ring-inset ring-slate-200 focus:ring-2 focus:ring-primary-600" />
            </label>
            <label class="flex items-center justify-between gap-3 rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <span class="flex items-center gap-1.5">
                <span>启用账号</span>
                <UiTooltip text="关闭后，这个账号不会参与签到、监控、水群或抢注任务。" width-class="w-64">
                  <button type="button" class="inline-flex h-4 w-4 items-center justify-center rounded-full text-slate-400 transition hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 focus-visible:ring-offset-2" aria-label="查看启用账号说明">
                    <InformationCircleIcon class="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </UiTooltip>
              </span>
              <input v-model="form.enabled" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-600" />
            </label>
          </div>
        </UiCard>

        <UiCard>
          <h3 class="text-base font-semibold text-slate-950">功能开关</h3>
          <div class="mt-4 grid gap-3 sm:grid-cols-2">
            <label class="flex items-center justify-between gap-3 rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <span class="flex items-center gap-1.5">
                <span>签到</span>
                <UiTooltip text="开启后，这个账号会参与机器人签到任务。" width-class="w-56">
                  <button type="button" class="inline-flex h-4 w-4 items-center justify-center rounded-full text-slate-400 transition hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 focus-visible:ring-offset-2" aria-label="查看签到功能说明">
                    <InformationCircleIcon class="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </UiTooltip>
              </span>
              <input v-model="form.checkiner" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-600" />
            </label>
            <label class="flex items-center justify-between gap-3 rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <span class="flex items-center gap-1.5">
                <span>监控</span>
                <UiTooltip text="开启后，这个账号会参与群组监控、抢邀请码和答题等任务。" width-class="w-64">
                  <button type="button" class="inline-flex h-4 w-4 items-center justify-center rounded-full text-slate-400 transition hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 focus-visible:ring-offset-2" aria-label="查看监控功能说明">
                    <InformationCircleIcon class="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </UiTooltip>
              </span>
              <input v-model="form.monitor" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-600" />
            </label>
            <label class="flex items-center justify-between gap-3 rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <span class="flex items-center gap-1.5">
                <span>水群</span>
                <UiTooltip text="开启后，这个账号会参与自动发言任务，使用前请确认风险。" width-class="w-64">
                  <button type="button" class="inline-flex h-4 w-4 items-center justify-center rounded-full text-slate-400 transition hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 focus-visible:ring-offset-2" aria-label="查看水群功能说明">
                    <InformationCircleIcon class="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </UiTooltip>
              </span>
              <input v-model="form.messager" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-600" />
            </label>
            <label class="flex items-center justify-between gap-3 rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <span class="flex items-center gap-1.5">
                <span>抢注</span>
                <UiTooltip text="开启后，这个账号会参与用户名、名额或邀请资格相关的抢注任务。" width-class="w-64">
                  <button type="button" class="inline-flex h-4 w-4 items-center justify-center rounded-full text-slate-400 transition hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 focus-visible:ring-offset-2" aria-label="查看抢注功能说明">
                    <InformationCircleIcon class="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </UiTooltip>
              </span>
              <input v-model="form.registrar" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-600" />
            </label>
          </div>
        </UiCard>

        <UiCard>
          <div class="flex items-start justify-between gap-3">
            <div>
              <h3 class="text-base font-semibold text-slate-950">站点范围</h3>
              <p class="mt-1 text-sm text-slate-500">指定这个账号参与哪些站点；未单独指定的模块会沿用系统设置。</p>
            </div>
            <UiButton size="sm" variant="secondary" :loading="sitesLoading" @click="loadSiteNames">
              刷新站点
            </UiButton>
          </div>

          <div class="mt-4 space-y-5">
            <UiSiteScopeSelector
              v-model="form.site_checkiner"
              label="签到站点"
              helper-text="这个账号要签到的站点。"
              :sites="siteNames.checkiner"
              :all-sites="allSiteNames.checkiner"
              :extra-sites="customSiteNames.checkiner"
              :display-names="siteDisplayNames.checkiner"
              site-type="checkiner"
              allow-inherit
            />
            <div class="border-t border-slate-200 pt-5">
              <UiSiteScopeSelector
                v-model="form.site_monitor"
                label="监控站点"
                helper-text="这个账号要监控的站点。"
                :sites="siteNames.monitor"
                :all-sites="allSiteNames.monitor"
                :extra-sites="customSiteNames.monitor"
                :display-names="siteDisplayNames.monitor"
                site-type="monitor"
                allow-inherit
              />
            </div>
            <div class="border-t border-slate-200 pt-5">
              <UiSiteScopeSelector
                v-model="form.site_messager"
                label="水群站点"
                helper-text="这个账号要参与水群的站点。"
                :sites="siteNames.messager"
                :all-sites="allSiteNames.messager"
                :extra-sites="customSiteNames.messager"
                :display-names="siteDisplayNames.messager"
                site-type="messager"
                allow-inherit
              />
            </div>
            <div class="border-t border-slate-200 pt-5">
              <UiSiteScopeSelector
                v-model="form.site_registrar"
                label="抢注站点"
                helper-text="这个账号要参与抢注的站点。"
                :sites="siteNames.registrar"
                :all-sites="allSiteNames.registrar"
                :extra-sites="customSiteNames.registrar"
                :display-names="siteDisplayNames.registrar"
                site-type="registrar"
                allow-inherit
              />
            </div>
          </div>
        </UiCard>

        <UiCard>
          <details :open="connectionInfoOpen" class="group" @toggle="syncConnectionInfoOpen">
            <summary class="flex cursor-pointer list-none items-start justify-between gap-4 rounded-[18px] bg-slate-50 px-4 py-4 [&::-webkit-details-marker]:hidden">
              <div>
                <h3 class="text-base font-semibold text-slate-950">连接信息</h3>
                <p class="mt-1 text-sm text-slate-500">仅在遇到问题时才需要填写（例如登录失败、频繁掉线等），平时可以保持收起。</p>
              </div>
              <span class="inline-flex items-center gap-2 text-sm font-medium text-slate-500">
                <span>{{ connectionInfoOpen ? '收起' : '展开' }}</span>
                <ChevronDownIcon class="h-5 w-5 transition duration-200" :class="connectionInfoOpen ? 'rotate-180' : ''" aria-hidden="true" />
              </span>
            </summary>

            <div class="mt-4 grid gap-4 sm:grid-cols-2">
              <label class="space-y-2 text-sm text-slate-600">
                <span class="font-medium text-slate-900">API ID</span>
                <input v-model="form.api_id" type="text" placeholder="可选" class="block w-full rounded-[18px] border-0 bg-slate-50 px-4 py-3 text-slate-900 ring-1 ring-inset ring-slate-200 focus:ring-2 focus:ring-primary-600" />
              </label>
              <label class="space-y-2 text-sm text-slate-600">
                <span class="font-medium text-slate-900">API Hash</span>
                <input v-model="form.api_hash" type="text" placeholder="可选" class="block w-full rounded-[18px] border-0 bg-slate-50 px-4 py-3 text-slate-900 ring-1 ring-inset ring-slate-200 focus:ring-2 focus:ring-primary-600" />
              </label>
              <label class="space-y-2 text-sm text-slate-600 sm:col-span-2">
                <span class="font-medium text-slate-900">Session</span>
                <textarea v-model="form.session" rows="4" placeholder="可选，如已有 Session 可直接粘贴" class="block w-full rounded-[18px] border-0 bg-slate-50 px-4 py-3 text-slate-900 ring-1 ring-inset ring-slate-200 focus:ring-2 focus:ring-primary-600"></textarea>
              </label>
            </div>
          </details>
        </UiCard>

        <div v-if="testResult" class="rounded-[20px] border px-4 py-3 text-sm" :class="testResult.success ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-amber-200 bg-amber-50 text-amber-800'">
          {{ testResult.message }}
        </div>

        <div v-if="testPhase === 'code' || testPhase === 'password'" class="rounded-[20px] border border-slate-200 bg-slate-50 px-4 py-4">
          <label class="space-y-2 text-sm text-slate-600">
            <span class="font-medium text-slate-900">{{ testPhase === 'password' ? '两步验证密码' : 'Telegram 验证码' }}</span>
            <input
              v-model="testCode"
              type="text"
              :placeholder="testPhase === 'password' ? '请输入登录密码' : '请输入手机上收到的验证码'"
              class="block w-full rounded-[18px] border-0 bg-white px-4 py-3 text-slate-900 ring-1 ring-inset ring-slate-200 focus:ring-2 focus:ring-primary-600"
              @keyup.enter="submitTestCode"
            />
          </label>
          <div class="mt-3 flex justify-end gap-3">
            <UiButton variant="outline" :loading="testSubmitting" @click="submitTestCode">提交</UiButton>
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
      <div v-if="currentAccount" class="space-y-6">
        <UiCard>
          <div class="flex items-start justify-between gap-4">
            <div>
              <h3 class="text-lg font-semibold text-slate-950">{{ currentAccount.masked_phone || currentAccount.phone }}</h3>
              <p class="mt-1 text-sm text-slate-500">查看账号状态、用途与连接信息。</p>
            </div>
            <UiBadge :variant="currentAccount.enabled ? 'success' : 'default'">
              {{ currentAccount.enabled ? '启用' : '停用' }}
            </UiBadge>
          </div>

          <div class="mt-5 flex flex-wrap gap-2">
            <UiBadge :variant="currentAccount.checkiner ? 'success' : 'default'">签到</UiBadge>
            <UiBadge :variant="currentAccount.monitor ? 'info' : 'default'">监控</UiBadge>
            <UiBadge :variant="currentAccount.messager ? 'warning' : 'default'">水群</UiBadge>
            <UiBadge :variant="currentAccount.registrar ? 'error' : 'default'">抢注</UiBadge>
          </div>
        </UiCard>

        <UiCard>
          <div class="grid gap-4 sm:grid-cols-2">
            <div v-for="item in accountDetailItems" :key="item.label" class="rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3">
              <p class="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">{{ item.label }}</p>
              <p class="mt-2 break-all text-sm font-medium text-slate-900">{{ item.value }}</p>
            </div>
          </div>
        </UiCard>

        <div class="flex justify-end gap-3">
          <UiButton variant="secondary" @click="openEditDrawer(currentAccount)">
            <PencilSquareIcon class="mr-2 h-4 w-4" />
            编辑
          </UiButton>
        </div>
      </div>
    </UiDrawer>
  </div>
</template>
