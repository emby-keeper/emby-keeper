import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'
import Login from './views/Login.vue'
import Status from './views/Status.vue'
import Telegram from './views/Telegram.vue'
import Emby from './views/Emby.vue'
import Subsonic from './views/Subsonic.vue'
import Runinfo from './views/Runinfo.vue'
import Sites from './views/Sites.vue'
import Settings from './views/Settings.vue'

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to, _from, savedPosition) {
    if (savedPosition) {
      return savedPosition
    }

    if (to.hash) {
      return {
        el: to.hash,
        top: 24,
        behavior: 'smooth',
      }
    }

    return { top: 0 }
  },
  routes: [
    { path: '/login', component: Login },
    { path: '/', redirect: '/status' },
    { path: '/status', component: Status, meta: { requiresAuth: true } },
    { path: '/telegram', component: Telegram, meta: { requiresAuth: true } },
    { path: '/emby', component: Emby, meta: { requiresAuth: true } },
    { path: '/subsonic', component: Subsonic, meta: { requiresAuth: true } },
    { path: '/runinfo', component: Runinfo, meta: { requiresAuth: true } },
    { path: '/sites', component: Sites, meta: { requiresAuth: true } },
    { path: '/settings', component: Settings, meta: { requiresAuth: true } },
  ]
})

// Cache auth result within a short window to avoid redundant /api/auth/me calls
let authCache: { valid: boolean; ts: number } | null = null
const AUTH_CACHE_TTL = 10_000

router.beforeEach(async (to, _from, next) => {
  const auth = useAuthStore()

  if (to.path === '/login') {
    authCache = null
    const isValid = await auth.checkAuth()
    if (isValid) next('/status')
    else next()
    return
  }

  if (!to.meta.requiresAuth) {
    next()
    return
  }

  const now = Date.now()
  if (!authCache || now - authCache.ts > AUTH_CACHE_TTL) {
    const isValid = await auth.checkAuth()
    authCache = { valid: isValid, ts: now }
    if (isValid) next()
    else next('/login')
  } else {
    if (authCache.valid) next()
    else next('/login')
  }
})

export default router
