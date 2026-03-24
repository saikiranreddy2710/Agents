"""
LinkedIn Actions — High-level LinkedIn-specific action helpers.

Reusable action functions that combine PageController + LinkedInSelectors
into semantic LinkedIn operations. Used by all LinkedIn agents.

Examples:
    await LinkedInActions.ensure_logged_in(pc)
    await LinkedInActions.search_people(pc, "ML engineer San Francisco")
    await LinkedInActions.send_connection(pc, profile_url, note="Hi...")
    profile = await LinkedInActions.scrape_profile(pc, profile_url)
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from loguru import logger

from .selectors import LinkedInSelectors

SEL = LinkedInSelectors()


class LinkedInActions:
    """
    Static helper methods for common LinkedIn operations.
    All methods accept a PageController instance as first argument.
    """

    # ── Session ───────────────────────────────────────────────────────────────

    @staticmethod
    async def is_logged_in(pc) -> bool:
        """Check if the current session is authenticated."""
        try:
            await pc.navigate("https://www.linkedin.com/feed/", timeout=10000)
            await pc.wait_for_load(timeout=8000)
            url = pc.url
            return "feed" in url or "mynetwork" in url
        except Exception:
            return False

    @staticmethod
    async def detect_security_challenge(pc) -> Optional[str]:
        """
        Detect if LinkedIn has triggered a security challenge.

        Returns:
            "captcha" | "checkpoint" | "rate_limit" | None
        """
        for selector in SEL.CAPTCHA.all:
            if await pc.element_exists(selector):
                return "captcha"

        for selector in SEL.SECURITY_CHECKPOINT.all:
            if await pc.element_exists(selector):
                return "checkpoint"

        for selector in SEL.RATE_LIMIT_WARNING.all:
            if await pc.element_exists(selector):
                return "rate_limit"

        return None

    # ── Search ────────────────────────────────────────────────────────────────

    @staticmethod
    async def search_people(
        pc,
        query: str,
        filters: Optional[Dict[str, str]] = None,
    ) -> bool:
        """
        Navigate to LinkedIn people search with a query.

        Args:
            pc:      PageController
            query:   Search query string
            filters: Optional filters {"location": "...", "title": "..."}

        Returns:
            True if search results loaded
        """
        import urllib.parse

        params = {"keywords": query, "origin": "GLOBAL_SEARCH_HEADER"}
        if filters:
            params.update(filters)

        url = f"https://www.linkedin.com/search/results/people/?{urllib.parse.urlencode(params)}"
        result = await pc.navigate(url, timeout=20000)
        await pc.wait_for_load(timeout=10000)
        await asyncio.sleep(2)

        return result.get("success", False) and "search/results" in pc.url

    @staticmethod
    async def extract_search_results(pc) -> List[Dict[str, Any]]:
        """
        Extract profile cards from the current search results page.

        Returns:
            List of {"name", "title", "company", "location", "url"}
        """
        profiles = await pc.run_js("""
            () => {
                const cards = document.querySelectorAll(
                    '.reusable-search__result-container li, .search-results__list li'
                );
                return Array.from(cards).map(card => {
                    const get = (sel) => {
                        const el = card.querySelector(sel);
                        return el ? el.innerText.trim() : '';
                    };
                    const linkEl = card.querySelector("a.app-aware-link[href*='/in/']");
                    const name = get(".entity-result__title-text a span[aria-hidden='true']")
                                 || get(".actor-name");
                    const url = linkEl ? linkEl.href.split('?')[0] : '';
                    if (!name || name === 'LinkedIn Member' || !url) return null;
                    return {
                        name,
                        title: get(".entity-result__primary-subtitle"),
                        company: get(".entity-result__secondary-subtitle"),
                        location: get(".entity-result__tertiary-subtitle"),
                        url,
                    };
                }).filter(Boolean);
            }
        """) or []
        return profiles

    # ── Profile ───────────────────────────────────────────────────────────────

    @staticmethod
    async def navigate_to_profile(pc, profile_url: str) -> bool:
        """Navigate to a LinkedIn profile URL."""
        result = await pc.navigate(profile_url, timeout=20000)
        await pc.wait_for_load(timeout=10000)
        await asyncio.sleep(2)
        return result.get("success", False) and "/in/" in pc.url

    @staticmethod
    async def get_profile_name(pc) -> str:
        """Get the name from the current profile page."""
        for selector in SEL.PROFILE_NAME.all:
            text = await pc.get_text(selector)
            if text:
                return text.strip()
        return ""

    @staticmethod
    async def get_connection_status(pc) -> str:
        """
        Get the connection status with the current profile.

        Returns:
            "connected" | "pending" | "not_connected" | "unknown"
        """
        # Check for Message button (= connected)
        for selector in SEL.MESSAGE_BUTTON.all:
            if await pc.element_exists(selector):
                return "connected"

        # Check for Pending button
        for selector in SEL.PENDING_BUTTON.all:
            if await pc.element_exists(selector):
                return "pending"

        # Check for Connect button
        for selector in SEL.CONNECT_BUTTON.all:
            if await pc.element_exists(selector):
                return "not_connected"

        return "unknown"

    # ── Connection ────────────────────────────────────────────────────────────

    @staticmethod
    async def click_connect_button(pc) -> bool:
        """
        Click the Connect button on a profile page.
        Tries primary selector then all fallbacks.
        """
        for selector in SEL.CONNECT_BUTTON.all:
            if await pc.element_exists(selector):
                result = await pc.click_selector(selector, timeout=5000)
                if result.get("success"):
                    await asyncio.sleep(1)
                    return True

        # Try More → Connect
        return await LinkedInActions._connect_via_more_menu(pc)

    @staticmethod
    async def _connect_via_more_menu(pc) -> bool:
        """Try to find Connect via the More dropdown."""
        for selector in SEL.MORE_ACTIONS_BUTTON.all:
            if await pc.element_exists(selector):
                await pc.click_selector(selector)
                await asyncio.sleep(0.5)
                connect_in_menu = await pc.element_exists(
                    ".artdeco-dropdown__content li button:has-text('Connect')"
                )
                if connect_in_menu:
                    result = await pc.click_selector(
                        ".artdeco-dropdown__content li button:has-text('Connect')"
                    )
                    return result.get("success", False)
        return False

    @staticmethod
    async def add_connection_note(pc, note: str) -> bool:
        """
        Add a personalized note to a connection request dialog.
        Assumes the connect dialog is already open.
        """
        # Click "Add a note" if present
        for selector in SEL.ADD_NOTE_BUTTON.all:
            if await pc.element_exists(selector):
                await pc.click_selector(selector)
                await asyncio.sleep(0.5)
                break

        # Fill note
        for selector in SEL.NOTE_TEXTAREA.all:
            if await pc.element_exists(selector):
                result = await pc.fill_input(selector, note[:300], human_like=True)
                return result.get("success", False)

        return False

    @staticmethod
    async def send_connection_request(pc) -> bool:
        """Click the Send/Done button in the connection dialog."""
        for selector in SEL.SEND_INVITE_BUTTON.all:
            if await pc.element_exists(selector):
                result = await pc.click_selector(selector, timeout=5000)
                if result.get("success"):
                    await asyncio.sleep(1)
                    return True
        return False

    @staticmethod
    async def full_connect_flow(
        pc,
        profile_url: str,
        note: str = "",
    ) -> Dict[str, Any]:
        """
        Complete connection flow: navigate → connect → add note → send.

        Returns:
            {"success": bool, "status": str, "error": str}
        """
        # Navigate
        if not await LinkedInActions.navigate_to_profile(pc, profile_url):
            return {"success": False, "status": "nav_failed", "error": "Navigation failed"}

        # Check status
        status = await LinkedInActions.get_connection_status(pc)
        if status == "connected":
            return {"success": True, "status": "already_connected", "error": ""}
        if status == "pending":
            return {"success": True, "status": "already_pending", "error": ""}

        # Click connect
        if not await LinkedInActions.click_connect_button(pc):
            return {"success": False, "status": "no_connect_btn", "error": "Connect button not found"}

        # Add note
        if note:
            await LinkedInActions.add_connection_note(pc, note)

        # Send
        if not await LinkedInActions.send_connection_request(pc):
            return {"success": False, "status": "send_failed", "error": "Could not send request"}

        return {"success": True, "status": "request_sent", "error": ""}

    # ── Messaging ─────────────────────────────────────────────────────────────

    @staticmethod
    async def open_message_dialog(pc) -> bool:
        """Click the Message button to open the compose dialog."""
        for selector in SEL.MESSAGE_BUTTON.all:
            if await pc.element_exists(selector):
                result = await pc.click_selector(selector, timeout=5000)
                if result.get("success"):
                    await asyncio.sleep(1)
                    return True
        return False

    @staticmethod
    async def type_and_send_message(pc, message: str) -> bool:
        """Type a message and send it."""
        # Find compose area
        for selector in SEL.MESSAGE_COMPOSE.all:
            if await pc.element_exists(selector):
                await pc.click_selector(selector)
                await asyncio.sleep(0.3)
                await pc.page.keyboard.type(message, delay=60)
                await asyncio.sleep(0.5)

                # Send
                for send_sel in SEL.MESSAGE_SEND_BUTTON.all:
                    if await pc.element_exists(send_sel):
                        result = await pc.click_selector(send_sel)
                        return result.get("success", False)

                # Fallback: press Enter
                await pc.page.keyboard.press("Enter")
                return True

        return False

    @staticmethod
    async def full_message_flow(
        pc,
        profile_url: str,
        message: str,
    ) -> Dict[str, Any]:
        """
        Complete messaging flow: navigate → open dialog → type → send.
        """
        if not await LinkedInActions.navigate_to_profile(pc, profile_url):
            return {"success": False, "error": "Navigation failed"}

        if not await LinkedInActions.open_message_dialog(pc):
            return {"success": False, "error": "Message button not found — not connected?"}

        if not await LinkedInActions.type_and_send_message(pc, message):
            return {"success": False, "error": "Failed to send message"}

        return {"success": True, "error": ""}

    # ── Utilities ─────────────────────────────────────────────────────────────

    @staticmethod
    async def dismiss_modal(pc) -> bool:
        """Dismiss any open modal dialog."""
        for selector in SEL.DISMISS_DIALOG.all:
            if await pc.element_exists(selector):
                result = await pc.click_selector(selector)
                return result.get("success", False)
        # Try pressing Escape
        await pc.page.keyboard.press("Escape")
        return True

    @staticmethod
    async def scroll_profile(pc, sections: int = 3) -> None:
        """Scroll through a profile to load lazy-loaded sections."""
        for _ in range(sections):
            await pc.scroll_down(amount=800)
            await asyncio.sleep(1.5)

    @staticmethod
    def build_search_url(
        query: str,
        location: Optional[str] = None,
        title: Optional[str] = None,
        company: Optional[str] = None,
        page: int = 1,
    ) -> str:
        """Build a LinkedIn people search URL with filters."""
        import urllib.parse
        params: Dict[str, str] = {
            "keywords": query,
            "origin": "GLOBAL_SEARCH_HEADER",
        }
        if location:
            params["geoUrn"] = location
        if title:
            params["title"] = title
        if company:
            params["company"] = company
        if page > 1:
            params["page"] = str(page)

        return f"https://www.linkedin.com/search/results/people/?{urllib.parse.urlencode(params)}"
