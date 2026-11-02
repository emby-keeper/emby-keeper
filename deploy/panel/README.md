# 网页管理部署

用户安装步骤见 [面板模式部署](../../docs/guide/面板模式部署.md)。

## 快速开始

复制 `.env.example` 为 `.env`，将 `EK_WEBPASS` 的 `your-password` 替换为自己的密码后执行：

```bash
docker compose pull
docker compose up -d
```

浏览器打开 `http://服务器IP:8000`，使用设置的密码登录。

## 发布与维护

正式镜像为 `embykeeper/embykeeper`，默认启动网页管理，无需设置 `command`。显式传入命令行参数时，仍可使用原有命令行与旧在线控制台入口。

`docker.yml` 构建本目录 Dockerfile 的 `release` 目标；`docker-dev.yml` 构建 `editable` 目标。两者均包含已构建的前端，保留原有镜像名称、版本标签和 amd64/arm64 发布流程。

维护者在仓库根目录构建：

```bash
docker build -f deploy/panel/Dockerfile --target release -t embykeeper/embykeeper:local .
docker build -f deploy/panel/Dockerfile --target editable -t embykeeper/embykeeper:local-dev .
```

开发镜像需要挂载源码到 `/src`。

## 文件说明

| 文件 | 说明 |
| --- | --- |
| `Dockerfile` | 正式与开发镜像共用的构建文件，包含已构建的前端 |
| `docker-compose.yaml` | 拉取正式镜像，挂载 `./data:/app`，暴露 8000 |
| `.env.example` | 登录密码、端口和运行用户示例 |
| `entrypoint.sh` | 入口脚本: 准备数据目录、生成空配置、校验密码、启动面板 |
| `entrypoint-dev.sh` | 为开发镜像准备 `/src`，再使用相同启动入口 |

## 数据与备份

所有状态都在 `deploy/panel/data/` 一个目录内:

```text
deploy/panel/data/
├── config.toml            # 业务配置 (可在面板中修改)
├── cache.json             # 缓存 / 登录状态
├── *.session              # Telegram 会话文件
├── logs/                  # 运行日志
└── .embykeeper/           # 面板自身状态 (设置与界面偏好)
```

备份即打包该目录; 从旧版迁移时, 把旧数据目录 (`embykeeper/`) 的内容复制进来即可, 配置与会话文件完全兼容.

设置 `EK_MONGODB` 后, 配置、缓存与面板自身状态都改存 MongoDB, 不再需要挂载 `data`:

```bash
EK_WEBPASS='your-password' EK_MONGODB='mongodb://用户名:密码@主机:27017/embykeeper' \
  docker compose up -d
```

首次以数据库模式启动时, 若数据目录里存在旧的 `config.toml` 与 `cache.json`, 会一次性导入数据库, `cache.json` 改名为 `cache.json.migrated`; 之后删除 volumes 挂载也不会丢配置. 用户文档见 [用 MongoDB 无持久化部署](../../docs/guide/面板模式部署.md#用-mongodb-无持久化部署).

## 常用命令

```bash
docker compose logs -f panel          # 查看日志
docker compose restart panel          # 重启
docker compose down                   # 停止并删除容器 (数据保留)
docker compose pull && docker compose up -d  # 更新镜像并重启
```

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `EK_WEBPASS` | (无, 必填) | 面板访问密码; 未设置或使用 `your-password` 时拒绝启动 |
| `EK_PANEL_PORT` | `8000` | 面板对外端口 |
| `TZ` | `Asia/Shanghai` | 容器时区, 镜像已内置该默认值, 一般无需设置 |
| `EMBYKEEPERAPI_BASEDIR` | `/app` | 业务配置与用户数据目录 (镜像内已设定) |
| `EMBYKEEPERAPI_STATIC_DIR` | `/opt/embykeeper-panel/static` | 面板界面目录 (镜像内已设定) |
| `EK_MONGODB` | (无) | MongoDB 连接字符串; 设置后配置、缓存与面板状态全部入库, 无需挂载数据目录 |

## 说明

- 业务后端由面板自动拉起, 仅监听容器内 `127.0.0.1:8001`, 不对外暴露; 面板 `8000` 同时提供界面与 API (同源, 无 CORS 问题).
- 需要使用宿主机代理时, 在面板「系统设置 - 网络代理」中填写 `host.docker.internal` 与代理端口 (Compose 已配置 `host-gateway` 映射).
- 若宿主机端口冲突, 修改 `.env` 中的 `EK_PANEL_PORT` 即可 (容器内端口保持 8000).
