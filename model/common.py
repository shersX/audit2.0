import asyncio
import heapq
import itertools


class PrioritySemaphore:
    """优先级信号量：空槽优先分配给 priority 数值最小的等待者。

    - 数值越小优先级越高（按提交顺序，PDF1=0, PDF2=1 ...）。
    - 不抢占：运行中的调用不会被打断，卡住的调用只占用它自己那 1 个槽。
    - 不空转：只要有空槽且有等待者，立即分配；优先级只决定“给谁”，不决定“给不给”。
    """

    def __init__(self, value: int):
        self._value = value
        self._waiters: list = []
        self._counter = itertools.count()

    async def acquire(self, priority: int = 0) -> None:
        if self._value > 0:
            self._value -= 1
            return
        fut = asyncio.get_running_loop().create_future()
        # (priority, 入队序号) 作为堆排序键：优先级相同则先到先得
        heapq.heappush(self._waiters, (priority, next(self._counter), fut))
        try:
            await fut
        except asyncio.CancelledError:
            # 已被授予槽位却又被取消，需把槽位转交下一个等待者
            if fut.done() and not fut.cancelled():
                self._release_slot()
            raise

    def release(self) -> None:
        self._release_slot()

    def _release_slot(self) -> None:
        while self._waiters:
            _, _, fut = heapq.heappop(self._waiters)
            if not fut.done():
                fut.set_result(None)
                return
        self._value += 1

    def context(self, priority: int = 0):
        return _PriorityContext(self, priority)


class _PriorityContext:
    def __init__(self, sem: PrioritySemaphore, priority: int):
        self._sem = sem
        self._priority = priority

    async def __aenter__(self):
        await self._sem.acquire(self._priority)
        return self._sem

    async def __aexit__(self, *exc):
        self._sem.release()


api_semaphore = PrioritySemaphore(6)
