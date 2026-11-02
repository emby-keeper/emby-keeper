# Docker 部署 (旧版)

::: warning 这是旧版部署方式
本页介绍命令行模式 (终端登录、`tmux` 后台运行). 若你希望使用图形界面管理签到、保活与日志,
请参考 [**🖥️ 面板模式部署 (推荐)**](/guide/面板模式部署).
:::

## 配置与部署

Embykeeper 可以通过 `docker` 部署, 您需 [安装 docker](https://yeasy.gitbook.io/docker_practice/install), 然后执行:

```bash
docker run -v $(pwd)/embykeeper:/app --rm -it --net=host embykeeper/embykeeper
```

::: tip 说明
`--net=host` 用于连接主机上的代理, 若您不需要可以不使用这个选项.
:::

命令将会在 `embykeeper` 目录下生成模板 `config.toml` 文件 (您也可以从[这里](https://github.com/emby-keeper/emby-keeper/blob/main/config.example.toml)下载).

<!--@include: ./_简要配置.md-->

随后, 再次执行命令:

```bash
docker run -v $(pwd)/embykeeper:/app --rm -it --net=host embykeeper/embykeeper -i
```

::: info 注意

命令行中的 `-i` 指: 启动后立刻运行一次签到和保活, 如果您需要频繁多次运行, 请去掉该命令行参数运行:

```bash
docker run -v $(pwd)/embykeeper:/app --rm -it --net=host embykeeper/embykeeper
```

:::

您将被询问设备验证码以登录, 登录成功后, Embykeeper 将首先执行一次签到和保活, 此后每日进行一次签到和保活.

恭喜您！您已经成功部署了 Embykeeper.

::: info 支持

<!--@include: ./_支持.md-->

:::

## 后台运行

为了让 Embykeeper 长期后台运行, 您可以通过 `Ctrl + C` 停止, 然后运行:

```bash
tmux
```

这将启动一个 `tmux` 终端, 您可以在该终端中重新运行上述命令, 并按 `Ctrl + B`, 松开再按 `D`, 以脱离 `tmux` 终端.

您随时可以通过运行:

```bash
tmux a
```

以重新连接到 `tmux` 终端.

## 版本更新

当您需要更新版本时, 您需要按 `Ctrl + C` 停止现有程序, 然后执行:

```bash
docker pull embykeeper/embykeeper
```

然后重新运行:

```bash
docker run -v $(pwd)/embykeeper:/app --rm -it --net=host embykeeper/embykeeper -i
```

## 使用其他版本

当您需要使用旧版本 (例如`v1.1.1`) 时, 您可以在镜像名后追加版本号:

```bash
docker run -v $(pwd)/embykeeper:/app --rm -it --net=host embykeeper/embykeeper:v1.1.1 -i
```

## 命令行参数

Embykeeper 支持多样化的 [**⌨️ 命令行参数**](/guide/命令行参数).

<!-- #region command -->

当通过 Docker 部署时, 末尾的所有参数将被传递给 Embykeeper, 例如:

```bash
docker run -v $(pwd)/embykeeper:/app --rm -it --net=host embykeeper/embykeeper -e
```

<!-- #endregion command -->

将执行 `embykeeper -e`, 即仅启动 Emby 保活功能.

## 修改程序源码, 并用 Docker 运行

Embykeeper 提供 `dev` 系列镜像, 您可以运行:

```bash
docker run -v $(pwd)/embykeeper-src:/src -v $(pwd)/embykeeper:/app --rm -it --net=host embykeeper/embykeeper:main-dev -i
```

这将在 `./embykeeper-src` 目录挂载源码, `./embykeeper` 目录挂载数据.

您可以直接修改 `./embykeeper-src` 中的源码, 重启容器后程序将据此运行.

例如, 只要您有基本的编程能力, 您就可以在 `./embykeeper-src/embykeeper/telechecker/bots` 中按照 [教程](/guide/参与开发#每日签到站点) 提供的方式非常容易地新建一个站点的签到.

::: tip 如何更新

如果您需要更新 `dev` 系列构象, 您需要直接在 `./embykeeper-src/` 目录中使用 `git pull`.

::::

欢迎您在实现签到器后, 通过 [Pull requests](https://github.com/emby-keeper/emby-keeper/pulls) 向 Embykeeper 分享你的成果.
