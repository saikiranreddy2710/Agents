"""Click tool — Click an element by selector, text, or coordinates."""
from __future__ import annotations
import time
from typing import Any, Dict, Optional


async def click(
    page,
    selector: Optional[str] = None,
    text: Optional[str] = None,
    x: Optional[int] = None,
    y: Optional[int] = None,
    button: str = "left",
    click_count: int = 1,
    delay: int = 50,
    timeout: int = 10000,
    force: bool = False,
    scroll_into_view: bool = True,
) -> Dict[str, Any]:
    """
    Click an element on the page.

    Priority: selector > text > (x, y) coordinates

    Args:
        page:             Playwright page object
        selector:         CSS selector or XPath (e.g., ".connect-button", "//button[@aria-label='Connect']")
        text:             Click element containing this text (uses page.get_by_text)
        x, y:             Click at specific coordinates (fallback)
        button:           "left" | "right" | "middle"
        click_count:      Number of clicks (2 for double-click)
        delay:            Delay between mousedown and mouseup in ms (human-like)
        timeout:          Timeout waiting for element in ms
        force:            Force click even if element is not visible
        scroll_into_view: Scroll element into view before clicking

    Returns:
        {"success": bool, "method": str, "selector": str, "error": str|None}
    """
    start = time.time()
    method_used = ""

    try:
        click_opts: Dict[str, Any] = {
            "button": button,
            "click_count": click_count,
            "delay": delay,
            "force": force,
            "timeout": timeout,
        }

        if selector:
            method_used = f"selector:{selector}"
            element = page.locator(selector).first
            if scroll_into_view:
                await element.scroll_into_view_if_needed(timeout=timeout)
            await element.click(**click_opts)

        elif text:
            method_used = f"text:{text}"
            element = page.get_by_text(text, exact=False).first
            if scroll_into_view:
                await element.scroll_into_view_if_needed(timeout=timeout)
            await element.click(**click_opts)

        elif x is not None and y is not None:
            method_used = f"coords:({x},{y})"
            await page.mouse.click(x, y, button=button, click_count=click_count, delay=delay)

        else:
            return {
                "success": False,
                "method": "",
                "selector": "",
                "duration_ms": 0,
                "error": "Must provide selector, text, or (x, y) coordinates",
            }

        return {
            "success": True,
            "method": method_used,
            "selector": selector or text or f"({x},{y})",
            "duration_ms": int((time.time() - start) * 1000),
            "error": None,
        }

    except Exception as e:
        error_msg = str(e)

        # Try fallback: if selector failed, try JavaScript click
        if selector and "timeout" not in error_msg.lower():
            try:
                await page.evaluate(
                    f"document.querySelector('{selector}')?.click()"
                )
                return {
                    "success": True,
                    "method": f"js_fallback:{selector}",
                    "selector": selector,
                    "duration_ms": int((time.time() - start) * 1000),
                    "error": None,
                    "note": "Used JavaScript click fallback",
                }
            except Exception:
                pass

        return {
            "success": False,
            "method": method_used,
            "selector": selector or text or f"({x},{y})" if x else "",
            "duration_ms": int((time.time() - start) * 1000),
            "error": error_msg,
        }
