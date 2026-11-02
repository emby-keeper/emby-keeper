# 旧版命令行镜像 (仍受支持)
#   - 未设置 EK_WEBPASS: 运行命令行模式 (终端登录, 适合 tmux / systemd)
#   - 设置 EK_WEBPASS:   运行旧版在线控制台 (embykeeperweb, 端口 1818)
#
# 新版图形界面部署 (推荐) 请使用 deploy/panel/Dockerfile:
#   docker build -f deploy/panel/Dockerfile -t embykeeper-panel:latest .
#   参考文档 docs/guide/面板模式部署.md

FROM python:3.8 AS builder

WORKDIR /src
COPY . .

RUN python -m venv /opt/venv \
    && . /opt/venv/bin/activate \
    && pip install --no-cache-dir -U pip setuptools wheel \
    && pip install --no-cache-dir .

FROM python:3.8-slim
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /src/deploy/legacy/entrypoint.sh /entrypoint.sh

ENV TZ="Asia/Shanghai"
ENV EK_IN_DOCKER="1"

WORKDIR /app
RUN chmod +x /entrypoint.sh \
    && touch config.toml
ENV PATH="/opt/venv/bin:$PATH"

ENTRYPOINT ["/entrypoint.sh"]
