<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { Dialog, DialogPanel, TransitionChild, TransitionRoot } from '@headlessui/vue'
import { ArrowPathIcon, PencilSquareIcon, PlusIcon, PuzzlePieceIcon, TrashIcon } from '@heroicons/vue/24/outline'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiCard from '@/components/ui/UiCard.vue'
import UiDrawer from '@/components/ui/UiDrawer.vue'
import UiTooltip from '@/components/ui/UiTooltip.vue'
import UiListInput from '@/components/ui/UiListInput.vue'
import UiScheduleIntervalOverride from '@/components/ui/UiScheduleIntervalOverride.vue'
import UiScheduleTimeOverride from '@/components/ui/UiScheduleTimeOverride.vue'
import UiSelect, { type UiSelectOption } from '@/components/ui/UiSelect.vue'
import Switch from '@/components/Switch.vue'
import { useAuthStore } from '@/stores/auth'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { logger } from '@/utils/logger'

type TemplateOption = {
  key: string
  type: string
  default: unknown
  effective_default?: unknown
  description: string
  required?: boolean
  choices?: string[]
  choice_values?: Record<string, unknown>
}

type TemplateSpec = {
  kind: string
  hint: string
  options: TemplateOption[]
}

type BuiltinSite = {
  site: string
  display_name: string
  options: TemplateOption[]
}

type CustomSiteItem = {
  name: string
  kind: string
  bot?: string | null
  site?: string
  builtin?: boolean
  display_name: string
  in_site_list: boolean
  options: Record<string, unknown>
}

type TypeInfo = {
  label: string
  templates: TemplateSpec[]
  builtin: BuiltinSite[]
  items: CustomSiteItem[]
  required_group?: { keys: string[], message: string } | null
}

const typeOrder = ['checkiner', 'monitor', 'messager', 'registrar'] as const
type SiteType = (typeof typeOrder)[number]

const auth = useAuthStore()
const loading = ref(true)
const saving = ref(false)
const deleting = ref<string | null>(null)
const pageError = ref('')
const formError = ref('')
const types = ref<Record<string, TypeInfo>>({})
const defaults = ref<{ time_range?: string | null, interval_days?: string | null }>({})
const activeType = ref<SiteType>('checkiner')
const drawerOpen = ref(false)
const editingName = ref('')
const deleteDialogOpen = ref(false)
const deleteTarget = ref<CustomSiteItem | null>(null)

const form = reactive({
  kind: 'template' as 'template' | 'builtin',
  template: 'templ_a',
  bot: '',
  site: '',
  displayName: '',
  inSiteList: true,
  options: {} as Record<string, unknown>,
  custom: {} as Record<string, unknown>,
})
const customKey = ref('')
const customValue = ref('')
const storedOptionTypes = ref<Record<string, string>>({})

const serializeFormDraft = () => JSON.stringify({
  kind: form.kind,
  template: form.template,
  bot: form.bot,
  site: form.site,
  displayName: form.displayName,
  inSiteList: form.inSiteList,
  options: Object.fromEntries(Object.entries(form.options).filter(([, value]) =>
    value !== '' && value !== undefined && value !== null && (!Array.isArray(value) || value.length > 0),
  )),
  custom: form.custom,
  customKey: customKey.value,
  customValue: customValue.value,
})

const { model: drawerModel, markSaved } = useUnsavedChanges(drawerOpen, serializeFormDraft, saving)

const fieldClass = 'block w-full rounded-[16px] border-0 bg-white px-4 py-3 text-sm text-slate-900 ring-1 ring-inset ring-slate-200 placeholder:text-slate-400 focus:ring-2 focus:ring-primary-600'

const activeInfo = computed<TypeInfo | undefined>(() => types.value[activeType.value])
const templates = computed<TemplateSpec[]>(() => activeInfo.value?.templates || [])
const builtinSites = computed<BuiltinSite[]>(() => activeInfo.value?.builtin || [])
const items = computed<CustomSiteItem[]>(() => activeInfo.value?.items || [])
const templateHint = (kind: string) => templates.value.find(template => template.kind === kind)?.hint || '该站点使用自定义模板。'

const typeTabs = computed(() =>
  typeOrder.map((key) => ({
    key,
    label: types.value[key]?.label || key,
    count: types.value[key]?.items?.length || 0,
  })),
)

const templateSelectOptions = computed<UiSelectOption[]>(() =>
  templates.value.map((template) => ({
    label: template.kind,
    value: template.kind,
    description: template.hint,
  })),
)

const currentTemplate = computed<TemplateSpec | undefined>(() =>
  templates.value.find((template) => template.kind === form.template),
)

const selectedBuiltin = computed<BuiltinSite | undefined>(() =>
  builtinSites.value.find((item) => item.site === form.site.trim()),
)

const builtinOptions = computed<TemplateOption[]>(() => selectedBuiltin.value?.options || [])

const optionFields = computed<TemplateOption[]>(() => {
  if (form.kind === 'builtin') return builtinOptions.value
  return (currentTemplate.value?.options || []).filter((option) => option.key !== 'name')
})

const isEditing = computed(() => Boolean(editingName.value))
const drawerTitle = computed(() => (isEditing.value ? '编辑站点选项' : '新增自定义站点'))

const previewName = computed(() => {
  if (form.kind === 'builtin') return form.site.trim()
  const bot = form.bot.trim().replace(/^@/, '')
  return bot ? `${form.template}<${bot}>` : ''
})

const ENUM_DEFAULT = '__default__'
const ENUM_CUSTOM = '__custom__'

const enumCustomMode = ref<Record<string, boolean>>({})

const enumValueOf = (option: TemplateOption) => {
  if (enumCustomMode.value[option.key]) return ENUM_CUSTOM
  const raw = form.options[option.key]
  const text = raw === undefined || raw === null ? '' : String(raw)
  if (!text) return ENUM_DEFAULT
  const matchingChoice = (option.choices || []).find((choice) => {
    const runtimeValue = option.choice_values?.[choice] ?? choice
    return String(runtimeValue) === text || choice === text
  })
  return matchingChoice || ENUM_CUSTOM
}

const enumSelectOptions = (option: TemplateOption): UiSelectOption[] => [
  { label: '使用默认', value: ENUM_DEFAULT },
  ...(option.choices || []).map((choice) => ({ label: choice, value: choice })),
  ...(option.type.split('|').includes('str') ? [{ label: '自定义值', value: ENUM_CUSTOM }] : []),
]

const onEnumChange = (option: TemplateOption, value: string) => {
  const next = { ...enumCustomMode.value }
  delete next[option.key]
  enumCustomMode.value = next

  if (value === ENUM_DEFAULT) {
    delete form.options[option.key]
    return
  }
  if (value === ENUM_CUSTOM) {
    enumCustomMode.value = { ...enumCustomMode.value, [option.key]: true }
    form.options[option.key] = ''
    return
  }
  form.options[option.key] = option.choice_values?.[value] ?? value
}

const customEntries = computed(() => Object.entries(form.custom))

const requiredGroupMissing = computed(() => {
  const group = activeInfo.value?.required_group
  if (!group || !group.keys.length) return false
  if (form.kind === 'builtin' && !form.site.trim()) return false

  const values: Record<string, unknown> = { ...form.options, ...form.custom }
  const configured = group.keys.filter((key) => {
    const value = values[key]
    if (key === 'times') return Array.isArray(value) && value.some((item) => String(item).trim())
    if (key === 'interval_minutes') return Number.isInteger(Number(value)) && Number(value) > 0
    return value !== undefined && value !== null && value !== ''
  })
  return configured.length !== 1
})

const fetchSites = async () => {
  loading.value = true
  pageError.value = ''
  try {
    const data = await auth.request<{
      types: Record<string, TypeInfo>,
      defaults?: { time_range?: string | null, interval_days?: string | null },
    }>('/sites/custom')
    types.value = data.types || {}
    defaults.value = data.defaults || {}
  } catch (error) {
    logger.error('Failed to load custom sites', error)
    pageError.value = logger.message(error, '自定义站点加载失败')
  } finally {
    loading.value = false
  }
}

// 机器人用户名不需要 @, 但粘贴带 @ 的也能自适应
const onBotInput = (event: Event) => {
  form.bot = (event.target as HTMLInputElement).value.replace(/@/g, '')
}

const ATOM_LABELS: Record<string, string> = {
  bool: '开关',
  int: '整数',
  float: '小数',
  enum: '预设选项',
  str: '文本',
  list: '列表',
  dict: '键值表',
  any: '任意值',
}

const atomsOf = (type?: string) => String(type || '').split('|').filter(Boolean)

const optionTypeLabel = (option: TemplateOption) => {
  const atoms = atomsOf(option.type)
  if (!atoms.length) return '任意值'
  return atoms.map((atom) => ATOM_LABELS[atom] || atom).join(' / ')
}

const effectiveOptionType = (option: TemplateOption, value = form.options[option.key]) => {
  if (option.type !== 'any') return option.type
  if (storedOptionTypes.value[option.key]) return storedOptionTypes.value[option.key]

  if (Array.isArray(value)) {
    if (value.some((item) => typeof item !== 'string' && typeof item !== 'number')) return 'json'
    return value.length && value.every((item) => typeof item === 'number') ? 'int|list' : 'list'
  }
  if (typeof value === 'boolean') return 'bool'
  if (typeof value === 'number') return Number.isInteger(value) ? 'int' : 'float'
  if (typeof value === 'string') return 'str'
  if (value && typeof value === 'object') return 'dict'
  return 'any'
}

const isToggleOption = (option: TemplateOption) => effectiveOptionType(option) === 'bool'
const isNumberOption = (option: TemplateOption) => ['int', 'float'].includes(effectiveOptionType(option))
const isListOption = (option: TemplateOption) => atomsOf(effectiveOptionType(option)).includes('list')
// 列表类选项统一用列表控件; 单个元素时序列化为标量
const isListInputOption = (option: TemplateOption) => isListOption(option)
const isNumericListOption = (option: TemplateOption) => {
  const atoms = atomsOf(effectiveOptionType(option))
  return atoms.includes('list') && (atoms.includes('int') || atoms.includes('float')) && !atoms.includes('str')
}
const isEnumOption = (option: TemplateOption) => Boolean(option.choices?.length)
const isTimeRangeOption = (option: TemplateOption) => option.key === 'time_range'
const isIntervalDaysOption = (option: TemplateOption) => option.key === 'interval_days'
const isSensitiveOption = (key: string) => /password|passwd|secret|token|session|api.?hash/i.test(key)

const formatCustomValue = (key: string, value: unknown) => {
  if (isSensitiveOption(key)) return '••••••'
  return Array.isArray(value) ? value.join(', ') : String(value)
}

const optionPlaceholder = (option: TemplateOption) => {
  if (isNumericListOption(option)) return '输入数字后按回车或点添加'
  return '留空则使用默认值'
}

const defaultOptionValue = (option: TemplateOption) =>
  option.effective_default !== undefined ? option.effective_default : option.default

const toggleSummary = (option: TemplateOption) => {
  if (option.key in form.options) return form.options[option.key] ? '已开启' : '已关闭'
  const defaultValue = defaultOptionValue(option)
  if (typeof defaultValue === 'boolean') return `未设置，默认${defaultValue ? '开启' : '关闭'}`
  return '未设置，使用默认'
}

const resetForm = () => {
  form.kind = 'template'
  form.template = templates.value[0]?.kind || 'templ_a'
  form.bot = ''
  form.site = ''
  form.displayName = ''
  form.inSiteList = true
  form.options = {}
  form.custom = {}
  storedOptionTypes.value = {}
  enumCustomMode.value = {}
  customKey.value = ''
  customValue.value = ''
  markSaved()
}

const openCreate = () => {
  editingName.value = ''
  formError.value = ''
  resetForm()
  drawerOpen.value = true
}

const formatOptionValue = (option: TemplateOption, value: unknown) => {
  if (value === null || value === undefined) return ''
  if (effectiveOptionType(option, value) === 'json') return JSON.stringify(value, null, 2)
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

const applyStoredOptions = (stored: Record<string, unknown>) => {
  storedOptionTypes.value = {}
  const specs = optionFields.value
  const specMap = new Map(specs.map((option) => [option.key, option]))
  const next: Record<string, unknown> = {}
  const custom: Record<string, unknown> = {}

  for (const [key, value] of Object.entries(stored || {})) {
    if (key === 'name' && form.kind === 'template') continue
    if (value === null || value === undefined) continue
    const spec = specMap.get(key)
    if (!spec) {
      custom[key] = value
      continue
    }
    const type = effectiveOptionType(spec, value)
    if (spec.type === 'any') storedOptionTypes.value[key] = type
    if (type === 'bool') next[key] = Boolean(value)
    else if (isEnumOption(spec)) next[key] = value
    else if (isTimeRangeOption(spec) || isIntervalDaysOption(spec)) next[key] = String(value)
    else if (atomsOf(type).includes('list')) {
      next[key] = Array.isArray(value)
        ? value.map((item) => String(item))
        : type.includes('str')
          ? String(value).split(',').map((item) => item.trim()).filter(Boolean)
          : [String(value)]
    } else if (type === 'int' || type === 'float') next[key] = value
    else next[key] = formatOptionValue(spec, value)
  }

  form.options = next
  form.custom = custom
}

const openEdit = (item: CustomSiteItem) => {
  editingName.value = item.name
  formError.value = ''
  enumCustomMode.value = {}
  customKey.value = ''
  customValue.value = ''

  if (item.builtin) {
    form.kind = 'builtin'
    form.site = item.site || item.name
    form.bot = ''
    form.displayName = ''
    form.inSiteList = true
  } else {
    form.kind = 'template'
    form.template = item.kind
    form.bot = item.bot || ''
    form.site = ''
    form.displayName = String(item.options?.name || '')
    form.inSiteList = item.in_site_list
  }

  applyStoredOptions(item.options || {})
  markSaved()
  drawerOpen.value = true
}

const onTemplateChange = () => {
  const previous = form.options
  const next: Record<string, unknown> = {}
  for (const option of optionFields.value) {
    if (option.key in previous) next[option.key] = previous[option.key]
  }
  form.options = next
}

const onKindChange = () => {
  form.options = {}
  formError.value = ''
}

const addCustomOption = () => {
  const key = customKey.value.trim()
  if (!key) return
  if (key in form.custom) {
    formError.value = `自定义选项 ${key} 已存在`
    return
  }
  formError.value = ''
  form.custom = { ...form.custom, [key]: parseCustomValue(customValue.value) }
  customKey.value = ''
  customValue.value = ''
}

const removeCustomOption = (key: string) => {
  const next = { ...form.custom }
  delete next[key]
  form.custom = next
}

const parseCustomValue = (raw: string): unknown => {
  const text = raw.trim()
  if (!text) return ''
  if (text === 'true') return true
  if (text === 'false') return false
  if (/^-?\d+$/.test(text)) return Number(text)
  if (/^-?\d*\.\d+$/.test(text)) return Number(text)
  if (text.startsWith('[') && text.endsWith(']')) {
    try {
      return JSON.parse(text)
    } catch {
      /* 交给下面的逗号拆分 */
    }
  }
  if (text.startsWith('{') && text.endsWith('}')) {
    try {
      return JSON.parse(text)
    } catch {
      // 保留为普通字符串, 由站点自己解释。
    }
  }
  if (text.includes(',')) {
    return text.split(',').map((part) => part.trim()).filter(Boolean)
  }
  return text
}

const coerceOptions = () => {
  const result: Record<string, unknown> = {}
  const displayName = form.displayName.trim()
  if (displayName) result.name = displayName

  for (const option of optionFields.value) {
    const value = form.options[option.key]
    if (value === undefined || value === null || value === '') continue

    const type = effectiveOptionType(option, value)

    if (type === 'bool') {
      result[option.key] = Boolean(value)
      continue
    }

    if (isEnumOption(option)) {
      result[option.key] = value
      continue
    }

    if (isTimeRangeOption(option) || isIntervalDaysOption(option)) {
      const text = String(value).trim()
      if (text) result[option.key] = text
      continue
    }

    if (atomsOf(type).includes('list')) {
      const list = (Array.isArray(value) ? value : [value]).map((item) => String(item).trim()).filter(Boolean)
      if (!list.length) continue
      const items: unknown[] = isNumericListOption(option)
        ? list.map((item) => {
            const numeric = Number(item)
            if (Number.isNaN(numeric)) throw new Error(`选项 ${option.key} 需要填写数字`)
            return numeric
          })
        : list
      // 类型允许标量且只填了一个值时写成标量, 否则写成数组
      const allowsScalar = atomsOf(option.type).some((atom) => atom !== 'list' && atom !== 'any')
      result[option.key] = allowsScalar && items.length === 1 ? items[0] : items
      continue
    }

    if (type === 'int' || type === 'float') {
      const numeric = Number(value)
      if (Number.isNaN(numeric)) throw new Error(`选项 ${option.key} 需要填写数字`)
      result[option.key] = numeric
      continue
    }

    if (type === 'dict' || type === 'json') {
      let parsed: unknown
      try {
        parsed = JSON.parse(String(value))
      } catch {
        throw new Error(`选项 ${option.key} 需要填写有效的 JSON`)
      }
      if (!parsed || typeof parsed !== 'object' || (type === 'dict' && Array.isArray(parsed))) {
        throw new Error(`选项 ${option.key} 需要填写 JSON 对象或列表`)
      }
      result[option.key] = parsed
      continue
    }

    const text = String(value).trim()
    if (!text) continue

    if (type === 'int|str') {
      result[option.key] = /^-?\d+$/.test(text) ? Number(text) : text
      continue
    }

    result[option.key] = text
  }

  return result
}

const submitForm = async () => {
  if (saving.value) return
  formError.value = ''
  try {
  if (activeType.value === 'registrar' && form.kind === 'template' && form.inSiteList && requiredGroupMissing.value) {
    formError.value = activeInfo.value?.required_group?.message || '请填写有效的抢注调度方式'
    return
  }

  const payload: Record<string, unknown> = {
    type: activeType.value,
    kind: form.kind,
    options: { ...coerceOptions(), ...form.custom },
  }

  if (form.kind === 'builtin') {
    const site = form.site.trim()
    if (!site) {
      formError.value = '请选择或填写要调整的内置站点'
      return
    }
    payload.site = site
  } else {
    const bot = form.bot.trim().replace(/^@/, '')
    if (!bot) {
      formError.value = '请填写机器人用户名'
      return
    }
    payload.template = form.template
    payload.bot = bot
    payload.in_site_list = form.inSiteList
  }

  saving.value = true
  formError.value = ''
    const data = await auth.request<{ items: CustomSiteItem[] }>('/sites/custom', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    if (types.value[activeType.value]) {
      types.value[activeType.value].items = data.items || []
    }
    markSaved()
    drawerOpen.value = false
  } catch (error) {
    logger.error('Failed to save custom site', error)
    formError.value = logger.message(error, '保存自定义站点失败')
  } finally {
    saving.value = false
  }
}

const askDelete = (item: CustomSiteItem) => {
  deleteTarget.value = item
  deleteDialogOpen.value = true
}

const confirmDelete = async () => {
  const target = deleteTarget.value
  if (!target) return

  deleting.value = target.name
  pageError.value = ''
  try {
    const data = await auth.request<{ items: CustomSiteItem[] }>(
      `/sites/custom?type=${encodeURIComponent(activeType.value)}&name=${encodeURIComponent(target.name)}`,
      { method: 'DELETE' },
    )
    if (types.value[activeType.value]) {
      types.value[activeType.value].items = data.items || []
    }
    deleteDialogOpen.value = false
    deleteTarget.value = null
  } catch (error) {
    logger.error('Failed to delete custom site', error)
    pageError.value = logger.message(error, '删除自定义站点失败')
  } finally {
    deleting.value = null
  }
}

const optionSummary = (item: CustomSiteItem) => {
  const entries = Object.entries(item.options || {}).filter(([key]) => key !== 'name')
  if (!entries.length) return []
  return entries.slice(0, 3).map(([key, value]) => `${key} = ${formatCustomValue(key, value)}`)
}

const optionIsSet = (key: string) => Object.prototype.hasOwnProperty.call(form.options, key)

const optionToggleValue = (option: TemplateOption) =>
  optionIsSet(option.key)
    ? Boolean(form.options[option.key])
    : Boolean(option.effective_default ?? option.default)

const optionToggleHint = (option: TemplateOption) => {
  if (optionIsSet(option.key)) return form.options[option.key] ? '已开启' : '已关闭'
  const defaultValue = option.effective_default ?? option.default
  return defaultValue === undefined || defaultValue === null
    ? '未设置，使用默认'
    : `未设置，默认${defaultValue ? '开启' : '关闭'}`
}

fetchSites()
</script>

<template>
  <div class="space-y-8">
    <section class="overflow-hidden rounded-[30px] border border-slate-200/80 bg-gradient-to-br from-white via-slate-50 to-slate-100 shadow-[0_20px_60px_-32px_rgba(15,23,42,0.35)]">
      <div class="px-4 py-5 sm:px-6 sm:py-6 xl:px-8">
        <div class="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div class="min-w-0 flex-1 space-y-3">
            <div class="inline-flex items-center gap-2 rounded-full bg-slate-900/5 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-slate-600 ring-1 ring-slate-200">
              <PuzzlePieceIcon class="h-4 w-4" aria-hidden="true" />
              Custom
            </div>
            <div>
              <h1 class="text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">自定义站点</h1>
              <p class="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
                用模板把尚未内置的机器人接入签到 / 监控 / 水群 / 抢注。新增的站点会写入配置文件，并可按需加入站点列表。
              </p>
            </div>
          </div>
          <div class="flex shrink-0 flex-wrap items-center gap-2 self-start">
            <UiButton variant="outline" :loading="loading" @click="fetchSites">
              <ArrowPathIcon class="mr-2 h-4 w-4" />
              刷新
            </UiButton>
            <UiButton @click="openCreate">
              <PlusIcon class="mr-2 h-4 w-4" />
              新增自定义站点
            </UiButton>
          </div>
        </div>
      </div>
    </section>

    <UiCard class="overflow-hidden border-slate-200/70 bg-white/90">
      <div class="rounded-[20px] border border-slate-200 bg-slate-50 p-1">
        <div class="grid grid-cols-2 gap-1 sm:grid-cols-4">
          <button
            v-for="tab in typeTabs"
            :key="tab.key"
            type="button"
            class="rounded-[16px] px-3 py-2 text-sm font-medium transition"
            :class="activeType === tab.key ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
            @click="activeType = tab.key"
          >
            {{ tab.label }}
            <span class="ml-1 text-xs text-slate-400">{{ tab.count }}</span>
          </button>
        </div>
      </div>

      <div v-if="pageError" class="mt-4 rounded-[20px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        {{ pageError }}
      </div>

      <div v-if="loading" class="mt-5 space-y-2.5">
        <div v-for="index in 3" :key="index" class="h-16 animate-pulse rounded-[16px] bg-slate-100"></div>
      </div>

      <template v-else>
        <div v-if="!templates.length" class="mt-5 rounded-[16px] border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
          {{ activeInfo?.label || '' }} 没有可用的自定义模板。
        </div>

        <div v-else-if="!items.length" class="mt-5 rounded-[16px] border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
          还没有为「{{ activeInfo?.label }}」添加自定义站点。
        </div>

        <div v-else class="mt-5 space-y-2.5">
          <div
            v-for="item in items"
            :key="item.name"
            class="rounded-[16px] border border-slate-200 bg-white px-4 py-3.5"
          >
            <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <p class="break-words text-sm font-semibold text-slate-900">{{ item.display_name }}</p>
                  <UiBadge v-if="item.builtin" size="sm" variant="warning">内置站点</UiBadge>
                  <UiTooltip v-else :text="templateHint(item.kind)">
                    <button
                      type="button"
                      class="inline-flex cursor-help rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 focus-visible:ring-offset-2"
                      :aria-label="`${item.kind} 模板说明`"
                    >
                      <UiBadge size="sm" variant="info">{{ item.kind }}</UiBadge>
                    </button>
                  </UiTooltip>
                  <UiBadge v-if="!item.builtin" size="sm" :variant="item.in_site_list ? 'success' : 'default'">
                    {{ item.in_site_list ? '已在站点列表' : '未加入站点列表' }}
                  </UiBadge>
                </div>
                <p class="mt-1 break-all font-mono text-xs text-slate-500">{{ item.name }}</p>
                <div v-if="optionSummary(item).length" class="mt-2 flex flex-wrap gap-1.5">
                  <span
                    v-for="entry in optionSummary(item)"
                    :key="entry"
                    class="max-w-full break-all rounded-lg bg-slate-100 px-2 py-0.5 font-mono text-[11px] text-slate-600"
                  >
                    {{ entry }}
                  </span>
                  <span v-if="Object.keys(item.options || {}).length > 4" class="px-1 text-[11px] text-slate-400">…</span>
                </div>
              </div>
              <div class="flex shrink-0 flex-wrap items-center justify-end gap-2">
                <UiButton size="sm" variant="secondary" @click="openEdit(item)">
                  <PencilSquareIcon class="mr-1.5 h-4 w-4" />
                  编辑
                </UiButton>
                <UiButton size="sm" variant="danger" :loading="deleting === item.name" @click="askDelete(item)">
                  <TrashIcon class="mr-1.5 h-4 w-4" />
                  删除
                </UiButton>
              </div>
            </div>
          </div>
        </div>
      </template>
    </UiCard>

    <UiDrawer v-model="drawerModel" :title="drawerTitle">
      <div class="space-y-5">
        <UiCard padding="sm">
          <div class="space-y-4">
            <div class="space-y-2">
              <p class="text-sm font-medium text-slate-900">站点类型</p>
              <div class="grid grid-cols-2 gap-1 rounded-[14px] bg-slate-100 p-1">
                <button
                  type="button"
                  class="rounded-[10px] px-3 py-1.5 text-xs font-medium transition disabled:cursor-not-allowed"
                  :class="form.kind === 'template' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
                  :disabled="isEditing"
                  @click="form.kind = 'template'; onKindChange()"
                >
                  新建模板站点
                </button>
                <button
                  type="button"
                  class="rounded-[10px] px-3 py-1.5 text-xs font-medium transition disabled:cursor-not-allowed"
                  :class="form.kind === 'builtin' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
                  :disabled="isEditing"
                  @click="form.kind = 'builtin'; onKindChange()"
                >
                  调整内置站点
                </button>
              </div>
            </div>

            <template v-if="form.kind === 'template'">
              <UiSelect
                v-model="form.template"
                label="模板类型"
                :options="templateSelectOptions"
                :disabled="isEditing"
                @update:model-value="onTemplateChange"
              />
              <p v-if="currentTemplate?.hint" class="rounded-[14px] border border-dashed border-slate-300 bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-500">
                {{ currentTemplate.hint }}
              </p>

              <label class="block space-y-2 text-sm text-slate-600">
                <span class="font-medium text-slate-900">机器人用户名</span>
                <input
                  :value="form.bot"
                  type="text"
                  :disabled="isEditing"
                  :class="fieldClass"
                  placeholder="例如 moumou_bot（不需要 @）"
                  @input="onBotInput"
                />
                <span v-if="previewName" class="block font-mono text-xs text-slate-400">将创建：{{ previewName }}</span>
              </label>

              <label class="block space-y-2 text-sm text-slate-600">
                <span class="font-medium text-slate-900">显示名称</span>
                <input v-model="form.displayName" type="text" :class="fieldClass" placeholder="可选，用于在界面上显示" />
              </label>

              <label class="flex items-center justify-between gap-3 rounded-[18px] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                <span>
                  <span class="block font-medium text-slate-900">加入站点列表</span>
                  <span class="mt-0.5 block text-xs text-slate-500">勾选后会以「+站点」的形式追加到全局站点列表，不会覆盖默认站点。</span>
                </span>
                <input v-model="form.inSiteList" type="checkbox" class="h-4 w-4 shrink-0 rounded border-slate-300 text-primary-600 focus:ring-primary-600" />
              </label>
            </template>

            <template v-else>
              <label class="block space-y-2 text-sm text-slate-600">
                <span class="font-medium text-slate-900">内置站点</span>
                <input
                  v-model="form.site"
                  type="text"
                  :class="fieldClass"
                  list="builtin-site-options"
                  :disabled="isEditing"
                  placeholder="输入站点标识，或从下拉列表选择"
                />
                <datalist id="builtin-site-options">
                  <option v-for="item in builtinSites" :key="item.site" :value="item.site">{{ item.display_name }}</option>
                </datalist>
                <span v-if="selectedBuiltin" class="block text-xs text-slate-400">
                  {{ selectedBuiltin.display_name }}（{{ selectedBuiltin.site }}），共 {{ selectedBuiltin.options.length }} 个可调项
                </span>
                <span v-else class="block text-xs text-slate-400">
                  仅列出有可调项的内置站点；该站点需已在站点列表中才会生效。
                </span>
              </label>
            </template>
          </div>
        </UiCard>

        <UiCard padding="sm">
          <div>
            <h3 class="text-base font-semibold text-slate-950">{{ form.kind === 'builtin' ? '站点选项' : '模板选项' }}</h3>
            <p class="mt-0.5 text-sm text-slate-500">留空表示使用默认值，只有填写的项会写入配置文件。</p>
          </div>

          <div v-if="!optionFields.length" class="mt-4 rounded-[14px] border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
            {{ form.kind === 'builtin' ? '请先选择内置站点，或在下方添加自定义选项。' : '该模板没有可配置项，可在下方添加自定义选项。' }}
          </div>

          <div v-else class="mt-4 space-y-4">
            <div v-for="option in optionFields" :key="option.key" class="space-y-2">
              <div class="flex flex-wrap items-baseline gap-2">
                <span class="font-mono text-xs font-medium text-slate-800">{{ option.key }}</span>
                <span class="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">{{ optionTypeLabel(option) }}</span>
                <span v-if="option.required" class="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">必填其一</span>
                <span v-if="option.default !== null && option.default !== undefined" class="text-[11px] text-slate-400">
                  默认：{{ Array.isArray(option.default) ? option.default.join(', ') : String(option.default) }}
                </span>
              </div>
              <p v-if="option.description" class="text-xs leading-5 text-slate-500">{{ option.description }}</p>

              <div v-if="isToggleOption(option)" class="flex items-center justify-between gap-3 rounded-[14px] border border-slate-200 bg-slate-50 px-3 py-2">
                <span class="text-xs text-slate-500">
                  {{ toggleSummary(option) }}
                </span>
                <span class="flex items-center gap-3">
                  <button
                    v-if="option.key in form.options"
                    type="button"
                    class="text-xs font-medium text-slate-400 transition hover:text-slate-700"
                    @click="delete form.options[option.key]"
                  >
                    恢复默认
                  </button>
                  <Switch
                    :model-value="Boolean(option.key in form.options ? form.options[option.key] : defaultOptionValue(option))"
                    :aria-label="option.key"
                    size="sm"
                    @change="(value: boolean) => (form.options[option.key] = value)"
                  />
                </span>
              </div>

              <div v-else-if="isEnumOption(option)" class="space-y-2">
                <UiSelect
                  :model-value="enumValueOf(option)"
                  :options="enumSelectOptions(option)"
                  :aria-label="option.key"
                  @update:model-value="(value: string) => onEnumChange(option, value)"
                />
                <input
                  v-if="enumValueOf(option) === ENUM_CUSTOM"
                  v-model="form.options[option.key]"
                  :type="isSensitiveOption(option.key) ? 'password' : 'text'"
                  :autocomplete="isSensitiveOption(option.key) ? 'new-password' : 'off'"
                  :class="fieldClass"
                  :aria-label="option.key"
                  placeholder="自定义值"
                />
              </div>

              <UiScheduleTimeOverride
                v-else-if="isTimeRangeOption(option)"
                variant="plain"
                :model-value="(form.options[option.key] as string) || ''"
                :global-value="defaults.time_range"
                global-label="不单独设置"
                global-hint="该站点将跟随全局签到时段"
                @update:model-value="form.options[option.key] = $event"
              />

              <UiScheduleIntervalOverride
                v-else-if="isIntervalDaysOption(option)"
                variant="plain"
                :model-value="(form.options[option.key] as string) || ''"
                :global-value="defaults.interval_days"
                global-label="不单独设置"
                global-hint="该站点将跟随全局间隔天数"
                @update:model-value="form.options[option.key] = $event"
              />

              <UiListInput
                v-else-if="isListInputOption(option)"
                :label="option.key"
                :model-value="(form.options[option.key] as string[]) || []"
                :input-type="option.key === 'times' ? 'time' : isNumericListOption(option) ? 'number' : 'text'"
                :placeholder="option.key === 'times' ? '选择时间后点添加' : optionPlaceholder(option)"
                :empty-hint="option.key === 'times' ? '未添加任何时间点' : '未添加任何项'"
                @update:model-value="form.options[option.key] = $event"
              />

              <input
                v-else-if="isNumberOption(option)"
                v-model="form.options[option.key]"
                type="number"
                :step="option.type === 'float' ? 'any' : '1'"
                :aria-label="option.key"
                :class="fieldClass"
                :placeholder="optionPlaceholder(option)"
              />

              <textarea
                v-else-if="['dict', 'json'].includes(effectiveOptionType(option))"
                v-model="form.options[option.key]"
                rows="4"
                :aria-label="option.key"
                :class="[fieldClass, 'font-mono']"
                placeholder="JSON"
              />

              <input
                v-else
                v-model="form.options[option.key]"
                :aria-label="option.key"
                :type="isSensitiveOption(option.key) ? 'password' : 'text'"
                :autocomplete="isSensitiveOption(option.key) ? 'new-password' : 'off'"
                :class="fieldClass"
                :placeholder="optionPlaceholder(option)"
              />
            </div>
          </div>

          <div v-if="requiredGroupMissing" class="mt-4 rounded-[14px] border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs leading-5 text-amber-800">
            {{ activeInfo?.required_group?.message }}
          </div>

          <div class="mt-5 border-t border-slate-200 pt-4">
            <h4 class="text-sm font-semibold text-slate-900">自定义选项</h4>
            <p class="mt-0.5 text-xs leading-5 text-slate-500">
              站点配置是按原始键值读取的，可以补充任意键；值会自动识别 true / false、数字、逗号分隔列表或 JSON 数组。
            </p>

            <div class="mt-3 flex flex-col gap-2 sm:flex-row">
              <div class="sm:flex-1">
                <input v-model="customKey" type="text" autocomplete="off" :class="fieldClass" placeholder="键名，如 unique_name" @keyup.enter="addCustomOption" />
              </div>
              <div class="sm:flex-1">
                <input v-model="customValue" :type="isSensitiveOption(customKey) ? 'password' : 'text'" :autocomplete="isSensitiveOption(customKey) ? 'new-password' : 'off'" :class="fieldClass" placeholder="值" @keyup.enter="addCustomOption" />
              </div>
              <UiButton variant="secondary" class="shrink-0" @click="addCustomOption">添加</UiButton>
            </div>

            <div v-if="customEntries.length" class="mt-3 space-y-1.5">
              <div
                v-for="[key, value] in customEntries"
                :key="key"
                class="flex items-center justify-between gap-3 rounded-[12px] border border-slate-200 bg-slate-50 px-3 py-2"
              >
                <span class="min-w-0 truncate font-mono text-xs text-slate-700">
                  {{ key }} = {{ formatCustomValue(key, value) }}
                </span>
                <button type="button" class="shrink-0 text-xs font-medium text-slate-400 transition hover:text-rose-600" @click="removeCustomOption(key)">移除</button>
              </div>
            </div>
          </div>
        </UiCard>

        <div v-if="formError" class="rounded-[20px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {{ formError }}
        </div>

      </div>
      <template #footer>
        <div class="flex flex-wrap justify-end gap-2">
          <UiButton variant="outline" @click="drawerModel = false">取消</UiButton>
          <UiButton :loading="saving" @click="submitForm">保存</UiButton>
        </div>
      </template>
    </UiDrawer>

    <TransitionRoot as="template" :show="deleteDialogOpen">
      <Dialog as="div" class="relative z-50" @close="deleteDialogOpen = false">
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
                    <div class="min-w-0">
                      <h3 class="text-base font-semibold text-slate-950">删除自定义站点</h3>
                      <p class="mt-1 text-sm text-slate-600">
                        确定要删除
                        <span class="font-medium text-slate-900">{{ deleteTarget?.display_name }}</span>
                        吗？{{ deleteTarget?.builtin ? '它的按站点选项会被移除。' : '它会从配置文件与站点列表中移除。' }}
                      </p>
                    </div>
                  </div>
                </div>
                <div class="flex justify-end gap-3 border-t border-slate-100 px-6 py-4">
                  <UiButton variant="outline" @click="deleteDialogOpen = false">取消</UiButton>
                  <UiButton variant="danger" :loading="Boolean(deleting)" @click="confirmDelete">删除</UiButton>
                </div>
              </DialogPanel>
            </TransitionChild>
          </div>
        </div>
      </Dialog>
    </TransitionRoot>
  </div>
</template>
