"""
Backtracker — Rolls back failed plans to the last known-good state.

When a plan fails mid-execution and replanning isn't possible,
the Backtracker:
  1. Identifies the last known-good checkpoint
  2. Determines what state the browser/agent was in at that point
  3. Navigates back to that state
  4. Resumes execution from the checkpoint

Checkpoints are automatically created:
  - After each successful subtask
  - After login (most important checkpoint)
  - After navigating to a key page
  - Before risky operations (sending messages, connection requests)
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger


class Checkpoint:
    """A snapshot of agent state at a point in time."""

    def __init__(
        self,
        checkpoint_id: str,
        label: str,
        url: str,
        page_title: str,
        plan_state: Dict[str, Any],
        browser_storage_state: Optional[str] = None,
        timestamp: Optional[str] = None,
    ):
        self.checkpoint_id = checkpoint_id
        self.label = label
        self.url = url
        self.page_title = page_title
        self.plan_state = plan_state
        self.browser_storage_state = browser_storage_state  # Playwright storage state path
        self.timestamp = timestamp or datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "label": self.label,
            "url": self.url,
            "page_title": self.page_title,
            "plan_state": self.plan_state,
            "browser_storage_state": self.browser_storage_state,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Checkpoint":
        return cls(
            checkpoint_id=data["checkpoint_id"],
            label=data["label"],
            url=data["url"],
            page_title=data["page_title"],
            plan_state=data["plan_state"],
            browser_storage_state=data.get("browser_storage_state"),
            timestamp=data.get("timestamp"),
        )


class Backtracker:
    """
    Manages checkpoints and rollback for agent execution.

    Creates checkpoints at key moments and can roll back
    to any previous checkpoint when execution fails.
    """

    def __init__(self, max_checkpoints: int = 10):
        self.max_checkpoints = max_checkpoints
        self._checkpoints: List[Checkpoint] = []
        self._rollback_count: int = 0
        self._max_rollbacks: int = 3

    # ── Checkpoint Management ─────────────────────────────────────────────────

    def create_checkpoint(
        self,
        label: str,
        url: str,
        page_title: str,
        plan_state: Dict[str, Any],
        browser_storage_state: Optional[str] = None,
    ) -> Checkpoint:
        """
        Create a new checkpoint of the current state.

        Args:
            label:                  Human-readable label (e.g., "after_login", "before_connect")
            url:                    Current page URL
            page_title:             Current page title
            plan_state:             Current plan state (subtask statuses, etc.)
            browser_storage_state:  Path to Playwright storage state file (cookies, localStorage)

        Returns:
            The created Checkpoint
        """
        import uuid
        checkpoint = Checkpoint(
            checkpoint_id=str(uuid.uuid4()),
            label=label,
            url=url,
            page_title=page_title,
            plan_state=json.loads(json.dumps(plan_state)),  # Deep copy
            browser_storage_state=browser_storage_state,
        )

        self._checkpoints.append(checkpoint)

        # Trim old checkpoints if over limit
        if len(self._checkpoints) > self.max_checkpoints:
            self._checkpoints = self._checkpoints[-self.max_checkpoints:]

        logger.debug(f"Checkpoint created: '{label}' at {url}")
        return checkpoint

    def get_last_checkpoint(self) -> Optional[Checkpoint]:
        """Get the most recent checkpoint."""
        return self._checkpoints[-1] if self._checkpoints else None

    def get_checkpoint_by_label(self, label: str) -> Optional[Checkpoint]:
        """Get a checkpoint by its label (most recent matching)."""
        for cp in reversed(self._checkpoints):
            if cp.label == label:
                return cp
        return None

    def get_checkpoint_before_failure(
        self,
        failed_subtask_id: str,
        plan: Dict[str, Any],
    ) -> Optional[Checkpoint]:
        """
        Find the best checkpoint to roll back to after a failure.

        Strategy:
          1. Find the checkpoint created just before the failed subtask
          2. Fall back to the most recent successful checkpoint
          3. Fall back to the login checkpoint
          4. Fall back to the very first checkpoint
        """
        # Try to find checkpoint labeled for the failed subtask
        for cp in reversed(self._checkpoints):
            if f"before_{failed_subtask_id}" in cp.label:
                return cp

        # Find the last checkpoint where the plan was in a good state
        for cp in reversed(self._checkpoints):
            cp_plan = cp.plan_state
            cp_subtasks = cp_plan.get("subtasks", [])
            # Check if the failed subtask was still pending at this checkpoint
            for st in cp_subtasks:
                if st.get("task_id") == failed_subtask_id and st.get("status") == "pending":
                    return cp

        # Fall back to login checkpoint
        login_cp = self.get_checkpoint_by_label("after_login")
        if login_cp:
            return login_cp

        # Fall back to first checkpoint
        return self._checkpoints[0] if self._checkpoints else None

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """List all checkpoints."""
        return [cp.to_dict() for cp in self._checkpoints]

    def clear_checkpoints(self) -> None:
        """Clear all checkpoints."""
        self._checkpoints.clear()
        logger.debug("All checkpoints cleared")

    # ── Rollback ──────────────────────────────────────────────────────────────

    def can_rollback(self) -> bool:
        """Check if rollback is possible."""
        return (
            len(self._checkpoints) > 0
            and self._rollback_count < self._max_rollbacks
        )

    async def rollback(
        self,
        checkpoint: Checkpoint,
        page_controller=None,
    ) -> Dict[str, Any]:
        """
        Roll back to a checkpoint.

        Args:
            checkpoint:      The checkpoint to roll back to
            page_controller: PageController instance for browser navigation

        Returns:
            {
                "success": bool,
                "checkpoint": dict,
                "message": str,
            }
        """
        if self._rollback_count >= self._max_rollbacks:
            return {
                "success": False,
                "checkpoint": checkpoint.to_dict(),
                "message": f"Max rollbacks ({self._max_rollbacks}) exceeded",
            }

        self._rollback_count += 1
        logger.info(
            f"Rolling back to checkpoint '{checkpoint.label}' "
            f"(attempt {self._rollback_count}/{self._max_rollbacks})"
        )

        try:
            # Restore browser state if available
            if checkpoint.browser_storage_state and page_controller:
                await self._restore_browser_state(
                    checkpoint.browser_storage_state,
                    checkpoint.url,
                    page_controller,
                )
            elif page_controller and checkpoint.url:
                # Just navigate back to the checkpoint URL
                await page_controller.navigate(checkpoint.url)
                await page_controller.wait_for_load()

            return {
                "success": True,
                "checkpoint": checkpoint.to_dict(),
                "message": f"Rolled back to '{checkpoint.label}' at {checkpoint.url}",
                "plan_state": checkpoint.plan_state,
            }

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return {
                "success": False,
                "checkpoint": checkpoint.to_dict(),
                "message": f"Rollback failed: {e}",
            }

    def rollback_plan_state(
        self,
        plan: Dict[str, Any],
        checkpoint: Checkpoint,
    ) -> Dict[str, Any]:
        """
        Roll back the plan state to a checkpoint (without browser navigation).
        Used when only the plan state needs to be restored.
        """
        restored_plan = json.loads(json.dumps(checkpoint.plan_state))
        logger.info(f"Plan state rolled back to checkpoint '{checkpoint.label}'")
        return restored_plan

    # ── Auto-Checkpoint Helpers ───────────────────────────────────────────────

    def should_checkpoint(
        self,
        action_type: str,
        subtask_label: str = "",
    ) -> bool:
        """
        Determine if a checkpoint should be created before this action.

        Creates checkpoints before risky operations.
        """
        risky_actions = {
            "send_connection_request",
            "send_message",
            "click_connect",
            "submit_form",
            "login",
        }
        risky_labels = {
            "before_connect",
            "before_message",
            "before_login",
            "before_submit",
        }

        return (
            action_type in risky_actions
            or subtask_label in risky_labels
            or "connect" in action_type.lower()
            or "message" in action_type.lower()
            or "send" in action_type.lower()
        )

    async def _restore_browser_state(
        self,
        storage_state_path: str,
        url: str,
        page_controller,
    ) -> None:
        """Restore browser cookies/localStorage from a storage state file."""
        import os
        if os.path.exists(storage_state_path):
            # Playwright storage state restoration
            # This requires creating a new browser context with the saved state
            logger.info(f"Restoring browser state from {storage_state_path}")
            # Navigate to the checkpoint URL
            await page_controller.navigate(url)
            await page_controller.wait_for_load()
        else:
            logger.warning(f"Storage state file not found: {storage_state_path}")
            await page_controller.navigate(url)
            await page_controller.wait_for_load()

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get backtracker statistics."""
        return {
            "total_checkpoints": len(self._checkpoints),
            "rollback_count": self._rollback_count,
            "max_rollbacks": self._max_rollbacks,
            "can_rollback": self.can_rollback(),
            "checkpoint_labels": [cp.label for cp in self._checkpoints],
        }
