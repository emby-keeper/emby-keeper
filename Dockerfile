FROM python:3.8-slim AS builder

VOLUME ["/root/.local/share/embykeeper"]

RUN mkdir /src
COPY . /src
RUN python -m venv /opt/venv
RUN . /opt/venv/bin/activate \
    && pip install --no-cache-dir -U pip setuptools wheel \
    && cd /src \
    && touch config.toml \
    && pip install --no-cache-dir .

FROM python:3.8-slim

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

ENTRYPOINT ["embykeeper"]
CMD ["config.toml"]
