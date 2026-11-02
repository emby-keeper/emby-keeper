/**
 * Centralised constants for frontend behaviour.
 * Every magic number / string that was previously scattered across views
 * should live here so it can be tuned in one place.
 */

// --- SSE / polling ---
export const SSE_BASE_RETRY_DELAY_MS = 3_000
export const SSE_MAX_RETRY_DELAY_MS = 60_000
export const SSE_RECONNECT_SHORT_MS = 2_000
export const SSE_CONNECT_TIMEOUT_MS = 10_000

// --- Logs ---
export const LOG_PAGE_LIMIT = 200
export const LOG_MAX_IN_MEMORY = 500
export const LOG_AUTO_SCROLL_DEBOUNCE_MS = 100

// --- Test-run polling ---
export const TEST_RUN_POLL_INTERVAL_MS = 2_000

// --- Auth ---
export const AUTH_CACHE_TTL_MS = 10_000

// --- Emby defaults ---
export const EMBY_DEFAULT_TIME_START = 300
export const EMBY_DEFAULT_TIME_END = 600

// --- Virtual scroller ---
export const VSCROLL_ITEM_HEIGHT_PX = 56
export const VSCROLL_BUFFER_ITEMS = 8
