"""
Persona Manager — Manages multiple LinkedIn accounts/personas.

Supports running automation across multiple LinkedIn accounts
with isolated sessions, rate limits, and fingerprints per persona.

Each persona has:
  - Credentials (email/password)
  - Session state (cookies)
  - Browser fingerprint (user agent, viewport)
  - Rate limit state (daily action counts)
  - Activity log
"""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Any, Dict, List, Optional

from loguru import logger


class Persona:
    """Represents a single LinkedIn account/persona."""

    def __init__(
        self,
        name: str,
        email: str,
        password: str,
        profile_idx: int = 0,
        daily_limits: Optional[Dict[str, int]] = None,
        notes: str = "",
    ):
        self.name = name
        self.email = email
        self.password = password
        self.profile_idx = profile_idx  # Browser fingerprint profile index
        self.daily_limits = daily_limits or {
            "connection_request": 15,
            "message": 8,
            "profile_view": 80,
        }
        self.notes = notes
        self.is_active = True
        self.is_banned = False
        self.last_used: Optional[str] = None
        self._daily_counts: Dict[str, Dict[str, int]] = {}

    def record_action(self, action_type: str) -> None:
        """Record an action for today."""
        today = str(date.today())
        if today not in self._daily_counts:
            self._daily_counts[today] = {}
        self._daily_counts[today][action_type] = (
            self._daily_counts[today].get(action_type, 0) + 1
        )
        self.last_used = today

    def get_remaining(self, action_type: str) -> int:
        """Get remaining actions for today."""
        today = str(date.today())
        used = self._daily_counts.get(today, {}).get(action_type, 0)
        limit = self.daily_limits.get(action_type, 999)
        return max(0, limit - used)

    def is_within_limit(self, action_type: str) -> bool:
        """Check if action is within daily limit."""
        return self.get_remaining(action_type) > 0

    def mark_banned(self) -> None:
        """Mark this persona as banned."""
        self.is_banned = True
        self.is_active = False
        logger.warning(f"[PersonaManager] Persona '{self.name}' marked as banned!")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict (without password)."""
        return {
            "name": self.name,
            "email": self.email,
            "profile_idx": self.profile_idx,
            "daily_limits": self.daily_limits,
            "notes": self.notes,
            "is_active": self.is_active,
            "is_banned": self.is_banned,
            "last_used": self.last_used,
        }


class PersonaManager:
    """
    Manages a pool of LinkedIn personas for multi-account automation.

    Features:
      - Round-robin persona selection
      - Per-persona rate limiting
      - Automatic persona rotation when limits reached
      - Ban detection and persona deactivation
      - Session state persistence per persona
    """

    def __init__(
        self,
        personas_file: str = "workspace/personas.json",
        sessions_dir: str = "workspace/sessions",
    ):
        self.personas_file = personas_file
        self.sessions_dir = sessions_dir
        self._personas: List[Persona] = []
        self._current_idx: int = 0

        os.makedirs(sessions_dir, exist_ok=True)
        self._load_personas()

    # ── Persona Management ────────────────────────────────────────────────────

    def add_persona(
        self,
        name: str,
        email: str,
        password: str,
        profile_idx: Optional[int] = None,
        daily_limits: Optional[Dict[str, int]] = None,
    ) -> Persona:
        """Add a new persona."""
        idx = profile_idx if profile_idx is not None else len(self._personas)
        persona = Persona(
            name=name,
            email=email,
            password=password,
            profile_idx=idx,
            daily_limits=daily_limits,
        )
        self._personas.append(persona)
        self._save_personas()
        logger.info(f"[PersonaManager] Added persona: {name} ({email})")
        return persona

    def remove_persona(self, name: str) -> bool:
        """Remove a persona by name."""
        before = len(self._personas)
        self._personas = [p for p in self._personas if p.name != name]
        if len(self._personas) < before:
            self._save_personas()
            logger.info(f"[PersonaManager] Removed persona: {name}")
            return True
        return False

    def get_persona(self, name: str) -> Optional[Persona]:
        """Get a persona by name."""
        return next((p for p in self._personas if p.name == name), None)

    def list_personas(self) -> List[Dict[str, Any]]:
        """List all personas (without passwords)."""
        return [p.to_dict() for p in self._personas]

    # ── Persona Selection ─────────────────────────────────────────────────────

    def get_active_persona(
        self,
        action_type: Optional[str] = None,
    ) -> Optional[Persona]:
        """
        Get the next available active persona.

        Args:
            action_type: If provided, only return personas with remaining quota

        Returns:
            Persona or None if no active personas available
        """
        active = [
            p for p in self._personas
            if p.is_active and not p.is_banned
        ]

        if not active:
            logger.warning("[PersonaManager] No active personas available")
            return None

        if action_type:
            active = [p for p in active if p.is_within_limit(action_type)]
            if not active:
                logger.warning(
                    f"[PersonaManager] All personas have reached daily limit for '{action_type}'"
                )
                return None

        # Round-robin selection
        self._current_idx = self._current_idx % len(active)
        persona = active[self._current_idx]
        self._current_idx = (self._current_idx + 1) % len(active)

        return persona

    def rotate_persona(self) -> Optional[Persona]:
        """Force rotation to the next persona."""
        self._current_idx = (self._current_idx + 1) % max(1, len(self._personas))
        return self.get_active_persona()

    # ── Session Management ────────────────────────────────────────────────────

    def get_session_path(self, persona: Persona) -> str:
        """Get the session file path for a persona."""
        safe_name = persona.name.replace(" ", "_").lower()
        return os.path.join(self.sessions_dir, f"{safe_name}_session.json")

    def has_session(self, persona: Persona) -> bool:
        """Check if a persona has a saved session."""
        return os.path.exists(self.get_session_path(persona))

    def delete_session(self, persona: Persona) -> bool:
        """Delete a persona's session (force re-login)."""
        path = self.get_session_path(persona)
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"[PersonaManager] Deleted session for: {persona.name}")
            return True
        return False

    # ── Status & Reporting ────────────────────────────────────────────────────

    def get_daily_summary(self) -> Dict[str, Any]:
        """Get today's usage summary across all personas."""
        today = str(date.today())
        summary = {}

        for persona in self._personas:
            counts = persona._daily_counts.get(today, {})
            summary[persona.name] = {
                "active": persona.is_active,
                "banned": persona.is_banned,
                "actions_today": counts,
                "remaining": {
                    action: persona.get_remaining(action)
                    for action in persona.daily_limits
                },
            }

        return summary

    def mark_persona_banned(self, name: str) -> bool:
        """Mark a persona as banned."""
        persona = self.get_persona(name)
        if persona:
            persona.mark_banned()
            self._save_personas()
            return True
        return False

    def get_total_remaining(self, action_type: str) -> int:
        """Get total remaining actions across all active personas."""
        return sum(
            p.get_remaining(action_type)
            for p in self._personas
            if p.is_active and not p.is_banned
        )

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_personas(self) -> None:
        """Save persona metadata to disk (without passwords)."""
        try:
            os.makedirs(
                os.path.dirname(self.personas_file)
                if os.path.dirname(self.personas_file) else ".",
                exist_ok=True,
            )
            data = [
                {
                    **p.to_dict(),
                    # Store encrypted password hint (not plaintext in production)
                    "email": p.email,
                }
                for p in self._personas
            ]
            with open(self.personas_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"[PersonaManager] Failed to save personas: {e}")

    def _load_personas(self) -> None:
        """Load persona metadata from disk."""
        if not os.path.exists(self.personas_file):
            return

        try:
            with open(self.personas_file) as f:
                data = json.load(f)

            for item in data:
                # Note: passwords are not stored in the JSON file
                # They must be provided via environment variables or .env
                persona = Persona(
                    name=item["name"],
                    email=item["email"],
                    password=os.getenv(
                        f"LINKEDIN_PASSWORD_{item['name'].upper().replace(' ', '_')}",
                        os.getenv("LINKEDIN_PASSWORD", ""),
                    ),
                    profile_idx=item.get("profile_idx", 0),
                    daily_limits=item.get("daily_limits"),
                    notes=item.get("notes", ""),
                )
                persona.is_active = item.get("is_active", True)
                persona.is_banned = item.get("is_banned", False)
                persona.last_used = item.get("last_used")
                self._personas.append(persona)

            logger.info(f"[PersonaManager] Loaded {len(self._personas)} personas")

        except Exception as e:
            logger.error(f"[PersonaManager] Failed to load personas: {e}")

    def __len__(self) -> int:
        return len(self._personas)

    def __repr__(self) -> str:
        active = sum(1 for p in self._personas if p.is_active and not p.is_banned)
        return f"PersonaManager({len(self._personas)} personas, {active} active)"
