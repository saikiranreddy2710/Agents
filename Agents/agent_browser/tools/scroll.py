"""Scroll tool — Scroll the page or to a specific element."""
from __future__ import annotations
import asyncio
import time
from typing import Any, Dict, Optional


async def scroll(
    page,
    direction: str = "down",
    amount: int = 500,
    selector: Optional[str] = None,
    smooth: bool = True,
    times: int = 1,
    delay_between: float = 0.3,
) -> Dict[str, Any]:
    """
    Scroll the page or scroll to a specific element.

    Args:
        page:           Playwright page object
        direction:      "down" | "up" | "left" | "right" | "to_element" | "to_top" | "to_bottom"
        amount:         Pixels to scroll (for directional scrolls)
        selector:       CSS selector to scroll to (when direction="to_element")
        smooth:         Use smooth scrolling behavior
        times:          Number of times to scroll
        delay_between:  Delay between multiple scrolls in seconds

    Returns:
        {"success": bool, "direction": str, "amount": int, "error": str|None}
    """
    start = time.time()
    behavior = "smooth" if smooth else "instant"

    try:
        for i in range(times):
            if direction == "to_element" and selector:
                element = page.locator(selector).first
                await element.scroll_into_view_if_needed()

            elif direction == "to_top":
                await page.evaluate("window.scrollTo({top: 0, behavior: arguments[0]})", behavior)

            elif direction == "to_bottom":
                await page.evaluate(
                    "window.scrollTo({top: document.body.scrollHeight, behavior: arguments[0]})",
                    behavior,
                )

            elif direction == "down":
                await page.evaluate(
                    "window.scrollBy({top: arguments[0], behavior: arguments[1]})",
                    amount, behavior,
                )

            elif direction == "up":
                await page.evaluate(
                    "window.scrollBy({top: -arguments[0], behavior: arguments[1]})",
                    amount, behavior,
                )

            elif direction == "left":
                await page.evaluate(
                    "window.scrollBy({left: -arguments[0], behavior: arguments[1]})",
                    amount, behavior,
                )

            elif direction == "right":
                await page.evaluate(
                    "window.scrollBy({left: arguments[0], behavior: arguments[1]})",
                    amount, behavior,
                )

            else:
                return {
                    "success": False,
                    "direction": direction,
                    "amount": amount,
                    "duration_ms": 0,
                    "error": f"Unknown direction: '{direction}'. Use: down|up|left|right|to_element|to_top|to_bottom",
                }

            if times > 1 and i < times - 1:
                await asyncio.sleep(delay_between)

        # Get current scroll position
        scroll_pos = await page.evaluate(
            "() => ({x: window.scrollX, y: window.scrollY, "
            "maxY: document.body.scrollHeight - window.innerHeight})"
        )

        return {
            "success": True,
            "direction": direction,
            "amount": amount * times,
            "scroll_x": scroll_pos.get("x", 0),
            "scroll_y": scroll_pos.get("y", 0),
            "max_scroll_y": scroll_pos.get("maxY", 0),
            "at_bottom": scroll_pos.get("y", 0) >= scroll_pos.get("maxY", 1) - 10,
            "duration_ms": int((time.time() - start) * 1000),
            "error": None,
        }

    except Exception as e:
        return {
            "success": False,
            "direction": direction,
            "amount": amount,
            "duration_ms": int((time.time() - start) * 1000),
            "error": str(e),
        }
