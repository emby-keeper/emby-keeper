<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ChartBarIcon, CheckCircleIcon, ChevronLeftIcon, ClockIcon, ExclamationTriangleIcon, PlayIcon , MagnifyingGlassIcon } from '@heroicons/vue/24/outline'
import UiButton from '@/components/ui/UiButton.vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiCard from '@/components/ui/UiCard.vue'
import UiDrawer from '@/components/ui/UiDrawer.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import UiStat from '@/components/ui/UiStat.vue'
import { useAuthStore } from '@/stores/auth'
import { useRoute, useRouter } from 'vue-router'
import type { RunSummary, RunDetail, RunLogEntry } from '@/types'
import { logger } from '@/utils/logger'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const runs = ref<RunSummary[]>([])
const status = ref(typeof route.query.status === 'string' ? route.query.status : '')
const search = ref(typeof route.query.q === 'string' ? route.query.q : '')
const drawerOpen = ref(false)
const detail = ref<RunDetail | null>(null)
const selectedChild = ref<RunDetail | null>(null)
const children = ref<RunSummary[]>([])
const logs = ref<RunLogEntry[]>([])
const childLogs = ref<RunLogEntry[]>([])
const loading = ref(true)
const detailLoading = ref(false)
const childDetailLoading = ref(false)
const actionLoading = ref<string | null>(null)
const error = ref('')
const detailError = ref('')
const initialDrawerSection = ref<'overview' | 'children'>('overview')
let detailRequestVersion = 0
let childRequestVersion = 0

const ACTIVE_STATUSES = new Set(['PENDING', 'INITIALIZING', 'RUNNING'])
const statusOptions = [
  { label: '全部状态', value: '' },
  { label: '等待执行', value: 'PENDING' },
  { label: '初始化中', value: 'INITIALIZING' },
  { label: '运行中', value: 'RUNNING' },
  { label: '成功', value: 'SUCCESS' },
  { label: '失败', value: 'FAIL' },
  { label: '异常', value: 'ERROR' },
  { label: '已取消', value: 'CANCELLED' },
  { label: '已跳过', value: 'SKIP' },
  { label: '等待重试', value: 'RESCHEDULE' },
]

const currentRun = computed(() => selectedChild.value?.run || detail.value?.run || null)
const currentLogs = computed(() => selectedChild.value ? childLogs.value : logs.value)
const breadcrumbItems = computed(() => {
  const items = []

  if (detail.value?.run) {
    items.push({ id: detail.value.run.id, label: detail.value.run.description || detail.value.run.id, isChild: false })
  }

  if (selectedChild.value?.run) {
    items.push({ id: selectedChild.value.run.id, label: selectedChild.value.run.description || selectedChild.value.run.id, isChild: true })
  }

  return items
})
const filteredRuns = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) {
    return runs.value
  }

  return runs.value.filter((run) => {
    return [run.id, run.description, run.status, run.status_info]
      .some((value) => String(value || '').toLowerCase().includes(keyword))
  })
})

const summary = computed(() => {
  return runs.value.reduce(
    (acc, run) => {
      acc.total += 1

      if (ACTIVE_STATUSES.has(run.status)) {
        acc.running += 1
      }

      if (run.status === 'SUCCESS') {
        acc.success += 1
      }

      if (['ERROR', 'FAIL', 'FAILED', 'CANCELLED'].includes(run.status)) {
        acc.failed += 1
      }

      return acc
    },
    { total: 0, running: 0, success: 0, failed: 0 },
  )
})

const fetchList = async () => {
  loading.value = true
  error.value = ''

  try {
    const q = status.value ? `?status=${encodeURIComponent(status.value)}` : ''
    const data = await auth.request<{ runs: RunSummary[] }>(`/runinfo${q}`)
    runs.value = data.runs || []
  } catch (err) {
    logger.error('Failed to fetch runs', err)
    error.value = logger.message(err, '运行记录加载失败')
  } finally {
    loading.value = false
  }
}

const normalizeLogs = (items: RunLogEntry[]): RunLogEntry[] => {
  return items.map((log) => ({
    ...log,
    level: log.level || 'INFO',
    message: log.message || '-',
    displayTime: (log.time || log.timestamp) ? new Date(log.time || log.timestamp!).toLocaleString('zh-CN') : '-',
  }))
}

const openDetail = async (id: string, section: 'overview' | 'children' = 'overview') => {
  const requestVersion = ++detailRequestVersion
  childRequestVersion++
  drawerOpen.value = true
  detailLoading.value = true
  childDetailLoading.value = false
  detailError.value = ''
  initialDrawerSection.value = section
  detail.value = null
  selectedChild.value = null
  children.value = []
  logs.value = []
  childLogs.value = []

  try {
    const [d, c, l] = await Promise.all([
      auth.request<RunDetail>(`/runinfo/${id}`),
      auth.request<{ runs: RunSummary[] }>(`/runinfo/${id}/children`),
      auth.request<{ logs: RunLogEntry[] }>(`/runinfo/${id}/logs?include_children=true`),
    ])

    if (requestVersion !== detailRequestVersion) return
    detail.value = d
    children.value = c.runs || []
    logs.value = normalizeLogs(l.logs || [])
  } catch (err) {
    if (requestVersion !== detailRequestVersion) return
    logger.error('Failed to fetch run detail', err)
    detailError.value = logger.message(err, '运行详情加载失败')
  } finally {
    if (requestVersion === detailRequestVersion) detailLoading.value = false
  }
}

const syncQuery = () => {
  const nextQuery: Record<string, string> = {}

  if (status.value) nextQuery.status = status.value
  if (search.value) nextQuery.q = search.value
  if (drawerOpen.value && detail.value?.run?.id) nextQuery.run = detail.value.run.id
  if (drawerOpen.value && initialDrawerSection.value === 'children') nextQuery.section = 'children'

  router.replace({ query: nextQuery })
}

const openChildDetail = async (childId: string) => {
  const requestVersion = ++childRequestVersion
  childDetailLoading.value = true
  detailError.value = ''

  try {
    const [childDetail, childLogResult] = await Promise.all([
      auth.request<RunDetail>(`/runinfo/${childId}`),
      auth.request<{ logs: RunLogEntry[] }>(`/runinfo/${childId}/logs?include_children=true`),
    ])

    if (requestVersion !== childRequestVersion) return
    selectedChild.value = childDetail
    childLogs.value = normalizeLogs(childLogResult.logs || [])
  } catch (err) {
    if (requestVersion !== childRequestVersion) return
    logger.error('Failed to fetch child run detail', err)
    detailError.value = logger.message(err, '子任务详情加载失败')
  } finally {
    if (requestVersion === childRequestVersion) childDetailLoading.value = false
  }
}

const backToParent = () => {
  childRequestVersion++
  childDetailLoading.value = false
  selectedChild.value = null
  childLogs.value = []
}

const cancelRun = async (id: string) => {
  if (!window.confirm('确定取消这个正在执行的任务吗？')) return
  actionLoading.value = id

  try {
    await auth.request(`/runinfo/${id}/cancel`, { method: 'POST' })
    await fetchList()

    if (detail.value?.run?.id === id) {
      await openDetail(id, initialDrawerSection.value)
    }
  } catch (err) {
    logger.error('Failed to cancel run', err)
    error.value = logger.message(err, '取消任务失败')
  } finally {
    actionLoading.value = null
  }
}

const cancelAll = async () => {
  if (!window.confirm('确定取消全部正在执行的任务吗？')) return
  actionLoading.value = 'all'

  try {
    await auth.request('/runinfo/cancel_all', { method: 'POST' })
    await fetchList()
  } catch (err) {
    logger.error('Failed to cancel all runs', err)
    error.value = logger.message(err, '取消全部任务失败')
  } finally {
    actionLoading.value = null
  }
}

const getStatusVariant = (s: string) => {
  if (s === 'SUCCESS') return 'success'
  if (s === 'ERROR' || s === 'FAILED' || s === 'FAIL') return 'error'
  if (s === 'RUNNING') return 'info'
  if (s === 'CANCELLED') return 'warning'
  return 'default'
}

const canCancel = (run: RunSummary) => ACTIVE_STATUSES.has(run.status)

const formatDateTime = (value?: string | null) => {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN')
}

const formatDuration = (value?: number | null) => {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-'

  if (value < 60) {
    return `${value.toFixed(1)}s`
  }

  const minutes = Math.floor(value / 60)
  const seconds = Math.round(value % 60)
  return `${minutes}m ${seconds}s`
}

watch([status, search], () => {
  syncQuery()
})

watch(drawerOpen, (open) => {
  if (!open) {
    detailRequestVersion++
    childRequestVersion++
    detailLoading.value = false
    childDetailLoading.value = false
    detail.value = null
    selectedChild.value = null
    children.value = []
    logs.value = []
    childLogs.value = []
  }
  syncQuery()
})

watch(detail, () => {
  syncQuery()
})

watch(initialDrawerSection, () => {
  syncQuery()
})

onMounted(async () => {
  await fetchList()

  const runId = typeof route.query.run === 'string' ? route.query.run : ''
  const section = route.query.section === 'children' ? 'children' : 'overview'
  if (runId) {
    await openDetail(runId, section)
  }
})
</script>

<template>
  <div class="space-y-8">
    <section class="overflow-hidden rounded-[30px] border border-slate-200/80 bg-gradient-to-br from-white via-slate-50 to-slate-100 shadow-[0_20px_60px_-32px_rgba(15,23,42,0.35)]">
  <div class="px-4 py-5 sm:px-6 sm:py-6 xl:px-8">
        <div class="max-w-2xl space-y-2">
          <p class="text-xs font-semibold uppercase tracking-[0.22em] text-primary-600">Task History</p>
          <div>
            <h1 class="text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">任务记录</h1>
            <p class="mt-2 text-sm leading-6 text-slate-600">查看任务执行状态、运行结果与调度信息。</p>
          </div>
        </div>
        <div class="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <UiStat label="运行记录" :value="summary.total" :icon="ChartBarIcon" />
          <UiStat label="运行中" :value="summary.running" :icon="PlayIcon" />
          <UiStat label="成功" :value="summary.success" :icon="CheckCircleIcon" />
          <UiStat label="异常/取消" :value="summary.failed" :icon="ExclamationTriangleIcon" />
        </div>
      </div>
    </section>

    <UiCard class="overflow-hidden">
      <template #header>
        <div class="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 class="text-lg font-semibold tracking-tight text-slate-950">任务列表</h2>
            <p class="mt-1 text-sm text-slate-600">支持筛选、查看详情和取消正在执行的任务。</p>
          </div>
          <div class="inline-flex items-center rounded-full bg-white px-3 py-1.5 text-xs font-medium text-slate-500 ring-1 ring-slate-200">
            共 {{ filteredRuns.length }} 条记录
          </div>
        </div>
      </template>

      <div class="min-w-0 rounded-[26px] border border-slate-200/70 bg-slate-50/80 p-3 sm:p-4">
      <div class="mb-5 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div class="flex min-w-0 flex-1 flex-col gap-3 sm:flex-row sm:items-end">
          <div class="relative w-full sm:max-w-xs">
            <label for="runinfo-search" class="sr-only">搜索运行记录</label>
            <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
              <MagnifyingGlassIcon class="h-5 w-5 text-gray-400" aria-hidden="true" />
            </div>
            <input
              id="runinfo-search"
              v-model="search"
              type="text"
              placeholder="搜索 ID、描述..."
              class="block w-full rounded-[20px] border-0 bg-white py-3 pl-10 text-slate-900 shadow-sm ring-1 ring-inset ring-slate-200 placeholder:text-slate-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6"
            />
          </div>
          <div class="relative w-full sm:max-w-xs">
            <UiSelect
              v-model="status"
              label="按状态筛选"
              :options="statusOptions"
              @update:model-value="fetchList"
            />
          </div>
        </div>
        <div class="flex shrink-0 flex-wrap items-center justify-end gap-2">
          <UiButton @click="fetchList" :disabled="loading" variant="secondary">
            {{ loading ? '加载中...' : '刷新' }}
          </UiButton>
          <UiButton
            v-if="summary.running > 0"
            variant="danger"
            :loading="actionLoading === 'all'"
            @click="cancelAll"
          >
            取消全部
          </UiButton>
        </div>
      </div>

      <div v-if="error" class="mb-5 rounded-[20px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        {{ error }}
      </div>

      <div v-if="loading" class="space-y-3">
        <div v-for="i in 5" :key="i" class="h-16 animate-pulse rounded-[24px] bg-white"></div>
      </div>

      <div v-else-if="filteredRuns.length === 0" class="rounded-[24px] bg-white px-6 py-16 text-center ring-1 ring-slate-200">
        <ChartBarIcon class="mx-auto mb-4 h-16 w-16 text-slate-300" />
        <p class="text-slate-500">没有匹配的运行记录</p>
      </div>

      <div v-else class="overflow-hidden rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_24px_-18px_rgba(15,23,42,0.28)]">
        <div class="divide-y divide-slate-200 lg:hidden">
          <article v-for="run in filteredRuns" :key="run.id" class="min-w-0 space-y-3 p-4">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <span class="break-all font-mono text-xs font-semibold text-slate-600">{{ run.id }}</span>
              <UiBadge :variant="getStatusVariant(run.status)">
                {{ statusOptions.find(option => option.value === run.status)?.label || run.status }}
              </UiBadge>
            </div>
            <p class="break-words text-sm font-medium leading-6 text-slate-900">{{ run.description || '-' }}</p>
            <p v-if="run.status_info" class="break-words text-xs leading-5 text-slate-500">{{ run.status_info }}</p>
            <dl class="grid grid-cols-2 gap-3 text-xs">
              <div class="min-w-0">
                <dt class="text-slate-400">开始时间</dt>
                <dd class="mt-1 break-words text-slate-700">{{ formatDateTime(run.start_time) }}</dd>
              </div>
              <div class="min-w-0">
                <dt class="text-slate-400">耗时</dt>
                <dd class="mt-1 text-slate-700">{{ formatDuration(run.duration) }}</dd>
              </div>
              <div v-if="run.next_time" class="col-span-2 min-w-0">
                <dt class="text-slate-400">下次执行</dt>
                <dd class="mt-1 break-words text-slate-700">{{ formatDateTime(run.next_time) }}</dd>
              </div>
            </dl>
            <div class="flex flex-wrap items-center justify-end gap-2 border-t border-slate-100 pt-3">
              <UiButton size="sm" variant="secondary" @click="openDetail(run.id)">查看详情</UiButton>
              <UiButton v-if="(run.child_count ?? 0) > 0" size="sm" variant="ghost" @click="openDetail(run.id, 'children')">
                子任务 {{ run.child_count }}
              </UiButton>
              <UiButton v-if="canCancel(run)" size="sm" variant="danger" :loading="actionLoading === run.id" @click="cancelRun(run.id)">取消</UiButton>
            </div>
          </article>
        </div>
        <div class="hidden overflow-x-auto lg:block" tabindex="0" role="region" aria-label="任务记录表格">
        <table class="min-w-[1120px] table-auto divide-y divide-slate-200" role="grid" aria-label="任务列表">
          <thead class="bg-slate-50/90">
            <tr>
              <th scope="col" class="whitespace-nowrap py-3.5 pl-4 pr-3 text-left text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 sm:pl-6">ID</th>
              <th scope="col" class="min-w-[20rem] px-3 py-3.5 text-left text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">描述</th>
              <th scope="col" class="whitespace-nowrap px-3 py-3.5 text-left text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">状态</th>
              <th scope="col" class="whitespace-nowrap px-3 py-3.5 text-left text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">开始时间</th>
              <th scope="col" class="whitespace-nowrap px-3 py-3.5 text-left text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">耗时</th>
              <th scope="col" class="whitespace-nowrap px-3 py-3.5 text-left text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">下次执行</th>
              <th scope="col" class="whitespace-nowrap px-3 py-3.5 text-left text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">子任务</th>
              <th scope="col" class="relative min-w-[11rem] py-3.5 pl-3 pr-4 sm:pr-6">
                <span class="sr-only">操作</span>
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 bg-white">
                <tr
              v-for="run in filteredRuns"
              :key="run.id"
              class="cursor-pointer transition-colors hover:bg-slate-50/80 focus-within:bg-slate-50 focus-within:ring-2 focus-within:ring-inset focus-within:ring-primary-400"
              :tabindex="0"
              :aria-label="`${run.description || run.id} - ${run.status}`"
              @click="openDetail(run.id)"
              @keydown.enter="openDetail(run.id)"
            >
              <td class="whitespace-nowrap py-4 pl-4 pr-3 text-sm font-semibold text-slate-900 sm:pl-6">
                {{ run.id }}
              </td>
              <td class="min-w-[20rem] px-3 py-4 text-sm text-slate-500">
                <div class="font-medium leading-6 text-slate-900">{{ run.description || '-' }}</div>
                <div v-if="run.status_info" class="mt-1 text-xs text-slate-500">{{ run.status_info }}</div>
              </td>
              <td class="whitespace-nowrap px-3 py-4 text-sm text-slate-500">
                <UiBadge :variant="getStatusVariant(run.status)">{{ run.status }}</UiBadge>
              </td>
              <td class="whitespace-nowrap px-3 py-4 text-sm text-slate-600">{{ formatDateTime(run.start_time) }}</td>
              <td class="whitespace-nowrap px-3 py-4 text-sm text-slate-600">{{ formatDuration(run.duration) }}</td>
              <td class="whitespace-nowrap px-3 py-4 text-sm text-slate-600">{{ formatDateTime(run.next_time) }}</td>
              <td class="whitespace-nowrap px-3 py-4 text-sm text-slate-600">
                <button
                  type="button"
                  class="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-200"
                  @click.stop="openDetail(run.id, 'children')"
                >
                  {{ run.child_count ?? 0 }} 个
                </button>
              </td>
              <td class="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-6">
                <div class="flex items-center justify-end gap-2">
                  <UiButton size="sm" variant="ghost" @click.stop="openDetail(run.id)">
                    查看详情
                  </UiButton>
                  <UiButton
                    v-if="(run.child_count ?? 0) > 0"
                    size="sm"
                    variant="secondary"
                    @click.stop="openDetail(run.id, 'children')"
                  >
                    查看子任务
                  </UiButton>
                  <UiButton
                    v-if="canCancel(run)"
                    size="sm"
                    variant="danger"
                    :loading="actionLoading === run.id"
                    @click.stop="cancelRun(run.id)"
                  >
                    取消
                  </UiButton>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        </div>
      </div>
      </div>
    </UiCard>

    <UiDrawer v-model="drawerOpen" :title="`任务详情: ${detail?.run?.id || ''}`">
      <div v-if="detailLoading" class="space-y-3">
        <div v-for="i in 3" :key="i" class="h-24 animate-pulse rounded-2xl bg-slate-100"></div>
      </div>

      <div v-else-if="detailError" class="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        {{ detailError }}
      </div>

      <div v-else class="space-y-6">
        <UiCard>
          <h3 class="text-lg font-semibold text-slate-900 mb-4">描述</h3>
          <p class="text-sm leading-7 text-slate-900">{{ currentRun?.description || '-' }}</p>
        </UiCard>

        <UiCard>
          <h3 class="text-lg font-semibold text-slate-900 mb-4">运行信息</h3>
          <div class="grid gap-3 text-sm sm:grid-cols-2">
            <div class="flex justify-between gap-4">
              <span class="text-slate-600">状态:</span>
              <UiBadge :variant="getStatusVariant(currentRun?.status)">
                {{ currentRun?.status }}
              </UiBadge>
            </div>
            <div class="flex justify-between gap-4">
              <span class="text-slate-600">父任务:</span>
              <span class="font-medium">{{ currentRun?.parent_ids?.join(', ') || '-' }}</span>
            </div>
            <div class="flex justify-between gap-4">
              <span class="text-slate-600">开始时间:</span>
              <span class="font-medium">{{ formatDateTime(currentRun?.start_time) }}</span>
            </div>
            <div class="flex justify-between gap-4">
              <span class="text-slate-600">结束时间:</span>
              <span class="font-medium">{{ formatDateTime(currentRun?.end_time) }}</span>
            </div>
            <div class="flex justify-between gap-4">
              <span class="text-slate-600">耗时:</span>
              <span class="font-medium">{{ formatDuration(currentRun?.duration) }}</span>
            </div>
            <div class="flex justify-between gap-4">
              <span class="text-slate-600">下次执行:</span>
              <span class="font-medium">{{ formatDateTime(currentRun?.next_time) }}</span>
            </div>
          </div>

          <div v-if="currentRun && canCancel(currentRun)" class="mt-5">
            <UiButton
              variant="danger"
              :loading="actionLoading === currentRun.id"
              @click="cancelRun(currentRun.id)"
            >
              取消当前任务
            </UiButton>
          </div>
        </UiCard>

        <UiCard v-if="!selectedChild && children.length > 0">
          <h3 class="text-lg font-semibold text-slate-900 mb-4">子任务 ({{ children.length }})</h3>
          <div class="space-y-2">
            <div
              v-for="child in children"
              :key="child.id"
              class="flex items-center justify-between p-3 bg-slate-50 rounded-xl"
            >
              <div class="flex-1">
                <div class="font-mono text-xs text-slate-600">{{ child.id }}</div>
                <div class="text-sm text-slate-900 mt-1">{{ child.description || '-' }}</div>
                <div class="mt-1 text-xs text-slate-500">
                  开始: {{ formatDateTime(child.start_time) }} | 耗时: {{ formatDuration(child.duration) }}
                </div>
              </div>
              <div class="flex items-center gap-2">
                <UiBadge size="sm" :variant="getStatusVariant(child.status)">
                  {{ child.status }}
                </UiBadge>
                <UiButton size="sm" variant="ghost" @click="openChildDetail(child.id)">
                  查看
                </UiButton>
              </div>
            </div>
          </div>
        </UiCard>

        <UiCard v-if="!selectedChild && children.length > 0 && initialDrawerSection === 'children'">
          <p class="text-sm text-slate-500">当前已定位到子任务分区，可继续查看单个子任务详情。</p>
        </UiCard>

        <UiCard v-if="childDetailLoading">
          <div class="space-y-3">
            <div v-for="i in 2" :key="i" class="h-20 animate-pulse rounded-2xl bg-slate-100"></div>
          </div>
        </UiCard>

        <UiCard>
          <h3 class="text-lg font-semibold text-slate-900 mb-4">日志记录</h3>

          <div v-if="currentLogs.length === 0" class="rounded-[18px] border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
            暂无日志记录。
          </div>

          <div v-else class="overflow-hidden rounded-[24px] border border-slate-200 bg-white shadow-[0_10px_24px_-18px_rgba(15,23,42,0.28)]">
            <div class="max-h-[50dvh] divide-y divide-slate-100 overflow-y-auto overscroll-contain sm:hidden">
              <article v-for="(log, index) in currentLogs" :key="index" class="min-w-0 space-y-2 p-3">
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <time class="text-[11px] tabular-nums text-slate-500">{{ log.displayTime }}</time>
                  <UiBadge size="sm" :variant="log.level === 'ERROR' ? 'error' : log.level === 'WARNING' ? 'warning' : 'default'">{{ log.level }}</UiBadge>
                </div>
                <p class="whitespace-pre-wrap break-all font-mono text-xs leading-6 text-slate-800">{{ log.message }}</p>
              </article>
            </div>
            <div class="hidden max-h-[50dvh] overflow-auto sm:block" tabindex="0" role="region" aria-label="日志记录表格">
              <table class="min-w-full divide-y divide-slate-200" role="grid" aria-label="日志记录">
                <thead class="bg-slate-50/90 sticky top-0 z-10">
                  <tr>
                    <th scope="col" class="whitespace-nowrap py-3.5 pl-4 pr-3 text-left text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 sm:pl-6">时间</th>
                    <th scope="col" class="whitespace-nowrap px-3 py-3.5 text-left text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">级别</th>
                    <th scope="col" class="px-3 py-3.5 text-left text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">消息</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100 bg-white">
                  <tr
                    v-for="(log, index) in currentLogs"
                    :key="`${log.displayTime}-${log.message}-${index}`"
                    class="transition-colors hover:bg-slate-50/80 focus-within:bg-slate-50 focus-within:ring-2 focus-within:ring-inset focus-within:ring-primary-400"
                    :tabindex="0"
                    :aria-label="`${log.displayTime} ${log.level} ${log.message}`"
                  >
                    <td class="whitespace-nowrap py-4 pl-4 pr-3 text-sm text-slate-600 sm:pl-6">{{ log.displayTime }}</td>
                    <td class="whitespace-nowrap px-3 py-4 text-sm text-slate-600">
                      <UiBadge :variant="log.level === 'ERROR' ? 'error' : log.level === 'WARNING' ? 'warning' : 'default'">{{ log.level }}</UiBadge>
                    </td>
                    <td class="break-words px-3 py-4 text-sm leading-6 text-slate-900">{{ log.message }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </UiCard>
      </div>
    </UiDrawer>
  </div>
</template>
