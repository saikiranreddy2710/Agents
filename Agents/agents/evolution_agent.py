"""
Evolution Agent — Rewrites strategies based on accumulated patterns.

The EvolutionAgent implements the self-improvement loop:
  1. Analyzes ChromaDB for failure patterns
  2. Identifies which selectors/strategies are outdated
  3. Generates improved code/selectors using LLM
  4. Updates skills via MetaAgent's modify_subagent()
  5. Adjusts rate limits based on warning signals
  6. Tracks evolution history (what changed, why, did it help)

Triggered:
  - After N consecutive failures of the same type
  - After each session (background evolution)
  - Manually via main.py --evolve flag
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from loguru import logger


class EvolutionAgent:
    """
    Self-improvement engine that evolves agent strategies over time.

    Reads failure patterns from ChromaDB → generates improvements
    → updates skills → validates improvements on next run.
    """

    def __init__(
        self,
        llm=None,
        memory=None,
        meta_agent=None,
        evolution_log_path: str = "workspace/evolution_log.json",
        failure_threshold: int = 3,
    ):
        self.llm = llm
        self.memory = memory
        self.meta_agent = meta_agent
        self.evolution_log_path = evolution_log_path
        self.failure_threshold = failure_threshold

        self._evolution_history: List[Dict[str, Any]] = []
        self._load_history()

    # ── Main Evolution Loop ───────────────────────────────────────────────────

    async def evolve(self) -> Dict[str, Any]:
        """
        Run one evolution cycle.

        Returns:
            {
              "improvements_made": int,
              "skills_updated": list,
              "patterns_analyzed": int,
              "evolution_summary": str,
            }
        """
        logger.info("[EvolutionAgent] Starting evolution cycle")
        start = time.time()

        improvements = []

        # 1. Analyze failure patterns from memory
        failure_patterns = await self._analyze_failures()
        logger.info(f"[EvolutionAgent] Found {len(failure_patterns)} failure patterns")

        # 2. Generate improvements for each pattern
        for pattern in failure_patterns[:5]:  # Process top 5 patterns
            improvement = await self._generate_improvement(pattern)
            if improvement:
                improvements.append(improvement)

        # 3. Apply improvements
        skills_updated = []
        for improvement in improvements:
            updated = await self._apply_improvement(improvement)
            if updated:
                skills_updated.append(improvement.get("target", "unknown"))

        # 4. Evolve selectors (LinkedIn UI changes frequently)
        selector_updates = await self._evolve_selectors()
        skills_updated.extend(selector_updates)

        # 5. Adjust rate limits based on warning signals
        await self._adjust_rate_limits()

        # 6. Record evolution
        duration = time.time() - start
        summary = (
            f"Evolution cycle: analyzed {len(failure_patterns)} patterns, "
            f"made {len(improvements)} improvements, "
            f"updated {len(skills_updated)} skills in {duration:.1f}s"
        )

        self._record_evolution({
            "timestamp": time.time(),
            "patterns_analyzed": len(failure_patterns),
            "improvements_made": len(improvements),
            "skills_updated": skills_updated,
            "summary": summary,
        })

        logger.info(f"[EvolutionAgent] {summary}")

        return {
            "improvements_made": len(improvements),
            "skills_updated": skills_updated,
            "patterns_analyzed": len(failure_patterns),
            "evolution_summary": summary,
        }

    async def should_evolve(self, agent_name: str, action: str) -> bool:
        """
        Check if evolution is needed for a specific agent/action.
        Returns True if failure threshold exceeded.
        """
        if not self.memory:
            return False

        try:
            recent_failures = await self.memory.retrieve_relevant(
                query=f"failure {agent_name} {action}",
                limit=10,
            )
            failure_count = sum(
                1 for r in recent_failures
                if not r.get("success", True) and r.get("action") == action
            )
            return failure_count >= self.failure_threshold
        except Exception:
            return False

    async def evolve_selector(
        self,
        selector: str,
        context: str,
        failure_count: int,
    ) -> Optional[str]:
        """
        Generate an improved CSS selector when the current one fails.

        Args:
            selector:      Current failing selector
            context:       What the selector is supposed to find
            failure_count: How many times it has failed

        Returns:
            New selector string, or None if no improvement found
        """
        if not self.llm:
            return None

        try:
            prompt = (
                f"LinkedIn CSS selector '{selector}' has failed {failure_count} times "
                f"when trying to find: {context}\n\n"
                f"LinkedIn frequently updates its UI. Generate 3 alternative CSS selectors "
                f"that might work for the same element.\n"
                f"Respond with JSON: {{\"selectors\": [\"sel1\", \"sel2\", \"sel3\"], "
                f"\"reasoning\": \"why these might work\"}}"
            )

            response = await self.llm.decide(prompt=prompt)
            alternatives = response.get("selectors", [])

            if alternatives:
                logger.info(
                    f"[EvolutionAgent] Generated {len(alternatives)} alternative selectors "
                    f"for: {context}"
                )
                return alternatives[0]  # Return best alternative

        except Exception as e:
            logger.debug(f"[EvolutionAgent] Selector evolution failed: {e}")

        return None

    async def evolve_note_template(
        self,
        current_template: str,
        acceptance_rate: float,
        rejection_patterns: List[str],
    ) -> Optional[str]:
        """
        Improve connection note templates based on acceptance rates.

        Args:
            current_template:   Current note template
            acceptance_rate:    % of requests accepted (0.0-1.0)
            rejection_patterns: Common patterns in rejected requests

        Returns:
            Improved template string
        """
        if not self.llm or acceptance_rate > 0.7:
            return None  # Don't fix what isn't broken

        try:
            prompt = (
                f"LinkedIn connection note template has {acceptance_rate:.0%} acceptance rate.\n"
                f"Current template: {current_template}\n"
                f"Rejection patterns: {', '.join(rejection_patterns)}\n\n"
                f"Generate an improved, more personalized connection note template "
                f"that avoids these patterns. Keep it under 300 characters.\n"
                f"Respond with JSON: {{\"template\": \"...\", \"reasoning\": \"...\"}}"
            )

            response = await self.llm.decide(prompt=prompt)
            new_template = response.get("template", "")

            if new_template and len(new_template) <= 300:
                logger.info(
                    f"[EvolutionAgent] Evolved note template "
                    f"(acceptance: {acceptance_rate:.0%} → expected improvement)"
                )
                return new_template

        except Exception as e:
            logger.debug(f"[EvolutionAgent] Note template evolution failed: {e}")

        return None

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _analyze_failures(self) -> List[Dict[str, Any]]:
        """Retrieve and analyze failure patterns from ChromaDB."""
        if not self.memory:
            return []

        try:
            failures = await self.memory.retrieve_relevant(
                query="failure error timeout not found",
                limit=20,
            )

            # Group by action type
            failure_groups: Dict[str, List] = {}
            for f in failures:
                if not f.get("success", True):
                    action = f.get("action", "unknown")
                    if action not in failure_groups:
                        failure_groups[action] = []
                    failure_groups[action].append(f)

            # Return patterns with >= threshold failures
            patterns = []
            for action, failures_list in failure_groups.items():
                if len(failures_list) >= self.failure_threshold:
                    patterns.append({
                        "action": action,
                        "count": len(failures_list),
                        "errors": list(set(
                            f.get("error", "") for f in failures_list if f.get("error")
                        ))[:3],
                        "urls": list(set(
                            f.get("url", "") for f in failures_list
                        ))[:3],
                    })

            return sorted(patterns, key=lambda p: p["count"], reverse=True)

        except Exception as e:
            logger.debug(f"[EvolutionAgent] Failure analysis failed: {e}")
            return []

    async def _generate_improvement(
        self,
        pattern: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Generate an improvement for a failure pattern."""
        if not self.llm:
            return None

        try:
            prompt = (
                f"LinkedIn automation action '{pattern['action']}' has failed "
                f"{pattern['count']} times.\n"
                f"Errors: {', '.join(pattern['errors'])}\n"
                f"URLs: {', '.join(pattern['urls'])}\n\n"
                f"Suggest an improvement to fix this. Respond with JSON:\n"
                f"{{\"target\": \"skill_name\", \"improvement\": \"description\", "
                f"\"code_change\": \"specific code fix\"}}"
            )

            response = await self.llm.decide(prompt=prompt)
            if response.get("improvement"):
                return {
                    "pattern": pattern,
                    "target": response.get("target", pattern["action"]),
                    "improvement": response.get("improvement", ""),
                    "code_change": response.get("code_change", ""),
                }

        except Exception as e:
            logger.debug(f"[EvolutionAgent] Improvement generation failed: {e}")

        return None

    async def _apply_improvement(
        self,
        improvement: Dict[str, Any],
    ) -> bool:
        """Apply an improvement via MetaAgent."""
        if not self.meta_agent:
            return False

        target = improvement.get("target", "")
        code_change = improvement.get("code_change", "")

        if not target or not code_change:
            return False

        try:
            result = await self.meta_agent.modify_subagent(
                name=target,
                new_code=code_change,
                reason=improvement.get("improvement", "Auto-evolved"),
            )
            return result.get("success", False)
        except Exception as e:
            logger.debug(f"[EvolutionAgent] Apply improvement failed: {e}")
            return False

    async def _evolve_selectors(self) -> List[str]:
        """Check and update outdated LinkedIn selectors."""
        # This would normally check which selectors have been failing
        # and update linkedin/selectors.py accordingly
        # For now, return empty list (selectors are manually maintained)
        return []

    async def _adjust_rate_limits(self) -> None:
        """Adjust rate limits based on warning signals in memory."""
        if not self.memory:
            return

        try:
            warnings = await self.memory.retrieve_relevant(
                query="warning captcha rate limit suspicious",
                limit=5,
            )

            warning_count = len([w for w in warnings if "warning" in str(w).lower()])
            if warning_count >= 2:
                logger.warning(
                    f"[EvolutionAgent] {warning_count} warnings detected — "
                    "rate limits should be reduced"
                )
                # Signal to rate limiter (would be injected in production)

        except Exception:
            pass

    def _record_evolution(self, record: Dict[str, Any]) -> None:
        """Record evolution history to disk."""
        self._evolution_history.append(record)

        try:
            os.makedirs(
                os.path.dirname(self.evolution_log_path)
                if os.path.dirname(self.evolution_log_path) else ".",
                exist_ok=True,
            )
            with open(self.evolution_log_path, "w") as f:
                json.dump(self._evolution_history[-50:], f, indent=2)  # Keep last 50
        except Exception as e:
            logger.debug(f"[EvolutionAgent] Failed to save evolution log: {e}")

    def _load_history(self) -> None:
        """Load evolution history from disk."""
        if os.path.exists(self.evolution_log_path):
            try:
                with open(self.evolution_log_path) as f:
                    self._evolution_history = json.load(f)
            except Exception:
                self._evolution_history = []
        else:
            self._evolution_history = []

    def get_evolution_stats(self) -> Dict[str, Any]:
        """Get evolution statistics."""
        return {
            "total_cycles": len(self._evolution_history),
            "total_improvements": sum(
                e.get("improvements_made", 0) for e in self._evolution_history
            ),
            "total_skills_updated": sum(
                len(e.get("skills_updated", [])) for e in self._evolution_history
            ),
            "last_evolution": (
                self._evolution_history[-1].get("timestamp")
                if self._evolution_history else None
            ),
        }
