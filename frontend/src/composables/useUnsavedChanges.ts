import { computed, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'

export function useUnsavedChanges(open: Ref<boolean>, snapshot: () => unknown, saving: Ref<boolean>) {
  const initial = ref('')
  const serialize = () => JSON.stringify(snapshot())
  const markSaved = () => { initial.value = serialize() }
  const dirty = computed(() => open.value && initial.value !== serialize())
  const canLeave = () => !open.value || (!saving.value && (!dirty.value || window.confirm('有未保存的修改，确定放弃吗？')))
  const model = computed({
    get: () => open.value,
    set: (value: boolean) => {
      if (value || canLeave()) open.value = value
    },
  })

  watch(open, (value) => { if (value) markSaved() }, { flush: 'sync' })
  onBeforeRouteLeave(canLeave)

  const beforeUnload = (event: BeforeUnloadEvent) => {
    if (!dirty.value && !saving.value) return
    event.preventDefault()
    event.returnValue = ''
  }
  onMounted(() => window.addEventListener('beforeunload', beforeUnload))
  onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
  return { model, dirty, markSaved }
}