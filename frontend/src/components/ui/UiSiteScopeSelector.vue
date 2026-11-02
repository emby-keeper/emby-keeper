<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { MagnifyingGlassIcon } from '@heroicons/vue/24/outline'
import UiSelect, { type UiSelectOption } from '@/components/ui/UiSelect.vue'

type Mode = 'inherit' | 'default' | 'extend' | 'include'
type BaseMode = 'default' | 'all' | 'sgk' | 'explicit'

const props = withDefaults(defineProps<{
  label: string
  helperText?: string
  modelValue?: string[] | null
  sites?: string[]
  allSites?: string[]
  /** 配置里的自定义站点, 始终出现在候选列表里 (即使当前未启用) */
  extraSites?: string[]
  displayNames?: Record<string, string>
  siteType?: string
  allowInherit?: boolean
  variant?: 'card' | 'plain'
}>(), {
  helperText: '',
  modelValue: null,
  sites: () => [],
  allSites: () => [],
  extraSites: () => [],
  displayNames: () => ({}),
  siteType: '',
  allowInherit: false,
  variant: 'card',
})

const emit = defineEmits<{
  'update:modelValue': [value: string[] | null]
}>()

const mode = ref<Mode>('default')
const baseMode = ref<BaseMode>('default')
const explicitBase = ref<string[]>([])
/** extend 模式下追加的站点 */
const included = ref<string[]>([])
/** extend 模式下排除的站点 */
const excluded = ref<string[]>([])
/** include 模式下选中的站点 */
const selected = ref<string[]>([])
const keyword = ref('')
const customInput = ref('')
const customInputError = ref('')

const normalizeList = (value?: string[] | null) => {
  if (!Array.isArray(value)) return null
  return value.map((item) => String(item || '').trim()).filter(Boolean)
}

const clearSelection = () => {
  included.value = []
  excluded.value = []
  selected.value = []
  baseMode.value = 'default'
  explicitBase.value = []
}

const syncFromValue = (value?: string[] | null) => {
  const list = normalizeList(value)

  if (value === null || value === undefined) {
    // 保持用户刚切到的「在默认站点上调整 / 仅指定站点」空状态，避免刚点开就被弹回
    const idle =
      (mode.value === 'extend' || mode.value === 'include') &&
      !included.value.length &&
      !excluded.value.length &&
      !selected.value.length
    if (idle) return
    mode.value = props.allowInherit ? 'inherit' : 'default'
    clearSelection()
    return
  }

  if (list.length === 0) {
    mode.value = 'include'
    clearSelection()
    return
  }

  const positives = list.filter((item) => !item.startsWith('-') && !item.startsWith('+'))
  const hasAdjustments = list.some((item) => item.startsWith('+') || item.startsWith('-'))
  const specialBase = positives.includes('all') ? 'all' : props.siteType === 'checkiner' && positives.includes('sgk') ? 'sgk' : null

  // 保留 get_cls 的 all / sgk 和 +/- 组合语义
  if (specialBase || (hasAdjustments && positives.length === 0)) {
    mode.value = 'extend'
    baseMode.value = specialBase || 'default'
    explicitBase.value = []
    included.value = [
      ...list.filter((item) => item.startsWith('+')).map((item) => item.slice(1)),
      ...positives.filter((item) => item !== 'all' && item !== 'sgk' && item !== specialBase),
    ]
    excluded.value = list.filter((item) => item.startsWith('-')).map((item) => item.slice(1))
    selected.value = []
    return
  }

  if (hasAdjustments) {
    // 原始配置可有显式正向集合再叠加 +/- 修饰；将基础集与修饰分别保存
    mode.value = 'extend'
    baseMode.value = 'explicit'
    explicitBase.value = positives
    included.value = list.filter((item) => item.startsWith('+')).map((item) => item.slice(1))
    excluded.value = list.filter((item) => item.startsWith('-')).map((item) => item.slice(1))
    selected.value = []
    return
  }

  mode.value = 'include'
  selected.value = list
  included.value = []
  excluded.value = []
  baseMode.value = 'default'
  explicitBase.value = []
}

watch(() => props.modelValue, (value) => syncFromValue(value), { immediate: true })

const defaultSet = computed(() => new Set(props.sites))
const categorySites = computed(() => props.siteType === 'checkiner' ? props.allSites.filter(site => site.endsWith('sgk')) : [])
const expandSiteNames = (names: string[]) => names.flatMap(site => {
  if (site === 'sgk' && props.siteType === 'checkiner') return categorySites.value
  return site === 'all' ? [] : [site]
})
const effectiveBaseSites = computed(() => {
  if (baseMode.value === 'all') return props.allSites
  if (baseMode.value === 'sgk') return props.allSites.filter((site) => site.endsWith('sgk'))
  if (baseMode.value === 'explicit') return explicitBase.value
  return props.sites
})

const baseOptions = computed<UiSelectOption[]>(() => {
  const options: UiSelectOption[] = [
    { label: `默认启用站点（${props.sites.length} 个）`, value: 'default' },
    { label: `全部可用站点（${props.allSites.length} 个）`, value: 'all' },
  ]
  if (props.siteType === 'checkiner') {
    options.push({ label: `仅社工库站点（${categorySites.value.length} 个）`, value: 'sgk' })
  }
  if (baseMode.value === 'explicit') {
    options.push({ label: `自定义基准（${explicitBase.value.length} 个）`, value: 'explicit' })
  }
  return options
})

const onBaseChange = (value: string) => {
  const next = value as BaseMode
  if (next === baseMode.value) return
  baseMode.value = next

  const baseSites = effectiveBaseSites.value
  const baseSet = new Set(baseSites)
  const baseHasCategory = props.siteType === 'checkiner' && baseSites.some((site) => site.endsWith('sgk'))

  // 切换基准后清掉已经失去意义的调整项, 避免残留「追加了基准里已有的站点」或「排除了基准里没有的站点」
  included.value = included.value.filter((site) => {
    if (site === 'sgk') return next !== 'all' && next !== 'sgk' && !baseHasCategory
    return !baseSet.has(site)
  })
  excluded.value = excluded.value.filter((site) => {
    // 基准就是社工库时, 分组由基准决定, 不再保留会互相抵消的分组排除
    if (site === 'sgk') return next !== 'sgk' && baseHasCategory
    return baseSet.has(site)
  })
  emitValue()
}

const categoryMode = computed<'follow' | 'include' | 'exclude'>(() => {
  if (props.siteType !== 'checkiner') return 'follow'
  if (included.value.includes('sgk')) return 'include'
  if (excluded.value.includes('sgk')) return 'exclude'
  return 'follow'
})

/** 基准本身已经包含全部社工库站点时,「全部加入」没有意义 */
const baseCoversCategory = computed(() => {
  if (props.siteType !== 'checkiner' || !categorySites.value.length) return false
  const base = new Set(effectiveBaseSites.value)
  return categorySites.value.every((site) => base.has(site))
})

const categoryOptions = computed(() => {
  const options = [{ key: 'follow' as const, label: '跟随基准' }]
  // 已保存的配置若显式加入了社工库, 即使基准已覆盖也要显示出这个状态
  if (!baseCoversCategory.value || categoryMode.value === 'include') {
    options.push({ key: 'include' as const, label: '全部加入' })
  }
  options.push({ key: 'exclude' as const, label: '全部排除' })
  return options
})

const setCategoryMode = (value: 'follow' | 'include' | 'exclude') => {
  included.value = included.value.filter((item) => item !== 'sgk')
  excluded.value = excluded.value.filter((item) => item !== 'sgk')
  if (value === 'include') included.value = [...included.value, 'sgk']
  if (value === 'exclude') excluded.value = [...excluded.value, 'sgk']
  emitValue()
}

/** 站点列表跟随当前范围：调整模式列出基准范围，仅指定模式列出全部可用站点。 */
const sourceSites = computed(() =>
  mode.value === 'include' ? (props.allSites.length ? props.allSites : props.sites) : effectiveBaseSites.value,
)

/** 当前已选/已排除的站点，保证它们始终出现在列表里 */
const activeSites = computed(() => expandSiteNames([...explicitBase.value, ...included.value, ...excluded.value, ...selected.value]))

const visibleSites = computed(() => {
  const merged: string[] = []
  // 自定义站点排在最前，方便查找
  for (const item of [...props.extraSites, ...sourceSites.value, ...activeSites.value]) {
    if (item !== 'all' && !(item === 'sgk' && props.siteType === 'checkiner') && !merged.includes(item)) merged.push(item)
  }
  return merged
})

const isCustom = (site: string) => !props.sites.includes(site) && !props.allSites.includes(site)

const siteLabel = (site: string) => props.displayNames[site] || site

const filteredSites = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return visibleSites.value
  return visibleSites.value.filter(
    (site) => site.toLowerCase().includes(kw) || (props.displayNames[site] || '').toLowerCase().includes(kw),
  )
})

const isChecked = (site: string) => {
  if (mode.value === 'extend') {
    // 针对单个站点的调整优先于分组设置, 保证「在社工库里单独去掉某个站点」这类例外不会丢
    if (included.value.includes(site)) return true
    if (excluded.value.includes(site)) return false
    const inCategory = props.siteType === 'checkiner' && site.endsWith('sgk')
    if (inCategory && included.value.includes('sgk')) return true
    if (!effectiveBaseSites.value.includes(site)) return false
    return !(inCategory && excluded.value.includes('sgk'))
  }
  return selected.value.includes(site)
}

const emitValue = () => {
  if (mode.value === 'inherit' || mode.value === 'default') {
    emit('update:modelValue', null)
    return
  }

  if (mode.value === 'include') {
    emit('update:modelValue', [...selected.value])
    return
  }

  const entries = [
    ...(baseMode.value === 'all' ? ['all'] : baseMode.value === 'sgk' ? ['sgk'] : baseMode.value === 'explicit' ? explicitBase.value : []),
    ...included.value.map((site) => `+${site}`),
    ...excluded.value.map((site) => `-${site}`),
  ]
  emit('update:modelValue', entries.length ? entries : null)
}

const toggleSite = (site: string) => {
  if (mode.value === 'extend') {
    // 保持已选基准，只记录这个站点本身的例外，避免丢失“全部 / 仅社工库”这类范围语义。
    if (isChecked(site)) {
      excluded.value = excluded.value.includes(site) ? excluded.value : [...excluded.value, site]
      included.value = included.value.filter((item) => item !== site)
    } else {
      excluded.value = excluded.value.filter((item) => item !== site)
      included.value = included.value.includes(site) ? included.value : [...included.value, site]
    }
  } else {
    selected.value = selected.value.includes(site)
      ? selected.value.filter((item) => item !== site)
      : [...selected.value, site]
  }
  emitValue()
}

const selectAll = () => {
  if (mode.value === 'extend') {
    // 全部启用 = 默认站点不再排除 + 追加所有非默认站点
    if (baseMode.value !== 'default') {
      baseMode.value = 'all'
      explicitBase.value = []
      included.value = []
      excluded.value = []
      emitValue()
      return
    }
    included.value = filteredSites.value.filter((site) => !defaultSet.value.has(site))
    excluded.value = []
  } else {
    selected.value = [...filteredSites.value]
  }
  emitValue()
}

const clearAll = () => {
  if (mode.value === 'extend') {
    // 重置为默认 = 清空追加与排除
    included.value = []
    excluded.value = []
    baseMode.value = 'default'
    explicitBase.value = []
  } else {
    selected.value = []
  }
  emitValue()
}

const addCustom = () => {
  const value = customInput.value.trim()
  if (!value) return
  customInputError.value = ''
  if (value === 'all' || (props.siteType === 'checkiner' && value === 'sgk')) {
    customInputError.value = '这类范围请使用上方的基准范围与社工库选项设置。'
    return
  }
  if (!/^templ_\w+<@?\w+>$/.test(value)) {
    customInputError.value = '请填写 templ_a<机器人用户名> 形式的模板站点。'
    return
  }
  if (mode.value === 'extend') {
    if (!included.value.includes(value)) included.value = [...included.value, value]
    emitValue()
  } else if (!selected.value.includes(value)) {
    selected.value = [...selected.value, value]
    emitValue()
  }
  customInput.value = ''
}

const setMode = (next: Mode) => {
  if (mode.value === next) return
  const previous = mode.value
  const previousEffectiveSites = previous === 'extend'
    ? [...new Set([...effectiveBaseSites.value, ...expandSiteNames(included.value)].filter((site) => isChecked(site)))]
    : [...selected.value]

  if (next === 'inherit' || next === 'default') {
    clearSelection()
  } else if (next === 'extend') {
    // 「仅指定」切过来时没有可继承的默认概念，直接留空
    if (previous === 'include') clearSelection()
    selected.value = []
  } else {
    // 切到「仅指定」：把当前真正生效的站点作为初值
    if (previous === 'extend') {
      selected.value = previousEffectiveSites
      included.value = []
      excluded.value = []
      baseMode.value = 'default'
      explicitBase.value = []
    }
  }
  mode.value = next
  emitValue()
}

const modeButtons = computed(() => {
  const buttons: { key: Mode; label: string }[] = props.allowInherit
    ? [{ key: 'inherit', label: '继承系统设置' }]
    : [{ key: 'default', label: '全部默认站点' }]
  buttons.push({ key: 'extend', label: '在默认站点上调整' })
  buttons.push({ key: 'include', label: '仅指定站点' })
  return buttons
})

const modeButtonClass = (value: Mode) => [
  'rounded-[10px] px-3 py-1.5 text-xs font-medium transition',
  mode.value === value ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-700',
]

const baseLabel = computed(() => {
  if (baseMode.value === 'all') return '全部可用站点'
  if (baseMode.value === 'sgk') return '社工库站点'
  if (baseMode.value === 'explicit') return '自定义基准'
  return '默认启用站点'
})

/** 追加生效的站点：分组标识展开成成员, 只统计基准里没有的 */
const extendAdded = computed(() => {
  const base = new Set(effectiveBaseSites.value)
  return [...new Set(expandSiteNames(included.value).filter((site) => !base.has(site)))]
})

/** 排除生效的站点：分组标识展开成成员, 只统计基准里有的 */
const extendRemoved = computed(() => {
  const base = new Set(effectiveBaseSites.value)
  return [...new Set(expandSiteNames(excluded.value).filter((site) => base.has(site)))]
})

/** 当前实际生效的站点数目, 用于摘要展示 */
const extendEffective = computed(() => {
  const names = new Set<string>()
  for (const site of effectiveBaseSites.value) if (isChecked(site)) names.add(site)
  for (const site of extendAdded.value) if (isChecked(site)) names.add(site)
  return names.size
})

const summary = computed(() => {
  if (mode.value === 'inherit') return '当前账号沿用系统设置中的站点范围。'
  if (mode.value === 'default') return '使用系统默认站点范围。'
  if (mode.value === 'extend') {
    const parts = [`在${baseLabel.value}基础上生效 ${extendEffective.value} 个`]
    if (extendAdded.value.length) parts.push(`追加 ${extendAdded.value.length} 项`)
    if (extendRemoved.value.length) parts.push(`排除 ${extendRemoved.value.length} 项`)
    return `${parts.join('，')}。`
  }
  if (!selected.value.length) return '尚未选择站点，将不会运行任何站点。'
  return `已选择 ${selected.value.length} 个站点。`
})

const emptyHint = computed(() =>
  mode.value === 'extend' ? '基准范围内的站点默认启用：取消勾选即为排除，勾选范围外的站点即为追加。' : '',
)
</script>

<template>
  <div :class="props.variant === 'plain' ? 'space-y-4' : 'space-y-4 rounded-[22px] border border-slate-200 bg-slate-50 p-4 sm:p-5'">
    <div class="space-y-1.5">
      <p class="text-sm font-medium text-slate-900">{{ label }}</p>
      <p v-if="helperText" class="text-xs leading-5 text-slate-400">{{ helperText }}</p>
    </div>

    <div class="grid grid-cols-1 gap-1 rounded-[14px] bg-white p-1 ring-1 ring-inset ring-slate-200 sm:grid-cols-3">
      <button
        v-for="button in modeButtons"
        :key="button.key"
        type="button"
        :class="modeButtonClass(button.key)"
        @click="setMode(button.key)"
      >
        {{ button.label }}
      </button>
    </div>

    <div
      v-if="mode === 'inherit' || mode === 'default'"
      class="rounded-[16px] border border-dashed border-slate-300 bg-white/70 px-4 py-3 text-sm text-slate-500"
    >
      {{ summary }}
    </div>

    <div v-else class="space-y-3">
      <div v-if="mode === 'extend'" class="space-y-2">
        <UiSelect :model-value="baseMode" :options="baseOptions" label="基准范围" @update:model-value="onBaseChange" />
        <div v-if="siteType === 'checkiner' && baseMode !== 'sgk'" class="space-y-2">
          <p class="text-xs font-medium text-slate-600">社工库站点</p>
          <div class="grid grid-cols-3 gap-1 rounded-[12px] bg-white p-1 ring-1 ring-inset ring-slate-200">
            <button
              v-for="option in categoryOptions"
              :key="option.key"
              type="button"
              class="rounded-[9px] px-2.5 py-1.5 text-xs font-medium transition"
              :class="categoryMode === option.key ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-700'"
              @click="setCategoryMode(option.key)"
            >
              {{ option.label }}
            </button>
          </div>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <div class="relative min-w-0 basis-full sm:flex-1 sm:basis-auto">
          <MagnifyingGlassIcon class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
          <input
            v-model="keyword"
            type="text"
            placeholder="搜索站点"
            class="block w-full rounded-[14px] border-0 bg-white py-2 pl-9 pr-3 text-sm text-slate-900 ring-1 ring-inset ring-slate-200 placeholder:text-slate-400 focus:ring-2 focus:ring-primary-600"
          />
        </div>
        <button type="button" class="shrink-0 rounded-[10px] px-2.5 py-1.5 text-xs font-medium text-slate-500 transition hover:text-slate-800" @click="selectAll">
          {{ mode === 'extend' ? '全部启用' : '全选' }}
        </button>
        <button type="button" class="shrink-0 rounded-[10px] px-2.5 py-1.5 text-xs font-medium text-slate-500 transition hover:text-slate-800" @click="clearAll">
          {{ mode === 'extend' ? '重置为默认' : '清空' }}
        </button>
      </div>

      <p class="text-xs leading-5 text-slate-400">{{ summary }}</p>
      <p v-if="emptyHint" class="text-xs leading-5 text-slate-400">{{ emptyHint }}</p>

      <div class="space-y-1.5">
        <div class="flex items-center gap-2">
          <input
            v-model="customInput"
            type="text"
            placeholder="添加模板站点，如 templ_a<机器人用户名>"
            class="block min-w-0 flex-1 rounded-[14px] border-0 bg-white px-3 py-2 text-sm text-slate-900 ring-1 ring-inset ring-slate-200 placeholder:text-slate-400 focus:ring-2 focus:ring-primary-600"
            @keyup.enter="addCustom"
          />
          <button type="button" class="shrink-0 rounded-[10px] px-2.5 py-1.5 text-xs font-medium text-slate-500 transition hover:text-slate-800" @click="addCustom">添加</button>
        </div>
        <p v-if="customInputError" class="text-xs leading-5 text-amber-600">{{ customInputError }}</p>
      </div>

      <div v-if="!visibleSites.length" class="rounded-[14px] border border-dashed border-slate-300 bg-white px-4 py-6 text-center text-sm text-slate-500">
        当前模块没有内置站点，可直接用下方输入框添加模板站点。
      </div>

      <div v-else class="max-h-56 space-y-0.5 overflow-y-auto rounded-[14px] border border-slate-200 bg-white p-2">
        <label
          v-for="site in filteredSites"
          :key="site"
          class="flex cursor-pointer items-center gap-2 rounded-[10px] px-2 py-1.5 text-sm text-slate-700 transition hover:bg-slate-50"
        >
          <input
            type="checkbox"
            :checked="isChecked(site)"
            class="h-4 w-4 shrink-0 rounded border-slate-300 text-primary-600 focus:ring-primary-600"
            @change="toggleSite(site)"
          />
          <span class="flex min-w-0 flex-1 flex-col items-start gap-0.5 sm:flex-row sm:items-baseline sm:gap-1.5">
            <span class="break-words text-slate-800">{{ siteLabel(site) }}</span>
            <span v-if="displayNames[site]" class="max-w-full break-all font-mono text-[11px] text-slate-400">{{ site }}</span>
          </span>
          <span v-if="isCustom(site)" class="shrink-0 rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">自定义</span>
          <span
            v-else-if="mode === 'extend' && excluded.includes(site)"
            class="shrink-0 rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700"
          >
            已排除
          </span>
        </label>
        <p v-if="!filteredSites.length" class="px-2 py-3 text-center text-xs text-slate-400">没有匹配的站点</p>
      </div>
    </div>
  </div>
</template>
