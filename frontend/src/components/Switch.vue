<template>
  <label :class="['inline-flex items-center select-none', disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer']">
    <input
      type="checkbox"
      class="sr-only peer"
      :checked="modelValue"
      :disabled="disabled"
      @change="onInputChange"
    />
    <span
      :class="[
        'relative inline-flex shrink-0 items-center rounded-full border border-transparent transition-colors duration-200 ease-out',
        'peer-focus-visible:ring-2 peer-focus-visible:ring-primary/30',
        trackSizeClass,
        trackStateClass,
      ]"
      role="switch"
      :aria-checked="modelValue"
      :aria-label="ariaLabel"
      @click.stop.prevent="toggle"
      @keydown.enter.prevent="toggle"
      @keydown.space.prevent="toggle"
      tabindex="0"
    >
      <span
        :class="[
          'rounded-full bg-white shadow-sm transition-transform duration-200 ease-out',
          knobSizeClass,
          modelValue ? knobTranslateClass : ''
        ]"
      />
    </span>
    <span v-if="label" class="ml-3 text-sm text-gray-900 dark:text-gray-100">{{ label }}</span>
  </label>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type SwitchSize = 'sm' | 'md' | 'lg'

const props = withDefaults(defineProps<{
  modelValue: boolean
  disabled?: boolean
  size?: SwitchSize
  label?: string
  ariaLabel?: string
}>(), {
  disabled: false,
  size: 'md',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'change', value: boolean): void
}>()

const trackSizeClass = computed(() => {
  switch (props.size) {
    case 'sm':
      return 'h-5 w-9'
    case 'lg':
      return 'h-7 w-12'
    default:
      return 'h-6 w-11'
  }
})

const trackStateClass = computed(() => {
  return props.modelValue
    ? 'bg-primary-600 shadow-sm'
    : 'bg-gray-200 shadow-inner'
})

const knobSizeClass = computed(() => {
  switch (props.size) {
    case 'sm':
      return 'h-3.5 w-3.5'
    case 'lg':
      return 'h-5 w-5'
    default:
      return 'h-4 w-4'
  }
})

const knobTranslateClass = computed(() => {
  switch (props.size) {
    case 'sm':
      return 'translate-x-4'
    case 'lg':
      return 'translate-x-6'
    default:
      return 'translate-x-5'
  }
})

function toggle() {
  if (props.disabled) return
  const next = !props.modelValue
  emit('update:modelValue', next)
  emit('change', next)
}

function onInputChange(event: Event) {
  if (props.disabled) return
  const target = event.target as HTMLInputElement
  emit('update:modelValue', target.checked)
  emit('change', target.checked)
}
</script>
