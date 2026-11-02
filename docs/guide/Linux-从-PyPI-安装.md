# 从 PyPi 安装

## 安装并用网页管理

Embykeeper 可以在 `python >= 3.8` 运行. 建议使用 [virtualenv](https://virtualenv.pypa.io/) 进行环境管理和包安装:

```bash
python -m venv embykeeper-venv
. ./embykeeper-venv/bin/activate
pip install embykeeper
```

安装包里已经包含已构建的面板界面. 设置数据目录和登录密码后启动:

```bash
export EMBYKEEPERAPI_BASEDIR="$HOME/embykeeper-data"
mkdir -p "$EMBYKEEPERAPI_BASEDIR"
export EK_WEBPASS='your-password'   # 换成自己的密码, 否则面板会拒绝启动
embykeeper web --host 127.0.0.1
```

浏览器打开 <http://127.0.0.1:8000>, 用刚才设置的密码登录, 即可添加账号、配置任务并查看日志. 面板会把配置写入数据目录下的 `config.toml`.

之后更新版本:

```bash
pip install -U embykeeper
```

## 命令行模式 (旧版)

::: warning 旧版部署方式
以下为命令行模式 (终端登录、`tmux` 后台运行), 没有网页界面. 若你希望使用图形界面, 请参考上文的网页管理
或 [**🖥️ 面板模式部署 (推荐)**](/guide/面板模式部署).
:::

已经安装 Embykeeper 后, 不设置 `EK_WEBPASS`, 直接执行:

```bash
embykeeper -i
```

命令将会在 `embykeeper` 目录下生成模板 `config.toml` 文件 (您也可以从[这里](https://github.com/emby-keeper/emby-keeper/blob/main/config.example.toml)下载).

<!--@include: ./_简要配置.md-->

然后, 再次运行:

```bash
embykeeper -i
```

您将被询问设备验证码以登录, 登录成功后, Embykeeper 将首先执行一次签到和保活, 此后每日进行一次签到和保活.

恭喜您！您已经成功安装了 Embykeeper.

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

当您需要更新版本时, 您需要执行:

```
pip install -U embykeeper
```

然后重新运行应用.
