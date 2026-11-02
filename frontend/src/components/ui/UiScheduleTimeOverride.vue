<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { formatScheduleTimeRange, formatTimeRangeValue, normalizeClockValue, parseTimeRangeValue } from '@/utils/schedulerDisplay'

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
  globalHint: '当前账号将跟随全局执行时段',
  variant: 'card',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const mode = ref<'global' | 'single' | 'range'>('global')
const start = ref('11:00')
const end = ref('23:00')

const fieldClass = 'block w-full rounded-[16px] border-0 bg-white px-4 py-3 text-sm text-slate-900 ring-1 ring-inset ring-slate-200 focus:ring-2 focus:ring-primary-600'
const modeButtonClass = (value: 'global' | 'single' | 'range') => [
  'rounded-[10px] px-3 py-1.5 text-xs font-medium transition',
  mode.value === value ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-700',
]

const normalizedValue = computed(() => String(props.modelValue || '').trim())

const globalDisplay = computed(() => {
  const value = String(props.globalValue || '').trim()
  if (!value) return ''
  const formatted = formatScheduleTimeRange(value)
  return formatted === '-' ? '' : formatted
})

const syncFromValue = (value: string) => {
  if (!value) {
    mode.value = 'global'
    start.value = '11:00'
    end.value = '23:00'
    return
  }

  const parsed = parseTimeRangeValue(value)
  if (!parsed) {
    mode.value = 'global'
    return
  }

  mode.value = parsed.mode
  start.value = parsed.start
  end.value = parsed.end
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
    emit('update:modelValue', start.value)
    return
  }

  emit('update:modelValue', formatTimeRangeValue('range', start.value, end.value))
})

watch([start, end], ([nextStart, nextEnd]) => {
  const safeStart = normalizeClockValue(nextStart) || '11:00'
  const safeEnd = normalizeClockValue(nextEnd) || safeStart

  if (safeStart !== start.value) {
    start.value = safeStart
    return
  }

  if (mode.value === 'range' && safeEnd !== end.value) {
    end.value = safeEnd
    return
  }

  if (mode.value === 'single') {
    emit('update:modelValue', safeStart)
    return
  }

  if (mode.value === 'range') {
    emit('update:modelValue', formatTimeRangeValue('range', safeStart, safeEnd))
  }
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
      <button type="button" :class="modeButtonClass('single')" @click="mode = 'single'">单个时间</button>
      <button type="button" :class="modeButtonClass('range')" @click="mode = 'range'">时间范围</button>
    </div>

    <div v-if="mode === 'global'" class="rounded-[16px] border border-dashed border-slate-300 bg-white/70 px-4 py-3 text-sm text-slate-500">
      {{ globalHint }}<span v-if="globalDisplay">（全局：{{ globalDisplay }}）</span>。
    </div>

    <div v-else class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:items-end">
      <label class="space-y-2 text-sm text-slate-600">
        <span class="text-xs font-medium text-slate-500">{{ mode === 'single' ? '执行时间' : '开始时间' }}</span>
        <input v-model="start" type="time" :class="fieldClass" />
      </label>
      <div v-if="mode === 'range'" class="pb-3 text-center text-lg font-semibold text-slate-300">~</div>
      <label v-if="mode === 'range'" class="space-y-2 text-sm text-slate-600">
        <span class="text-xs font-medium text-slate-500">结束时间</span>
        <input v-model="end" type="time" :class="fieldClass" />
      </label>
    </div>
  </div>
</template>