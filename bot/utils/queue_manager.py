import asyncio
import itertools
import logging
from typing import Awaitable, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

MAX_CONCURRENT = 5
GENERATION_TIMEOUT = 120
AVG_GENERATION_SECONDS = 60

T = TypeVar("T")


class GenerationQueue:
    """
    Priority-aware generation queue backed by asyncio.PriorityQueue.

    Paid orders (is_trial=False) get priority 0 and are dispatched before
    trial orders (priority 1). Within the same priority level, FIFO order
    is preserved via a monotonic sequence counter.

    Up to MAX_CONCURRENT jobs run simultaneously; the rest wait in the heap.
    """

    def __init__(self, max_concurrent: int = MAX_CONCURRENT) -> None:
        self._max = max_concurrent
        self._pq: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._counter = itertools.count()
        self._total = 0    # queued + running
        self._active = 0   # running
        self._workers: list[asyncio.Task] = []

    # Workers are started lazily on first submit so the event loop is ready.
    def _start_workers(self) -> None:
        if not self._workers:
            for _ in range(self._max):
                self._workers.append(asyncio.create_task(self._worker()))

    async def _worker(self) -> None:
        while True:
            priority, seq, fut, coro = await self._pq.get()
            self._active += 1
            try:
                result = await asyncio.wait_for(coro, timeout=GENERATION_TIMEOUT)
                if not fut.done():
                    fut.set_result(result)
            except asyncio.TimeoutError as exc:
                logger.error("Generation timed out after %ss", GENERATION_TIMEOUT)
                if not fut.done():
                    fut.set_exception(exc)
            except Exception as exc:
                logger.exception("Generation worker error: %s", exc)
                if not fut.done():
                    fut.set_exception(exc)
            finally:
                self._active -= 1
                self._total -= 1

    @property
    def is_full(self) -> bool:
        return self._total >= self._max

    @property
    def waiting_count(self) -> int:
        return max(0, self._total - self._max)

    def estimate_wait_minutes(self) -> int:
        if not self.is_full:
            return 0
        batches = (self._total - self._max) // self._max + 1
        return max(1, batches * (AVG_GENERATION_SECONDS // 60))

    async def submit(
        self,
        coro: Awaitable[T],
        is_trial: bool = False,
        is_vip: bool = False,
        on_queued: Optional[Callable[[int], Awaitable[None]]] = None,
    ) -> T:
        """
        Schedule *coro* for execution with the given priority.
        VIP (0) > paid (1) > trial (2) in the min-heap.
        Raises asyncio.TimeoutError if execution exceeds GENERATION_TIMEOUT.
        """
        self._start_workers()

        if self.is_full and on_queued is not None:
            await on_queued(self.estimate_wait_minutes())

        # Lower value = higher priority in PriorityQueue (min-heap).
        if is_vip:
            priority = 0
        elif not is_trial:
            priority = 1
        else:
            priority = 2
        seq = next(self._counter)

        fut: asyncio.Future[T] = asyncio.get_running_loop().create_future()
        self._total += 1
        await self._pq.put((priority, seq, fut, coro))

        return await fut


# Global singleton imported by handlers
generation_queue = GenerationQueue()
