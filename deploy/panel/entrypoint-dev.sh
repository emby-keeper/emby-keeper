#!/bin/bash

set -e

if [ ! -d /src ]; then
    echo ">> 请挂载源码目录到 /src。" >&2
    exit 1
fi

if [ -z "$(ls -A /src)" ]; then
    cp -a /build/. /src/
fi

pip install --no-deps --no-build-isolation -e /src
exec /entrypoint.sh "$@"