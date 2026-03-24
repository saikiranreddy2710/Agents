"""
Browser Pool — Multiple parallel browser instances with load balancing.

Manages a pool of BrowserInstance objects for parallel task execution.
Agents request a browser from the pool, use it, then release it back.

Features:
  - Configurable pool size (default: 3 instances)
  - Round-robin + least-busy load balancing
  - Automatic restart of crashed instances
  - Session state persistence per instance
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from loguru import logger

from .browser_instance import BrowserInstance
from .page_controller import PageController


class PooledBrowser:
    """A browser instance managed by the pool."""

    def __init__(self, instance_id: str, browser: BrowserInstance):
        self.instance_id = instance_id
        self.browser = browser
        self.is_busy = False
        self.task_count = 0
        self.error_count = 0
        self.current_task: Optional[str] = None

    @property
    def is_healthy(self) -> bool:
        return self.browser.is_running and self.error_count < 5


class BrowserPool:
    """
    Pool of browser instances for parallel task execution.

    Usage:
        pool = BrowserPool(size=3)
        await pool.start()

        async with pool.acquire() as (browser, page_controller):
            await page_controller.navigate("https://linkedin.com")
            # ... do work ...

        await pool.stop()
    """

    def __init__(
        self,
        size: int = 3,
        headless: bool = True,
        browser_type: str = "chromium",
        storage_state_dir: Optional[str] = None,
        slow_mo: int = 0,
    ):
        self.size = size
        self.headless = headless
        self.browser_type = browser_type
        self.storage_state_dir = storage_state_dir
        self.slow_mo = slow_mo

        self._pool: List[PooledBrowser] = []
        self._lock = asyncio.Lock()
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._started = False

    async def start(self) -> bool:
        """Launch all browser instances in the pool."""
        self._semaphore = asyncio.Semaphore(self.size)
        success_count = 0

        for i in range(self.size):
            instance_id = f"browser_{i}"
            storage_path = None
            if self.storage_state_dir:
                import os
                storage_path = os.path.join(self.storage_state_dir, f"session_{i}.json")

            browser = BrowserInstance(
                headless=self.headless,
                browser_type=self.browser_type,
                storage_state_path=storage_path,
                slow_mo=self.slow_mo,
                instance_id=instance_id,
            )

            if await browser.start():
                self._pool.append(PooledBrowser(instance_id, browser))
                success_count += 1
                logger.info(f"Pool: started {instance_id}")
            else:
                logger.error(f"Pool: failed to start {instance_id}")

        self._started = success_count > 0
        logger.info(f"BrowserPool started: {success_count}/{self.size} instances ready")
        return self._started

    async def stop(self) -> None:
        """Stop all browser instances."""
        for pooled in self._pool:
            try:
                await pooled.browser.stop()
            except Exception as e:
                logger.error(f"Error stopping {pooled.instance_id}: {e}")
        self._pool.clear()
        self._started = False
        logger.info("BrowserPool stopped")

    def acquire(self) -> "_BrowserContextManager":
        """
        Acquire a browser from the pool.

        Usage:
            async with pool.acquire() as (browser_instance, page_controller):
                await page_controller.navigate("https://example.com")
        """
        return _BrowserContextManager(self)

    async def _get_available(self) -> Optional[PooledBrowser]:
        """Get the least-busy available browser instance."""
        async with self._lock:
            # Filter healthy, non-busy instances
            available = [p for p in self._pool if not p.is_busy and p.is_healthy]

            if not available:
                # All busy — wait and retry
                return None

            # Pick least-busy (fewest total tasks)
            return min(available, key=lambda p: p.task_count)

    async def _release(self, pooled: PooledBrowser) -> None:
        """Release a browser back to the pool."""
        async with self._lock:
            pooled.is_busy = False
            pooled.current_task = None

    async def _restart_instance(self, pooled: PooledBrowser) -> bool:
        """Restart a crashed browser instance."""
        logger.warning(f"Restarting crashed instance: {pooled.instance_id}")
        try:
            await pooled.browser.stop()
        except Exception:
            pass

        new_browser = BrowserInstance(
            headless=self.headless,
            browser_type=self.browser_type,
            storage_state_path=pooled.browser.storage_state_path,
            slow_mo=self.slow_mo,
            instance_id=pooled.instance_id,
        )

        if await new_browser.start():
            pooled.browser = new_browser
            pooled.error_count = 0
            pooled.is_busy = False
            logger.info(f"Restarted: {pooled.instance_id}")
            return True

        logger.error(f"Failed to restart: {pooled.instance_id}")
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        return {
            "total": len(self._pool),
            "busy": sum(1 for p in self._pool if p.is_busy),
            "available": sum(1 for p in self._pool if not p.is_busy and p.is_healthy),
            "unhealthy": sum(1 for p in self._pool if not p.is_healthy),
            "instances": [
                {
                    "id": p.instance_id,
                    "busy": p.is_busy,
                    "healthy": p.is_healthy,
                    "task_count": p.task_count,
                    "error_count": p.error_count,
                    "current_task": p.current_task,
                }
                for p in self._pool
            ],
        }

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.stop()


class _BrowserContextManager:
    """Context manager for acquiring/releasing a browser from the pool."""

    def __init__(self, pool: BrowserPool):
        self._pool = pool
        self._pooled: Optional[PooledBrowser] = None
        self._page = None

    async def __aenter__(self):
        # Wait for an available browser (with timeout)
        for attempt in range(30):  # 30 * 1s = 30s max wait
            self._pooled = await self._pool._get_available()
            if self._pooled:
                break
            await asyncio.sleep(1.0)

        if not self._pooled:
            raise RuntimeError("No browser available in pool after 30s timeout")

        self._pooled.is_busy = True
        self._pooled.task_count += 1

        # Create a new page for this task
        try:
            self._page = await self._pooled.browser.new_page()
        except Exception as e:
            # Try to restart the instance
            await self._pool._restart_instance(self._pooled)
            self._page = await self._pooled.browser.new_page()

        pc = PageController(self._page, session_id=self._pooled.instance_id)
        return self._pooled.browser, pc

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            if self._pooled:
                self._pooled.error_count += 1

        # Close the page
        if self._page:
            try:
                await self._page.close()
            except Exception:
                pass

        # Release back to pool
        if self._pooled:
            await self._pool._release(self._pooled)

        return False  # Don't suppress exceptions
