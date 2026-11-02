<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  disabled?: boolean
  block?: boolean
  loading?: boolean
}>(), {
  variant: 'primary',
  size: 'md',
  block: false,
  loading: false,
})

const sizeClass = computed(() => {
  const sizes: Record<string, string> = {
    sm: 'px-3 py-1.5 text-xs',
    md: 'px-4 py-2 text-sm',
    lg: 'px-6 py-3 text-base'
  }
  return sizes[props.size] || sizes.md
})

const variantClass = computed(() => {
  if (props.disabled) {
    switch (props.variant) {
      case 'outline':
        return 'bg-gray-50 text-gray-400 border border-gray-200 shadow-none'
      case 'danger':
        return 'bg-gray-200 text-gray-400 border border-transparent shadow-none'
      case 'secondary':
        return 'bg-gray-100 text-gray-400 border border-transparent shadow-none'
      case 'ghost':
        return 'text-gray-400 bg-transparent shadow-none'
      default:
        return 'bg-gray-200 text-gray-400 border border-transparent shadow-none'
    }
  }

  switch (props.variant) {
    case 'outline':
      return 'bg-white text-gray-900 border border-gray-300 hover:bg-gray-50 focus-visible:ring-gray-300 shadow-sm'
    case 'danger':
      return 'bg-red-600 text-white border border-transparent hover:bg-red-500 focus-visible:ring-red-600 shadow-sm'
    case 'secondary':
      return 'bg-gray-100 text-gray-900 border border-transparent hover:bg-gray-200 focus-visible:ring-gray-200'
    case 'ghost':
      return 'text-gray-700 bg-transparent hover:bg-gray-100 focus-visible:ring-gray-200'
    default:
      return 'bg-primary-600 text-white border border-transparent hover:bg-primary-500 focus-visible:ring-primary-600 shadow-sm'
  }
})
</script>

<template>
  <button
    :disabled="disabled || loading"
    :class="[
      'inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-2xl font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 [&>svg]:shrink-0',
      'disabled:cursor-not-allowed',
      sizeClass,
      variantClass,
      block ? 'w-full' : '',
    ]"
  >
    <svg v-if="loading" class="animate-spin -ml-1 mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
    </svg>
    <slot />
  </button>
</template>

<style scoped>
@media (pointer: coarse) {
  button {
    min-height: 44px;
    touch-action: manipulation;
  }
}
</style>
