<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { Dialog, DialogPanel, TransitionChild, TransitionRoot } from '@headlessui/vue'
import {
  Bars3Icon,
  XMarkIcon,
  HomeIcon,
  ChatBubbleLeftRightIcon,
  TvIcon,
  MusicalNoteIcon,
  ChartBarIcon,
  PuzzlePieceIcon,
  Cog6ToothIcon,
  ArrowRightOnRectangleIcon
} from '@heroicons/vue/24/outline'

const authStore = useAuthStore()
const route = useRoute()

const sidebarOpen = ref(false)

const navigation = [
  { name: '概览', href: '/status', icon: HomeIcon },
  { name: 'Telegram 账号', href: '/telegram', icon: ChatBubbleLeftRightIcon },
  { name: 'Emby 账号', href: '/emby', icon: TvIcon },
  { name: 'Subsonic 账号', href: '/subsonic', icon: MusicalNoteIcon },
  { name: '任务记录', href: '/runinfo', icon: ChartBarIcon },
  { name: '自定义站点', href: '/sites', icon: PuzzlePieceIcon },
  { name: '系统设置', href: '/settings', icon: Cog6ToothIcon },
]

const isLoginPage = computed(() => route.path === '/login')

const logout = async () => {
  await authStore.logout()
  window.location.href = '/login'
}
</script>

<template>
  <div v-if="isLoginPage" class="h-full">
    <router-view />
  </div>

  <div v-else class="h-full bg-slate-100">
    <TransitionRoot as="template" :show="sidebarOpen">
      <Dialog as="div" class="relative z-50 xl:hidden" @close="sidebarOpen = false">
        <TransitionChild as="template" enter="transition-opacity ease-linear duration-300" enter-from="opacity-0" enter-to="opacity-100" leave="transition-opacity ease-linear duration-300" leave-from="opacity-100" leave-to="opacity-0">
          <div class="fixed inset-0 bg-gray-900/80" />
        </TransitionChild>

        <div class="fixed inset-0 flex">
          <TransitionChild as="template" enter="transition ease-in-out duration-300 transform" enter-from="-translate-x-full" enter-to="translate-x-0" leave="transition ease-in-out duration-300 transform" leave-from="translate-x-0" leave-to="-translate-x-full">
            <DialogPanel class="relative mr-16 flex w-full max-w-xs flex-1">
              <TransitionChild as="template" enter="ease-in-out duration-300" enter-from="opacity-0" enter-to="opacity-100" leave="ease-in-out duration-300" leave-from="opacity-100" leave-to="opacity-0">
                <div class="absolute left-full top-0 flex w-16 justify-center pt-5">
                  <button type="button" class="-m-2.5 p-2.5" @click="sidebarOpen = false">
                    <span class="sr-only">Close sidebar</span>
                    <XMarkIcon class="h-6 w-6 text-white" aria-hidden="true" />
                  </button>
                </div>
              </TransitionChild>

              <!-- Mobile Sidebar -->
              <div class="flex grow flex-col gap-y-5 overflow-y-auto bg-white px-6 pb-4 shadow-2xl shadow-slate-900/10">
                <div class="flex h-16 shrink-0 items-center justify-center pt-4">
                  <img class="h-10 w-auto" src="/assets/img/illustrations/logo-only.svg" alt="EmbyKeeper" />
                </div>
                <nav class="flex flex-1 flex-col mt-4">
                  <ul role="list" class="flex flex-1 flex-col gap-y-7">
                    <li>
                      <ul role="list" class="-mx-2 space-y-2">
                        <li v-for="item in navigation" :key="item.name">
                          <router-link :to="item.href" @click="sidebarOpen = false" :class="[route.path.startsWith(item.href) ? 'bg-primary-50 text-primary-600' : 'text-gray-700 hover:bg-gray-50 hover:text-primary-600', 'group flex gap-x-3 rounded-md p-2 text-sm font-semibold leading-6']">
                            <component :is="item.icon" :class="[route.path.startsWith(item.href) ? 'text-primary-600' : 'text-gray-400 group-hover:text-primary-600', 'h-6 w-6 shrink-0']" aria-hidden="true" />
                            {{ item.name }}
                          </router-link>
                        </li>
                      </ul>
                    </li>
                    <li class="mt-auto">
                      <button @click="logout" class="group -mx-2 flex gap-x-3 rounded-md p-2 text-sm font-semibold leading-6 text-red-600 hover:bg-red-50 hover:text-red-700 w-full text-left">
                        <ArrowRightOnRectangleIcon class="h-6 w-6 shrink-0 text-red-500 group-hover:text-red-600" aria-hidden="true" />
                        退出登录
                      </button>
                    </li>
                  </ul>
                </nav>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </Dialog>
    </TransitionRoot>

    <!-- Static sidebar for desktop -->
    <div class="hidden xl:fixed xl:inset-y-0 xl:z-50 xl:flex xl:w-72 xl:flex-col border-r border-slate-200/80 bg-white/90 backdrop-blur-sm">
      <div class="flex grow flex-col gap-y-5 overflow-y-auto bg-transparent px-6 pb-4">
        <div class="flex h-16 shrink-0 items-center gap-3 pt-6 pb-2">
          <img class="h-10 w-auto" src="/assets/img/illustrations/logo-only.svg" alt="EmbyKeeper" />
          <span class="text-xl font-bold text-gray-900 tracking-tight">EmbyKeeper</span>
        </div>
        <nav class="flex flex-1 flex-col mt-4">
          <ul role="list" class="flex flex-1 flex-col gap-y-7">
            <li>
              <ul role="list" class="-mx-2 space-y-2">
                <li v-for="item in navigation" :key="item.name">
                  <router-link :to="item.href" :class="[route.path.startsWith(item.href) ? 'bg-primary-50 text-primary-600 ring-1 ring-primary-100' : 'text-gray-700 hover:bg-gray-50 hover:text-primary-600', 'group flex gap-x-3 rounded-xl p-2.5 text-sm font-semibold leading-6 transition-all']">
                    <component :is="item.icon" :class="[route.path.startsWith(item.href) ? 'text-primary-600' : 'text-gray-400 group-hover:text-primary-600', 'h-5 w-5 shrink-0']" aria-hidden="true" />
                    {{ item.name }}
                  </router-link>
                </li>
              </ul>
            </li>
            <li class="mt-auto">
              <button @click="logout" class="group w-full flex items-center gap-x-3 rounded-xl p-2.5 text-sm font-semibold leading-6 text-red-600 hover:bg-red-50 hover:text-red-700 transition-all">
                <ArrowRightOnRectangleIcon class="h-5 w-5 shrink-0 text-red-500 group-hover:text-red-600" aria-hidden="true" />
                退出登录
              </button>
            </li>
          </ul>
        </nav>
      </div>
    </div>

    <!-- Main content area -->
    <div class="flex h-dvh min-w-0 flex-col xl:pl-72">
      <!-- Mobile header -->
      <div class="sticky top-0 z-40 flex h-14 shrink-0 items-center gap-x-4 border-b border-slate-200/80 bg-white/90 px-4 backdrop-blur-sm sm:h-16 sm:gap-x-6 sm:px-6 xl:hidden">
        <button type="button" class="-m-2.5 p-2.5 text-gray-700 xl:hidden" @click="sidebarOpen = true">
          <span class="sr-only">打开导航菜单</span>
          <Bars3Icon class="h-6 w-6" aria-hidden="true" />
        </button>
        <div class="flex-1 text-sm font-semibold leading-6 text-gray-900">EmbyKeeper</div>
      </div>

      <main class="min-h-0 min-w-0 flex-1 overflow-y-auto">
        <div class="mx-auto w-full min-w-0 max-w-7xl p-3 sm:p-5 xl:p-8">
          <router-view />
        </div>
      </main>
    </div>
  </div>
</template>
