"""
Message Agent — Sends messages to existing LinkedIn connections.

Handles:
  - Navigate to a connection's profile or messaging thread
  - Open the message dialog
  - Type and send a personalized message
  - Confirm message was sent
  - Handle "Can't message" states (not connected, InMail required)
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from loguru import logger

from .base_agent import BaseAgent


class MessageAgent(BaseAgent):
    """
    Sends a message to an existing LinkedIn connection.

    Usage:
        result = await agent.run(pc, context={
            "recipient": {"name": "Jane Doe", "url": "https://linkedin.com/in/..."},
            "message": "Hi Jane, I wanted to follow up on...",
        })
    """

    def __init__(self, **kwargs):
        super().__init__(name="MessageAgent", max_steps=8, **kwargs)
        self._recipient: Dict[str, Any] = {}
        self._message: str = ""

    @property
    def goal(self) -> str:
        name = self._recipient.get("name", "unknown")
        return f"Send message to {name}"

    async def run(self, page_controller, context: Optional[Dict] = None) -> Dict[str, Any]:
        ctx = context or {}
        self._recipient = ctx.get("recipient", {})
        self._message = ctx.get("message", "")
        return await super().run(page_controller, context)

    async def execute_step(
        self,
        page_controller,
        screenshot_b64: str,
        experiences: List[Dict],
        step: int,
    ) -> Dict[str, Any]:
        """Execute one messaging step."""

        # Step 1: Navigate to recipient's profile
        if step == 1:
            return await self._navigate_to_profile(page_controller)

        # Step 2: Click Message button
        if step == 2:
            return await self._click_message_button(page_controller)

        # Step 3: Type and send message
        if step == 3:
            return await self._type_and_send(page_controller)

        # Step 4: Confirm sent
        if step >= 4:
            return await self._confirm_sent(page_controller)

        return {"action": "wait", "success": True, "done": False}

    # ── Message Steps ─────────────────────────────────────────────────────────

    async def _navigate_to_profile(self, pc) -> Dict[str, Any]:
        """Navigate to the recipient's profile."""
        profile_url = self._recipient.get("url", "")
        if not profile_url:
            return {
                "action": "navigate",
                "success": False,
                "done": True,
                "abort": True,
                "error": "No recipient URL provided",
            }

        self.log_step(f"Navigating to: {profile_url}")
        result = await pc.navigate(profile_url, timeout=20000)
        await pc.wait_for_load(timeout=10000)
        await asyncio.sleep(2)

        return {
            "action": "navigate",
            "success": result.get("success", False),
            "done": False,
        }

    async def _click_message_button(self, pc) -> Dict[str, Any]:
        """Find and click the Message button on the profile."""
        self.log_step("Looking for Message button")

        # Check if Message button exists (only for connections)
        message_selectors = [
            "button[aria-label*='Message']",
            "a[href*='/messaging/thread/']",
            ".pv-s-profile-actions button:has-text('Message')",
            ".pvs-profile-actions button:has-text('Message')",
        ]

        for selector in message_selectors:
            exists = await pc.element_exists(selector)
            if exists:
                result = await pc.click_selector(selector, timeout=5000)
                if result.get("success"):
                    await asyncio.sleep(1)
                    return {
                        "action": "click_message",
                        "success": True,
                        "done": False,
                    }

        # Message button not found — not connected or InMail required
        self.log_step("Message button not found — not a connection?", "warning")
        return {
            "action": "click_message",
            "success": False,
            "done": True,
            "error": (
                f"Cannot message {self._recipient.get('name', 'this person')} — "
                "not connected or InMail required"
            ),
            "result": {"status": "cannot_message", "recipient": self._recipient},
        }

    async def _type_and_send(self, pc) -> Dict[str, Any]:
        """Type the message and send it."""
        if not self._message:
            return {
                "action": "type_send",
                "success": False,
                "done": True,
                "error": "No message content provided",
            }

        self.log_step(f"Typing message ({len(self._message)} chars)")

        # Wait for message compose area
        compose_selectors = [
            ".msg-form__contenteditable",
            "[data-placeholder='Write a message…']",
            ".msg-form__msg-content-container--scrollable",
            "div[role='textbox'][aria-label*='message']",
        ]

        compose_found = False
        for selector in compose_selectors:
            if await pc.element_exists(selector):
                # Click to focus
                await pc.click_selector(selector)
                await asyncio.sleep(0.3)

                # Type the message
                await pc.page.keyboard.type(self._message, delay=60)
                compose_found = True
                break

        if not compose_found:
            return {
                "action": "type_send",
                "success": False,
                "done": True,
                "error": "Message compose area not found",
            }

        await asyncio.sleep(0.5)

        # Click Send button
        send_selectors = [
            "button.msg-form__send-button",
            "button[aria-label='Send']",
            "button:has-text('Send')",
            ".msg-form__send-btn",
        ]

        for selector in send_selectors:
            if await pc.element_exists(selector):
                result = await pc.click_selector(selector, timeout=5000)
                if result.get("success"):
                    await asyncio.sleep(1)
                    return {
                        "action": "type_send",
                        "success": True,
                        "done": False,
                    }

        # Try pressing Enter to send
        await pc.page.keyboard.press("Enter")
        await asyncio.sleep(1)
        return {"action": "type_send", "success": True, "done": False}

    async def _confirm_sent(self, pc) -> Dict[str, Any]:
        """Confirm the message was sent."""
        self.log_step("Confirming message sent")

        # Check if message appears in the thread
        sent_indicators = [
            ".msg-s-message-list__event",
            ".msg-s-event-listitem",
            ".msg-s-message-group",
        ]

        for selector in sent_indicators:
            if await pc.element_exists(selector):
                # Get last message text to verify
                last_msg = await pc.run_js(f"""
                    () => {{
                        const msgs = document.querySelectorAll('{selector}');
                        const last = msgs[msgs.length - 1];
                        return last ? last.innerText.trim().substring(0, 100) : '';
                    }}
                """) or ""

                self.log_step(
                    f"Message sent to {self._recipient.get('name', 'unknown')}", "info"
                )
                return {
                    "action": "confirm_sent",
                    "success": True,
                    "done": True,
                    "result": {
                        "status": "message_sent",
                        "recipient": self._recipient,
                        "message_preview": self._message[:50],
                    },
                }

        # Assume sent if compose area is now empty
        compose_empty = await pc.run_js("""
            () => {
                const el = document.querySelector('.msg-form__contenteditable');
                return el ? el.innerText.trim() === '' : false;
            }
        """)

        if compose_empty:
            return {
                "action": "confirm_sent",
                "success": True,
                "done": True,
                "result": {
                    "status": "likely_sent",
                    "recipient": self._recipient,
                },
            }

        return {
            "action": "confirm_sent",
            "success": True,
            "done": True,
            "result": {
                "status": "unknown",
                "recipient": self._recipient,
            },
        }
