"""Evaluate tool — Execute JavaScript on the page."""
from __future__ import annotations
import time
from typing import Any, Dict, Optional


async def evaluate(
    page,
    script: str,
    arg: Optional[Any] = None,
    timeout: int = 10000,
) -> Dict[str, Any]:
    """
    Execute JavaScript on the page and return the result.

    Args:
        page:    Playwright page object
        script:  JavaScript to execute. Can be:
                   - Expression: "document.title"
                   - Function:   "() => window.scrollY"
                   - With arg:   "el => el.textContent" (arg must be an element handle)
        arg:     Optional argument to pass to the script function
        timeout: Timeout in milliseconds

    Returns:
        {"success": bool, "result": any, "error": str|None}

    Examples:
        # Get page scroll position
        await evaluate(page, "() => ({x: window.scrollX, y: window.scrollY})")

        # Check if element exists
        await evaluate(page, "() => !!document.querySelector('.connect-button')")

        # Get all text content
        await evaluate(page, "() => document.body.innerText")

        # Trigger a custom event
        await evaluate(page, "() => document.querySelector('form').submit()")
    """
    start = time.time()
    try:
        if arg is not None:
            result = await page.evaluate(script, arg)
        else:
            result = await page.evaluate(script)

        return {
            "success": True,
            "result": result,
            "duration_ms": int((time.time() - start) * 1000),
            "error": None,
        }
    except Exception as e:
        return {
            "success": False,
            "result": None,
            "duration_ms": int((time.time() - start) * 1000),
            "error": str(e),
        }
