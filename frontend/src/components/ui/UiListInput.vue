<script setup lang="ts">
import { ref } from 'vue'
import { PlusIcon, XMarkIcon } from '@heroicons/vue/24/outline'
import UiButton from '@/components/ui/UiButton.vue'

const props = withDefaults(defineProps<{
  modelValue?: string[]
  placeholder?: string
  inputType?: 'text' | 'time' | 'number'
  emptyHint?: string
  addLabel?: string
  label?: string
}>(), {
  modelValue: () => [],
  placeholder: '输入后按回车或点添加',
  inputType: 'text',
  emptyHint: '',
  addLabel: '添加',
})

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
}>()

const draft = ref('')

const fieldClass = 'block min-w-0 w-full flex-1 rounded-[14px] border-0 bg-white px-3 py-2 text-sm text-slate-900 ring-1 ring-inset ring-slate-200 placeholder:text-slate-400 focus:ring-2 focus:ring-primary-600'

const add = () => {
  const value = draft.value.trim()
  if (!value) return
  draft.value = ''
  if (props.modelValue.includes(value)) return
  emit('update:modelValue', [...props.modelValue, value])
}

const remove = (value: string) => {
  emit('update:modelValue', props.modelValue.filter((item) => item !== value))
}
</script>

<template>
  <div class="space-y-2">
    <div class="flex items-center gap-2">
      <input
        :value="draft"
        :type="inputType"
        :aria-label="label"
        :placeholder="placeholder"
        :class="fieldClass"
        @input="draft = String(($event.target as HTMLInputElement).value)"
        @keyup.enter="add"
      />
      <UiButton size="sm" variant="secondary" class="shrink-0" @click="add">
        <PlusIcon class="mr-1 h-3.5 w-3.5" />
        {{ addLabel }}
      </UiButton>
    </div>

    <div v-if="modelValue.length" class="flex flex-wrap gap-1.5">
      <span
        v-for="item in modelValue"
        :key="item"
        class="inline-flex max-w-full items-center gap-1 rounded-lg bg-slate-100 py-1 pl-2.5 pr-1.5 font-mono text-xs text-slate-700"
      >
        <span class="min-w-0 break-all">{{ item }}</span>
        <button
          type="button"
          class="shrink-0 rounded-full p-0.5 text-slate-400 transition hover:bg-white hover:text-rose-600"
          :aria-label="`移除 ${item}`"
          @click="remove(item)"
        >
          <XMarkIcon class="h-3 w-3" />
        </button>
      </span>
    </div>

    <p v-else-if="emptyHint" class="text-xs leading-5 text-slate-400">{{ emptyHint }}</p>
  </div>
</template>
