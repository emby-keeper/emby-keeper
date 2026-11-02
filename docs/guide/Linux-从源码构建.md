# 从源码构建

## 构建并启动网页面板

需要 Python 3.8 及以上版本和 Node.js 20。拉取源码并构建界面：

```bash
git clone https://github.com/emby-keeper/emby-keeper.git
cd emby-keeper
corepack enable
corepack prepare pnpm@9.15.9 --activate
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend run build
```

安装 Python 依赖并准备数据目录：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
export EMBYKEEPERAPI_BASEDIR="$PWD/data"
mkdir -p "$EMBYKEEPERAPI_BASEDIR"
touch "$EMBYKEEPERAPI_BASEDIR/config.toml"
```

将以下 `your-password` 换成自己的登录密码，否则面板会拒绝启动：

```bash
export EK_WEBPASS='your-password'
embykeeper web --host 127.0.0.1
```

浏览器打开 <http://127.0.0.1:8000>。如需从其他设备访问，应通过安全的反向代理或隧道提供 HTTPS 和访问控制。

## 命令行模式 (旧版)

::: warning 旧版部署方式
以下为命令行模式 (终端登录、`systemd` 后台运行), 没有网页界面. 若你希望使用图形界面, 请参考上文的网页面板
或 [**🖥️ 面板模式部署 (推荐)**](/guide/面板模式部署).
:::

Embykeeper 可以从源码构建, 首先请拉取并设置环境:

```bash
git clone https://github.com/emby-keeper/emby-keeper.git
make install && make run
```

命令将会在 `embykeeper` 目录下生成模板 `config.toml` 文件 (您也可以从[这里](https://github.com/emby-keeper/emby-keeper/blob/main/config.example.toml)下载).

<!--@include: ./_简要配置.md-->

然后, 再次运行:

```bash
make run
```

您将被询问设备验证码以登录, 登录成功后, Embykeeper 将首先执行一次签到和保活, 此后每日进行一次签到和保活.

恭喜您！您已经成功构建了 Embykeeper.

::: info 支持

<!--@include: ./_支持.md-->

:::

## 服务持久化

您可以通过 [systemd](https://www.ruanyifeng.com/blog/2016/03/systemd-tutorial-commands.html) 部署自启动服务.

首先, 您需要成功登录运行一次, 然后请运行:

```bash
make systemd
```

这将在 `~/.config/systemd/user` 中创建服务, 使 Embykeeper 在用户登录时自动启动.

## 版本更新

当您需要更新版本时, 您需要执行:

```
git pull
```

然后重新运行应用.
