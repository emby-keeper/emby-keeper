# Embykeeper 正式镜像 (命令行与网页管理)
#
# 内容: Embykeeper 业务后端 + 面板 API (embykeeperapi) + 已构建的面板界面
# 用途: 单容器提供「界面 + API + 计划任务」, 无需命令行登录, 无需额外 Web 服务器
#
# 旧版 (命令行镜像 + embykeeperweb 在线控制台) 请使用 deploy/legacy/Dockerfile.
#
# 构建 (在仓库根目录执行):
#   docker build -f deploy/panel/Dockerfile -t embykeeper/embykeeper:latest .
# 国内网络可追加:
#   --build-arg NPM_REGISTRY=https://registry.npmmirror.com --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# ==============================================================================
# 阶段一: 构建面板界面 (Vue 3 + Vite)
# ==============================================================================
FROM node:20-alpine AS ui

ARG NPM_REGISTRY=https://registry.npmjs.org

WORKDIR /ui

RUN corepack enable \
    && corepack prepare pnpm@9.15.9 --activate \
    && pnpm config set registry "${NPM_REGISTRY}"

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
RUN pnpm run build

# ==============================================================================
# 阶段二: 安装 Python 运行环境 (构建阶段镜像自带编译器, 便于源码依赖编译)
# ==============================================================================
FROM python:3.11 AS builder

ARG PIP_INDEX_URL=https://pypi.org/simple

WORKDIR /src
# 只复制打包所需内容: 仓库中其它文件 (文档、部署、前端) 变动不再触发依赖重装
COPY pyproject.toml README.md LICENSE MANIFEST.in requirements.txt ./
COPY embykeeper ./embykeeper
COPY embykeeperapi ./embykeeperapi
COPY embykeeperweb ./embykeeperweb

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --retries 5 --timeout 60 -U pip setuptools wheel \
    && /opt/venv/bin/pip install --no-cache-dir --retries 5 --timeout 60 \
        --index-url "${PIP_INDEX_URL}" .

# ==============================================================================
# 阶段三: 运行镜像
# ==============================================================================
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai \
    EK_IN_DOCKER=1 \
    HOME=/app \
    EMBYKEEPERAPI_BASEDIR=/app \
    EMBYKEEPERAPI_STATIC_DIR=/opt/embykeeper-panel/static \
    PATH=/opt/venv/bin:$PATH

# ca-certificates: 访问 Telegram / Emby 站点; tzdata: 计划任务时区; libgomp1: onnxruntime (验证码识别)
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates tzdata libgomp1; \
    rm -rf /var/lib/apt/lists/*; \
    ln -snf "/usr/share/zoneinfo/${TZ}" /etc/localtime; \
    echo "${TZ}" > /etc/timezone

COPY --from=builder /opt/venv /opt/venv
COPY --from=ui /ui/dist /opt/embykeeper-panel/static
COPY deploy/panel/entrypoint.sh /entrypoint.sh
COPY deploy/legacy/entrypoint.sh /legacy-entrypoint.sh

RUN chmod +x /entrypoint.sh /legacy-entrypoint.sh \
    && mkdir -p /app \
    && touch /app/.keep

WORKDIR /app
VOLUME ["/app"]

# 8000 = 面板 (界面与 API); 被托管的业务后端仅监听容器内 127.0.0.1:8001, 无需暴露
EXPOSE 8000 1818

ENTRYPOINT ["/entrypoint.sh"]
CMD ["web"]

FROM runtime AS editable

COPY pyproject.toml README.md LICENSE MANIFEST.in requirements.txt /build/
COPY embykeeper /build/embykeeper
COPY embykeeperapi /build/embykeeperapi
COPY embykeeperweb /build/embykeeperweb
COPY deploy/panel/entrypoint-dev.sh /entrypoint-dev.sh

RUN pip install --no-deps --no-build-isolation -e /build \
    && chmod +x /entrypoint-dev.sh

ENTRYPOINT ["/entrypoint-dev.sh"]
CMD ["web"]

FROM runtime AS release
