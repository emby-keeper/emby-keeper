#!/bin/bash
# Embykeeper 面板容器入口脚本
#
# 职责:
#   1. 准备数据目录 (内含 config.toml, cache.json, 会话, 日志与面板自身状态)
#   2. 首次运行时生成空配置文件 (等价于全部默认值, 之后可在面板中修改)
#   3. 校验面板访问密码 EK_WEBPASS
#   4. 启动面板 (面板会自动拉起被托管的 Embykeeper 业务后端)

set -e

if [ "${1:-}" != "web" ]; then
    exec /legacy-entrypoint.sh "$@"
fi

for argument in "$@"; do
    if [ "$argument" = "--help" ]; then
        exec embykeeper "$@"
    fi
done

basedir="${EMBYKEEPERAPI_BASEDIR:-/app}"

mkdir -p "${basedir}"

if [ -n "${EK_MONGODB:-}" ]; then
    echo ">> 检测到 EK_MONGODB: 配置、缓存与面板设置将保存在 MongoDB, 无需挂载数据目录."
else
    # 空 TOML 是合法的, 表示全部使用默认配置; 面板的「系统设置」页会按需写入
    if [ ! -f "${basedir}/config.toml" ]; then
        : > "${basedir}/config.toml"
        echo ">> 已生成配置文件 ${basedir}/config.toml (默认配置, 可直接在面板中修改)."
    fi
fi

if [ -z "${EK_WEBPASS}" ]; then
    echo "!! 未设置面板访问密码 EK_WEBPASS, 拒绝启动 (面板不可无密码暴露在网络上)." >&2
    echo "!! 请在 docker-compose 的 .env 中设置, 或使用 docker run -e EK_WEBPASS=你的密码 ..." >&2
    exit 1
fi

echo ">> 数据目录: ${basedir}"
port=8000
previous=""
for argument in "$@"; do
    if [ "${previous}" = "--port" ]; then
        port="${argument}"
    fi
    previous="${argument}"
done
echo ">> 面板地址: http://<服务器地址>:${port} (容器内端口 ${port})"

exec "embykeeper" "$@"
