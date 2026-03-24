"""
Fingerprint Rotator — Rotates browser profiles and user agents.

Prevents LinkedIn from fingerprinting the automation by:
  - Cycling through realistic user agent strings
  - Varying viewport sizes
  - Rotating browser locale/timezone settings
  - Managing multiple browser profiles (cookies, localStorage)
"""

from __future__ import annotations

import json
import os
import random
from typing import Any, Dict, List, Optional

from loguru import logger


# ── Realistic User Agents ─────────────────────────────────────────────────────

USER_AGENTS = [
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

# ── Viewport Sizes (common screen resolutions) ────────────────────────────────

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 800},
    {"width": 1536, "height": 864},
    {"width": 1280, "height": 720},
]

# ── Timezones ─────────────────────────────────────────────────────────────────

TIMEZONES = [
    "America/New_York",
    "America/Chicago",
    "America/Los_Angeles",
    "America/Denver",
    "Europe/London",
    "Europe/Paris",
    "Asia/Tokyo",
    "Asia/Singapore",
    "Australia/Sydney",
]

# ── Locales ───────────────────────────────────────────────────────────────────

LOCALES = [
    "en-US",
    "en-GB",
    "en-CA",
    "en-AU",
]


class FingerprintRotator:
    """
    Manages browser fingerprint rotation to avoid detection.

    Each session can use a different combination of:
    - User agent
    - Viewport size
    - Timezone
    - Locale
    - Browser profile (cookies/localStorage)
    """

    def __init__(
        self,
        profiles_dir: str = "workspace/profiles",
        max_profiles: int = 5,
        rotate_every_n_sessions: int = 3,
    ):
        self.profiles_dir = profiles_dir
        self.max_profiles = max_profiles
        self.rotate_every_n_sessions = rotate_every_n_sessions
        self._session_count = 0
        self._current_profile_idx = 0
        os.makedirs(profiles_dir, exist_ok=True)

    def get_fingerprint(self, profile_idx: Optional[int] = None) -> Dict[str, Any]:
        """
        Get a browser fingerprint configuration.

        Args:
            profile_idx: Specific profile index (None = auto-select)

        Returns:
            Dict with user_agent, viewport, timezone, locale, storage_state_path
        """
        idx = profile_idx if profile_idx is not None else self._current_profile_idx

        # Deterministic selection based on profile index
        # (same profile = same fingerprint for session continuity)
        ua_idx = idx % len(USER_AGENTS)
        vp_idx = idx % len(VIEWPORTS)
        tz_idx = idx % len(TIMEZONES)
        lc_idx = idx % len(LOCALES)

        storage_path = os.path.join(self.profiles_dir, f"profile_{idx}.json")

        return {
            "user_agent": USER_AGENTS[ua_idx],
            "viewport": VIEWPORTS[vp_idx],
            "timezone_id": TIMEZONES[tz_idx],
            "locale": LOCALES[lc_idx],
            "storage_state_path": storage_path if os.path.exists(storage_path) else None,
            "profile_idx": idx,
        }

    def get_random_fingerprint(self) -> Dict[str, Any]:
        """Get a completely random fingerprint (for new sessions)."""
        return {
            "user_agent": random.choice(USER_AGENTS),
            "viewport": random.choice(VIEWPORTS),
            "timezone_id": random.choice(TIMEZONES),
            "locale": random.choice(LOCALES),
            "storage_state_path": None,
            "profile_idx": -1,
        }

    def rotate(self) -> Dict[str, Any]:
        """
        Rotate to the next profile.
        Called at the start of each new session.
        """
        self._session_count += 1
        if self._session_count % self.rotate_every_n_sessions == 0:
            self._current_profile_idx = (self._current_profile_idx + 1) % self.max_profiles
            logger.info(f"Fingerprint rotated to profile {self._current_profile_idx}")

        return self.get_fingerprint()

    def save_profile(
        self,
        profile_idx: int,
        storage_state: Dict[str, Any],
    ) -> bool:
        """Save a browser profile (cookies, localStorage) to disk."""
        try:
            path = os.path.join(self.profiles_dir, f"profile_{profile_idx}.json")
            with open(path, "w") as f:
                json.dump(storage_state, f)
            logger.debug(f"Profile {profile_idx} saved to {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save profile {profile_idx}: {e}")
            return False

    def load_profile(self, profile_idx: int) -> Optional[Dict[str, Any]]:
        """Load a saved browser profile."""
        path = os.path.join(self.profiles_dir, f"profile_{profile_idx}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load profile {profile_idx}: {e}")
            return None

    def delete_profile(self, profile_idx: int) -> bool:
        """Delete a browser profile (e.g., after account ban)."""
        path = os.path.join(self.profiles_dir, f"profile_{profile_idx}.json")
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"Profile {profile_idx} deleted")
            return True
        return False

    def list_profiles(self) -> List[Dict[str, Any]]:
        """List all saved profiles."""
        profiles = []
        for i in range(self.max_profiles):
            path = os.path.join(self.profiles_dir, f"profile_{i}.json")
            profiles.append({
                "profile_idx": i,
                "exists": os.path.exists(path),
                "path": path,
                "size_bytes": os.path.getsize(path) if os.path.exists(path) else 0,
            })
        return profiles

    def get_context_options(self, fingerprint: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert a fingerprint to Playwright context options.

        Usage:
            fp = rotator.get_fingerprint()
            opts = rotator.get_context_options(fp)
            context = await browser.new_context(**opts)
        """
        opts: Dict[str, Any] = {
            "user_agent": fingerprint["user_agent"],
            "viewport": fingerprint["viewport"],
            "locale": fingerprint["locale"],
            "timezone_id": fingerprint["timezone_id"],
            "java_script_enabled": True,
            "accept_downloads": False,
            "ignore_https_errors": True,
            "extra_http_headers": {
                "Accept-Language": f"{fingerprint['locale']},en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            },
        }

        if fingerprint.get("storage_state_path"):
            opts["storage_state"] = fingerprint["storage_state_path"]

        return opts
