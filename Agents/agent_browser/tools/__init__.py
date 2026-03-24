"""
Browser Tools — 8 atomic browser actions.

Each tool is a standalone async function that takes a Playwright page
and returns a standardized result dict.

Tools:
  navigate    → Go to a URL
  screenshot  → Capture current page as base64 PNG
  click       → Click an element (by selector, text, or coordinates)
  type_text   → Type text into an input field
  scroll      → Scroll the page (up/down/to element)
  dom         → Extract DOM information (text, attributes, structure)
  evaluate    → Execute JavaScript on the page
  wait        → Wait for element/condition/time
"""

from .navigate import navigate
from .screenshot import screenshot
from .click import click
from .type_text import type_text
from .scroll import scroll
from .dom import dom
from .evaluate import evaluate
from .wait import wait

__all__ = [
    "navigate",
    "screenshot",
    "click",
    "type_text",
    "scroll",
    "dom",
    "evaluate",
    "wait",
]

# Tool registry for dynamic dispatch
TOOL_REGISTRY = {
    "navigate": navigate,
    "screenshot": screenshot,
    "click": click,
    "type_text": type_text,
    "type": type_text,       # alias
    "scroll": scroll,
    "dom": dom,
    "evaluate": evaluate,
    "wait": wait,
}


async def execute_tool(tool_name: str, page, **params) -> dict:
    """
    Execute a browser tool by name.

    Args:
        tool_name: Name of the tool to execute
        page:      Playwright page object
        **params:  Tool-specific parameters

    Returns:
        {"success": bool, "data": any, "error": str|None}
    """
    tool_fn = TOOL_REGISTRY.get(tool_name)
    if tool_fn is None:
        return {
            "success": False,
            "error": f"Unknown tool: '{tool_name}'. Available: {list(TOOL_REGISTRY.keys())}",
        }
    try:
        return await tool_fn(page, **params)
    except Exception as e:
        return {"success": False, "error": str(e)}
