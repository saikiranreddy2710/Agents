"""
Agent Browser — Core Playwright browser automation library.

Components:
  tools/           → 8 atomic browser tools (navigate, click, type, scroll, etc.)
  browser_instance → Single Playwright browser instance manager
  page_controller  → High-level page actions combining multiple tools
  browser_pool     → Multiple parallel browser instances + load balancing
  coordinator      → Distributes tasks to subagents across browser pool
  stealth/         → Anti-detection: human behavior, fingerprint rotation, rate limiting
"""

from .browser_instance import BrowserInstance
from .page_controller import PageController
from .browser_pool import BrowserPool

__all__ = [
    "BrowserInstance",
    "PageController",
    "BrowserPool",
]
