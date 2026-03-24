"""Wait tool — Wait for element, condition, navigation, or time."""
from __future__ import annotations
import asyncio
import time
from typing import Any, Dict, Optional


async def wait(
    page,
    condition: str = "time",
    selector: Optional[str] = None,
    state: str = "visible",
    url_pattern: Optional[str] = None,
    duration: float = 1.0,
    timeout: int = 30000,
) -> Dict[str, Any]:
    """
    Wait for a condition before proceeding.

    Args:
        page:        Playwright page object
        condition:   What to wait for:
                       "time"        → Wait for a fixed duration
                       "element"     → Wait for element to appear/disappear
                       "navigation"  → Wait for page navigation to complete
                       "network"     → Wait for network to be idle
                       "load"        → Wait for page load event
                       "url"         → Wait for URL to match pattern
                       "text"        → Wait for text to appear on page
        selector:    CSS selector (for "element" and "text" conditions)
        state:       Element state for "element": "visible"|"hidden"|"attached"|"detached"
        url_pattern: URL pattern for "url" condition (substring match)
        duration:    Seconds to wait for "time" condition
        timeout:     Max wait time in ms for other conditions

    Returns:
        {"success": bool, "condition": str, "elapsed_ms": int, "error": str|None}
    """
    start = time.time()

    try:
        if condition == "time":
            await asyncio.sleep(duration)

        elif condition == "element":
            if not selector:
                return {
                    "success": False, "condition": condition,
                    "elapsed_ms": 0,
                    "error": "selector is required for 'element' condition",
                }
            await page.locator(selector).first.wait_for(state=state, timeout=timeout)

        elif condition == "navigation":
            await page.wait_for_load_state("domcontentloaded", timeout=timeout)

        elif condition == "network":
            await page.wait_for_load_state("networkidle", timeout=timeout)

        elif condition == "load":
            await page.wait_for_load_state("load", timeout=timeout)

        elif condition == "url":
            if not url_pattern:
                return {
                    "success": False, "condition": condition,
                    "elapsed_ms": 0,
                    "error": "url_pattern is required for 'url' condition",
                }
            await page.wait_for_url(f"**{url_pattern}**", timeout=timeout)

        elif condition == "text":
            if not selector:
                # Wait for text anywhere on page
                await page.wait_for_function(
                    f"() => document.body.innerText.includes({repr(url_pattern or '')})",
                    timeout=timeout,
                )
            else:
                await page.locator(selector).first.wait_for(state="visible", timeout=timeout)

        else:
            return {
                "success": False, "condition": condition,
                "elapsed_ms": 0,
                "error": f"Unknown condition: '{condition}'. Use: time|element|navigation|network|load|url|text",
            }

        elapsed = int((time.time() - start) * 1000)
        return {
            "success": True,
            "condition": condition,
            "elapsed_ms": elapsed,
            "current_url": page.url,
            "error": None,
        }

    except Exception as e:
        return {
            "success": False,
            "condition": condition,
            "elapsed_ms": int((time.time() - start) * 1000),
            "error": str(e),
        }
