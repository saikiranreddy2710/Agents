"""
Evolution Engine — Self-improvement through strategy mutation and prompt evolution.

After accumulating enough experiences, the Evolution Engine:
  1. Analyzes patterns across all past experiences
  2. Identifies what works and what fails
  3. Rewrites/improves strategies and prompt templates
  4. A/B tests new strategies against old ones
  5. Keeps winners, discards losers

This is the "meta-learning" layer — the agent learns HOW to learn better.

Evolution triggers:
  - After N sessions (e.g., every 10 sessions)
  - When failure rate exceeds threshold (e.g., >30% failures)
  - When explicitly called by the orchestrator
  - After a new task type is encountered
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from .base_model import BaseLLM, get_llm
from .prompt_engine import EVOLUTION_PROMPT


class EvolutionEngine:
    """
    Self-improvement engine that evolves agent strategies over time.

    Works by:
    1. Pulling recent experiences from ChromaDB
    2. Asking the LLM to analyze patterns and suggest improvements
    3. Storing evolved strategies back to ChromaDB
    4. Injecting evolved strategies into future prompts
    """

    def __init__(
        self,
        llm: Optional[BaseLLM] = None,
        min_experiences_to_evolve: int = 10,
        evolution_interval_sessions: int = 10,
        failure_rate_threshold: float = 0.3,
    ):
        self.llm = llm or get_llm()
        self.min_experiences = min_experiences_to_evolve
        self.evolution_interval = evolution_interval_sessions
        self.failure_threshold = failure_rate_threshold
        self._collections: Dict[str, Any] = {}
        self._initialized = False
        self._strategies: Dict[str, Dict[str, Any]] = {}  # In-memory strategy cache

    def _ensure_initialized(self) -> bool:
        if self._initialized:
            return True
        try:
            from memory.chroma_client import get_chroma_client
            from memory.collections import get_or_create_collections
            client = get_chroma_client()
            self._collections = get_or_create_collections(client)
            self._initialized = True
            return True
        except Exception as e:
            logger.warning(f"ChromaDB not available for evolution engine: {e}")
            return False

    # ── Core Evolution ────────────────────────────────────────────────────────

    async def evolve(
        self,
        task_type: str,
        session_count: int = 0,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Run an evolution cycle for a specific task type.

        Args:
            task_type:     Type of task to evolve strategy for
                           (e.g., "linkedin_connect", "linkedin_search", "browser_navigate")
            session_count: Number of sessions completed (for interval check)
            force:         Force evolution even if interval not reached

        Returns:
            {
                "evolved": bool,
                "strategy": dict | None,
                "improvements": list,
                "reason": str,
            }
        """
        # Check if evolution should run
        if not force and not self._should_evolve(task_type, session_count):
            return {
                "evolved": False,
                "strategy": None,
                "improvements": [],
                "reason": "Evolution interval not reached",
            }

        if not self._ensure_initialized():
            return {
                "evolved": False,
                "strategy": None,
                "improvements": [],
                "reason": "ChromaDB not available",
            }

        # Pull recent experiences for this task type
        experiences = self._pull_experiences(task_type, limit=50)

        if len(experiences) < self.min_experiences:
            return {
                "evolved": False,
                "strategy": None,
                "improvements": [],
                "reason": f"Not enough experiences ({len(experiences)}/{self.min_experiences})",
            }

        # Analyze experiences and generate evolved strategy
        evolved_strategy = await self._generate_evolved_strategy(task_type, experiences)

        if not evolved_strategy:
            return {
                "evolved": False,
                "strategy": None,
                "improvements": [],
                "reason": "LLM failed to generate evolved strategy",
            }

        # Store evolved strategy
        self._store_strategy(task_type, evolved_strategy)

        logger.info(
            f"Evolution complete for '{task_type}': "
            f"{len(evolved_strategy.get('successful_patterns', []))} patterns, "
            f"confidence={evolved_strategy.get('confidence', 0):.2f}"
        )

        return {
            "evolved": True,
            "strategy": evolved_strategy,
            "improvements": evolved_strategy.get("successful_patterns", []),
            "reason": "Evolution successful",
        }

    async def evolve_all(self, session_count: int = 0) -> Dict[str, Any]:
        """Run evolution for all known task types."""
        task_types = self._get_known_task_types()
        results = {}
        for task_type in task_types:
            result = await self.evolve(task_type, session_count)
            results[task_type] = result
        return results

    # ── Strategy Retrieval ────────────────────────────────────────────────────

    def get_strategy(self, task_type: str) -> Optional[Dict[str, Any]]:
        """
        Get the current evolved strategy for a task type.
        Returns None if no strategy has been evolved yet.
        """
        # Check in-memory cache first
        if task_type in self._strategies:
            return self._strategies[task_type]

        # Try loading from ChromaDB
        if not self._ensure_initialized():
            return None

        collection = self._collections.get("agent_context")
        if collection is None:
            return None

        try:
            results = collection.query(
                query_texts=[f"evolved_strategy:{task_type}"],
                n_results=1,
                where={"type": "evolved_strategy", "task_type": task_type},
            )
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            if docs and metas:
                strategy = json.loads(metas[0].get("strategy_json", "{}"))
                self._strategies[task_type] = strategy
                return strategy
        except Exception as e:
            logger.debug(f"Could not load strategy for '{task_type}': {e}")

        return None

    def get_strategy_prompt_addition(self, task_type: str) -> str:
        """
        Get the evolved prompt addition for a task type.
        Returns empty string if no strategy evolved yet.
        """
        strategy = self.get_strategy(task_type)
        if not strategy:
            return ""
        return strategy.get("evolved_prompt_addition", "")

    def get_failure_modes(self, task_type: str) -> List[str]:
        """Get known failure modes for a task type."""
        strategy = self.get_strategy(task_type)
        if not strategy:
            return []
        return strategy.get("failure_modes", [])

    def get_successful_patterns(self, task_type: str) -> List[str]:
        """Get known successful patterns for a task type."""
        strategy = self.get_strategy(task_type)
        if not strategy:
            return []
        return strategy.get("successful_patterns", [])

    # ── A/B Testing ───────────────────────────────────────────────────────────

    async def ab_test_strategies(
        self,
        task_type: str,
        strategy_a: Dict[str, Any],
        strategy_b: Dict[str, Any],
        test_experiences: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        A/B test two strategies against a set of experiences.
        Returns the winner.
        """
        prompt = (
            f"Compare these two strategies for task type '{task_type}':\n\n"
            f"Strategy A:\n{json.dumps(strategy_a, indent=2)}\n\n"
            f"Strategy B:\n{json.dumps(strategy_b, indent=2)}\n\n"
            f"Test experiences:\n"
            + "\n".join(f"- {e.get('content', '')[:200]}" for e in test_experiences[:10])
            + "\n\nWhich strategy would perform better on these experiences? "
            "Respond in JSON: {\"winner\": \"A\" or \"B\", \"reason\": \"...\", \"confidence\": 0.0-1.0}"
        )

        messages = [{"role": "user", "content": prompt}]
        result = await self.llm.complete(messages, max_tokens=512)

        if not result.get("success"):
            return {"winner": "A", "reason": "LLM failed", "confidence": 0.5}

        from .prompt_engine import OutputParser
        parser = OutputParser()
        parsed = parser.parse_json_response(result["response"])

        if parsed:
            winner_key = parsed.get("winner", "A")
            return {
                "winner": strategy_a if winner_key == "A" else strategy_b,
                "winner_label": winner_key,
                "reason": parsed.get("reason", ""),
                "confidence": parsed.get("confidence", 0.5),
            }

        return {"winner": strategy_a, "winner_label": "A", "reason": "Parse failed", "confidence": 0.5}

    # ── Prompt Mutation ───────────────────────────────────────────────────────

    async def mutate_prompt(
        self,
        original_prompt: str,
        task_type: str,
        failure_examples: List[str],
        success_examples: List[str],
    ) -> str:
        """
        Mutate a prompt to improve it based on failure/success examples.
        Returns the improved prompt.
        """
        mutation_prompt = (
            f"You are improving a system prompt for task type: {task_type}\n\n"
            f"Original prompt:\n{original_prompt[:2000]}\n\n"
            f"Recent failures (what went wrong):\n"
            + "\n".join(f"- {f[:200]}" for f in failure_examples[:5])
            + f"\n\nRecent successes (what worked):\n"
            + "\n".join(f"- {s[:200]}" for s in success_examples[:5])
            + "\n\nRewrite the prompt to:\n"
            "1. Avoid the failure patterns\n"
            "2. Reinforce the success patterns\n"
            "3. Be more specific about edge cases\n\n"
            "Return ONLY the improved prompt text, no explanation."
        )

        messages = [{"role": "user", "content": mutation_prompt}]
        result = await self.llm.complete(messages, max_tokens=2048)

        if result.get("success") and result.get("response"):
            return result["response"]

        return original_prompt  # Fall back to original if mutation fails

    # ── Internal Methods ──────────────────────────────────────────────────────

    def _should_evolve(self, task_type: str, session_count: int) -> bool:
        """Determine if evolution should run."""
        # Check session interval
        if session_count > 0 and session_count % self.evolution_interval == 0:
            return True

        # Check failure rate
        failure_rate = self._get_failure_rate(task_type)
        if failure_rate > self.failure_threshold:
            logger.info(
                f"Evolution triggered for '{task_type}': "
                f"failure rate {failure_rate:.1%} > threshold {self.failure_threshold:.1%}"
            )
            return True

        return False

    def _get_failure_rate(self, task_type: str) -> float:
        """Calculate recent failure rate for a task type."""
        if not self._ensure_initialized():
            return 0.0

        collection = self._collections.get("action_outcomes")
        if collection is None:
            return 0.0

        try:
            results = collection.query(
                query_texts=[task_type],
                n_results=20,
                where={"action_type": task_type},
            )
            metas = results.get("metadatas", [[]])[0]
            if not metas:
                return 0.0

            failures = sum(1 for m in metas if m.get("outcome") == "failure")
            return failures / len(metas)
        except Exception:
            return 0.0

    def _pull_experiences(
        self, task_type: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Pull recent experiences for a task type from ChromaDB."""
        if not self._ensure_initialized():
            return []

        experiences = []
        for collection_name in ["action_outcomes", "screenshot_patterns", "procedural_memory"]:
            collection = self._collections.get(collection_name)
            if collection is None:
                continue
            try:
                count = collection.count()
                if count == 0:
                    continue
                results = collection.query(
                    query_texts=[task_type],
                    n_results=min(limit // 3, count),
                )
                docs = results.get("documents", [[]])[0]
                metas = results.get("metadatas", [[]])[0]
                for doc, meta in zip(docs, metas):
                    experiences.append({"content": doc, "metadata": meta})
            except Exception as e:
                logger.debug(f"Could not pull experiences from '{collection_name}': {e}")

        return experiences

    async def _generate_evolved_strategy(
        self,
        task_type: str,
        experiences: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Ask the LLM to analyze experiences and generate an evolved strategy."""
        exp_summary = "\n".join(
            f"- [{e['metadata'].get('outcome', 'unknown')}] {e['content'][:200]}"
            for e in experiences[:30]
        )

        prompt = (
            f"{EVOLUTION_PROMPT}\n\n"
            f"Task type: {task_type}\n\n"
            f"Recent experiences ({len(experiences)} total, showing 30):\n{exp_summary}"
        )

        messages = [{"role": "user", "content": prompt}]
        result = await self.llm.complete(messages, max_tokens=1024)

        if not result.get("success"):
            return None

        from .prompt_engine import OutputParser
        parser = OutputParser()
        return parser.parse_json_response(result["response"])

    def _store_strategy(self, task_type: str, strategy: Dict[str, Any]) -> None:
        """Store an evolved strategy to ChromaDB and in-memory cache."""
        # Update in-memory cache
        self._strategies[task_type] = strategy

        # Store to ChromaDB
        if not self._ensure_initialized():
            return

        collection = self._collections.get("agent_context")
        if collection is None:
            return

        try:
            doc_text = (
                f"Evolved strategy for: {task_type}\n"
                f"Patterns: {', '.join(strategy.get('successful_patterns', []))}\n"
                f"Failures: {', '.join(strategy.get('failure_modes', []))}\n"
                f"Strategy: {strategy.get('evolved_strategy', '')}"
            )

            metadata = {
                "type": "evolved_strategy",
                "task_type": task_type,
                "strategy_json": json.dumps(strategy),
                "confidence": strategy.get("confidence", 0.0),
                "timestamp": datetime.utcnow().isoformat(),
            }

            record_id = f"strategy_{task_type}_{str(uuid.uuid4())[:8]}"
            collection.add(
                documents=[doc_text],
                metadatas=[metadata],
                ids=[record_id],
            )
        except Exception as e:
            logger.error(f"Failed to store evolved strategy: {e}")

    def _get_known_task_types(self) -> List[str]:
        """Get all task types that have been encountered."""
        return [
            "linkedin_login",
            "linkedin_search",
            "linkedin_connect",
            "linkedin_scrape",
            "linkedin_message",
            "browser_navigate",
            "browser_click",
            "browser_type",
        ]
