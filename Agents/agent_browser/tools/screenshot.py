"""Screenshot tool — Capture current page as base64 PNG for LLaVA/Gemini vision."""
from __future__ import annotations
import base64
import os
import time
from typing import Any, Dict, Optional


async def screenshot(
    page,
    save_path: Optional[str] = None,
    full_page: bool = False,
    clip: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """
    Capture a screenshot of the current page.

    Args:
        page:       Playwright page object
        save_path:  Optional file path to save the PNG
        full_page:  Capture full scrollable page (default: viewport only)
        clip:       Optional clip region {"x": 0, "y": 0, "width": 800, "height": 600}

    Returns:
        {
            "success": bool,
            "base64": str,        ← Base64-encoded PNG for LLM vision
            "path": str|None,     ← File path if saved
            "width": int,
            "height": int,
            "error": str|None,
        }
    """
    start = time.time()
    try:
        kwargs: Dict[str, Any] = {"full_page": full_page}
        if clip:
            kwargs["clip"] = clip

        # Capture as bytes
        img_bytes = await page.screenshot(**kwargs)

        # Encode to base64
        b64 = base64.b64encode(img_bytes).decode("utf-8")

        # Optionally save to file
        path = None
        if save_path:
            os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(img_bytes)
            path = save_path

        # Get dimensions from PIL
        width, height = 0, 0
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(img_bytes))
            width, height = img.size
        except Exception:
            pass

        return {
            "success": True,
            "base64": b64,
            "path": path,
            "width": width,
            "height": height,
            "size_bytes": len(img_bytes),
            "duration_ms": int((time.time() - start) * 1000),
            "error": None,
        }
    except Exception as e:
        return {
            "success": False,
            "base64": "",
            "path": None,
            "width": 0,
            "height": 0,
            "duration_ms": int((time.time() - start) * 1000),
            "error": str(e),
        }
