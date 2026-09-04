import asyncio

from agent.adk_runtime import ADKRuntime


class AgentManager:
    def __init__(self) -> None:
        self._runtime: ADKRuntime | None = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> ADKRuntime:
        if self._runtime is None:
            async with self._lock:
                if self._runtime is None:
                    self._runtime = ADKRuntime()
                    self._runtime.initialize()
        return self._runtime

    async def get_runtime(self) -> ADKRuntime:
        if self._runtime is None:
            return await self.initialize()
        return self._runtime
