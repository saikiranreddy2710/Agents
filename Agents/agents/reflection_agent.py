"""
Reflection Agent — Evaluates every action outcome and extracts learnings.

After each agent step, the ReflectionAgent:
  1. Analyzes what happened (success/failure + why)
  2. Extracts reusable patterns ("clicking .connect-btn works on profile pages")
  3. Identifies anti-patterns ("never click X before Y")
  4. Stores insights to ChromaDB for future retrieval
  5. Suggests strategy adjustments to the calling agent
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from loguru import logger


class ReflectionAgent:
    """
    Reflects on action outcomes and extracts learnings for ChromaDB.

    Used by BaseAgent after each step to improve future performance.
    """

    def __init__(self, llm=None, memory=None):
        self.llm = llm
        self.memory = memory
        self._reflection_count = 0

    async def reflect(
        self,
        agent_name: str,
        action: str,
        success: bool,
        url: str,
        screenshot_b64: str = "",
        error: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Reflect on a single action outcome.

        Args:
            agent_name:     Name of the agent that performed the action
            action:         Action that was taken
            success:        Whether the action succeeded
            url:            Page URL where action occurred
            screenshot_b64: Screenshot after the action
            error:          Error message if failed
            context:        Additional context

        Returns:
            {
              "pattern": str,       # Extracted pattern
              "suggestion": str,    # Suggested next action
              "confidence": float,  # Confidence in the reflection
              "stored": bool,       # Whether it was stored to ChromaDB
            }
        """
        self._reflection_count += 1

        # Build reflection
        reflection = self._rule_based_reflect(
            agent_name=agent_name,
            action=action,
            success=success,
            url=url,
            error=error,
        )

        # Enhance with LLM if available
        if self.llm and screenshot_b64:
            try:
                llm_reflection = await self._llm_reflect(
                    agent_name=agent_name,
                    action=action,
                    success=success,
                    url=url,
                    screenshot_b64=screenshot_b64,
                    error=error,
                )
                reflection.update(llm_reflection)
            except Exception as e:
                logger.debug(f"[ReflectionAgent] LLM reflection failed: {e}")

        # Store to ChromaDB
        stored = await self._store_reflection(
            agent_name=agent_name,
            action=action,
            success=success,
            url=url,
            reflection=reflection,
        )
        reflection["stored"] = stored

        if not success:
            logger.debug(
                f"[ReflectionAgent] Failure pattern: {reflection.get('pattern', 'unknown')}"
            )

        return reflection

    async def reflect_on_session(
        self,
        agent_name: str,
        action_history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Reflect on an entire session's action history.
        Extracts high-level patterns and workflow insights.

        Args:
            agent_name:     Agent that ran the session
            action_history: List of step results from BaseAgent.run()

        Returns:
            {
              "success_rate": float,
              "common_failures": list,
              "best_actions": list,
              "workflow_insight": str,
            }
        """
        if not action_history:
            return {"success_rate": 0.0, "common_failures": [], "best_actions": []}

        total = len(action_history)
        successes = sum(1 for s in action_history if s.get("success"))
        success_rate = successes / total if total > 0 else 0.0

        # Find common failure patterns
        failures = [s for s in action_history if not s.get("success")]
        failure_actions = [f.get("action", "unknown") for f in failures]

        # Find best performing actions
        best = [s.get("action") for s in action_history if s.get("success")]

        insight = (
            f"Session for {agent_name}: {successes}/{total} steps succeeded. "
            f"Success rate: {success_rate:.0%}. "
        )
        if failure_actions:
            insight += f"Common failures: {', '.join(set(failure_actions))}."

        # Store session-level insight
        await self._store_session_insight(agent_name, insight, success_rate)

        return {
            "success_rate": success_rate,
            "common_failures": list(set(failure_actions)),
            "best_actions": list(set(best)),
            "workflow_insight": insight,
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _rule_based_reflect(
        self,
        agent_name: str,
        action: str,
        success: bool,
        url: str,
        error: str,
    ) -> Dict[str, Any]:
        """Fast rule-based reflection (no LLM needed)."""

        # Determine page context from URL
        page_context = "unknown"
        if "linkedin.com/in/" in url:
            page_context = "profile_page"
        elif "search/results" in url:
            page_context = "search_results"
        elif "messaging" in url:
            page_context = "messaging"
        elif "feed" in url:
            page_context = "feed"
        elif "login" in url:
            page_context = "login"

        # Build pattern description
        if success:
            pattern = f"[SUCCESS] {agent_name}.{action} works on {page_context}"
            suggestion = "continue"
            confidence = 0.8
        else:
            pattern = f"[FAILURE] {agent_name}.{action} failed on {page_context}"
            suggestion = self._suggest_recovery(action, error, page_context)
            confidence = 0.6

            # Specific error patterns
            if "timeout" in error.lower():
                pattern += " (timeout — element may not exist)"
                suggestion = "wait_longer_or_scroll"
                confidence = 0.7
            elif "not found" in error.lower():
                pattern += " (element not found — UI may have changed)"
                suggestion = "try_alternative_selector"
                confidence = 0.75
            elif "captcha" in error.lower():
                pattern += " (CAPTCHA — slow down)"
                suggestion = "pause_and_retry_later"
                confidence = 0.9

        return {
            "pattern": pattern,
            "page_context": page_context,
            "suggestion": suggestion,
            "confidence": confidence,
        }

    async def _llm_reflect(
        self,
        agent_name: str,
        action: str,
        success: bool,
        url: str,
        screenshot_b64: str,
        error: str,
    ) -> Dict[str, Any]:
        """Use LLM to analyze screenshot and extract deeper insights."""
        status = "succeeded" if success else f"failed with: {error}"
        prompt = (
            f"Agent '{agent_name}' performed action '{action}' on {url}. "
            f"The action {status}. "
            f"Look at the screenshot and provide:\n"
            f"1. What went wrong (if failed) or what worked well\n"
            f"2. A reusable pattern for future reference\n"
            f"3. Suggested next action\n"
            f"Respond with JSON: {{\"pattern\": str, \"suggestion\": str, \"insight\": str}}"
        )

        response = await self.llm.decide(
            prompt=prompt,
            screenshot_b64=screenshot_b64,
        )
        return {
            "pattern": response.get("pattern", ""),
            "suggestion": response.get("suggestion", "continue"),
            "llm_insight": response.get("insight", ""),
            "confidence": 0.85,
        }

    async def _store_reflection(
        self,
        agent_name: str,
        action: str,
        success: bool,
        url: str,
        reflection: Dict[str, Any],
    ) -> bool:
        """Store reflection to ChromaDB."""
        if not self.memory:
            return False
        try:
            await self.memory.record_action(
                agent=agent_name,
                url=url,
                action=action,
                success=success,
                duration=0,
                metadata={
                    "pattern": reflection.get("pattern", ""),
                    "suggestion": reflection.get("suggestion", ""),
                    "confidence": reflection.get("confidence", 0.5),
                    "reflection_id": self._reflection_count,
                },
            )
            return True
        except Exception as e:
            logger.debug(f"[ReflectionAgent] Store failed: {e}")
            return False

    async def _store_session_insight(
        self,
        agent_name: str,
        insight: str,
        success_rate: float,
    ) -> None:
        """Store session-level insight to ChromaDB."""
        if not self.memory:
            return
        try:
            await self.memory.record_action(
                agent=agent_name,
                url="session_summary",
                action="session_reflection",
                success=success_rate > 0.5,
                duration=0,
                metadata={"insight": insight, "success_rate": success_rate},
            )
        except Exception:
            pass

    def _suggest_recovery(self, action: str, error: str, page_context: str) -> str:
        """Suggest a recovery action based on failure context."""
        if "navigate" in action:
            return "retry_navigation"
        elif "click" in action:
            return "try_js_click_or_scroll_to_element"
        elif "fill" in action or "type" in action:
            return "clear_and_retype"
        elif "wait" in action:
            return "increase_timeout"
        return "take_screenshot_and_reassess"
