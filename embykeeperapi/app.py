import os
import errno
import socket
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
import signal
import time
from pathlib import Path
from types import FrameType
from typing import Callable, List, Optional

import typer
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from uvicorn import Config, Server
from uvicorn.supervisors import ChangeReload

from . import __version__

from .auth import require_auth, router as auth_router, validate_webpass
from .pm import router as pm_router, pm
from .proxy import router as proxy_router
from .sse import router as sse_router
from .kv_router import router as kv_router
from .settings_router import router as settings_router
from .state_store import check_mongodb
from .events import register_broadcast_loop, reset_shutdown_event, signal_shutdown, signal_shutdown_async

cli = typer.Typer(help="Embykeeper Panel API server")
STARTED_AT = datetime.now(timezone.utc)
logger = logging.getLogger("uvicorn.error")
TARGET_HOST_ENV = "EMBYKEEPERAPI_TARGET_HOST"
TARGET_PORT_ENV = "EMBYKEEPERAPI_TARGET_PORT"
STATIC_DIR_ENV = "EMBYKEEPERAPI_STATIC_DIR"
BACKEND_SHUTDOWN_LOG_GRACE_SECONDS = 0.5


def _resolve_static_dir() -> Optional[Path]:
    """定位已构建的面板界面, 未随部署提供界面时返回 None (仅提供 API)."""
    candidates: List[Path] = []

    env_value = os.environ.get(STATIC_DIR_ENV, "").strip()
    if env_value:
        candidates.append(Path(env_value).expanduser())

    package_root = Path(__file__).resolve().parent
    candidates.append(package_root / "static")
    candidates.append(package_root.parent / "frontend" / "dist")
    candidates.append(Path("/opt/embykeeper-panel/static"))

    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate.resolve()

    return None


class PanelUIStaticFiles(StaticFiles):
    """面板界面静态资源, 未知路径回落 index.html 以支持前端路由."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or path.startswith("api/"):
                raise
            return await super().get_response("index.html", scope)


def _ensure_bind_available(host: str, port: int) -> None:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError as exc:
            if exc.errno == errno.EADDRINUSE:
                logger.error("Address already in use: %s:%s", host, port)
            else:
                logger.error("Unable to bind %s:%s: %s", host, port, exc)
            raise typer.Exit(1) from exc


def _configure_pm_target_from_env() -> None:
    target_host = os.environ.get(TARGET_HOST_ENV)
    target_port = os.environ.get(TARGET_PORT_ENV)

    if target_host:
        pm.host = target_host

    if target_port:
        try:
            pm.port = int(target_port)
        except ValueError:
            logger.warning("Ignoring invalid %s value: %s", TARGET_PORT_ENV, target_port)


_configure_pm_target_from_env()


class PanelServer(Server):
    def __init__(self, config: Config, managed_backend: bool = False):
        super().__init__(config=config)
        self.managed_backend = managed_backend

    def handle_exit(self, sig: int, frame) -> None:
        signal_shutdown()
        super().handle_exit(sig, frame)

    async def shutdown(self, sockets=None) -> None:
        await super().shutdown(sockets)
        if self.managed_backend:
            await self._shutdown_managed_backend()

    async def _shutdown_managed_backend(self) -> None:
        import asyncio

        pid = pm.managed_pid()
        if not pid:
            return

        pm.request_stop(pid)

        if self.force_exit:
            logger.warning("Force stopping managed Embykeeper backend")
            pm.force_stop(pid)
            return

        announced_wait = False
        started_waiting_at = time.monotonic()
        while pm.is_managed_pid_running(pid):
            if self.force_exit:
                logger.warning("Force stopping managed Embykeeper backend")
                pm.force_stop(pid)
                return

            if (not announced_wait) and (
                time.monotonic() - started_waiting_at >= BACKEND_SHUTDOWN_LOG_GRACE_SECONDS
            ):
                logger.info(
                    "Waiting for managed Embykeeper backend to stop. Press Ctrl+C again to force quit."
                )
                announced_wait = True

            await asyncio.sleep(0.2)


class PanelReload(ChangeReload):
    def __init__(
        self,
        config: Config,
        target: Callable[[Optional[list]], None],
        sockets: list,
        managed_backend: bool = False,
    ):
        super().__init__(config=config, target=target, sockets=sockets)
        self.managed_backend = managed_backend
        self.force_exit = False

    def signal_handler(self, sig: int, frame: Optional[FrameType]) -> None:
        if self.should_exit.is_set() and sig == signal.SIGINT:
            self.force_exit = True
        super().signal_handler(sig, frame)

    def shutdown(self) -> None:
        super().shutdown()
        if self.managed_backend:
            self._shutdown_managed_backend()

    def _shutdown_managed_backend(self) -> None:
        pid = pm.managed_pid()
        if not pid:
            return

        pm.request_stop(pid)
        if self.force_exit:
            logger.warning("Force stopping managed Embykeeper backend")
            pm.force_stop(pid)
            return

        announced_wait = False
        started_waiting_at = time.monotonic()
        while pm.is_managed_pid_running(pid):
            if self.force_exit:
                logger.warning("Force stopping managed Embykeeper backend")
                pm.force_stop(pid)
                return

            if (not announced_wait) and (
                time.monotonic() - started_waiting_at >= BACKEND_SHUTDOWN_LOG_GRACE_SECONDS
            ):
                logger.info(
                    "Waiting for managed Embykeeper backend to stop. Press Ctrl+C again to force quit."
                )
                announced_wait = True

            time.sleep(0.2)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import asyncio
    import sys

    validate_webpass()
    loop = asyncio.get_running_loop()

    # Suppress noisy ConnectionResetError on Windows when SSE/proxy clients disconnect.
    # The ProactorEventLoop calls socket.shutdown() on an already-closed transport,
    # which raises [WinError 10054]. This is harmless and expected.
    if sys.platform == "win32":
        _original_handler = loop.get_exception_handler()

        def _suppress_connection_reset(loop, context):
            exc = context.get("exception")
            if isinstance(exc, ConnectionResetError):
                return
            if _original_handler:
                _original_handler(loop, context)
            else:
                loop.default_exception_handler(context)

        loop.set_exception_handler(_suppress_connection_reset)

    reset_shutdown_event()
    register_broadcast_loop(loop)

    try:
        yield
    finally:
        await signal_shutdown_async()


def build_app(allow_origins: List[str] = None) -> FastAPI:
    app = FastAPI(title="Embykeeper Panel API", version=__version__, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins
        or [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Panel endpoints under /api
    app.include_router(auth_router, prefix="/api")
    app.include_router(pm_router, prefix="/api")
    app.include_router(sse_router, prefix="/api")
    app.include_router(kv_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")

    @app.get("/api/panel/health")
    async def panel_health(_: bool = Depends(require_auth)):
        return {
            "name": "embykeeper-panel",
            "version": __version__,
            "pid": os.getpid(),
            "started_at": STARTED_AT.isoformat(),
            "backend": pm.status(),
        }

    @app.get("/healthz")
    async def healthz():
        # Platform health checks (Koyeb / Render) hit this without credentials.
        return {"status": "ok"}

    # Finally mount proxy that forwards /api/* to backend
    app.include_router(proxy_router)

    static_dir = _resolve_static_dir()
    if static_dir is not None:
        # 服务端已带界面 (镜像或源码构建) 时, 同源提供界面与 API
        logger.info("Serving panel UI from %s", static_dir)
        app.mount("/", PanelUIStaticFiles(directory=str(static_dir), html=True), name="panel-ui")
    else:

        @app.get("/")
        async def root():
            return {
                "message": "Embykeeper Panel API",
                "version": __version__,
            }

    return app


app = build_app()


def _run_server(
    host: str = typer.Option("0.0.0.0", help="Bind host"),
    port: int = typer.Option(8000, help="Bind port"),
    target_host: str = typer.Option("127.0.0.1", help="Backend host (embykeeper --api)"),
    target_port: int = typer.Option(8001, help="Backend port (embykeeper --api)"),
    autostart: bool = typer.Option(True, help="Auto start backend on launch"),
    reload: bool = typer.Option(False, help="Auto-reload on code changes"),
    debug: bool = typer.Option(False, help="Enable uvicorn access log"),
    cors: List[str] = typer.Option([], help="Add extra CORS origins, repeatable"),
    server_callback: Optional[Callable[[PanelServer], None]] = None,
):
    """Start panel server via uvicorn and optionally manage backend."""
    try:
        validate_webpass()
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    try:
        check_mongodb()
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    _ensure_bind_available(host, port)

    pm.host = target_host
    pm.port = target_port
    os.environ[TARGET_HOST_ENV] = target_host
    os.environ[TARGET_PORT_ENV] = str(target_port)
    owned_backend = False
    if autostart:
        pm.start()
        owned_backend = pm.owns_backend()

    _ = cors  # reserved for future dynamic CORS configuration

    config = Config(
        "embykeeperapi.app:app",
        host=host,
        port=port,
        loop="auto",
        lifespan="auto",
        reload=reload,
        access_log=debug,
        factory=False,
    )

    server = PanelServer(config=config, managed_backend=owned_backend)
    if server_callback is not None:
        server_callback(server)

    if config.should_reload:
        sock = config.bind_socket()
        PanelReload(
            config=config,
            target=server.run,
            sockets=[sock],
            managed_backend=owned_backend,
        ).run()
    else:
        server.run()


@cli.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    host: str = typer.Option("0.0.0.0", help="Bind host"),
    port: int = typer.Option(8000, help="Bind port"),
    target_host: str = typer.Option("127.0.0.1", help="Backend host (embykeeper --api)"),
    target_port: int = typer.Option(8001, help="Backend port (embykeeper --api)"),
    autostart: bool = typer.Option(True, help="Auto start backend on launch"),
    debug: bool = typer.Option(False, help="Enable uvicorn access log"),
    cors: List[str] = typer.Option([], help="Add extra CORS origins, repeatable"),
):
    if ctx.invoked_subcommand is None:
        _run_server(
            host=host,
            port=port,
            target_host=target_host,
            target_port=target_port,
            autostart=autostart,
            reload=False,
            debug=debug,
            cors=cors,
        )


@cli.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind host"),
    port: int = typer.Option(8000, help="Bind port"),
    target_host: str = typer.Option("127.0.0.1", help="Backend host (embykeeper --api)"),
    target_port: int = typer.Option(8001, help="Backend port (embykeeper --api)"),
    autostart: bool = typer.Option(True, help="Auto start backend on launch"),
    debug: bool = typer.Option(False, help="Enable uvicorn access log"),
    cors: List[str] = typer.Option([], help="Add extra CORS origins, repeatable"),
):
    _run_server(
        host=host,
        port=port,
        target_host=target_host,
        target_port=target_port,
        autostart=autostart,
        reload=False,
        debug=debug,
        cors=cors,
    )


@cli.command()
def dev(
    host: str = typer.Option("127.0.0.1", help="Bind host"),
    port: int = typer.Option(8000, help="Bind port"),
    target_host: str = typer.Option("127.0.0.1", help="Backend host (embykeeper --api)"),
    target_port: int = typer.Option(8001, help="Backend port (embykeeper --api)"),
    autostart: bool = typer.Option(True, help="Auto start backend on launch"),
    debug: bool = typer.Option(True, help="Enable uvicorn access log"),
    cors: List[str] = typer.Option([], help="Add extra CORS origins, repeatable"),
):
    _run_server(
        host=host,
        port=port,
        target_host=target_host,
        target_port=target_port,
        autostart=autostart,
        reload=True,
        debug=debug,
        cors=cors,
    )


if __name__ == "__main__":
    cli()
