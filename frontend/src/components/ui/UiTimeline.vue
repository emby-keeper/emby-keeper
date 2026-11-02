<script setup lang="ts">
const props = defineProps<{
  items: Array<{
    time?: string
    title: string
    description?: string
    type?: 'default' | 'success' | 'error' | 'warning'
  }>
}>()

const shortTime = (value?: string) => (value ? value.slice(-8) : '')

const styles = (type?: string) => {
  switch (type) {
    case 'error': return { dot: 'bg-red-500', level: 'text-red-600' }
    case 'warning': return { dot: 'bg-yellow-500', level: 'text-yellow-700' }
    case 'success': return { dot: 'bg-green-500', level: 'text-green-600' }
    default: return { dot: 'bg-gray-400', level: 'text-slate-500' }
  }
}
</script>

<template>
  <div class="space-y-1">
    <div
      v-for="(item, index) in items"
      :key="index"
      class="flex items-start gap-2.5 rounded-lg px-2 py-1.5 transition-colors hover:bg-slate-50"
    >
      <span class="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full" :class="styles(item.type).dot" />
      <span class="shrink-0 pt-px font-mono text-xs leading-5 tabular-nums text-slate-400">{{ shortTime(item.time) }}</span>
      <span class="w-14 shrink-0 pt-px text-xs font-semibold leading-5" :class="styles(item.type).level">{{ item.description || 'INFO' }}</span>
      <p class="min-w-0 flex-1 pt-px text-sm leading-5 text-slate-700">{{ item.title }}</p>
    </div>
  </div>
</template>
