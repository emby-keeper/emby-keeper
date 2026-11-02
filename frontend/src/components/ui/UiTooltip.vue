<script setup lang="ts">
import { computed, getCurrentInstance, nextTick, onBeforeUnmount, onMounted, ref, useSlots } from 'vue'

const props = withDefaults(defineProps<{
  text?: string
  widthClass?: string
  position?: 'top' | 'bottom'
}>(), {
  position: 'top',
  widthClass: 'w-72',
})

const slots = useSlots()
const hasContentSlot = computed(() => Boolean(slots.content))
const triggerRef = ref<HTMLElement | null>(null)
const tooltipRef = ref<HTMLElement | null>(null)
const isOpen = ref(false)
const isPinned = ref(false)
const tooltipId = `ui-tooltip-${getCurrentInstance()?.uid}`
const tooltipStyle = ref({ left: '12px', top: '12px', visibility: 'hidden' as 'hidden' | 'visible' })
let closeTimer: ReturnType<typeof setTimeout> | null = null

const VIEWPORT_MARGIN = 12

const updatePosition = () => {
  const tooltipEl = tooltipRef.value
  const triggerEl = triggerRef.value
  if (!tooltipEl || !triggerEl) return

  const trigger = triggerEl.getBoundingClientRect()
  const tooltip = tooltipEl.getBoundingClientRect()
  const left = Math.max(VIEWPORT_MARGIN, Math.min(
    trigger.left + trigger.width / 2 - tooltip.width / 2,
    window.innerWidth - tooltip.width - VIEWPORT_MARGIN,
  ))
  const above = trigger.top - tooltip.height - 10
  const below = trigger.bottom + 10
  let top = props.position === 'top' ? above : below
  if (top < VIEWPORT_MARGIN) top = below
  if (top + tooltip.height > window.innerHeight - VIEWPORT_MARGIN) top = above
  top = Math.max(VIEWPORT_MARGIN, Math.min(top, window.innerHeight - tooltip.height - VIEWPORT_MARGIN))
  tooltipStyle.value = { left: `${left}px`, top: `${top}px`, visibility: 'visible' }
}

const cancelClose = () => {
  if (closeTimer !== null) clearTimeout(closeTimer)
  closeTimer = null
}

const openTooltip = async () => {
  cancelClose()
  isOpen.value = true
  await nextTick()
  const control = triggerRef.value?.querySelector<HTMLElement>('button, a, input, [tabindex]')
  if (control) {
    const descriptions = new Set((control.getAttribute('aria-describedby') || '').split(' ').filter(Boolean))
    descriptions.add(tooltipId)
    control.setAttribute('aria-describedby', [...descriptions].join(' '))
  }
  updatePosition()
}

const closeTooltip = () => {
  cancelClose()
  isOpen.value = false
  isPinned.value = false
  const control = triggerRef.value?.querySelector<HTMLElement>('button, a, input, [tabindex]')
  if (control) {
    const descriptions = (control.getAttribute('aria-describedby') || '').split(' ').filter(value => value && value !== tooltipId)
    if (descriptions.length) control.setAttribute('aria-describedby', descriptions.join(' '))
    else control.removeAttribute('aria-describedby')
  }
}

const scheduleClose = () => {
  cancelClose()
  if (!isPinned.value) closeTimer = setTimeout(closeTooltip, 150)
}

const togglePinned = () => {
  if (isPinned.value) closeTooltip()
  else {
    isPinned.value = true
    void openTooltip()
  }
}

const closeOutside = (event: PointerEvent) => {
  const target = event.target as Node | null
  if (!triggerRef.value?.contains(target) && !tooltipRef.value?.contains(target)) closeTooltip()
}

const onEscape = (event: KeyboardEvent) => {
  if (isOpen.value && event.key === 'Escape') {
    event.stopPropagation()
    closeTooltip()
  }
}

const syncTooltipPosition = () => {
  if (isOpen.value) {
    updatePosition()
  }
}

onMounted(() => {
  window.addEventListener('resize', syncTooltipPosition)
  window.addEventListener('scroll', syncTooltipPosition, true)
  document.addEventListener('pointerdown', closeOutside)
  window.addEventListener('keydown', onEscape, true)
})

onBeforeUnmount(() => {
  closeTooltip()
  window.removeEventListener('resize', syncTooltipPosition)
  window.removeEventListener('scroll', syncTooltipPosition, true)
  document.removeEventListener('pointerdown', closeOutside)
  window.removeEventListener('keydown', onEscape, true)
})
</script>

<template>
  <span
    ref="triggerRef"
    class="inline-flex shrink-0 items-center"
    @pointerenter="openTooltip"
    @pointerleave="scheduleClose"
    @focusin="openTooltip"
    @focusout="scheduleClose"
    @click="togglePinned"
  >
    <slot />
    <Teleport to="body">
      <div
        v-if="isOpen"
        :id="tooltipId"
        ref="tooltipRef"
        :class="[
          'fixed z-[100] max-h-[calc(100dvh-1.5rem)] max-w-[calc(100vw-1.5rem)] overflow-y-auto overscroll-contain break-words rounded-lg border border-slate-200 bg-white px-4 py-3 text-xs leading-5 text-slate-700 shadow-lg',
          props.widthClass,
        ]"
        :style="tooltipStyle"
        role="tooltip"
        @pointerenter="cancelClose"
        @pointerleave="scheduleClose"
      >
        <slot name="content">
          <span v-if="!hasContentSlot">{{ text }}</span>
        </slot>
      </div>
    </Teleport>
  </span>
</template>