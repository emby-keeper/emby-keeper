# 部署目录

本目录集中存放所有 Docker 部署文件, 按 **新版 / 旧版 / 云平台** 三组区分:

| 目录      | 内容                                                  | 状态             |
| --------- | ----------------------------------------------------- | ---------------- |
| `panel/`  | 正式镜像与开发镜像的构建、网页管理部署示例            | **当前发布入口** |
| `legacy/` | 命令行镜像与旧版在线控制台 (`embykeeperweb`)          | 旧版, 仍维护     |
| `cloud/`  | 云平台 (Render / Heroku 等) 使用的镜像转发 Dockerfile | 云平台专用       |

## panel/ — 新版面板模式 (推荐)

- 文档: [面板模式部署](../docs/guide/面板模式部署.md)
- 快速开始:

  ```bash
  cd deploy/panel
  cp .env.example .env      # 将 EK_WEBPASS 的 your-password 换成自己的密码
  docker compose pull
  docker compose up -d
  ```

- 镜像名: `embykeeper/embykeeper`，默认启动网页管理，对外端口 8000，无需设置 `command`。
- 正式版 Action 构建 `panel/Dockerfile` 的 `release` 目标；开发版构建 `editable` 目标，均包含前端。

## legacy/ — 旧版

- 文档: [Docker 部署](../docs/guide/Linux-Docker-部署.md) / [Docker Compose 部署](../docs/guide/Linux-Docker-Compose-部署.md)
- 此处保留原有构建文件，不再作为默认 Action 的构建入口。
- `entrypoint.sh` 继续用于正式镜像的兼容启动：未指定 `web` 时，未设置 `EK_WEBPASS` 运行命令行模式，设置后运行旧版在线控制台 (端口 1818)。
- `Dockerfile.dev` + `entrypoint-dev.sh` 保留旧版源码挂载方式。

## cloud/ — 云平台

`Dockerfile` 只做两件事: 基于已发布镜像 `embykeeper/embykeeper` 创建 UID 1000 的用户, 供 Render / Heroku 等平台直接拉取, 避免在平台侧从源码构建.

引用该文件的位置: `heroku.yml`、`render.yaml`. 若把旧版正式镜像升级到新版面板, 也应同步修改这两处.
