#!/bin/bash
# 旧版镜像入口: 根据 EK_WEBPASS 决定启动命令行模式还是旧版在线控制台 (embykeeperweb).
# 面板模式 (图形界面, 推荐) 请使用 deploy/panel/entrypoint.sh.

set -e

if [ -z "${EK_WEBPASS}" ]; then
    exec "embykeeper" "--basedir" "/app" "$@"
else
    exec "embykeeperweb" "--basedir" "/app" "--public" "$@"
fi
