"""Type text tool — Type text into an input field with human-like timing."""
from __future__ import annotations
import asyncio
import time
from typing import Any, Dict, Optional


async def type_text(
    page,
    selector: Optional[str] = None,
    text: Optional[str] = None,
    delay: int = 80,
    clear_first: bool = True,
    press_enter: bool = False,
    timeout: int = 10000,
    use_fill: bool = False,
) -> Dict[str, Any]:
    """
    Type text into an input field.

    Args:
        page:        Playwright page object
        selector:    CSS selector of the input field
        text:        Text to type
        delay:       Delay between keystrokes in ms (human-like, 0 = instant)
        clear_first: Clear the field before typing
        press_enter: Press Enter after typing
        timeout:     Timeout waiting for element in ms
        use_fill:    Use fill() instead of type() — faster but less human-like

    Returns:
        {"success": bool, "selector": str, "text_length": int, "error": str|None}
    """
    start = time.time()

    if not selector:
        return {
            "success": False,
            "selector": "",
            "text_length": 0,
            "duration_ms": 0,
            "error": "selector is required for type_text",
        }
    if text is None:
        return {
            "success": False,
            "selector": selector,
            "text_length": 0,
            "duration_ms": 0,
            "error": "text is required for type_text",
        }

    try:
        element = page.locator(selector).first
        await element.wait_for(state="visible", timeout=timeout)
        await element.scroll_into_view_if_needed(timeout=timeout)

        if clear_first:
            await element.clear()
            await asyncio.sleep(0.1)

        if use_fill or delay == 0:
            # Fast fill — not human-like but reliable
            await element.fill(text)
        else:
            # Human-like typing with per-keystroke delay
            await element.type(text, delay=delay)

        if press_enter:
            await element.press("Enter")

        return {
            "success": True,
            "selector": selector,
            "text_length": len(text),
            "duration_ms": int((time.time() - start) * 1000),
            "error": None,
        }

    except Exception as e:
        # Fallback: try JavaScript to set value
        if selector:
            try:
                await page.evaluate(
                    f"""
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        el.value = {repr(text)};
                        el.dispatchEvent(new Event('input', {{bubbles: true}}));
                        el.dispatchEvent(new Event('change', {{bubbles: true}}));
                    }}
                    """
                )
                return {
                    "success": True,
                    "selector": selector,
                    "text_length": len(text),
                    "duration_ms": int((time.time() - start) * 1000),
                    "error": None,
                    "note": "Used JavaScript fill fallback",
                }
            except Exception:
                pass

        return {
            "success": False,
            "selector": selector,
            "text_length": 0,
            "duration_ms": int((time.time() - start) * 1000),
            "error": str(e),
        }
