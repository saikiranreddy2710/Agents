"""
Experience Recorder — Records action outcomes back to ChromaDB.

This is the "learning" half of the self-evolution loop:

  Execute Action → Observe Outcome → Reflect → Record to ChromaDB
                                              → Future retrieval gets smarter

Records to:
  - action_outcomes      → Every action result (success/failure + context)
  - screenshot_patterns  → Visual patterns recognized from screenshots
  - procedural_memory    → Successful multi-step sequences
  - personalization      → Connection notes/messages that got accepted
  - linkedin_profiles    → Profiles interacted with
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger


class ExperienceRecorder:
    """
    Records agent experiences to ChromaDB for future RAG retrieval.

    Every action outcome — success or failure — is recorded with rich context
    so the agent can learn from it on future similar tasks.
    """

    def __init__(self, chroma_client=None):
        self._client = chroma_client
        self._collections: Dict[str, Any] = {}
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        """Lazy initialization of ChromaDB connection."""
        if self._initialized:
            return True
        try:
            from memory.chroma_client import get_chroma_client
            from memory.collections import get_or_create_collections

            self._client = get_chroma_client()
            self._collections = get_or_create_collections(self._client)
            self._initialized = True
            return True
        except Exception as e:
            logger.warning(f"ChromaDB not available, experience recorder disabled: {e}")
            return False

    # ── Core Recording ────────────────────────────────────────────────────────

    def record_action_outcome(
        self,
        action_type: str,
        action_params: Dict[str, Any],
        outcome: str,                    # "success" | "failure" | "partial"
        page_url: str = "",
        page_title: str = "",
        page_context: str = "",
        error_message: str = "",
        learned_pattern: str = "",
        session_id: str = "",
        tags: Optional[List[str]] = None,
    ) -> bool:
        """
        Record an action outcome to the action_outcomes collection.

        Args:
            action_type:     Type of action (click, type, navigate, etc.)
            action_params:   Parameters used for the action
            outcome:         "success" | "failure" | "partial"
            page_url:        URL where action was performed
            page_title:      Page title for context
            page_context:    DOM summary or description of page state
            error_message:   Error details if action failed
            learned_pattern: What pattern was recognized (from reflection)
            session_id:      Current session ID
            tags:            Additional tags for filtering

        Returns:
            True if recorded successfully, False otherwise
        """
        if not self._ensure_initialized():
            return False

        collection = self._collections.get("action_outcomes")
        if collection is None:
            return False

        try:
            # Build rich document text for embedding
            doc_text = self._build_action_document(
                action_type, action_params, outcome,
                page_url, page_title, page_context,
                error_message, learned_pattern,
            )

            metadata = {
                "action_type": action_type,
                "outcome": outcome,
                "page_url": page_url,
                "page_title": page_title,
                "error_message": error_message[:500] if error_message else "",
                "learned_pattern": learned_pattern[:500] if learned_pattern else "",
                "session_id": session_id,
                "tags": json.dumps(tags or []),
                "timestamp": datetime.utcnow().isoformat(),
            }

            record_id = str(uuid.uuid4())
            collection.add(
                documents=[doc_text],
                metadatas=[metadata],
                ids=[record_id],
            )
            logger.debug(f"Recorded action outcome: {action_type} → {outcome}")
            return True

        except Exception as e:
            logger.error(f"Failed to record action outcome: {e}")
            return False

    def record_screenshot_pattern(
        self,
        pattern_description: str,
        page_url: str = "",
        page_title: str = "",
        element_selectors: Optional[List[str]] = None,
        confidence: float = 1.0,
        session_id: str = "",
    ) -> bool:
        """
        Record a visual UI pattern recognized from a screenshot.

        Examples:
        - "LinkedIn login button is always at top-right with class 'nav__button-secondary'"
        - "LinkedIn search results show profile cards with class 'entity-result'"
        - "Connection request modal appears with 'Add a note' button"

        Args:
            pattern_description: Human-readable description of the pattern
            page_url:            URL where pattern was observed
            page_title:          Page title
            element_selectors:   CSS/XPath selectors for key elements
            confidence:          How confident we are in this pattern (0.0-1.0)
            session_id:          Current session ID
        """
        if not self._ensure_initialized():
            return False

        collection = self._collections.get("screenshot_patterns")
        if collection is None:
            return False

        try:
            doc_text = (
                f"Visual Pattern: {pattern_description}\n"
                f"Page: {page_title} ({page_url})\n"
                f"Selectors: {', '.join(element_selectors or [])}\n"
                f"Confidence: {confidence}"
            )

            metadata = {
                "pattern_description": pattern_description[:500],
                "page_url": page_url,
                "page_title": page_title,
                "selectors": json.dumps(element_selectors or []),
                "confidence": confidence,
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat(),
            }

            record_id = str(uuid.uuid4())
            collection.add(
                documents=[doc_text],
                metadatas=[metadata],
                ids=[record_id],
            )
            logger.debug(f"Recorded screenshot pattern: {pattern_description[:80]}")
            return True

        except Exception as e:
            logger.error(f"Failed to record screenshot pattern: {e}")
            return False

    def record_procedural_memory(
        self,
        task_description: str,
        action_sequence: List[Dict[str, Any]],
        success: bool,
        total_steps: int = 0,
        duration_seconds: float = 0.0,
        session_id: str = "",
    ) -> bool:
        """
        Record a successful multi-step action sequence as a procedural memory.

        These are "macros" — known-good workflows that can be replayed.
        Examples:
        - "LinkedIn login: navigate → fill email → fill password → click sign in"
        - "Send connection request: click Connect → click Add note → type note → Send"

        Args:
            task_description: What task this sequence accomplishes
            action_sequence:  List of actions taken (type + params)
            success:          Whether the sequence succeeded
            total_steps:      Number of steps in the sequence
            duration_seconds: How long the sequence took
            session_id:       Current session ID
        """
        if not self._ensure_initialized():
            return False

        collection = self._collections.get("procedural_memory")
        if collection is None:
            return False

        try:
            # Summarize the action sequence
            steps_summary = " → ".join(
                f"{a.get('action_type', a.get('type', 'unknown'))}"
                for a in action_sequence[:20]
            )

            doc_text = (
                f"Task: {task_description}\n"
                f"Steps: {steps_summary}\n"
                f"Total steps: {total_steps or len(action_sequence)}\n"
                f"Success: {success}\n"
                f"Duration: {duration_seconds:.1f}s"
            )

            metadata = {
                "task_description": task_description[:500],
                "steps_summary": steps_summary[:500],
                "action_sequence": json.dumps(action_sequence[:20]),
                "success": success,
                "total_steps": total_steps or len(action_sequence),
                "duration_seconds": duration_seconds,
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat(),
            }

            record_id = str(uuid.uuid4())
            collection.add(
                documents=[doc_text],
                metadatas=[metadata],
                ids=[record_id],
            )
            logger.debug(f"Recorded procedural memory: {task_description[:80]}")
            return True

        except Exception as e:
            logger.error(f"Failed to record procedural memory: {e}")
            return False

    def record_personalization(
        self,
        profile_info: str,
        message_or_note: str,
        message_type: str,              # "connection_note" | "message"
        outcome: str,                   # "accepted" | "replied" | "ignored" | "pending"
        profile_url: str = "",
        template_used: str = "",
        session_id: str = "",
    ) -> bool:
        """
        Record a personalized connection note or message and its outcome.

        Used to learn which personalization styles work best.

        Args:
            profile_info:      Summary of the recipient's profile
            message_or_note:   The actual note/message sent
            message_type:      "connection_note" or "message"
            outcome:           Result: "accepted", "replied", "ignored", "pending"
            profile_url:       LinkedIn profile URL
            template_used:     Which template was used to generate the message
            session_id:        Current session ID
        """
        if not self._ensure_initialized():
            return False

        collection = self._collections.get("personalization")
        if collection is None:
            return False

        try:
            doc_text = (
                f"Type: {message_type}\n"
                f"Profile: {profile_info}\n"
                f"Message: {message_or_note}\n"
                f"Outcome: {outcome}\n"
                f"Template: {template_used}"
            )

            metadata = {
                "message_type": message_type,
                "outcome": outcome,
                "profile_url": profile_url,
                "template_used": template_used,
                "message_length": len(message_or_note),
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat(),
            }

            record_id = str(uuid.uuid4())
            collection.add(
                documents=[doc_text],
                metadatas=[metadata],
                ids=[record_id],
            )
            logger.debug(f"Recorded personalization: {message_type} → {outcome}")
            return True

        except Exception as e:
            logger.error(f"Failed to record personalization: {e}")
            return False

    def record_linkedin_profile(
        self,
        profile_data: Dict[str, Any],
        interaction_type: str = "viewed",  # "viewed" | "connected" | "messaged" | "scraped"
        session_id: str = "",
    ) -> bool:
        """
        Record a LinkedIn profile interaction.

        Args:
            profile_data:     Profile information dict
            interaction_type: What was done with this profile
            session_id:       Current session ID
        """
        if not self._ensure_initialized():
            return False

        collection = self._collections.get("linkedin_profiles")
        if collection is None:
            return False

        try:
            name = profile_data.get("name", "Unknown")
            headline = profile_data.get("headline", "")
            company = profile_data.get("company", "")
            location = profile_data.get("location", "")
            url = profile_data.get("linkedin_url", "")

            doc_text = (
                f"Name: {name}\n"
                f"Headline: {headline}\n"
                f"Company: {company}\n"
                f"Location: {location}\n"
                f"Interaction: {interaction_type}\n"
                f"URL: {url}"
            )

            metadata = {
                "name": name,
                "headline": headline[:200],
                "company": company,
                "location": location,
                "linkedin_url": url,
                "interaction_type": interaction_type,
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat(),
            }

            record_id = str(uuid.uuid4())
            collection.add(
                documents=[doc_text],
                metadatas=[metadata],
                ids=[record_id],
            )
            logger.debug(f"Recorded LinkedIn profile: {name} ({interaction_type})")
            return True

        except Exception as e:
            logger.error(f"Failed to record LinkedIn profile: {e}")
            return False

    def record_reflection(
        self,
        reflection_data: Dict[str, Any],
        action_type: str = "",
        session_id: str = "",
    ) -> bool:
        """
        Record a reflection result (from ReflectionAgent) to action_outcomes.

        Args:
            reflection_data: Output from ReflectionAgent (learned, pattern, etc.)
            action_type:     The action that was reflected on
            session_id:      Current session ID
        """
        learned = reflection_data.get("learned", "")
        pattern = reflection_data.get("pattern", "")
        success = reflection_data.get("success", False)
        confidence = reflection_data.get("confidence", 0.5)

        if pattern:
            self.record_screenshot_pattern(
                pattern_description=pattern,
                confidence=confidence,
                session_id=session_id,
            )

        if learned:
            return self.record_action_outcome(
                action_type=action_type,
                action_params={},
                outcome="success" if success else "failure",
                learned_pattern=learned,
                session_id=session_id,
            )
        return True

    # ── Batch Recording ───────────────────────────────────────────────────────

    def record_session_summary(
        self,
        session_id: str,
        task: str,
        actions_taken: List[Dict[str, Any]],
        final_outcome: str,
        duration_seconds: float = 0.0,
    ) -> bool:
        """
        Record a full session summary as a procedural memory.
        Called at the end of each agent session.
        """
        successful_actions = [
            a for a in actions_taken
            if a.get("outcome") == "success" or a.get("status") == "success"
        ]

        return self.record_procedural_memory(
            task_description=task,
            action_sequence=actions_taken,
            success=(final_outcome == "success"),
            total_steps=len(actions_taken),
            duration_seconds=duration_seconds,
            session_id=session_id,
        )

    # ── Document Builder ──────────────────────────────────────────────────────

    def _build_action_document(
        self,
        action_type: str,
        action_params: Dict[str, Any],
        outcome: str,
        page_url: str,
        page_title: str,
        page_context: str,
        error_message: str,
        learned_pattern: str,
    ) -> str:
        """Build a rich text document for ChromaDB embedding."""
        params_str = json.dumps(action_params, ensure_ascii=False)[:300]

        parts = [
            f"Action: {action_type}",
            f"Params: {params_str}",
            f"Outcome: {outcome}",
        ]

        if page_title:
            parts.append(f"Page: {page_title}")
        if page_url:
            parts.append(f"URL: {page_url}")
        if page_context:
            parts.append(f"Context: {page_context[:300]}")
        if error_message:
            parts.append(f"Error: {error_message[:300]}")
        if learned_pattern:
            parts.append(f"Learned: {learned_pattern}")

        return "\n".join(parts)
