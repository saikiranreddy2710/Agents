"""Navigate tool — Go to a URL and wait for page load."""
from __future__ import annotations
import time
from typing import Any, Dict, Optional


async def navigate(
    page,
    url: str,
    wait_until: str = "domcontentloaded",
    timeout: int = 30000,
    referer: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Navigate to a URL.

    Args:
        page:       Playwright page object
        url:        URL to navigate to
        wait_until: "load" | "domcontentloaded" | "networkidle" | "commit"
        timeout:    Timeout in milliseconds
        referer:    Optional referer header

    Returns:
        {"success": bool, "url": str, "title": str, "status": int, "error": str|None}
    """
    start = time.time()
    try:
        kwargs: Dict[str, Any] = {"wait_until": wait_until, "timeout": timeout}
        if referer:
            kwargs["referer"] = referer

        response = await page.goto(url, **kwargs)
        title = await page.title()
        current_url = page.url

        return {
            "success": True,
            "url": current_url,
            "title": title,
            "status": response.status if response else 200,
            "duration_ms": int((time.time() - start) * 1000),
            "error": None,
        }
    except Exception as e:
        return {
            "success": False,
            "url": url,
            "title": "",
            "status": 0,
            "duration_ms": int((time.time() - start) * 1000),
            "error": str(e),
        }
