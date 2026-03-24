"""
Search Agent — LinkedIn people search with filters.

Handles:
  - Navigate to LinkedIn People Search
  - Apply filters (title, location, company, industry)
  - Paginate through results
  - Extract profile cards (name, title, company, location, URL)
  - Return structured list of profiles
"""

from __future__ import annotations

import asyncio
import urllib.parse
from typing import Any, Dict, List, Optional

from loguru import logger

from .base_agent import BaseAgent


class SearchAgent(BaseAgent):
    """
    Searches LinkedIn for people matching given criteria.

    Returns a list of profile dicts:
      [{"name": str, "title": str, "company": str, "location": str, "url": str}]
    """

    def __init__(self, **kwargs):
        super().__init__(name="SearchAgent", **kwargs)
        self._query: str = ""
        self._limit: int = 10
        self._filters: Dict[str, str] = {}
        self._profiles: List[Dict[str, Any]] = []
        self._current_page: int = 1

    @property
    def goal(self) -> str:
        return f"Search LinkedIn for: {self._query} (limit: {self._limit})"

    async def run(self, page_controller, context: Optional[Dict] = None) -> Dict[str, Any]:
        """Override run to inject search context."""
        ctx = context or {}
        self._query = ctx.get("query", "software engineer")
        self._limit = ctx.get("limit", 10)
        self._filters = ctx.get("filters", {})
        self._profiles = []
        self._current_page = 1
        return await super().run(page_controller, context)

    async def execute_step(
        self,
        page_controller,
        screenshot_b64: str,
        experiences: List[Dict],
        step: int,
    ) -> Dict[str, Any]:
        """Execute one search step."""

        url = page_controller.url

        # Step 1: Navigate to search
        if step == 1:
            return await self._navigate_to_search(page_controller)

        # Step 2+: Extract results and paginate
        if "search/results/people" in url:
            return await self._extract_and_paginate(page_controller)

        # Fallback: try to navigate to search
        return await self._navigate_to_search(page_controller)

    # ── Search Steps ──────────────────────────────────────────────────────────

    async def _navigate_to_search(self, pc) -> Dict[str, Any]:
        """Navigate to LinkedIn people search with query."""
        self.log_step(f"Navigating to search: '{self._query}'")

        # Build search URL with filters
        params = {
            "keywords": self._query,
            "origin": "GLOBAL_SEARCH_HEADER",
        }

        # Apply optional filters
        if self._filters.get("location"):
            params["geoUrn"] = self._filters["location"]
        if self._filters.get("title"):
            params["title"] = self._filters["title"]

        query_string = urllib.parse.urlencode(params)
        search_url = f"https://www.linkedin.com/search/results/people/?{query_string}"

        result = await pc.navigate(search_url, timeout=20000)
        await pc.wait_for_load(timeout=10000)
        await asyncio.sleep(2)  # Let results render

        return {
            "action": "navigate_search",
            "success": result.get("success", False),
            "done": False,
        }

    async def _extract_and_paginate(self, pc) -> Dict[str, Any]:
        """Extract profile cards from current search results page."""
        self.log_step(f"Extracting profiles from page {self._current_page}")

        # Wait for results to load
        await pc.wait_for_element(
            ".reusable-search__result-container, .search-results-container",
            timeout=10000,
        )

        # Extract profile cards via JavaScript
        profiles = await pc.run_js("""
            () => {
                const cards = document.querySelectorAll(
                    '.reusable-search__result-container li, ' +
                    '.search-results__list li'
                );
                return Array.from(cards).map(card => {
                    const nameEl = card.querySelector(
                        '.entity-result__title-text a span[aria-hidden="true"], ' +
                        '.actor-name'
                    );
                    const titleEl = card.querySelector(
                        '.entity-result__primary-subtitle, ' +
                        '.subline-level-1'
                    );
                    const companyEl = card.querySelector(
                        '.entity-result__secondary-subtitle, ' +
                        '.subline-level-2'
                    );
                    const locationEl = card.querySelector(
                        '.entity-result__tertiary-subtitle, ' +
                        '.subline-level-3'
                    );
                    const linkEl = card.querySelector(
                        'a.app-aware-link[href*="/in/"], ' +
                        'a[href*="linkedin.com/in/"]'
                    );

                    const name = nameEl ? nameEl.innerText.trim() : '';
                    const url = linkEl ? linkEl.href.split('?')[0] : '';

                    // Skip "LinkedIn Member" (private profiles)
                    if (!name || name === 'LinkedIn Member') return null;

                    return {
                        name: name,
                        title: titleEl ? titleEl.innerText.trim() : '',
                        company: companyEl ? companyEl.innerText.trim() : '',
                        location: locationEl ? locationEl.innerText.trim() : '',
                        url: url,
                    };
                }).filter(p => p !== null && p.name && p.url);
            }
        """) or []

        self.log_step(f"Found {len(profiles)} profiles on page {self._current_page}")
        self._profiles.extend(profiles)

        # Check if we have enough profiles
        if len(self._profiles) >= self._limit:
            self._profiles = self._profiles[:self._limit]
            return {
                "action": "extract_profiles",
                "success": True,
                "done": True,
                "result": {
                    "profiles": self._profiles,
                    "total_found": len(self._profiles),
                    "pages_searched": self._current_page,
                    "query": self._query,
                },
            }

        # Try to go to next page
        next_page_result = await self._go_to_next_page(pc)
        if not next_page_result:
            # No more pages
            return {
                "action": "extract_profiles",
                "success": True,
                "done": True,
                "result": {
                    "profiles": self._profiles,
                    "total_found": len(self._profiles),
                    "pages_searched": self._current_page,
                    "query": self._query,
                },
            }

        self._current_page += 1
        return {
            "action": "extract_profiles",
            "success": True,
            "done": False,
            "result": {"profiles_so_far": len(self._profiles)},
        }

    async def _go_to_next_page(self, pc) -> bool:
        """Navigate to the next search results page."""
        # Try clicking the "Next" button
        next_btn_exists = await pc.element_exists(
            "button[aria-label='Next'], .artdeco-pagination__button--next"
        )
        if not next_btn_exists:
            return False

        next_btn_disabled = await pc.run_js(
            "() => !!document.querySelector("
            "\"button[aria-label='Next']:disabled, "
            ".artdeco-pagination__button--next:disabled\")"
        )
        if next_btn_disabled:
            return False

        await pc.click_selector(
            "button[aria-label='Next'], .artdeco-pagination__button--next"
        )
        await pc.wait_for_load(timeout=10000)
        await asyncio.sleep(2)
        return True
