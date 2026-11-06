# Windows 面板安装

适用于 Windows 10/11 x64。下载包已包含 Python 和运行所需的依赖，无需预先安装 Python，也无需在首次启动时下载依赖。

## 安装与启动

1. 打开 [Embykeeper Releases](https://github.com/emby-keeper/emby-keeper/releases)，下载最新版本中的 `embykeeper-win-vx.x.x.zip`。
2. 将 ZIP 完整解压到自己的文件夹，双击 `Start-Embykeeper.bat`。不要直接在压缩包内运行，也不要单独移动启动文件。
3. 按窗口提示设置面板登录密码。输入时密码不会显示；请记住该密码，不能使用 `your-password`。
4. 等待浏览器自动打开，使用刚设置的密码登录并添加账号。

启动后，Embykeeper 会留在屏幕右下角的系统托盘。点击图标可打开网页；右键选择 **Exit** 可退出。再次双击启动文件会打开已运行的面板。

面板默认仅允许本机通过 <http://127.0.0.1:8000> 访问。关闭浏览器不会停止程序。

## 更新

先从托盘退出，然后将最新版本的 ZIP 解压到一个新文件夹，双击其中的 `Start-Embykeeper.bat`。已有账号、设置和面板密码会保留。不要将不同版本的运行文件混在同一个文件夹里。

## 忘记密码

先从托盘退出，在文件资源管理器地址栏输入 `%LOCALAPPDATA%\Embykeeper`，删除其中的 `panel-password.txt`。再次双击启动文件，按提示设置新密码。

## 常见问题

- 启动时提示缺少文件：重新完整解压 ZIP，保留启动文件旁的 `runtime` 文件夹。
- 网页未打开：确认本机 8000 端口未被其他程序占用；启动日志位于 `%LOCALAPPDATA%\Embykeeper\panel.log`。
- 托盘图标不可见：展开任务栏通知区域中的隐藏图标。

如果需要在线安装，可下载 `embykeeper-win-online-vx.x.x.zip`。这个较小的包会在首次运行时下载 Python 并通过 pip 安装依赖，耗时取决于网络和磁盘速度；国内源不可用时会尝试官方源。

账号数据和密码属于敏感信息，请妥善保护本机用户账户及备份。
