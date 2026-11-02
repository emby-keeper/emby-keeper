import asyncio
import json
import logging
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from .auth import get_current_user
from .events import broadcaster, get_shutdown_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sse", tags=["sse"])


async def event_generator(
    channel: str, request: Request, initial_data: Optional[dict] = None
) -> AsyncGenerator[str, None]:
    queue = await broadcaster.subscribe(channel)
    shutdown_event = get_shutdown_event()

    try:
        # Emit a comment frame immediately so the response headers are flushed
        # through proxies (e.g. Vite dev proxy) instead of hanging until
        # the first real event or heartbeat arrives.
        yield ": connected\n\n"

        if initial_data:
            yield f"event: initial\ndata: {json.dumps(initial_data)}\n\n"

        while True:
            if await request.is_disconnected():
                break

            if shutdown_event and shutdown_event.is_set():
                break

            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)

                if event.get("type") == "_shutdown":
                    break

                event_type = event.get("type", "message")
                event_data = event.get("data", {})

                yield f"event: {event_type}\ndata: {json.dumps(event_data)}\n\n"

            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"

    except asyncio.CancelledError:
        pass
    finally:
        await broadcaster.unsubscribe(channel, queue)


@router.get("/logs")
async def logs_events(request: Request, _user=Depends(get_current_user)):
    return StreamingResponse(
        event_generator("logs", request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/status")
async def status_events(request: Request, _user=Depends(get_current_user)):
    return StreamingResponse(
        event_generator("status", request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{channel}")
async def channel_events(channel: str, request: Request, _user=Depends(get_current_user)):
    return StreamingResponse(
        event_generator(channel, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
