import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'
import { computed, nextTick, reactive, ref, watch } from 'vue'

function loadSetup(relativePath, exports, bindings = {}) {
  const source = readFileSync(new URL(`../src/${relativePath}`, import.meta.url), 'utf8')
  const setup = source.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)?.[1] || source
  const parsed = ts.createSourceFile(relativePath, setup, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const printer = ts.createPrinter()
  const stripped = parsed.statements
    .filter(statement => !ts.isImportDeclaration(statement))
    .map(statement => printer.printNode(ts.EmitHint.Unspecified, statement, parsed))
    .join('\n')
  const javascript = ts.transpileModule(stripped, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText
  const context = { exports: {}, computed, reactive, ref, watch, ...bindings }
  return new Function(...Object.keys(context), `${javascript}\nreturn { ${exports.join(', ')} };`)(...Object.values(context))
}

function scope(value = null) {
  const updates = []
  const props = reactive({
    label: 'Audit', modelValue: value, siteType: 'checkiner',
    sites: ['cc', 'terminus'], allSites: ['cc', 'terminus', 'agentsgk', 'aisgk'],
    extraSites: ['templ_a<AuditBot>'], displayNames: {}, allowInherit: false,
  })
  const component = loadSetup('components/ui/UiSiteScopeSelector.vue', [
    'syncFromValue', 'setMode', 'toggleSite', 'clearAll', 'addCustom', 'emitValue',
    'visibleSites', 'isChecked', 'mode', 'customInput', 'customInputError',
    'baseOptions', 'onBaseChange', 'categoryMode', 'setCategoryMode',
    'summary', 'categoryOptions', 'baseCoversCategory',
  ], {
    defineProps: () => props,
    withDefaults: properties => properties,
    defineEmits: () => (_event, update) => updates.push(update),
  })
  return { ...component, updates }
}

async function siteEditor(options) {
  const info = { label: 'Audit', templates: [], builtin: [], items: [] }
  const component = loadSetup('views/Sites.vue', [
    'types', 'activeType', 'form', 'applyStoredOptions', 'coerceOptions',
    'enumSelectOptions', 'optionSummary',
    'serializeFormDraft',
  ], {
    useAuthStore: () => ({ request: async () => ({ types: { checkiner: info, messager: info } }) }),
    useUnsavedChanges: open => ({ model: open, markSaved() {} }),
    logger: { error() {}, message: error => error.message },
  })
  await nextTick()
  component.types.value.messager = {
    ...info, builtin: [{ site: 'marmot', display_name: 'Audit', options }],
  }
  component.activeType.value = 'messager'
  component.form.kind = 'builtin'
  component.form.site = 'marmot'
  return component
}

test('an empty explicit scope remains empty instead of enabling defaults', () => {
  const component = scope([])
  component.clearAll()
  assert.deepEqual(component.updates.at(-1), [])
})

test('configured custom sites remain candidates after deselection', () => {
  const component = scope(['+templ_a<AuditBot>'])
  component.toggleSite('templ_a<AuditBot>')
  assert.ok(component.visibleSites.value.includes('templ_a<AuditBot>'))
})

test('switching append mode to explicit mode preserves the effective scope', () => {
  const component = scope(['+templ_a<AuditBot>'])
  component.setMode('include')
  assert.deepEqual(new Set(component.updates.at(-1)), new Set(['cc', 'terminus', 'templ_a<AuditBot>']))
})

test('editing a single site keeps the chosen base range instead of flattening it', () => {
  const component = scope(['all', '-sgk'])
  component.toggleSite('cc')
  assert.deepEqual(component.updates.at(-1), ['all', '-sgk', '-cc'])
})

test('the raw range identifiers are not offered as free-text input', () => {
  const component = scope(['all', '-sgk'])
  component.customInput.value = 'all'
  component.addCustom()
  assert.equal(component.updates.length, 0)
  assert.ok(component.customInputError.value)

  component.customInput.value = 'sgk'
  component.addCustom()
  assert.equal(component.updates.length, 0)

  component.customInput.value = '-terminus'
  component.addCustom()
  assert.equal(component.updates.length, 0)

  component.customInput.value = 'templ_a<AuditBot>'
  component.addCustom()
  assert.deepEqual(component.updates.at(-1), ['all', '+templ_a<AuditBot>', '-sgk'])
  assert.equal(component.customInputError.value, '')
})

test('the base range is chosen from a list instead of typed', () => {
  const component = scope(['+cc'])
  const values = component.baseOptions.value.map(option => option.value)
  assert.deepEqual(values, ['default', 'all', 'sgk'])

  component.onBaseChange('sgk')
  assert.equal(component.isChecked('agentsgk'), true)
  assert.equal(component.isChecked('aisgk'), true)
  assert.equal(component.isChecked('terminus'), false)
  // 基准里没有的站点仍留着显式追加, 界面上能看到它被勾选
  assert.equal(component.isChecked('cc'), true)
  assert.deepEqual(component.updates.at(-1), ['sgk', '+cc'])
})

test('switching the base range drops adjustments the new base already covers', () => {
  const component = scope(['all', '-cc'])
  assert.equal(component.isChecked('cc'), false)

  component.onBaseChange('sgk')
  assert.deepEqual(component.updates.at(-1), ['sgk'])
  assert.equal(component.isChecked('cc'), false)
})

test('the category toggle round-trips to the same saved identifiers', () => {
  const component = scope(['+cc'])
  assert.equal(component.categoryMode.value, 'follow')

  component.setCategoryMode('exclude')
  assert.deepEqual(component.updates.at(-1), ['+cc', '-sgk'])
  assert.equal(component.categoryMode.value, 'exclude')

  component.setCategoryMode('include')
  assert.deepEqual(component.updates.at(-1), ['+cc', '+sgk'])
  assert.equal(component.categoryMode.value, 'include')

  component.setCategoryMode('follow')
  assert.deepEqual(component.updates.at(-1), ['+cc'])
})

test('unchecking a category member records only that site as an exception', () => {
  const component = scope(['+sgk'])
  component.toggleSite('agentsgk')
  assert.deepEqual(component.updates.at(-1), ['+sgk', '-agentsgk'])
  assert.equal(component.isChecked('aisgk'), true)
  assert.equal(component.isChecked('agentsgk'), false)
})

test('saved rule identifiers are never displayed as individual candidate sites', () => {
  const component = scope(['all', '-sgk'])
  assert.ok(!component.visibleSites.value.includes('all'))
  assert.ok(!component.visibleSites.value.includes('sgk'))
})

test('a saved category inclusion selects the actual category members', () => {
  const component = scope(['+sgk'])
  assert.equal(component.isChecked('agentsgk'), true)
  assert.equal(component.isChecked('aisgk'), true)
})

test('an individual inclusion takes priority over a category exclusion', () => {
  const component = scope(['all', '-sgk', '+agentsgk'])
  assert.equal(component.isChecked('agentsgk'), true)
  assert.equal(component.isChecked('aisgk'), false)
})

test('the scope summary counts category members instead of the group identifier', () => {
  const component = scope(['+sgk'])
  // 基准 2 个站点 + 社工库 2 个成员
  assert.equal(component.summary.value, '在默认启用站点基础上生效 4 个，追加 2 项。')

  // 基准里本来就没有社工库站点, 排除整个分组是空操作, 不能报成生效 0 个
  component.setCategoryMode('exclude')
  assert.equal(component.summary.value, '在默认启用站点基础上生效 2 个。')

  // 基准换成全量时分组排除才真正生效, 并按成员数计数
  component.onBaseChange('all')
  assert.equal(component.summary.value, '在全部可用站点基础上生效 2 个，排除 2 项。')
})

test('a base range that already covers the category hides the redundant include', () => {
  const component = scope(['all'])
  assert.equal(component.baseCoversCategory.value, true)
  assert.deepEqual(component.categoryOptions.value.map(option => option.key), ['follow', 'exclude'])

  component.onBaseChange('default')
  assert.equal(component.baseCoversCategory.value, false)
  assert.deepEqual(component.categoryOptions.value.map(option => option.key), ['follow', 'include', 'exclude'])

  // 显式分组加入在基准已覆盖时会被清理掉, 不再残留冗余配置
  component.setCategoryMode('include')
  component.onBaseChange('all')
  assert.deepEqual(component.updates.at(-1), ['all'])
  assert.deepEqual(component.categoryOptions.value.map(option => option.key), ['follow', 'exclude'])
})

test('unknown numeric arrays and nested options survive an edit unchanged', async () => {
  const component = await siteEditor([
    { key: 'lengths', type: 'any' }, { key: 'metadata', type: 'any' },
    { key: 'max_interval', type: 'any' }, { key: 'messages', type: 'list' },
    { key: 'one_length', type: 'any' }, { key: 'nested_list', type: 'any' },
  ])
  const stored = {
    lengths: [3, 5], metadata: { nested: ['a', 'b'] }, max_interval: 90,
    messages: ['one.yaml', 'two.yaml'], one_length: [4], nested_list: [{ text: 'a' }],
  }
  component.applyStoredOptions(stored)
  assert.deepEqual(component.coerceOptions(), stored)
})

test('closed enumerations do not offer unsupported custom values', async () => {
  const component = await siteEditor([])
  assert.ok(!component.enumSelectOptions({ type: 'enum', choices: ['weekday', 'weekend'] })
    .some(option => option.value === '__custom__'))
  assert.ok(component.enumSelectOptions({ type: 'enum|str', choices: ['NUMBER'] })
    .some(option => option.value === '__custom__'))
})

test('sensitive options are not exposed in list summaries', async () => {
  const component = await siteEditor([])
  assert.ok(!component.optionSummary({ options: { password: 'audit-secret' } }).join().includes('audit-secret'))
})

test('initializing unset schedule controls does not make a draft dirty', async () => {
  const component = await siteEditor([])
  const initial = component.serializeFormDraft()
  component.form.options.time_range = ''
  component.form.options.interval_days = ''
  assert.equal(component.serializeFormDraft(), initial)
})

function streaming(fetch) {
  const { useSSE } = loadSetup('composables/useSSE.ts', ['useSSE'], {
    useAuthStore: () => ({ token: '' }), onUnmounted() {}, fetch,
    SSE_BASE_RETRY_DELAY_MS: 1000, SSE_MAX_RETRY_DELAY_MS: 30000, SSE_CONNECT_TIMEOUT_MS: 30000,
    logger: { error() {}, warn() {} },
  })
  return useSSE(ref('/audit'))
}

test('a previous SSE connection cannot remove the current cancellation handle', async () => {
  const requests = []
  const stream = streaming((_url, { signal }) => new Promise((_resolve, reject) => {
    requests.push(signal)
    signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
  }))
  const previous = stream.connect()
  const current = stream.connect()
  await previous
  stream.disconnect()
  await current
  assert.ok(requests.every(signal => signal.aborted))
  assert.equal(stream.isConnected.value, false)
})

test('a late SSE response cannot reconnect a disconnected view', async () => {
  let respond
  const stream = streaming(() => new Promise(resolve => { respond = resolve }))
  const pending = stream.connect()
  stream.disconnect()
  respond(new Response(new ReadableStream({ start(controller) { controller.close() } })))
  await pending
  assert.equal(stream.isConnected.value, false)
})

test('dirty drafts survive rejected close and route navigation', () => {
  let leaveGuard
  let allowDiscard = false
  const { useUnsavedChanges } = loadSetup('composables/useUnsavedChanges.ts', ['useUnsavedChanges'], {
    onBeforeRouteLeave: guard => { leaveGuard = guard }, onMounted() {}, onBeforeUnmount() {},
    window: { confirm: () => allowDiscard },
  })
  const open = ref(false)
  const state = reactive({ name: '' })
  const saving = ref(false)
  const guard = useUnsavedChanges(open, () => state, saving)
  open.value = true
  state.name = 'audit draft'
  guard.model.value = false
  assert.equal(open.value, true)
  assert.equal(leaveGuard(), false)
  allowDiscard = true
  guard.model.value = false
  assert.equal(open.value, false)
})

test('tooltip position stays in a narrow viewport and flips away from its top edge', () => {
  const component = loadSetup('components/ui/UiTooltip.vue', ['triggerRef', 'tooltipRef', 'tooltipStyle', 'updatePosition'], {
    defineProps: () => ({ position: 'top', text: 'Audit', widthClass: 'w-72' }),
    withDefaults: properties => properties,
    useSlots: () => ({}), getCurrentInstance: () => ({ uid: 1 }),
    onMounted() {}, onBeforeUnmount() {},
    window: { innerWidth: 320, innerHeight: 240 },
  })
  component.triggerRef.value = { getBoundingClientRect: () => ({ left: 300, width: 20, top: 5, bottom: 25 }) }
  component.tooltipRef.value = { getBoundingClientRect: () => ({ width: 288, height: 80 }) }
  component.updatePosition()
  assert.ok(Number.parseFloat(component.tooltipStyle.value.left) >= 12)
  assert.ok(Number.parseFloat(component.tooltipStyle.value.left) + 288 <= 308)
  assert.equal(Number.parseFloat(component.tooltipStyle.value.top), 35)
})