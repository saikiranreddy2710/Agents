"""
Page Controller — High-level page actions combining multiple browser tools.

Provides semantic, task-oriented methods built on top of the 8 atomic tools.
This is what agents use directly — they don't call tools individually.

Examples:
    pc = PageController(page)
    await pc.navigate("https://linkedin.com")
    screenshot = await pc.get_screenshot()
    await pc.click_button("Connect")
    await pc.fill_input("#email", "user@example.com")
    text = await pc.get_text(".profile-name")
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any, Dict, List, Optional

from loguru import logger

from .tools import navigate, screenshot, click, type_text, scroll, dom, evaluate, wait


class PageController:
    """
    High-level page controller for agent interactions.

    Wraps the 8 atomic tools with semantic methods and
    adds error handling, retries, and logging.
    """

    def __init__(self, page, session_id: str = "default"):
        self.page = page
        self.session_id = session_id
        self._action_count = 0

    # ── Navigation ────────────────────────────────────────────────────────────

    async def navigate(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        timeout: int = 30000,
    ) -> Dict[str, Any]:
        """Navigate to a URL."""
        self._action_count += 1
        result = await navigate(self.page, url=url, wait_until=wait_until, timeout=timeout)
        if result["success"]:
            logger.debug(f"[{self.session_id}] Navigated to: {result['url']}")
        else:
            logger.warning(f"[{self.session_id}] Navigation failed: {result['error']}")
        return result

    async def go_back(self) -> Dict[str, Any]:
        """Navigate back in browser history."""
        try:
            await self.page.go_back(wait_until="domcontentloaded")
            return {"success": True, "url": self.page.url, "error": None}
        except Exception as e:
            return {"success": False, "url": self.page.url, "error": str(e)}

    async def reload(self) -> Dict[str, Any]:
        """Reload the current page."""
        try:
            await self.page.reload(wait_until="domcontentloaded")
            return {"success": True, "url": self.page.url, "error": None}
        except Exception as e:
            return {"success": False, "url": self.page.url, "error": str(e)}

    # ── Screenshots ───────────────────────────────────────────────────────────

    async def get_screenshot(
        self,
        save_path: Optional[str] = None,
        full_page: bool = False,
    ) -> Dict[str, Any]:
        """Capture a screenshot and return base64 + metadata."""
        result = await screenshot(self.page, save_path=save_path, full_page=full_page)
        return result

    async def get_screenshot_base64(self) -> str:
        """Get screenshot as base64 string (for LLM vision)."""
        result = await screenshot(self.page)
        return result.get("base64", "")

    # ── Clicking ──────────────────────────────────────────────────────────────

    async def click_selector(
        self,
        selector: str,
        timeout: int = 10000,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Click an element by CSS selector."""
        self._action_count += 1
        result = await click(self.page, selector=selector, timeout=timeout, force=force)
        if not result["success"]:
            logger.warning(f"[{self.session_id}] Click failed on '{selector}': {result['error']}")
        return result

    async def click_button(
        self,
        text: str,
        timeout: int = 10000,
    ) -> Dict[str, Any]:
        """Click a button by its text content."""
        self._action_count += 1
        result = await click(self.page, text=text, timeout=timeout)
        if not result["success"]:
            logger.warning(f"[{self.session_id}] Click button '{text}' failed: {result['error']}")
        return result

    async def click_coords(self, x: int, y: int) -> Dict[str, Any]:
        """Click at specific coordinates."""
        self._action_count += 1
        return await click(self.page, x=x, y=y)

    # ── Typing ────────────────────────────────────────────────────────────────

    async def fill_input(
        self,
        selector: str,
        text: str,
        clear_first: bool = True,
        press_enter: bool = False,
        human_like: bool = True,
    ) -> Dict[str, Any]:
        """Fill an input field with text."""
        self._action_count += 1
        result = await type_text(
            self.page,
            selector=selector,
            text=text,
            clear_first=clear_first,
            press_enter=press_enter,
            delay=80 if human_like else 0,
        )
        if not result["success"]:
            logger.warning(f"[{self.session_id}] Fill input '{selector}' failed: {result['error']}")
        return result

    # ── Scrolling ─────────────────────────────────────────────────────────────

    async def scroll_down(self, amount: int = 500, times: int = 1) -> Dict[str, Any]:
        """Scroll down the page."""
        return await scroll(self.page, direction="down", amount=amount, times=times)

    async def scroll_up(self, amount: int = 500) -> Dict[str, Any]:
        """Scroll up the page."""
        return await scroll(self.page, direction="up", amount=amount)

    async def scroll_to_element(self, selector: str) -> Dict[str, Any]:
        """Scroll to a specific element."""
        return await scroll(self.page, direction="to_element", selector=selector)

    async def scroll_to_bottom(self) -> Dict[str, Any]:
        """Scroll to the bottom of the page."""
        return await scroll(self.page, direction="to_bottom")

    async def scroll_to_top(self) -> Dict[str, Any]:
        """Scroll to the top of the page."""
        return await scroll(self.page, direction="to_top")

    # ── DOM Extraction ────────────────────────────────────────────────────────

    async def get_text(self, selector: Optional[str] = None) -> str:
        """Get text content of an element or the full page."""
        result = await dom(self.page, action="text", selector=selector)
        return result.get("data", "") if result["success"] else ""

    async def get_html(self, selector: Optional[str] = None) -> str:
        """Get HTML content of an element or the full page."""
        result = await dom(self.page, action="html", selector=selector)
        return result.get("data", "") if result["success"] else ""

    async def get_attribute(self, selector: str, attribute: str) -> Optional[str]:
        """Get an attribute value from an element."""
        result = await dom(self.page, action="attribute", selector=selector, attribute=attribute)
        return result.get("data") if result["success"] else None

    async def get_links(self) -> List[Dict[str, str]]:
        """Get all links on the page."""
        result = await dom(self.page, action="links")
        return result.get("data", []) if result["success"] else []

    async def get_buttons(self) -> List[Dict[str, Any]]:
        """Get all visible buttons on the page."""
        result = await dom(self.page, action="buttons")
        return result.get("data", []) if result["success"] else []

    async def get_inputs(self) -> List[Dict[str, Any]]:
        """Get all input fields on the page."""
        result = await dom(self.page, action="inputs")
        return result.get("data", []) if result["success"] else []

    async def get_page_structure(self) -> Dict[str, Any]:
        """Get a simplified DOM structure summary."""
        result = await dom(self.page, action="structure")
        return result if result["success"] else {}

    async def element_exists(self, selector: str) -> bool:
        """Check if an element exists on the page."""
        result = await dom(self.page, action="exists", selector=selector)
        return result.get("data", False) if result["success"] else False

    async def count_elements(self, selector: str) -> int:
        """Count elements matching a selector."""
        result = await dom(self.page, action="count", selector=selector)
        return result.get("data", 0) if result["success"] else 0

    # ── JavaScript ────────────────────────────────────────────────────────────

    async def run_js(self, script: str, arg: Optional[Any] = None) -> Any:
        """Execute JavaScript and return the result."""
        result = await evaluate(self.page, script=script, arg=arg)
        return result.get("result") if result["success"] else None

    # ── Waiting ───────────────────────────────────────────────────────────────

    async def wait_for_element(
        self,
        selector: str,
        state: str = "visible",
        timeout: int = 30000,
    ) -> bool:
        """Wait for an element to reach a specific state."""
        result = await wait(
            self.page, condition="element", selector=selector,
            state=state, timeout=timeout,
        )
        return result["success"]

    async def wait_for_navigation(self, timeout: int = 30000) -> bool:
        """Wait for page navigation to complete."""
        result = await wait(self.page, condition="navigation", timeout=timeout)
        return result["success"]

    async def wait_for_load(self, timeout: int = 30000) -> bool:
        """Wait for page load event."""
        result = await wait(self.page, condition="load", timeout=timeout)
        return result["success"]

    async def wait_for_network_idle(self, timeout: int = 30000) -> bool:
        """Wait for network to be idle."""
        result = await wait(self.page, condition="network", timeout=timeout)
        return result["success"]

    async def sleep(self, seconds: float) -> None:
        """Wait for a fixed duration."""
        await asyncio.sleep(seconds)

    # ── Page Info ─────────────────────────────────────────────────────────────

    @property
    def url(self) -> str:
        """Current page URL."""
        return self.page.url

    async def get_title(self) -> str:
        """Get the current page title."""
        try:
            return await self.page.title()
        except Exception:
            return ""

    async def get_page_info(self) -> Dict[str, Any]:
        """Get current page URL, title, and scroll position."""
        title = await self.get_title()
        scroll_pos = await self.run_js(
            "() => ({x: window.scrollX, y: window.scrollY, "
            "maxY: document.body.scrollHeight - window.innerHeight})"
        ) or {}
        return {
            "url": self.url,
            "title": title,
            "scroll_x": scroll_pos.get("x", 0),
            "scroll_y": scroll_pos.get("y", 0),
            "max_scroll_y": scroll_pos.get("maxY", 0),
            "action_count": self._action_count,
        }

    # ── Composite Actions ─────────────────────────────────────────────────────

    async def click_and_wait(
        self,
        selector: str,
        wait_condition: str = "navigation",
        timeout: int = 15000,
    ) -> Dict[str, Any]:
        """Click an element and wait for navigation/network."""
        click_result = await self.click_selector(selector, timeout=timeout)
        if not click_result["success"]:
            return click_result
        await asyncio.sleep(0.5)
        if wait_condition == "navigation":
            await self.wait_for_navigation(timeout=timeout)
        elif wait_condition == "network":
            await self.wait_for_network_idle(timeout=timeout)
        return click_result

    async def type_and_search(
        self,
        selector: str,
        text: str,
        submit_selector: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Type text and submit (press Enter or click submit button)."""
        type_result = await self.fill_input(selector, text)
        if not type_result["success"]:
            return type_result
        await asyncio.sleep(0.3)
        if submit_selector:
            return await self.click_selector(submit_selector)
        else:
            await self.page.keyboard.press("Enter")
            await self.wait_for_navigation()
            return {"success": True, "method": "enter_key", "error": None}
