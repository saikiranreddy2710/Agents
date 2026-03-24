"""
Auth Agent — LinkedIn login + session persistence.

Handles:
  - Login with email/password
  - Session cookie persistence (avoid re-login)
  - 2FA detection and handling
  - CAPTCHA detection (pause + alert)
  - Session health check (are we still logged in?)
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from loguru import logger

from .base_agent import BaseAgent


class AuthAgent(BaseAgent):
    """
    Manages LinkedIn authentication.

    Checks if a valid session exists first (via cookies).
    Only performs full login if session is expired/missing.
    """

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        session_file: str = "workspace/linkedin_session.json",
        **kwargs,
    ):
        super().__init__(name="AuthAgent", **kwargs)
        self.email = email or os.getenv("LINKEDIN_EMAIL", "")
        self.password = password or os.getenv("LINKEDIN_PASSWORD", "")
        self.session_file = session_file
        self._logged_in = False

    @property
    def goal(self) -> str:
        return "Authenticate with LinkedIn and maintain a valid session"

    async def execute_step(
        self,
        page_controller,
        screenshot_b64: str,
        experiences: List[Dict],
        step: int,
    ) -> Dict[str, Any]:
        """Execute one authentication step."""

        url = page_controller.url

        # Step 1: Check if already logged in
        if step == 1:
            return await self._check_session(page_controller)

        # Step 2: Navigate to login page
        if step == 2:
            return await self._navigate_to_login(page_controller)

        # Step 3: Fill credentials
        if step == 3:
            return await self._fill_credentials(page_controller)

        # Step 4: Handle post-login state
        if step >= 4:
            return await self._handle_post_login(page_controller)

        return {"action": "wait", "success": True, "done": False}

    # ── Auth Steps ────────────────────────────────────────────────────────────

    async def _check_session(self, pc) -> Dict[str, Any]:
        """Check if we have a valid LinkedIn session."""
        self.log_step("Checking existing session")

        # Navigate to LinkedIn feed
        result = await pc.navigate("https://www.linkedin.com/feed/", timeout=15000)

        await pc.wait_for_load(timeout=10000)
        current_url = pc.url

        # If we're on the feed, we're logged in
        if "feed" in current_url or "mynetwork" in current_url:
            self._logged_in = True
            self.log_step("Already logged in!", "info")
            return {
                "action": "check_session",
                "success": True,
                "done": True,
                "result": {"logged_in": True, "method": "existing_session"},
            }

        # If redirected to login page, need to authenticate
        if "login" in current_url or "checkpoint" in current_url:
            self.log_step("Session expired, need to login")
            return {
                "action": "check_session",
                "success": True,
                "done": False,
                "result": {"logged_in": False},
            }

        # Unknown state — try navigating to login
        return {
            "action": "check_session",
            "success": True,
            "done": False,
            "result": {"logged_in": False, "url": current_url},
        }

    async def _navigate_to_login(self, pc) -> Dict[str, Any]:
        """Navigate to LinkedIn login page."""
        self.log_step("Navigating to login page")
        result = await pc.navigate("https://www.linkedin.com/login", timeout=15000)
        await pc.wait_for_element("input#username", timeout=10000)
        return {
            "action": "navigate_login",
            "success": result.get("success", False),
            "done": False,
        }

    async def _fill_credentials(self, pc) -> Dict[str, Any]:
        """Fill in email and password."""
        if not self.email or not self.password:
            self.log_step("No credentials configured!", "error")
            return {
                "action": "fill_credentials",
                "success": False,
                "done": True,
                "abort": True,
                "error": "LINKEDIN_EMAIL and LINKEDIN_PASSWORD not set in .env",
            }

        self.log_step(f"Filling credentials for {self.email}")

        # Fill email
        email_result = await pc.fill_input(
            "input#username", self.email, human_like=True
        )
        if not email_result["success"]:
            return {"action": "fill_email", "success": False, "done": False,
                    "error": email_result.get("error")}

        await pc.sleep(0.5)

        # Fill password
        pass_result = await pc.fill_input(
            "input#password", self.password, human_like=True
        )
        if not pass_result["success"]:
            return {"action": "fill_password", "success": False, "done": False,
                    "error": pass_result.get("error")}

        await pc.sleep(0.5)

        # Click sign in button
        click_result = await pc.click_selector(
            "button[type='submit'], button[data-litms-control-urn='login-submit']",
            timeout=5000,
        )

        await pc.wait_for_navigation(timeout=15000)

        return {
            "action": "fill_credentials",
            "success": click_result.get("success", False),
            "done": False,
        }

    async def _handle_post_login(self, pc) -> Dict[str, Any]:
        """Handle the state after clicking login."""
        await pc.wait_for_load(timeout=10000)
        current_url = pc.url

        self.log_step(f"Post-login URL: {current_url}")

        # Success: on feed
        if "feed" in current_url or "mynetwork" in current_url:
            self._logged_in = True
            # Save session
            await self._save_session(pc)
            return {
                "action": "post_login",
                "success": True,
                "done": True,
                "result": {"logged_in": True, "method": "fresh_login"},
            }

        # 2FA required
        if "checkpoint" in current_url or "two-step" in current_url:
            self.log_step("2FA required — manual intervention needed", "warning")
            return {
                "action": "post_login",
                "success": False,
                "done": True,
                "abort": True,
                "error": "2FA required. Please complete manually and save session cookies.",
            }

        # CAPTCHA
        captcha_exists = await pc.element_exists(".captcha-container, #captcha")
        if captcha_exists:
            self.log_step("CAPTCHA detected — pausing", "warning")
            return {
                "action": "post_login",
                "success": False,
                "done": True,
                "abort": True,
                "error": "CAPTCHA detected. Please solve manually.",
            }

        # Wrong credentials
        error_exists = await pc.element_exists(".alert-error, #error-for-password")
        if error_exists:
            error_text = await pc.get_text(".alert-error, #error-for-password")
            return {
                "action": "post_login",
                "success": False,
                "done": True,
                "abort": True,
                "error": f"Login failed: {error_text}",
            }

        # Unknown state — wait and retry
        return {
            "action": "post_login",
            "success": True,
            "done": False,
            "result": {"url": current_url},
        }

    async def _save_session(self, pc) -> None:
        """Save session cookies to file."""
        try:
            os.makedirs(os.path.dirname(self.session_file) if os.path.dirname(self.session_file) else ".", exist_ok=True)
            await pc.page.context.storage_state(path=self.session_file)
            self.log_step(f"Session saved to {self.session_file}", "info")
        except Exception as e:
            self.log_step(f"Failed to save session: {e}", "warning")

    @property
    def is_logged_in(self) -> bool:
        return self._logged_in
