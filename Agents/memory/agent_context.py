"""
Agent Context — Tracks and persists agent state across sessions.

Responsibilities:
  - Store current agent state (URL, task, iteration, working memory)
  - Persist state to ChromaDB so it survives restarts
  - Load previous session context on startup
  - Track which profiles have been contacted (deduplication)
  - Maintain session history for episodic memory
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger


class AgentContextManager:
    """
    Manages agent state persistence across sessions.

    Working memory (in-RAM) is fast but ephemeral.
    ChromaDB persistence survives restarts and enables cross-session learning.
    """

    def __init__(self, session_id: Optional[str] = None, chroma_client=None):
        self.session_id = session_id or str(uuid.uuid4())
        self._client = chroma_client
        self._collection = None
        self._initialized = False

        # In-memory working memory (fast, ephemeral)
        self._working_memory: Dict[str, Any] = {
            "session_id": self.session_id,
            "current_task": "",
            "current_url": "",
            "current_page_title": "",
            "iteration": 0,
            "agent_name": "",
            "status": "idle",
            "contacted_profiles": [],   # LinkedIn URLs contacted this session
            "scraped_profiles": [],     # LinkedIn URLs scraped this session
            "actions_taken": [],        # Actions taken this session
            "errors": [],               # Errors encountered
            "notes": {},                # Arbitrary key-value notes
            "started_at": datetime.utcnow().isoformat(),
        }

    def _ensure_initialized(self) -> bool:
        if self._initialized:
            return True
        try:
            from memory.chroma_client import get_chroma_client
            from memory.collections import get_collection
            if self._client is None:
                self._client = get_chroma_client()
            self._collection = get_collection(self._client, "agent_context")
            self._initialized = True
            return True
        except Exception as e:
            logger.warning(f"AgentContext ChromaDB init failed: {e}")
            return False

    # ── Working Memory (in-RAM, fast) ─────────────────────────────────────────

    def set(self, key: str, value: Any) -> None:
        """Set a value in working memory."""
        self._working_memory[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from working memory."""
        return self._working_memory.get(key, default)

    def update(self, data: Dict[str, Any]) -> None:
        """Update multiple values in working memory."""
        self._working_memory.update(data)

    def get_all(self) -> Dict[str, Any]:
        """Get the full working memory dict."""
        return dict(self._working_memory)

    # ── Task & URL Tracking ───────────────────────────────────────────────────

    def set_task(self, task: str) -> None:
        """Update the current task."""
        self._working_memory["current_task"] = task

    def set_url(self, url: str) -> None:
        """Update the current URL."""
        self._working_memory["current_url"] = url

    def set_page_title(self, title: str) -> None:
        """Update the current page title."""
        self._working_memory["current_page_title"] = title

    def increment_iteration(self) -> int:
        """Increment and return the current iteration count."""
        self._working_memory["iteration"] = self._working_memory.get("iteration", 0) + 1
        return self._working_memory["iteration"]

    def set_status(self, status: str) -> None:
        """Update agent status: idle | running | waiting | finished | failed"""
        self._working_memory["status"] = status

    # ── Profile Tracking (deduplication) ─────────────────────────────────────

    def mark_profile_contacted(self, linkedin_url: str, note: str = "") -> None:
        """Mark a LinkedIn profile as contacted this session."""
        contacted = self._working_memory.setdefault("contacted_profiles", [])
        if linkedin_url not in contacted:
            contacted.append(linkedin_url)
        # Also persist to ChromaDB
        self._persist_profile_contact(linkedin_url, "contacted", note)

    def mark_profile_scraped(self, linkedin_url: str) -> None:
        """Mark a LinkedIn profile as scraped this session."""
        scraped = self._working_memory.setdefault("scraped_profiles", [])
        if linkedin_url not in scraped:
            scraped.append(linkedin_url)

    def was_profile_contacted(self, linkedin_url: str) -> bool:
        """Check if a profile was contacted in this session."""
        return linkedin_url in self._working_memory.get("contacted_profiles", [])

    def was_profile_contacted_ever(self, linkedin_url: str) -> bool:
        """
        Check if a profile was ever contacted (across all sessions).
        Queries ChromaDB for historical contact records.
        """
        if not self._ensure_initialized():
            return self.was_profile_contacted(linkedin_url)

        try:
            from memory.collections import get_collection
            profiles_collection = get_collection(self._client, "linkedin_profiles")
            if profiles_collection is None:
                return False

            results = profiles_collection.query(
                query_texts=[linkedin_url],
                n_results=1,
                where={"linkedin_url": linkedin_url, "interaction_type": "connected"},
            )
            docs = results.get("documents", [[]])[0]
            return len(docs) > 0
        except Exception as e:
            logger.debug(f"Profile contact check failed: {e}")
            return False

    # ── Action Tracking ───────────────────────────────────────────────────────

    def record_action(
        self,
        action_type: str,
        params: Dict[str, Any],
        outcome: str,
        error: str = "",
    ) -> None:
        """Record an action taken this session."""
        actions = self._working_memory.setdefault("actions_taken", [])
        actions.append(
            {
                "action_type": action_type,
                "params": params,
                "outcome": outcome,
                "error": error,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    def record_error(self, error: str, context: str = "") -> None:
        """Record an error encountered this session."""
        errors = self._working_memory.setdefault("errors", [])
        errors.append(
            {
                "error": error,
                "context": context,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    def get_action_history(self) -> List[Dict[str, Any]]:
        """Get all actions taken this session."""
        return self._working_memory.get("actions_taken", [])

    def get_success_rate(self) -> float:
        """Calculate success rate for this session."""
        actions = self.get_action_history()
        if not actions:
            return 0.0
        successes = sum(1 for a in actions if a.get("outcome") == "success")
        return successes / len(actions)

    # ── Notes (arbitrary key-value store) ────────────────────────────────────

    def note(self, key: str, value: Any) -> None:
        """Store an arbitrary note in working memory."""
        notes = self._working_memory.setdefault("notes", {})
        notes[key] = value

    def get_note(self, key: str, default: Any = None) -> Any:
        """Retrieve a note from working memory."""
        return self._working_memory.get("notes", {}).get(key, default)

    # ── ChromaDB Persistence ──────────────────────────────────────────────────

    def save_session_state(self) -> bool:
        """
        Persist current session state to ChromaDB.
        Call this periodically and at session end.
        """
        if not self._ensure_initialized():
            return False

        try:
            state_summary = (
                f"Session: {self.session_id}\n"
                f"Task: {self._working_memory.get('current_task', '')}\n"
                f"Status: {self._working_memory.get('status', 'unknown')}\n"
                f"Iterations: {self._working_memory.get('iteration', 0)}\n"
                f"Actions: {len(self._working_memory.get('actions_taken', []))}\n"
                f"Success rate: {self.get_success_rate():.1%}\n"
                f"Contacted: {len(self._working_memory.get('contacted_profiles', []))} profiles"
            )

            metadata = {
                "type": "session_state",
                "task_type": "session",
                "session_id": self.session_id,
                "status": self._working_memory.get("status", "unknown"),
                "iteration": self._working_memory.get("iteration", 0),
                "strategy_json": json.dumps(
                    {
                        "contacted_profiles": self._working_memory.get("contacted_profiles", []),
                        "success_rate": self.get_success_rate(),
                        "action_count": len(self._working_memory.get("actions_taken", [])),
                    }
                ),
                "confidence": self.get_success_rate(),
                "timestamp": datetime.utcnow().isoformat(),
            }

            record_id = f"session_{self.session_id}"
            self._collection.upsert(
                documents=[state_summary],
                metadatas=[metadata],
                ids=[record_id],
            )
            return True

        except Exception as e:
            logger.error(f"Failed to save session state: {e}")
            return False

    def load_previous_session(self, task: str) -> Optional[Dict[str, Any]]:
        """
        Load context from the most recent similar session.
        Used to resume interrupted tasks or learn from past sessions.
        """
        if not self._ensure_initialized():
            return None

        try:
            results = self._collection.query(
                query_texts=[task],
                n_results=1,
                where={"type": "session_state"},
            )
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]

            if docs and metas:
                meta = metas[0]
                strategy = json.loads(meta.get("strategy_json", "{}"))
                return {
                    "session_id": meta.get("session_id", ""),
                    "status": meta.get("status", ""),
                    "iteration": meta.get("iteration", 0),
                    "contacted_profiles": strategy.get("contacted_profiles", []),
                    "success_rate": strategy.get("success_rate", 0.0),
                    "summary": docs[0],
                }
        except Exception as e:
            logger.debug(f"Could not load previous session: {e}")

        return None

    def _persist_profile_contact(
        self, linkedin_url: str, interaction_type: str, note: str = ""
    ) -> None:
        """Persist a profile contact record to ChromaDB."""
        if not self._ensure_initialized():
            return
        try:
            from memory.collections import get_collection
            profiles_collection = get_collection(self._client, "linkedin_profiles")
            if profiles_collection is None:
                return

            doc_text = (
                f"URL: {linkedin_url}\n"
                f"Interaction: {interaction_type}\n"
                f"Note: {note}\n"
                f"Session: {self.session_id}"
            )
            metadata = {
                "linkedin_url": linkedin_url,
                "interaction_type": interaction_type,
                "name": "",
                "headline": "",
                "company": "",
                "location": "",
                "session_id": self.session_id,
                "timestamp": datetime.utcnow().isoformat(),
            }
            record_id = f"contact_{self.session_id}_{uuid.uuid4().hex[:8]}"
            profiles_collection.add(
                documents=[doc_text],
                metadatas=[metadata],
                ids=[record_id],
            )
        except Exception as e:
            logger.debug(f"Failed to persist profile contact: {e}")

    # ── Session Summary ───────────────────────────────────────────────────────

    def get_session_summary(self) -> Dict[str, Any]:
        """Get a summary of the current session."""
        actions = self.get_action_history()
        return {
            "session_id": self.session_id,
            "task": self._working_memory.get("current_task", ""),
            "status": self._working_memory.get("status", "idle"),
            "iterations": self._working_memory.get("iteration", 0),
            "total_actions": len(actions),
            "successful_actions": sum(1 for a in actions if a.get("outcome") == "success"),
            "failed_actions": sum(1 for a in actions if a.get("outcome") == "failure"),
            "success_rate": self.get_success_rate(),
            "contacted_profiles": len(self._working_memory.get("contacted_profiles", [])),
            "scraped_profiles": len(self._working_memory.get("scraped_profiles", [])),
            "errors": len(self._working_memory.get("errors", [])),
            "started_at": self._working_memory.get("started_at", ""),
            "current_url": self._working_memory.get("current_url", ""),
        }

    def reset(self) -> None:
        """Reset working memory for a new task (keeps session_id)."""
        session_id = self.session_id
        started_at = self._working_memory.get("started_at", datetime.utcnow().isoformat())
        self._working_memory = {
            "session_id": session_id,
            "current_task": "",
            "current_url": "",
            "current_page_title": "",
            "iteration": 0,
            "agent_name": "",
            "status": "idle",
            "contacted_profiles": [],
            "scraped_profiles": [],
            "actions_taken": [],
            "errors": [],
            "notes": {},
            "started_at": started_at,
        }
