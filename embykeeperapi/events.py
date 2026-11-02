import asyncio
import logging
from typing import Optional
from typing import Dict, Set
from collections import defaultdict

logger = logging.getLogger(__name__)

_shutdown_event: asyncio.Event = None
_broadcast_loop: Optional[asyncio.AbstractEventLoop] = None


def get_shutdown_event() -> asyncio.Event:
    global _shutdown_event
    if _shutdown_event is None:
        _shutdown_event = asyncio.Event()
    return _shutdown_event


def reset_shutdown_event():
    global _shutdown_event
    _shutdown_event = asyncio.Event()


async def signal_shutdown_async():
    global _shutdown_event
    if _shutdown_event is not None:
        _shutdown_event.set()
        await broadcaster.broadcast_shutdown()
        logger.debug("SSE shutdown signal sent")


def signal_shutdown():
    global _shutdown_event
    if _shutdown_event is not None:
        _shutdown_event.set()
        if _broadcast_loop and _broadcast_loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(
                    broadcaster.broadcast_shutdown(),
                    _broadcast_loop,
                )
            except Exception:
                logger.debug("Failed to schedule SSE shutdown broadcast", exc_info=True)
        logger.debug("SSE shutdown signal sent")


def register_broadcast_loop(loop: asyncio.AbstractEventLoop):
    global _broadcast_loop
    _broadcast_loop = loop


class EventBroadcaster:

    def __init__(self):
        self.subscribers: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, channel: str) -> asyncio.Queue:
        queue = asyncio.Queue()
        async with self._lock:
            self.subscribers[channel].add(queue)
        logger.debug(f"Client subscribed to channel {channel}")
        return queue

    async def unsubscribe(self, channel: str, queue: asyncio.Queue):
        async with self._lock:
            if channel in self.subscribers:
                self.subscribers[channel].discard(queue)
                if not self.subscribers[channel]:
                    del self.subscribers[channel]
        logger.debug(f"Client unsubscribed from channel {channel}")

    async def broadcast(self, channel: str, event_type: str, data: dict):
        async with self._lock:
            queues = list(self.subscribers.get(channel, []))

        dead_queues = []
        for queue in queues:
            try:
                await asyncio.wait_for(queue.put({"type": event_type, "data": data}), timeout=1.0)
            except Exception as e:
                logger.warning(f"Failed to send event to subscriber: {e}")
                dead_queues.append(queue)

        if dead_queues:
            async with self._lock:
                for queue in dead_queues:
                    self.subscribers[channel].discard(queue)

    async def broadcast_all(self, event_type: str, data: dict):
        async with self._lock:
            all_queues = []
            for queues in self.subscribers.values():
                all_queues.extend(queues)

        for queue in all_queues:
            try:
                await asyncio.wait_for(queue.put({"type": event_type, "data": data}), timeout=1.0)
            except Exception:
                pass

    def subscriber_count(self, channel: str) -> int:
        return len(self.subscribers.get(channel, set()))

    async def broadcast_shutdown(self):
        async with self._lock:
            all_queues = []
            for queues in self.subscribers.values():
                all_queues.extend(queues)

        for queue in all_queues:
            try:
                queue.put_nowait({"type": "_shutdown", "data": {}})
            except Exception:
                pass


broadcaster = EventBroadcaster()


def broadcast_from_sync(channel: str, event_type: str, data: dict):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.create_task(broadcaster.broadcast(channel, event_type, data))
        return

    if _broadcast_loop and _broadcast_loop.is_running():
        asyncio.run_coroutine_threadsafe(
            broadcaster.broadcast(channel, event_type, data),
            _broadcast_loop,
        )
