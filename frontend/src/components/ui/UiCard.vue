<script setup lang="ts">
withDefaults(defineProps<{
  hover?: boolean
  padding?: 'sm' | 'md' | 'lg' | 'none'
  bodyVisible?: boolean
}>(), {
  bodyVisible: true,
})

defineOptions({
  inheritAttrs: false
})
</script>

<template>
  <div
    :class="[
      'min-w-0 rounded-3xl border border-slate-200/80 bg-white/92 shadow-[0_12px_32px_-18px_rgba(15,23,42,0.28)] backdrop-blur-sm transition-all duration-200',
      hover && 'cursor-pointer hover:-translate-y-0.5 hover:shadow-[0_18px_40px_-20px_rgba(15,23,42,0.34)]',
      $attrs.class
    ]"
  >
    <div v-if="$slots.header" class="rounded-t-3xl border-b border-slate-200/80 bg-slate-50/85 px-4 py-4 sm:px-6 sm:py-5">
      <slot name="header" />
    </div>
    <div
      v-show="bodyVisible"
      :class="[
        padding === 'sm' && 'p-4 sm:p-5',
        padding === 'lg' && 'p-5 sm:p-8',
        padding === 'none' && 'p-0',
        (!padding || padding === 'md') && 'p-4 sm:p-6',
      ]"
    >
      <slot />
    </div>
    <div v-if="$slots.footer" class="rounded-b-3xl border-t border-slate-200/80 bg-slate-50/85 px-4 py-4 sm:px-6 sm:py-5">
      <slot name="footer" />
    </div>
  </div>
</template>
