import { defineConfig } from 'vitepress';

// https://vitepress.dev/reference/site-config
export default defineConfig({
  lang: 'zh-CN',
  title: 'Embykeeper',
  description: 'Emby 签到保号的自动执行工具',
  cleanUrls: true,
  head: [['link', { rel: 'icon', href: '/favicon.ico' }]],
  sitemap: {
    hostname: 'https://emby-keeper.github.io',
  },
  vite: {
    optimizeDeps: {
      // 首页终端演示组件: 预先与主应用一起预构建, 避免被单独优化后加载到第二份 Vue
      include: ['@lehoczky/vue-termynal'],
    },
  },
  // vite: {
  //   plugins: [
  //     pagefindPlugin({
  //       customSearchQuery: chineseSearchOptimize,
  //       btnPlaceholder: '搜索',
  //       placeholder: '搜索文档',
  //       emptyText: '空空如也',
  //       heading: '共: {{searchResult}} 条结果',
  //       excludeSelector: ['img', 'a.header-anchor'],
  //     }),
  //   ],
  // },
  themeConfig: {
    // https://vitepress.dev/reference/default-theme-config

    logo: '/logo.svg',

    footer: {
      message: 'Released under the GPLv3 License.',
      copyright: 'Copyright © 2023-2025',
    },

    nav: [
      { text: '首页', link: '/' },
      { text: '教程', link: '/guide' },
    ],

    search: {
      provider: 'algolia',
      options: {
        appId: 'DE5VN80QVQ',
        apiKey: 'c83775524e9e6a76a929d33cece33fc4',
        indexName: 'emby-keeperio',
        placeholder: '搜索文档',
        translations: {
          button: {
            buttonText: '搜索文档',
            buttonAriaLabel: '搜索文档',
          },
          modal: {
            searchBox: {
              resetButtonTitle: '清除查询条件',
              resetButtonAriaLabel: '清除查询条件',
              cancelButtonText: '取消',
              cancelButtonAriaLabel: '取消',
            },
            startScreen: {
              recentSearchesTitle: '搜索历史',
              noRecentSearchesText: '没有搜索历史',
              saveRecentSearchButtonTitle: '保存至搜索历史',
              removeRecentSearchButtonTitle: '从搜索历史中移除',
              favoriteSearchesTitle: '收藏',
              removeFavoriteSearchButtonTitle: '从收藏中移除',
            },
            errorScreen: {
              titleText: '无法获取结果',
              helpText: '你可能需要检查你的网络连接',
            },
            footer: {
              selectText: '选择',
              navigateText: '切换',
              closeText: '关闭',
              searchByText: '搜索提供者',
            },
            noResultsScreen: {
              noResultsText: '无法找到相关结果',
              suggestedQueryText: '你可以尝试查询',
              reportMissingResultsText: '你认为该查询应该有结果？',
              reportMissingResultsLinkText: '点击反馈',
            },
          },
        },
      },
    },

    sidebar: [
      {
        text: '开始使用',
        items: [
          { text: '🏡 什么是 Embykeeper?', link: '/guide/' },
          { text: '🎬 支持的站点', link: '/guide/支持的站点' },
          { text: '🚀 安装指南', link: '/guide/安装指南' },
          {
            text: '🐧 Linux 安装',
            collapsed: true,
            items: [
              { text: '🖥️ 面板模式部署 (推荐)', link: '/guide/面板模式部署' },
              {
                text: '🐳 Docker 部署 (旧版)',
                link: '/guide/Linux-Docker-部署',
              },
              {
                text: '📚 Docker Compose 部署 (旧版)',
                link: '/guide/Linux-Docker-Compose-部署',
              },
              { text: '🏗️ 从源码构建', link: '/guide/Linux-从源码构建' },
              { text: '📦 PyPI 安装', link: '/guide/Linux-从-PyPI-安装' },
            ],
          },
          {
            text: '💻 Windows 安装',
            collapsed: true,
            items: [
              { text: '🖥️ Windows 面板安装', link: '/guide/Windows-面板安装' },
            ],
          },
          { text: '🪐 在线部署', link: '/guide/在线部署' },
          { text: '❔ 常见问题', link: '/guide/常见问题' },
        ],
      },
      {
        text: '功能配置',
        items: [
          {
            text: '💡 功能说明',
            collapsed: true,
            items: [
              { text: '🎬 自动保活', link: '/guide/功能说明-自动保活' },
              { text: '📅 每日签到', link: '/guide/功能说明-每日签到' },
              { text: '👀 群组监控', link: '/guide/功能说明-群组监控' },
              { text: '🕒 定时抢注', link: '/guide/功能说明-定时抢注' },
              { text: '💬 自动水群', link: '/guide/功能说明-自动水群' },
              { text: '📝 考核辅助', link: '/guide/功能说明-考核辅助' },
              { text: '🔔 日志推送', link: '/guide/功能说明-日志推送' },
            ],
          },
          { text: '🔧 配置文件', link: '/guide/配置文件' },
          { text: '⌨️ 命令行参数', link: '/guide/命令行参数' },
          { text: '👑 高级用户', link: '/guide/高级用户' },
        ],
      },
      {
        text: '关于开发',
        items: [
          { text: '🤝 参与开发', link: '/guide/参与开发' },
          { text: '🛠️ 调试工具', link: '/guide/调试工具' },
          { text: '⚖️ 许可', link: '/guide/许可' },
          { text: '🏭 发布周期', link: '/guide/发布周期' },
        ],
      },
    ],

    socialLinks: [
      { icon: 'github', link: 'https://github.com/emby-keeper/emby-keeper' },
    ],

    editLink: {
      pattern:
        'https://github.com/emby-keeper/emby-keeper/edit/main/docs/:path',
    },
  },
});
