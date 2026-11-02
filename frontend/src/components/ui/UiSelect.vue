<script setup lang="ts">
import { computed } from 'vue'
import { Listbox, ListboxButton, ListboxLabel, ListboxOption, ListboxOptions } from '@headlessui/vue'
import { CheckIcon, ChevronUpDownIcon } from '@heroicons/vue/20/solid'

export type UiSelectOption = {
	label: string
	value: string
	description?: string
}

const props = withDefaults(defineProps<{
	modelValue: string
	options: UiSelectOption[]
	label?: string
	disabled?: boolean
	placeholder?: string
	ariaLabel?: string
}>(), {
	disabled: false,
	placeholder: '请选择',
})

const emit = defineEmits<{
	'update:modelValue': [value: string]
}>()

defineOptions({
	inheritAttrs: false,
})

const selectedOption = computed(() => props.options.find((option) => option.value === props.modelValue) || null)

const updateValue = (value: string) => {
	emit('update:modelValue', value)
}
</script>

<template>
	<Listbox :model-value="modelValue" :disabled="disabled" @update:model-value="updateValue">
		<div :class="['space-y-2', $attrs.class]">
			<ListboxLabel v-if="label" class="block text-sm font-medium text-slate-900">
				{{ label }}
			</ListboxLabel>
			<div class="relative">
				<ListboxButton
					:aria-label="ariaLabel"
					:class="[
						'relative w-full min-w-0 rounded-[18px] border-0 bg-slate-50 py-2.5 pl-3 pr-9 text-left text-sm text-slate-900 ring-1 ring-inset ring-slate-200 transition focus:outline-none focus:ring-2 focus:ring-primary-600 sm:py-3 sm:pl-4 sm:pr-11',
						disabled ? 'cursor-not-allowed bg-slate-100 text-slate-400' : 'cursor-pointer',
					]"
				>
					<span class="block truncate">
						{{ selectedOption?.label || placeholder }}
					</span>
					<span class="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-3 text-slate-400">
						<ChevronUpDownIcon class="h-5 w-5" aria-hidden="true" />
					</span>
				</ListboxButton>

				<transition
					enter-active-class="transition duration-100 ease-out"
					enter-from-class="transform scale-95 opacity-0"
					enter-to-class="transform scale-100 opacity-100"
					leave-active-class="transition duration-75 ease-in"
					leave-from-class="transform scale-100 opacity-100"
					leave-to-class="transform scale-95 opacity-0"
				>
					<ListboxOptions class="absolute z-20 mt-2 max-h-64 w-full overflow-auto rounded-[20px] border border-slate-200 bg-white p-2 shadow-[0_20px_40px_-24px_rgba(15,23,42,0.35)] focus:outline-none">
						<ListboxOption
							v-for="option in options"
							:key="option.value"
							v-slot="{ active, selected }"
							:value="option.value"
							as="template"
						>
							<li
								:class="[
									'flex cursor-pointer items-start justify-between gap-3 rounded-[14px] px-3 py-2.5 text-sm transition',
									active ? 'bg-slate-100 text-slate-950' : 'text-slate-700',
								]"
							>
								<div class="min-w-0">
									<p :class="['truncate', selected ? 'font-semibold text-slate-950' : 'font-medium']">{{ option.label }}</p>
									<p v-if="option.description" class="mt-0.5 text-xs leading-5 text-slate-400">{{ option.description }}</p>
								</div>
								<CheckIcon v-if="selected" class="mt-0.5 h-5 w-5 shrink-0 text-primary-600" aria-hidden="true" />
							</li>
						</ListboxOption>
					</ListboxOptions>
				</transition>
			</div>
		</div>
	</Listbox>
</template>
