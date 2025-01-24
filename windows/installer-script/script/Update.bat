@echo off

where powershell >nul 2>nul
if not %errorlevel% == 0 (
    echo Powershell 不可用, 您需要安装 Powershell 以使用该软件.
    (((echo.%cmdcmdline%)|find /I "%~0")>nul) && pause
    exit /b 1
)
echo **************************************************
echo *            请等待, 正在更新 Embykeeper         *
echo **************************************************
powershell Unblock-File -Path '%~dp0downloaders\download_python.ps1'
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0downloaders\download_python.ps1" -Version 3.8.10 -TargetDirectory "." || goto :error
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0downloaders\download_pip.ps1" -TargetDirectory "python-3.8.10-embed-amd64" || goto :error
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0downloaders\download_deps.ps1" -Update -PythonPath "python-3.8.10-embed-amd64\python.exe" || goto :error

echo **************************************************
"%~dp0/python-3.8.10-embed-amd64/python.exe" -c "import embykeeper; print(f'更新已结束, 当前版本为: {embykeeper.__version__}')"
(((echo.%cmdcmdline%)|find /I "%~0")>nul) && echo | set /p="请按任意键退出..." & pause>nul
goto :EOF

:error
echo **************************************************
echo 发生错误, 即将退出, 请反馈以上信息.
(((echo.%cmdcmdline%)|find /I "%~0")>nul) && pause
