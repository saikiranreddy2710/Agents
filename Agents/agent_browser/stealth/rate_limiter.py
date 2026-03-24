"""
Rate Limiter — Learned rate limiting that respects LinkedIn's limits.

LinkedIn enforces strict limits on automation:
  - Max ~20 connection requests per day
  - Max ~10 messages per day
  - Max ~100 profile views per day
  - Suspicious if actions happen too fast or too uniformly

This rate limiter:
  1. Tracks daily action counts per action type
  2. Enforces hard limits (never exceed)
  3. Adds jitter to action timing (avoid uniform patterns)
  4. Learns from past sessions (adjusts limits if warnings detected)
  5. Implements daily reset at midnight
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import time
from datetime import datetime, date
from typing import Any, Dict, Optional

from loguru import logger


# ── Default LinkedIn Limits ───────────────────────────────────────────────────

DEFAULT_LIMITS = {
    "connection_request": 20,   # Max connection requests per day
    "message":            10,   # Max messages per day
    "profile_view":       100,  # Max profile views per day
    "search":             50,   # Max searches per day
    "navigate":           500,  # Max page navigations per day
    "click":              1000, # Max clicks per day (generous)
}

# ── Minimum delays between actions (seconds) ─────────────────────────────────

MIN_DELAYS = {
    "connection_request": 30,   # At least 30s between connection requests
    "message":            60,   # At least 60s between messages
    "profile_view":       5,    # At least 5s between profile views
    "search":             10,   # At least 10s between searches
    "navigate":           2,    # At least 2s between navigations
    "click":              0.5,  # At least 0.5s between clicks
}


class RateLimiter:
    """
    Enforces rate limits for LinkedIn automation.

    Tracks action counts per day and enforces minimum delays
    between actions to avoid triggering LinkedIn's bot detection.
    """

    def __init__(
        self,
        state_file: str = "workspace/rate_limit_state.json",
        custom_limits: Optional[Dict[str, int]] = None,
    ):
        self.state_file = state_file
        self.limits = {**DEFAULT_LIMITS, **(custom_limits or {})}
        self.min_delays = dict(MIN_DELAYS)

        self._state: Dict[str, Any] = {}
        self._last_action_time: Dict[str, float] = {}
        self._load_state()

    # ── Public API ────────────────────────────────────────────────────────────

    async def check_and_wait(
        self,
        action_type: str,
        raise_on_limit: bool = False,
    ) -> bool:
        """
        Check if an action is allowed and wait if needed.

        Args:
            action_type:    Type of action (e.g., "connection_request", "message")
            raise_on_limit: Raise exception if daily limit exceeded (default: return False)

        Returns:
            True if action is allowed, False if daily limit exceeded
        """
        # Reset counts if it's a new day
        self._maybe_reset_daily_counts()

        # Check daily limit
        if not self._is_within_limit(action_type):
            msg = (
                f"Daily limit reached for '{action_type}': "
                f"{self._get_count(action_type)}/{self.limits.get(action_type, 999)}"
            )
            logger.warning(f"[RateLimiter] {msg}")
            if raise_on_limit:
                raise RuntimeError(msg)
            return False

        # Wait for minimum delay
        await self._wait_for_delay(action_type)

        return True

    def record_action(self, action_type: str) -> None:
        """Record that an action was performed."""
        self._maybe_reset_daily_counts()

        today = str(date.today())
        if today not in self._state:
            self._state[today] = {}

        counts = self._state[today]
        counts[action_type] = counts.get(action_type, 0) + 1
        self._last_action_time[action_type] = time.time()

        self._save_state()

        count = counts[action_type]
        limit = self.limits.get(action_type, 999)
        logger.debug(f"[RateLimiter] {action_type}: {count}/{limit} today")

    def get_remaining(self, action_type: str) -> int:
        """Get remaining allowed actions for today."""
        self._maybe_reset_daily_counts()
        limit = self.limits.get(action_type, 999)
        count = self._get_count(action_type)
        return max(0, limit - count)

    def get_daily_summary(self) -> Dict[str, Any]:
        """Get today's action counts and remaining limits."""
        self._maybe_reset_daily_counts()
        today = str(date.today())
        counts = self._state.get(today, {})

        summary = {}
        for action_type, limit in self.limits.items():
            count = counts.get(action_type, 0)
            summary[action_type] = {
                "used": count,
                "limit": limit,
                "remaining": max(0, limit - count),
                "percentage": round(count / limit * 100, 1) if limit > 0 else 0,
            }
        return summary

    def is_safe_to_continue(self) -> bool:
        """
        Check if it's safe to continue automation.
        Returns False if critical limits are nearly exhausted.
        """
        connection_remaining = self.get_remaining("connection_request")
        message_remaining = self.get_remaining("message")

        # Stop if both connection and message limits are exhausted
        if connection_remaining == 0 and message_remaining == 0:
            return False

        return True

    def reduce_limits(self, factor: float = 0.8) -> None:
        """
        Reduce limits (called when LinkedIn warning is detected).
        Learns to be more conservative after warnings.
        """
        for key in self.limits:
            self.limits[key] = max(1, int(self.limits[key] * factor))
        logger.warning(
            f"[RateLimiter] Limits reduced by {int((1-factor)*100)}% due to warning detection"
        )
        self._save_state()

    def increase_delays(self, factor: float = 1.5) -> None:
        """Increase minimum delays (called when suspicious activity detected)."""
        for key in self.min_delays:
            self.min_delays[key] = self.min_delays[key] * factor
        logger.warning(f"[RateLimiter] Delays increased by {int((factor-1)*100)}%")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _is_within_limit(self, action_type: str) -> bool:
        """Check if action count is within daily limit."""
        limit = self.limits.get(action_type)
        if limit is None:
            return True  # No limit defined = unlimited
        return self._get_count(action_type) < limit

    def _get_count(self, action_type: str) -> int:
        """Get today's count for an action type."""
        today = str(date.today())
        return self._state.get(today, {}).get(action_type, 0)

    async def _wait_for_delay(self, action_type: str) -> None:
        """Wait for the minimum delay since the last action of this type."""
        min_delay = self.min_delays.get(action_type, 0)
        if min_delay <= 0:
            return

        last_time = self._last_action_time.get(action_type, 0)
        elapsed = time.time() - last_time
        remaining_wait = min_delay - elapsed

        if remaining_wait > 0:
            # Add jitter (±30% of remaining wait)
            jitter = random.uniform(-remaining_wait * 0.3, remaining_wait * 0.3)
            actual_wait = max(0, remaining_wait + jitter)

            if actual_wait > 1:
                logger.debug(
                    f"[RateLimiter] Waiting {actual_wait:.1f}s before '{action_type}'"
                )
            await asyncio.sleep(actual_wait)

    def _maybe_reset_daily_counts(self) -> None:
        """Reset counts if it's a new day."""
        today = str(date.today())
        # Clean up old days (keep only last 7 days)
        old_days = [d for d in self._state if d != today and d < str(date.today())]
        for old_day in old_days[:-7]:  # Keep last 7 days
            del self._state[old_day]

    def _load_state(self) -> None:
        """Load rate limit state from disk."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                    self._state = data.get("counts", {})
                    # Restore learned limits if available
                    if "learned_limits" in data:
                        self.limits.update(data["learned_limits"])
            except Exception as e:
                logger.debug(f"Could not load rate limit state: {e}")
                self._state = {}
        else:
            self._state = {}

    def _save_state(self) -> None:
        """Save rate limit state to disk."""
        try:
            os.makedirs(os.path.dirname(self.state_file) if os.path.dirname(self.state_file) else ".", exist_ok=True)
            with open(self.state_file, "w") as f:
                json.dump({
                    "counts": self._state,
                    "learned_limits": self.limits,
                    "updated_at": datetime.utcnow().isoformat(),
                }, f, indent=2)
        except Exception as e:
            logger.debug(f"Could not save rate limit state: {e}")
