"""
Memory Manager — Unified 4-tier memory access layer.

Provides a single interface to all memory tiers:

  Tier 1: Working Memory   → In-RAM dict (AgentContextManager)
  Tier 2: Episodic Memory  → Full session replays (ChromaDB: agent_context)
  Tier 3: Semantic Memory  → Learned patterns + strategies (ChromaDB: screenshot_patterns, action_outcomes)
  Tier 4: Procedural Memory → Successful action sequences (ChromaDB: procedural_memory)

Usage:
    mm = MemoryManager(session_id="abc123")

    # Store
    mm.remember("current_task", "Send connection requests")
    mm.record_outcome("click", {...}, "success", page_url="...")
    mm.record_pattern("LinkedIn Connect button has class 'connect-button'")

    # Retrieve
    experiences = mm.recall("click Connect button on LinkedIn profile")
    context = mm.get_context()
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from loguru import logger

from .agent_context import AgentContextManager
from .chroma_client import get_chroma_client
from .collections import get_or_create_collections, get_collection_stats


class MemoryManager:
    """
    Unified interface to all 4 memory tiers.

    This is the single entry point for all memory operations.
    Agents interact with memory exclusively through this class.
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        chroma_client=None,
    ):
        # Initialize ChromaDB
        self._client = chroma_client
        self._collections: Dict[str, Any] = {}
        self._chroma_ready = False

        # Initialize working memory (always available, no ChromaDB needed)
        self.context = AgentContextManager(
            session_id=session_id,
            chroma_client=chroma_client,
        )
        self.session_id = self.context.session_id

        # Lazy-init ChromaDB
        self._init_chroma()

    def _init_chroma(self) -> bool:
        """Initialize ChromaDB connection and collections."""
        if self._chroma_ready:
            return True
        try:
            if self._client is None:
                self._client = get_chroma_client()
            self._collections = get_or_create_collections(self._client)
            self._chroma_ready = True
            logger.debug(f"MemoryManager: ChromaDB ready ({len(self._collections)} collections)")
            return True
        except Exception as e:
            logger.warning(f"MemoryManager: ChromaDB not available: {e}")
            return False

    # ── Tier 1: Working Memory ────────────────────────────────────────────────

    def remember(self, key: str, value: Any) -> None:
        """Store a value in working memory (in-RAM, fast)."""
        self.context.set(key, value)

    def recall_working(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from working memory."""
        return self.context.get(key, default)

    def get_context(self) -> Dict[str, Any]:
        """Get the full working memory context."""
        return self.context.get_all()

    def update_context(self, data: Dict[str, Any]) -> None:
        """Update multiple working memory values at once."""
        self.context.update(data)

    # ── Tier 2: Episodic Memory ───────────────────────────────────────────────

    def save_session(self) -> bool:
        """Persist current session state to ChromaDB (episodic memory)."""
        return self.context.save_session_state()

    def load_similar_session(self, task: str) -> Optional[Dict[str, Any]]:
        """Load context from the most recent similar session."""
        return self.context.load_previous_session(task)

    # ── Tier 3: Semantic Memory ───────────────────────────────────────────────

    def recall(
        self,
        query: str,
        context: Optional[str] = None,
        page_url: Optional[str] = None,
        action_type: Optional[str] = None,
        n_results: int = 5,
        collections: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant past experiences using semantic search.

        This is the main RAG retrieval method — call before every decision.

        Args:
            query:       What you're trying to do
            context:     Additional context (page description, DOM summary)
            page_url:    Current page URL
            action_type: Type of action being considered
            n_results:   Number of results to return
            collections: Which collections to search (default: all relevant)

        Returns:
            List of experience dicts sorted by relevance
        """
        from llm.experience_engine import ExperienceEngine
        engine = ExperienceEngine(chroma_client=self._client)
        return engine.retrieve(
            query=query,
            context=context,
            page_url=page_url,
            action_type=action_type,
            n_results=n_results,
            collections=collections,
        )

    def recall_for_screenshot(
        self,
        screenshot_description: str,
        page_url: str = "",
        n_results: int = 3,
    ) -> List[Dict[str, Any]]:
        """Retrieve experiences relevant to a screenshot/visual state."""
        from llm.experience_engine import ExperienceEngine
        engine = ExperienceEngine(chroma_client=self._client)
        return engine.retrieve_for_screenshot(
            screenshot_description=screenshot_description,
            page_url=page_url,
            n_results=n_results,
        )

    def recall_personalization(
        self,
        profile_info: str,
        n_results: int = 3,
    ) -> List[Dict[str, Any]]:
        """Retrieve successful personalization examples."""
        from llm.experience_engine import ExperienceEngine
        engine = ExperienceEngine(chroma_client=self._client)
        return engine.retrieve_personalization(
            profile_info=profile_info,
            n_results=n_results,
        )

    # ── Tier 4: Procedural Memory ─────────────────────────────────────────────

    def recall_procedure(
        self,
        task_description: str,
        n_results: int = 3,
    ) -> List[Dict[str, Any]]:
        """Retrieve successful action sequences for a task."""
        from llm.experience_engine import ExperienceEngine
        engine = ExperienceEngine(chroma_client=self._client)
        return engine.retrieve_procedural(
            task_description=task_description,
            n_results=n_results,
        )

    # ── Recording ─────────────────────────────────────────────────────────────

    def record_outcome(
        self,
        action_type: str,
        action_params: Dict[str, Any],
        outcome: str,
        page_url: str = "",
        page_title: str = "",
        page_context: str = "",
        error_message: str = "",
        learned_pattern: str = "",
    ) -> bool:
        """
        Record an action outcome to ChromaDB.
        Also updates working memory action history.
        """
        # Update working memory
        self.context.record_action(action_type, action_params, outcome, error_message)

        # Record to ChromaDB
        from llm.experience_recorder import ExperienceRecorder
        recorder = ExperienceRecorder(chroma_client=self._client)
        return recorder.record_action_outcome(
            action_type=action_type,
            action_params=action_params,
            outcome=outcome,
            page_url=page_url,
            page_title=page_title,
            page_context=page_context,
            error_message=error_message,
            learned_pattern=learned_pattern,
            session_id=self.session_id,
        )

    def record_pattern(
        self,
        pattern: str,
        page_url: str = "",
        selectors: Optional[List[str]] = None,
        confidence: float = 1.0,
    ) -> bool:
        """Record a visual UI pattern."""
        from llm.experience_recorder import ExperienceRecorder
        recorder = ExperienceRecorder(chroma_client=self._client)
        return recorder.record_screenshot_pattern(
            pattern_description=pattern,
            page_url=page_url,
            element_selectors=selectors,
            confidence=confidence,
            session_id=self.session_id,
        )

    def record_procedure(
        self,
        task_description: str,
        action_sequence: List[Dict[str, Any]],
        success: bool,
        duration_seconds: float = 0.0,
    ) -> bool:
        """Record a successful multi-step action sequence."""
        from llm.experience_recorder import ExperienceRecorder
        recorder = ExperienceRecorder(chroma_client=self._client)
        return recorder.record_procedural_memory(
            task_description=task_description,
            action_sequence=action_sequence,
            success=success,
            duration_seconds=duration_seconds,
            session_id=self.session_id,
        )

    def record_personalization(
        self,
        profile_info: str,
        message: str,
        message_type: str,
        outcome: str,
        profile_url: str = "",
    ) -> bool:
        """Record a personalization outcome."""
        from llm.experience_recorder import ExperienceRecorder
        recorder = ExperienceRecorder(chroma_client=self._client)
        return recorder.record_personalization(
            profile_info=profile_info,
            message_or_note=message,
            message_type=message_type,
            outcome=outcome,
            profile_url=profile_url,
            session_id=self.session_id,
        )

    def record_linkedin_profile(
        self,
        profile_data: Dict[str, Any],
        interaction_type: str = "viewed",
    ) -> bool:
        """Record a LinkedIn profile interaction."""
        from llm.experience_recorder import ExperienceRecorder
        recorder = ExperienceRecorder(chroma_client=self._client)
        return recorder.record_linkedin_profile(
            profile_data=profile_data,
            interaction_type=interaction_type,
            session_id=self.session_id,
        )

    # ── Profile Deduplication ─────────────────────────────────────────────────

    def mark_contacted(self, linkedin_url: str, note: str = "") -> None:
        """Mark a LinkedIn profile as contacted."""
        self.context.mark_profile_contacted(linkedin_url, note)

    def was_contacted(self, linkedin_url: str, check_all_sessions: bool = False) -> bool:
        """Check if a LinkedIn profile was already contacted."""
        if check_all_sessions:
            return self.context.was_profile_contacted_ever(linkedin_url)
        return self.context.was_profile_contacted(linkedin_url)

    def mark_scraped(self, linkedin_url: str) -> None:
        """Mark a LinkedIn profile as scraped."""
        self.context.mark_profile_scraped(linkedin_url)

    # ── Format for Prompt ─────────────────────────────────────────────────────

    def format_experiences_for_prompt(
        self,
        experiences: List[Dict[str, Any]],
        max_experiences: int = 5,
    ) -> str:
        """Format retrieved experiences as a string for prompt injection."""
        from llm.experience_engine import ExperienceEngine
        engine = ExperienceEngine()
        return engine.format_for_prompt(experiences, max_experiences)

    # ── Stats & Health ────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics across all tiers."""
        chroma_stats = {}
        if self._chroma_ready:
            chroma_stats = get_collection_stats(self._collections)

        session_summary = self.context.get_session_summary()

        return {
            "session": session_summary,
            "chroma_collections": chroma_stats,
            "chroma_ready": self._chroma_ready,
            "total_records": sum(
                v for v in chroma_stats.values() if isinstance(v, int) and v > 0
            ),
        }

    def is_healthy(self) -> bool:
        """Check if memory system is operational."""
        return self._chroma_ready

    def close(self) -> None:
        """Save session state and clean up."""
        self.context.set_status("finished")
        self.save_session()
        logger.debug(f"MemoryManager closed for session {self.session_id}")
