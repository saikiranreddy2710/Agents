"""
Experience Engine — RAG retrieval from ChromaDB.

Retrieves relevant past experiences to enrich LLM prompts before decisions.
This is the "memory recall" half of the self-evolution loop:

  Screenshot/Context → Experience Engine → Retrieved Experiences
                     → Enrich Prompt → Better Decision

Collections queried:
  - action_outcomes      → What worked/failed for similar actions
  - screenshot_patterns  → Visual UI patterns recognized before
  - procedural_memory    → Successful action sequences (macros)
  - personalization      → Connection notes/messages that worked
"""

from __future__ import annotations

import hashlib
import os
from typing import Any, Dict, List, Optional

from loguru import logger

# ── Mooncake KVCache-inspired Experience Cache ────────────────────────────────
# Eliminates redundant ChromaDB round-trips within a session.
# Cache key = MD5(query | page_url | action_type | collections).
# TTL = 300s (5 min); maxsize = 128 entries.
# Inspired by Mooncake (arXiv:2407.00079): KVCache-centric architecture that
# separates compute from memory access to maximise effective throughput.
try:
    from cachetools import TTLCache
    _experience_cache: TTLCache = TTLCache(maxsize=128, ttl=300)
    _CACHE_AVAILABLE = True
except ImportError:
    _experience_cache = {}          # type: ignore[assignment]
    _CACHE_AVAILABLE = False


def _make_cache_key(
    query: str,
    page_url: str,
    action_type: str,
    collections: List[str],
) -> str:
    """Create a deterministic cache key for experience retrieval."""
    raw = f"{query}|{page_url}|{action_type}|{','.join(sorted(collections))}"
    return hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()


class ExperienceEngine:
    """
    Retrieves relevant past experiences from ChromaDB using semantic search.

    The agent calls retrieve() before every decision to get context from
    past interactions — making it progressively smarter over time.
    """

    def __init__(self, chroma_client=None):
        """
        Args:
            chroma_client: Optional pre-initialized ChromaDB client.
                           If None, will lazy-initialize on first use.
        """
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
            logger.warning(f"ChromaDB not available, experience engine disabled: {e}")
            return False

    # ── Core Retrieval ────────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        context: Optional[str] = None,
        page_url: Optional[str] = None,
        action_type: Optional[str] = None,
        n_results: int = 5,
        collections: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant past experiences for a given query/context.

        Mooncake KVCache optimisation: results are cached in a module-level
        TTLCache (5-min TTL, 128 entries) so repeated calls with the same
        query/URL/action within a session skip ChromaDB entirely.

        Args:
            query:       The current task or action description
            context:     Additional context (page title, DOM summary, etc.)
            page_url:    Current page URL (used to filter relevant experiences)
            action_type: Type of action being considered (click, type, navigate, etc.)
            n_results:   Number of experiences to retrieve per collection
            collections: Which collections to query (default: all relevant)

        Returns:
            List of experience dicts sorted by relevance, each with:
            {"content": str, "similarity_score": float, "outcome": str,
             "collection": str, "metadata": dict}
        """
        if not self._ensure_initialized():
            return []

        target_collections = collections or self._get_relevant_collections(action_type)

        # ── Cache lookup (Mooncake KVCache concept) ───────────────────────────
        cache_key = _make_cache_key(
            query, page_url or "", action_type or "", target_collections
        )
        if _CACHE_AVAILABLE and cache_key in _experience_cache:
            logger.debug(f"[ExperienceEngine] Cache HIT for: {query[:60]}")
            return _experience_cache[cache_key]

        search_query = self._build_search_query(query, context, page_url, action_type)
        all_experiences: List[Dict[str, Any]] = []

        for collection_name in target_collections:
            collection = self._collections.get(collection_name)
            if collection is None:
                continue
            try:
                results = collection.query(
                    query_texts=[search_query],
                    n_results=min(n_results, self._get_collection_count(collection)),
                    include=["documents", "metadatas", "distances"],
                )
                experiences = self._parse_results(results, collection_name)
                all_experiences.extend(experiences)
            except Exception as e:
                logger.debug(f"Experience retrieval from '{collection_name}' failed: {e}")

        # Sort by similarity score (highest first) and deduplicate
        all_experiences.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
        final = self._deduplicate(all_experiences)[:n_results * 2]

        # ── Store in cache ────────────────────────────────────────────────────
        if _CACHE_AVAILABLE:
            _experience_cache[cache_key] = final

        return final

    def retrieve_for_screenshot(
        self,
        screenshot_description: str,
        page_url: str = "",
        n_results: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve experiences relevant to a specific screenshot/visual state.
        Queries the screenshot_patterns collection.
        """
        return self.retrieve(
            query=screenshot_description,
            page_url=page_url,
            collections=["screenshot_patterns", "action_outcomes"],
            n_results=n_results,
        )

    def retrieve_for_linkedin_action(
        self,
        action_description: str,
        profile_context: Optional[str] = None,
        n_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve experiences relevant to a LinkedIn-specific action.
        Queries all LinkedIn-relevant collections.
        """
        context = profile_context or ""
        return self.retrieve(
            query=action_description,
            context=context,
            collections=[
                "action_outcomes",
                "screenshot_patterns",
                "personalization",
                "procedural_memory",
            ],
            n_results=n_results,
        )

    def retrieve_personalization(
        self,
        profile_info: str,
        n_results: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve successful personalization examples (connection notes, messages).
        Used by connection_agent and message_agent.
        """
        return self.retrieve(
            query=profile_info,
            collections=["personalization"],
            n_results=n_results,
        )

    def retrieve_procedural(
        self,
        task_description: str,
        n_results: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve successful action sequences (procedural memory / macros).
        Used to replay known-good workflows.
        """
        return self.retrieve(
            query=task_description,
            collections=["procedural_memory"],
            n_results=n_results,
        )

    # ── Helper Methods ────────────────────────────────────────────────────────

    def _build_search_query(
        self,
        query: str,
        context: Optional[str],
        page_url: Optional[str],
        action_type: Optional[str],
    ) -> str:
        """Build an enriched search query for ChromaDB."""
        parts = [query]
        if action_type:
            parts.append(f"action:{action_type}")
        if page_url:
            # Extract domain for context
            try:
                from urllib.parse import urlparse
                domain = urlparse(page_url).netloc
                parts.append(f"site:{domain}")
            except Exception:
                pass
        if context:
            parts.append(context[:200])
        return " | ".join(parts)

    def _get_relevant_collections(self, action_type: Optional[str]) -> List[str]:
        """Determine which collections to query based on action type."""
        base = ["action_outcomes", "screenshot_patterns"]

        if action_type in ("type", "fill"):
            base.append("personalization")
        if action_type in ("navigate", "click"):
            base.append("procedural_memory")

        return base

    def _get_collection_count(self, collection) -> int:
        """Safely get the count of items in a collection."""
        try:
            return collection.count()
        except Exception:
            return 0

    def _parse_results(
        self,
        results: Dict[str, Any],
        collection_name: str,
    ) -> List[Dict[str, Any]]:
        """Parse ChromaDB query results into experience dicts."""
        experiences = []
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc, meta, dist in zip(documents, metadatas, distances):
            # ChromaDB distance → similarity score (lower distance = higher similarity)
            similarity = max(0.0, 1.0 - dist)
            experiences.append(
                {
                    "content": doc,
                    "similarity_score": similarity,
                    "outcome": meta.get("outcome", "unknown"),
                    "action_type": meta.get("action_type", ""),
                    "page_url": meta.get("page_url", ""),
                    "collection": collection_name,
                    "metadata": meta,
                }
            )
        return experiences

    def _deduplicate(self, experiences: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate experiences based on content similarity."""
        seen_contents = set()
        unique = []
        for exp in experiences:
            content_key = exp["content"][:100]  # First 100 chars as key
            if content_key not in seen_contents:
                seen_contents.add(content_key)
                unique.append(exp)
        return unique

    def format_for_prompt(
        self,
        experiences: List[Dict[str, Any]],
        max_experiences: int = 5,
    ) -> str:
        """
        Format retrieved experiences as a string block for prompt injection.

        Returns a formatted string ready to be inserted into an LLM prompt.
        """
        if not experiences:
            return ""

        lines = ["📚 Relevant Past Experiences (use these to make better decisions):"]
        for i, exp in enumerate(experiences[:max_experiences], 1):
            score = exp.get("similarity_score", 0)
            outcome = exp.get("outcome", "unknown")
            content = exp.get("content", "")
            collection = exp.get("collection", "")

            outcome_emoji = "✅" if outcome == "success" else "❌" if outcome == "failure" else "⚠️"
            lines.append(
                f"  [{i}] {outcome_emoji} (score={score:.2f}, from={collection})\n"
                f"      {content[:300]}"
            )

        return "\n".join(lines)

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_memory_stats(self) -> Dict[str, int]:
        """Return count of records in each collection."""
        if not self._ensure_initialized():
            return {}

        stats = {}
        for name, collection in self._collections.items():
            try:
                stats[name] = collection.count()
            except Exception:
                stats[name] = -1
        return stats
