<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { formatIntervalValue, formatScheduleInterval, parseIntervalValue } from '@/utils/schedulerDisplay'

const props = withDefaults(defineProps<{
  variant?: 'card' | 'plain'
  helperText?: string
  label?: string
  modelValue?: string | null
  globalValue?: string | null
  globalLabel?: string
  globalHint?: string
}>(), {
  helperText: '',
  label: '',
  modelValue: '',
  globalValue: '',
  globalLabel: '使用全局设置',
  globalHint: '当前账号将跟随全局间隔天数',
  variant: 'card',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const mode = ref<'global' | 'single' | 'range'>('global')
const single = ref('7')
const start = ref('7')
const end = ref('12')

const fieldClass = 'block w-full rounded-[16px] border-0 bg-white px-4 py-3 text-sm text-slate-900 ring-1 ring-inset ring-slate-200 focus:ring-2 focus:ring-primary-600'
const modeButtonClass = (value: 'global' | 'single' | 'range') => [
  'rounded-[10px] px-3 py-1.5 text-xs font-medium transition',
  mode.value === value ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-700',
]

const normalizedValue = computed(() => String(props.modelValue || '').trim())

const globalDisplay = computed(() => {
  const value = String(props.globalValue || '').trim()
  if (!value) return ''
  const formatted = formatScheduleInterval(value)
  return formatted === '-' ? '' : formatted
})

const sanitizePositiveInteger = (value: string, fallback: string) => {
  const numeric = Number(value)
  if (!Number.isInteger(numeric) || numeric <= 0) return fallback
  return String(numeric)
}

const syncFromValue = (value: string) => {
  if (!value) {
    mode.value = 'global'
    single.value = '7'
    start.value = '7'
    end.value = '12'
    return
  }

  const parsed = parseIntervalValue(value)
  if (!parsed) {
    mode.value = 'global'
    return
  }

  mode.value = parsed.mode
  single.value = String(parsed.start)
  start.value = String(parsed.start)
  end.value = String(parsed.end)
}

watch(normalizedValue, (value) => {
  syncFromValue(value)
}, { immediate: true })

watch(mode, (value) => {
  if (value === 'global') {
    emit('update:modelValue', '')
    return
  }

  if (value === 'single') {
    emit('update:modelValue', single.value)
    return
  }

  emit('update:modelValue', formatIntervalValue('range', start.value, start.value, end.value))
})

watch(single, (value) => {
  if (mode.value !== 'single') return
  const safeValue = sanitizePositiveInteger(value, '7')
  if (safeValue !== single.value) {
    single.value = safeValue
    return
  }
  emit('update:modelValue', safeValue)
})

watch([start, end], ([nextStart, nextEnd]) => {
  if (mode.value !== 'range') return

  const safeStart = sanitizePositiveInteger(nextStart, '7')
  const safeEnd = sanitizePositiveInteger(nextEnd, safeStart)

  if (safeStart !== start.value) {
    start.value = safeStart
    return
  }

  if (safeEnd !== end.value) {
    end.value = safeEnd
    return
  }

  emit('update:modelValue', formatIntervalValue('range', safeStart, safeStart, safeEnd))
})
</script>

<template>
  <div :class="props.variant === 'plain' ? 'space-y-4' : 'space-y-4 rounded-[22px] border border-slate-200 bg-slate-50 p-4 sm:p-5'">
    <div class="space-y-1.5">
      <p v-if="label" class="text-sm font-medium text-slate-900">{{ label }}</p>
      <p v-if="helperText" class="text-xs leading-5 text-slate-400">{{ helperText }}</p>
    </div>

    <div class="grid grid-cols-1 gap-1 rounded-[14px] bg-white p-1 ring-1 ring-inset ring-slate-200 sm:grid-cols-3">
      <button type="button" :class="modeButtonClass('global')" @click="mode = 'global'">{{ globalLabel }}</button>
      <button type="button" :class="modeButtonClass('single')" @click="mode = 'single'">固定天数</button>
      <button type="button" :class="modeButtonClass('range')" @click="mode = 'range'">区间天数</button>
    </div>

    <div v-if="mode === 'global'" class="rounded-[16px] border border-dashed border-slate-300 bg-white/70 px-4 py-3 text-sm text-slate-500">
      {{ globalHint }}<span v-if="globalDisplay">（全局：{{ globalDisplay }}）</span>。
    </div>

    <div v-else-if="mode === 'single'" class="grid gap-3 sm:max-w-[220px]">
      <label class="space-y-2 text-sm text-slate-600">
        <span class="text-xs font-medium text-slate-500">间隔天数</span>
        <input v-model="single" type="number" min="1" step="1" :class="fieldClass" />
      </label>
    </div>

    <div v-else class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:items-end">
      <label class="space-y-2 text-sm text-slate-600">
        <span class="text-xs font-medium text-slate-500">最小天数</span>
        <input v-model="start" type="number" min="1" step="1" :class="fieldClass" />
      </label>
      <div class="pb-3 text-center text-lg font-semibold text-slate-300">~</div>
      <label class="space-y-2 text-sm text-slate-600">
        <span class="text-xs font-medium text-slate-500">最大天数</span>
        <input v-model="end" type="number" min="1" step="1" :class="fieldClass" />
      </label>
    </div>
  </div>
</template>