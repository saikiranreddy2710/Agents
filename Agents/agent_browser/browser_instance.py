"""
Browser Instance — Single Playwright browser instance manager.

Manages the lifecycle of one Playwright browser:
  - Launch with stealth settings
  - Create/manage browser contexts (isolated sessions)
  - Save/restore session state (cookies, localStorage)
  - Clean shutdown
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from loguru import logger


class BrowserInstance:
    """
    Manages a single Playwright browser instance.

    Each instance can have multiple contexts (isolated sessions).
    Use BrowserPool for multiple parallel instances.
    """

    def __init__(
        self,
        headless: bool = True,
        browser_type: str = "chromium",
        storage_state_path: Optional[str] = None,
        proxy: Optional[Dict[str, str]] = None,
        slow_mo: int = 0,
        viewport: Optional[Dict[str, int]] = None,
        user_agent: Optional[str] = None,
        instance_id: str = "default",
    ):
        self.headless = headless
        self.browser_type = browser_type
        self.storage_state_path = storage_state_path
        self.proxy = proxy
        self.slow_mo = slow_mo
        self.viewport = viewport or {"width": 1280, "height": 800}
        self.user_agent = user_agent
        self.instance_id = instance_id

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._is_running = False

    async def start(self) -> bool:
        """Launch the browser and create a context."""
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()

            # Select browser type
            browser_launcher = {
                "chromium": self._playwright.chromium,
                "firefox": self._playwright.firefox,
                "webkit": self._playwright.webkit,
            }.get(self.browser_type, self._playwright.chromium)

            # Launch args for stealth
            launch_args = [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--no-first-run",
                "--no-zygote",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
            ]

            self._browser = await browser_launcher.launch(
                headless=self.headless,
                slow_mo=self.slow_mo,
                args=launch_args if self.browser_type == "chromium" else [],
                proxy=self.proxy,
            )

            # Context options
            context_opts: Dict[str, Any] = {
                "viewport": self.viewport,
                "java_script_enabled": True,
                "accept_downloads": True,
                "ignore_https_errors": True,
            }

            if self.user_agent:
                context_opts["user_agent"] = self.user_agent
            else:
                # Use a realistic user agent
                context_opts["user_agent"] = (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )

            # Load saved session state if available
            if self.storage_state_path and os.path.exists(self.storage_state_path):
                context_opts["storage_state"] = self.storage_state_path
                logger.info(f"[{self.instance_id}] Loaded session state from {self.storage_state_path}")

            self._context = await self._browser.new_context(**context_opts)

            # Inject stealth scripts to avoid bot detection
            await self._inject_stealth_scripts()

            # Create initial page
            self._page = await self._context.new_page()
            self._is_running = True

            logger.info(
                f"[{self.instance_id}] Browser started: {self.browser_type} "
                f"(headless={self.headless})"
            )
            return True

        except Exception as e:
            logger.error(f"[{self.instance_id}] Failed to start browser: {e}")
            return False

    async def stop(self) -> None:
        """Close the browser and clean up."""
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            self._is_running = False
            logger.info(f"[{self.instance_id}] Browser stopped")
        except Exception as e:
            logger.error(f"[{self.instance_id}] Error stopping browser: {e}")

    async def save_session(self, path: Optional[str] = None) -> bool:
        """Save current session state (cookies, localStorage) to file."""
        save_path = path or self.storage_state_path
        if not save_path:
            logger.warning(f"[{self.instance_id}] No storage_state_path configured")
            return False
        try:
            os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)
            await self._context.storage_state(path=save_path)
            logger.info(f"[{self.instance_id}] Session saved to {save_path}")
            return True
        except Exception as e:
            logger.error(f"[{self.instance_id}] Failed to save session: {e}")
            return False

    async def new_page(self):
        """Create a new page in the current context."""
        if not self._context:
            raise RuntimeError("Browser not started. Call start() first.")
        page = await self._context.new_page()
        return page

    async def new_context(self, **kwargs):
        """Create a new isolated browser context."""
        if not self._browser:
            raise RuntimeError("Browser not started. Call start() first.")
        return await self._browser.new_context(**kwargs)

    @property
    def page(self):
        """Get the current active page."""
        return self._page

    @property
    def is_running(self) -> bool:
        return self._is_running

    async def _inject_stealth_scripts(self) -> None:
        """Inject JavaScript to make the browser less detectable."""
        stealth_js = """
        // Remove webdriver flag
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

        // Mock plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });

        // Mock languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });

        // Mock permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );

        // Remove automation indicators
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
        """
        try:
            await self._context.add_init_script(stealth_js)
        except Exception as e:
            logger.debug(f"Stealth script injection failed (non-critical): {e}")

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.stop()
