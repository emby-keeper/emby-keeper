# Docker Compose 部署

## 配置与部署

您可以使用 [docker-compose](https://docs.docker.com/compose/install/standalone/) 部署 Embykeeper.

::: warning 注意
您需要先进行过 [通过 Docker 部署](/guide/Linux-Docker-部署) 才能通过 Docker Compose 部署.

这是由于首次登录会命令行请求两步验证码, 登录成功后会生成 `.login` 后缀的文件, 随后才能部署为 `docker-compose` 服务.
:::

::: info 提示
如果你还没有安装 Docker Compose，下面是其安装步骤:

```bash
curl -L "https://github.com/docker/compose/releases/download/v2.32.4/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
```

:::

您应该已经运行了:

```bash
docker run -v $(pwd)/embykeeper:/app --rm -it --net=host embykeeper/embykeeper -i
```

您需要新建一个文件 `docker-compose.yml`, 此时您的目录结构如下:

```bash
.
├── embykeeper
│   ├── config.toml
│   ├── +xxxxx.session
│   └── +xxxxx.login
└── docker-compose.yml
```

然后向 `docker-compose.yml` 写入:

```yaml
version: '3'
services:
  embykeeper:
    container_name: embykeeper
    image: embykeeper/embykeeper
    restart: unless-stopped
    volumes:
      - ./embykeeper:/app
    network_mode: host
```

::: tip 提示
`network_mode: host` 用于连接主机上的代理, 若您不需要可以忽略
:::

然后运行以下命令以启动:

```bash
docker-compose up -d
```

::: tip 提示
`docker-compose` 命令会读取**当前路径**下的`docker-compose.yml`, 因此您需要先定位到 `docker-compose.yml` 所在的目录!
:::

::: tip 提示
由于我们没有使用 `docker run` 命令中使用的 `-i` 参数, 启动时将不会运行一次任务, 而是仅作为计划任务运行.
:::

恭喜您！您已经通过 Docker Compose 成功部署了 Embykeeper.

::: info 支持

<!--@include: ./_支持.md-->

:::

## 日志文件

您需要在 `docker-compose.yml` 所在目录执行:

```bash
docker-compose logs -f embykeeper
```

以监控最新日志.

## 版本更新

您需要在 `docker-compose.yml` 所在目录执行:

```bash
docker-compose pull
docker-compose up -d
```

以拉取最新版本镜像, 并完成更新.

## 自动版本更新

您可以使用 [watchtower](https://github.com/containrrr/watchtower) 来自动更新 Embykeeper 的 Docker 镜像。

在您的 `docker-compose.yml` 中添加 watchtower 服务：

```yaml
version: '3'
services:
  embykeeper:
    container_name: embykeeper
    image: embykeeper/embykeeper
    restart: unless-stopped
    volumes:
      - ./embykeeper:/app
    network_mode: host

  watchtower:
    container_name: watchtower
    image: containrrr/watchtower
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    command: --interval 86400 --cleanup embykeeper
    restart: unless-stopped
```

这将：

- 每24小时（86400秒）自动检查并更新 embykeeper 容器
- 仅监控名为 "embykeeper" 的容器
- 发现新版本时自动拉取镜像并重启容器

::: tip 提示
您可以通过修改 `--interval` 参数来调整检查更新的时间间隔（单位：秒）。
:::

## 使用其他版本

当您需要使用旧版本 (例如`v1.1.1`) 时, 您需要使用:

```yaml
version: '3'
services:
  embykeeper:
    container_name: embykeeper
    image: embykeeper/embykeeper:v1.1.1
    ....
```

## 命令行参数

Embykeeper 支持多样化的 [**⌨️ 命令行参数**](/guide/命令行参数).

<!-- #region command -->

当通过 Docker Compose 部署时, 您需要通过修改 `docker-compose.yml` 中的 `command` 项, 从而调整命令行参数, 例如:

```yaml
version: '3'
services:
  embykeeper:
    container_name: embykeeper
    image: embykeeper/embykeeper
    command: '-e'
    restart: unless-stopped
    volumes:
      - ./embykeeper:/app
    network_mode: host
```

<!-- #endregion command -->

以上配置将执行 `embykeeper -e`, 即仅启用 Emby 保活功能.

## 修改程序源码, 并用 Docker Compose 运行

Embykeeper 提供 `dev` 系列镜像, 您需要新建一个文件 `docker-compose.yml`:

```yaml
version: '3'
services:
  embykeeper:
    container_name: embykeeper
    image: embykeeper/embykeeper:main-dev
    restart: unless-stopped
    volumes:
      - ./embykeeper:/app
      - ./embykeeper-src:/src
    network_mode: host
```

然后运行:

```bash
docker-compose up -d
```

这将在 `./embykeeper-src` 目录挂载源码, `./embykeeper` 目录挂载数据.

您可以直接修改 `./embykeeper-src` 中的源码, 重启容器后程序将据此运行.

例如, 只要您有基本的编程能力, 您就可以在 `./embykeeper-src/embykeeper/telechecker/bots` 中按照 [教程](/guide/参与开发#每日签到站点) 提供的方式非常容易地新建一个站点的签到.

::: tip 如何更新

如果您需要更新 `dev` 系列构象, 您需要直接在 `./embykeeper-src/` 目录中使用 `git pull`.

::::

欢迎您在实现签到器后, 通过 [Pull requests](https://github.com/emby-keeper/emby-keeper/pulls) 向 Embykeeper 分享你的成果.

## 部署在线控制台

当 `EK_WEBPASS` 环境变量被设定时, 将启动在线控制台, 默认的命令行将不会启动.

::: warning 注意
自部署不推荐使用在线控制台, 目前的在线控制台实际上是控制台的在线版, 并不提供高级美观直观的界面.
之后, 我们会考虑在线界面的开发.
:::

::: warning 注意
在自部署模式下, 配置文件不生效, 需要通过环境变量输入配置.
:::

请使用 `docker-compose.yml`:

```yaml
version: '3'
services:
  embykeeper:
    container_name: embykeeper
    image: embykeeper/embykeeper
    restart: unless-stopped
    environment:
      - EK_WEBPASS=123456
    ports:
      - 80:1818
```

并运行:

```bash
docker-compose up -d
```

将在 80 端口启动在线控制台 HTTP 服务.
