# Windows 面板安装

## 安装与启动

1. 打开 [Embykeeper Releases](https://github.com/emby-keeper/emby-keeper/releases)，下载最新版本中的 `embykeeper-win-vx.x.x.zip`。
2. 将 ZIP 解压到自己的文件夹，双击 `Start-Embykeeper.bat`。首次启动需要联网，程序会自动安装 Python 和所需依赖；国内源不可用时会尝试官方源。
3. 按窗口提示设置面板登录密码。输入时密码不会显示；请记住该密码，不能使用 `your-password`。
4. 等待浏览器自动打开，使用刚设置的密码登录并添加账号。

启动后，Embykeeper 会留在屏幕右下角的系统托盘。点击图标可打开网页；右键选择 **Exit** 可退出。再次双击启动文件会打开已运行的面板。

面板默认仅允许本机通过 <http://127.0.0.1:8000> 访问。关闭浏览器不会停止程序。

## 更新

先从托盘退出，然后下载最新版本的 ZIP，解压并双击其中的 `Start-Embykeeper.bat`。安装器会联网更新对应版本，保留已有账号和设置。

## 忘记密码

先从托盘退出，在文件资源管理器地址栏输入 `%LOCALAPPDATA%\Embykeeper`，删除其中的 `panel-password.txt`。再次双击启动文件，按提示设置新密码。

## 常见问题

- 首次安装失败：检查网络连接后重新双击启动文件。安装器会在国内源和官方源之间自动回退。
- 网页未打开：确认本机 8000 端口未被其他程序占用；启动日志位于 `%LOCALAPPDATA%\Embykeeper\panel.log`。
- 托盘图标不可见：展开任务栏通知区域中的隐藏图标。

账号数据和密码属于敏感信息，请妥善保护本机用户账户及备份。
