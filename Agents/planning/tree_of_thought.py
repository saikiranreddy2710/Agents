"""
Tree of Thought (ToT) — Explores multiple action paths before committing.

Instead of greedily picking the first action, ToT:
  1. Generates N candidate action paths
  2. Evaluates each path's expected outcome
  3. Scores each path (0-10)
  4. Selects the highest-scoring path
  5. Executes it

This dramatically reduces mistakes on complex UI interactions
where the wrong action can be hard to recover from.

Example:
  Task: "Click the Connect button on this LinkedIn profile"
  
  Path 1: Click .connect-button directly → Score: 7
  Path 2: Scroll to see full profile first, then click → Score: 9  ← WINNER
  Path 3: Use keyboard shortcut → Score: 3
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from llm.base_model import BaseLLM, get_llm
from llm.prompt_engine import OutputParser


# ── ToT Prompt ────────────────────────────────────────────────────────────────

TOT_SYSTEM_PROMPT = """You are an expert browser automation agent using Tree of Thought reasoning.

For the given task and context, generate multiple candidate action paths,
evaluate each one, and select the best.

Respond in JSON:
{
  "task_analysis": "brief analysis of what needs to happen",
  "paths": [
    {
      "path_id": 1,
      "description": "what this path does",
      "actions": [
        {"type": "action_type", "params": {...}, "reason": "why"}
      ],
      "expected_outcome": "what will happen",
      "risks": ["risk1", "risk2"],
      "score": 8,
      "score_reason": "why this score"
    }
  ],
  "best_path_id": 2,
  "best_path_reason": "why path 2 is best",
  "confidence": 0.85
}
"""


class TreeOfThought:
    """
    Tree of Thought planner for browser actions.

    Generates and evaluates multiple action paths before committing,
    reducing mistakes on complex or ambiguous UI interactions.
    """

    def __init__(
        self,
        llm: Optional[BaseLLM] = None,
        num_paths: int = 3,
        min_confidence: float = 0.6,
    ):
        self.llm = llm or get_llm()
        self.num_paths = num_paths
        self.min_confidence = min_confidence
        self.parser = OutputParser()

    async def think(
        self,
        task: str,
        context: str = "",
        page_url: str = "",
        available_actions: Optional[List[str]] = None,
        past_experiences: Optional[List[Dict[str, Any]]] = None,
        screenshot_description: str = "",
    ) -> Dict[str, Any]:
        """
        Generate and evaluate multiple action paths for a task.

        Args:
            task:                 What needs to be accomplished
            context:              Current page context (DOM summary, etc.)
            page_url:             Current page URL
            available_actions:    List of available action types
            past_experiences:     Retrieved past experiences
            screenshot_description: Description of current screenshot

        Returns:
            {
                "best_action": dict,
                "all_paths": list,
                "confidence": float,
                "reasoning": str,
                "fallback_action": dict,
            }
        """
        prompt = self._build_tot_prompt(
            task, context, page_url,
            available_actions, past_experiences, screenshot_description,
        )

        messages = [{"role": "user", "content": prompt}]
        result = await self.llm.complete(
            messages=messages,
            system=TOT_SYSTEM_PROMPT,
            max_tokens=2048,
        )

        if not result.get("success"):
            logger.warning(f"ToT LLM call failed: {result.get('error')}")
            return self._fallback_response(task)

        parsed = self.parser.parse_json_response(result["response"])
        if not parsed:
            logger.warning("Could not parse ToT response")
            return self._fallback_response(task)

        return self._extract_best_path(parsed, task)

    def think_sync(
        self,
        task: str,
        context: str = "",
        page_url: str = "",
        available_actions: Optional[List[str]] = None,
        past_experiences: Optional[List[Dict[str, Any]]] = None,
        screenshot_description: str = "",
    ) -> Dict[str, Any]:
        """Synchronous wrapper around think()."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self.think(
                            task, context, page_url,
                            available_actions, past_experiences, screenshot_description,
                        ),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.think(
                        task, context, page_url,
                        available_actions, past_experiences, screenshot_description,
                    )
                )
        except Exception as e:
            logger.error(f"ToT sync failed: {e}")
            return self._fallback_response(task)

    def evaluate_path(
        self,
        path: Dict[str, Any],
        context: str = "",
    ) -> float:
        """
        Evaluate a single action path and return a score (0-10).
        Uses heuristics when LLM evaluation is too expensive.
        """
        score = path.get("score", 5.0)

        # Penalize paths with many risks
        risks = path.get("risks", [])
        score -= len(risks) * 0.5

        # Reward paths with fewer actions (simpler = better)
        actions = path.get("actions", [])
        if len(actions) <= 2:
            score += 1.0
        elif len(actions) > 5:
            score -= 1.0

        # Reward paths that include verification steps
        action_types = [a.get("type", "") for a in actions]
        if "screenshot" in action_types or "wait" in action_types:
            score += 0.5

        return max(0.0, min(10.0, score))

    def select_best_path(
        self,
        paths: List[Dict[str, Any]],
        context: str = "",
    ) -> Tuple[Dict[str, Any], float]:
        """
        Select the best path from a list of candidates.
        Returns (best_path, confidence_score).
        """
        if not paths:
            return {}, 0.0

        scored_paths = [
            (path, self.evaluate_path(path, context))
            for path in paths
        ]
        scored_paths.sort(key=lambda x: x[1], reverse=True)

        best_path, best_score = scored_paths[0]
        confidence = best_score / 10.0

        return best_path, confidence

    def _build_tot_prompt(
        self,
        task: str,
        context: str,
        page_url: str,
        available_actions: Optional[List[str]],
        past_experiences: Optional[List[Dict[str, Any]]],
        screenshot_description: str,
    ) -> str:
        parts = [
            f"Task: {task}",
            f"Current URL: {page_url}" if page_url else "",
            f"Page context: {context[:500]}" if context else "",
            f"Screenshot: {screenshot_description[:300]}" if screenshot_description else "",
        ]

        if available_actions:
            parts.append(f"Available actions: {', '.join(available_actions)}")

        if past_experiences:
            parts.append("\nRelevant past experiences:")
            for exp in past_experiences[:3]:
                outcome = exp.get("outcome", "unknown")
                content = exp.get("content", "")[:200]
                parts.append(f"  [{outcome}] {content}")

        parts.append(
            f"\nGenerate {self.num_paths} different action paths to accomplish this task. "
            "Score each path 0-10 and identify the best one."
        )

        return "\n".join(p for p in parts if p)

    def _extract_best_path(
        self,
        parsed: Dict[str, Any],
        task: str,
    ) -> Dict[str, Any]:
        """Extract the best path from parsed ToT response."""
        paths = parsed.get("paths", [])
        best_path_id = parsed.get("best_path_id", 1)
        confidence = parsed.get("confidence", 0.5)

        # Find the best path
        best_path = None
        for path in paths:
            if path.get("path_id") == best_path_id:
                best_path = path
                break

        if not best_path and paths:
            # Fall back to highest-scored path
            best_path = max(paths, key=lambda p: p.get("score", 0))

        if not best_path:
            return self._fallback_response(task)

        # Extract the first action from the best path
        actions = best_path.get("actions", [])
        first_action = actions[0] if actions else {"type": "screenshot", "params": {}}

        # Build fallback (second-best path)
        fallback_action = {"type": "screenshot", "params": {}}
        other_paths = [p for p in paths if p.get("path_id") != best_path_id]
        if other_paths:
            second_best = max(other_paths, key=lambda p: p.get("score", 0))
            second_actions = second_best.get("actions", [])
            if second_actions:
                fallback_action = second_actions[0]

        return {
            "best_action": first_action,
            "best_path": best_path,
            "all_paths": paths,
            "confidence": confidence,
            "reasoning": parsed.get("task_analysis", ""),
            "best_path_reason": parsed.get("best_path_reason", ""),
            "fallback_action": fallback_action,
            "all_actions_in_path": actions,
        }

    def _fallback_response(self, task: str) -> Dict[str, Any]:
        """Fallback when ToT fails — take a screenshot to assess state."""
        return {
            "best_action": {"type": "screenshot", "params": {}, "reason": "ToT failed, assess state"},
            "best_path": {},
            "all_paths": [],
            "confidence": 0.3,
            "reasoning": f"ToT planning failed for: {task}",
            "best_path_reason": "Fallback: take screenshot to assess current state",
            "fallback_action": {"type": "screenshot", "params": {}},
            "all_actions_in_path": [],
        }
