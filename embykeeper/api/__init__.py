"""Embykeeper API module."""

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Suppress noisy ConnectionResetError on Windows when SSE clients disconnect.
    if sys.platform == "win32":
        loop = asyncio.get_running_loop()
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

    yield


def create_app(allow_origins: List[str] = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="Embykeeper API", version=__version__, lifespan=_lifespan)

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

    from .config import router as config_router
    from .runinfo import router as runinfo_router
    from .auth import router as auth_router
    from .system import router as system_router
    from .telegram import router as telegram_router
    from .emby import router as emby_router
    from .subsonic import router as subsonic_router
    from .sites import router as sites_router
    from .ops import router as ops_router

    app.include_router(config_router, prefix="/api")
    app.include_router(runinfo_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(system_router, prefix="/api")
    app.include_router(telegram_router, prefix="/api")
    app.include_router(emby_router, prefix="/api")
    app.include_router(subsonic_router, prefix="/api")
    app.include_router(sites_router, prefix="/api")
    app.include_router(ops_router, prefix="/api")

    @app.get("/")
    async def root():
        return {"message": "Embykeeper API", "version": __version__}

    return app
