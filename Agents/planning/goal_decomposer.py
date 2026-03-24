"""
Goal Decomposer — Breaks high-level goals into executable subtask trees.

Given a high-level goal like:
  "Find 20 ML engineers at Series B startups and send personalized connection requests"

Produces a subtask tree:
  1. Search LinkedIn for ML engineers at Series B startups (search_agent)
  2. For each profile found:
     2a. Scrape profile details (scraper_agent)
     2b. Generate personalized connection note (connection_agent)
     2c. Send connection request (connection_agent)
  3. Record outcomes (experience_recorder)

The decomposer uses the LLM to intelligently break down goals,
enriched with past experience of similar decompositions.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from loguru import logger

from llm.base_model import BaseLLM, get_llm
from llm.prompt_engine import OutputParser


# ── Decomposition Prompt ──────────────────────────────────────────────────────

DECOMPOSE_PROMPT = """You are a task decomposition expert for a LinkedIn automation agent.

Break down the following high-level goal into a sequence of concrete subtasks.

Available agent types:
  - auth_agent:       LinkedIn login and session management
  - search_agent:     Search LinkedIn for people with specific criteria
  - scraper_agent:    Extract detailed profile information
  - connection_agent: Send personalized connection requests
  - message_agent:    Send messages to existing connections
  - orchestrator:     Coordinate multiple agents

Rules:
  1. Each subtask must be atomic (one clear action)
  2. Specify which agent handles each subtask
  3. Identify dependencies (which subtasks must complete before others)
  4. Estimate complexity: low | medium | high
  5. Maximum 10 subtasks per decomposition

Respond in JSON:
{
  "goal_summary": "one-line summary of the goal",
  "subtasks": [
    {
      "id": "task_1",
      "description": "what to do",
      "agent": "agent_name",
      "depends_on": [],
      "complexity": "low|medium|high",
      "estimated_actions": 5,
      "can_parallelize": false
    }
  ],
  "total_estimated_actions": 25,
  "requires_login": true,
  "linkedin_daily_limits": {
    "connections": 20,
    "messages": 10
  }
}
"""


class GoalDecomposer:
    """
    Decomposes high-level goals into executable subtask trees.

    Uses LLM to intelligently break down complex goals,
    enriched with past experience of similar decompositions.
    """

    def __init__(self, llm: Optional[BaseLLM] = None):
        self.llm = llm or get_llm()
        self.parser = OutputParser()

    async def decompose(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        past_experiences: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Decompose a high-level goal into subtasks.

        Args:
            goal:              The high-level goal to decompose
            context:           Additional context (current URL, session state, etc.)
            past_experiences:  Retrieved past experiences for similar goals

        Returns:
            {
                "plan_id": str,
                "goal": str,
                "goal_summary": str,
                "subtasks": list[SubTask],
                "total_estimated_actions": int,
                "requires_login": bool,
            }
        """
        prompt = self._build_decompose_prompt(goal, context, past_experiences)
        messages = [{"role": "user", "content": prompt}]

        result = await self.llm.complete(
            messages=messages,
            system=DECOMPOSE_PROMPT,
            max_tokens=2048,
        )

        if not result.get("success"):
            logger.error(f"Goal decomposition failed: {result.get('error')}")
            return self._fallback_decomposition(goal)

        parsed = self.parser.parse_json_response(result["response"])
        if not parsed:
            logger.warning("Could not parse decomposition response, using fallback")
            return self._fallback_decomposition(goal)

        # Build the plan
        plan_id = str(uuid.uuid4())
        subtasks = []
        for st in parsed.get("subtasks", []):
            subtasks.append(
                {
                    "task_id": st.get("id", str(uuid.uuid4())),
                    "description": st.get("description", ""),
                    "agent": st.get("agent", "orchestrator"),
                    "depends_on": st.get("depends_on", []),
                    "complexity": st.get("complexity", "medium"),
                    "estimated_actions": st.get("estimated_actions", 5),
                    "can_parallelize": st.get("can_parallelize", False),
                    "status": "pending",
                    "result": None,
                    "retries": 0,
                    "max_retries": 3,
                }
            )

        return {
            "plan_id": plan_id,
            "goal": goal,
            "goal_summary": parsed.get("goal_summary", goal[:100]),
            "subtasks": subtasks,
            "total_estimated_actions": parsed.get("total_estimated_actions", len(subtasks) * 5),
            "requires_login": parsed.get("requires_login", True),
            "linkedin_daily_limits": parsed.get(
                "linkedin_daily_limits", {"connections": 20, "messages": 10}
            ),
            "status": "planning",
        }

    def decompose_sync(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        past_experiences: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Synchronous wrapper around decompose()."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run, self.decompose(goal, context, past_experiences)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.decompose(goal, context, past_experiences)
                )
        except Exception as e:
            logger.error(f"Decompose sync failed: {e}")
            return self._fallback_decomposition(goal)

    def get_ready_subtasks(self, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get subtasks that are ready to execute (all dependencies completed).
        """
        completed_ids = {
            st["task_id"]
            for st in plan["subtasks"]
            if st["status"] == "done"
        }

        ready = []
        for st in plan["subtasks"]:
            if st["status"] != "pending":
                continue
            deps_met = all(dep in completed_ids for dep in st.get("depends_on", []))
            if deps_met:
                ready.append(st)

        return ready

    def get_parallel_groups(self, plan: Dict[str, Any]) -> List[List[Dict[str, Any]]]:
        """
        Group ready subtasks by parallelizability.
        Returns list of groups — each group can run in parallel.
        """
        ready = self.get_ready_subtasks(plan)
        parallel = [st for st in ready if st.get("can_parallelize")]
        sequential = [st for st in ready if not st.get("can_parallelize")]

        groups = []
        if parallel:
            groups.append(parallel)
        for st in sequential:
            groups.append([st])

        return groups

    def mark_subtask_done(
        self,
        plan: Dict[str, Any],
        task_id: str,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mark a subtask as completed."""
        for st in plan["subtasks"]:
            if st["task_id"] == task_id:
                st["status"] = "done"
                st["result"] = result
                break

    def mark_subtask_failed(
        self,
        plan: Dict[str, Any],
        task_id: str,
        error: str = "",
    ) -> None:
        """Mark a subtask as failed."""
        for st in plan["subtasks"]:
            if st["task_id"] == task_id:
                st["status"] = "failed"
                st["error"] = error
                st["retries"] = st.get("retries", 0) + 1
                break

    def is_plan_complete(self, plan: Dict[str, Any]) -> bool:
        """Check if all subtasks are done."""
        return all(st["status"] == "done" for st in plan["subtasks"])

    def is_plan_failed(self, plan: Dict[str, Any]) -> bool:
        """Check if any subtask has exceeded max retries."""
        return any(
            st["status"] == "failed" and st.get("retries", 0) >= st.get("max_retries", 3)
            for st in plan["subtasks"]
        )

    def _build_decompose_prompt(
        self,
        goal: str,
        context: Optional[Dict[str, Any]],
        past_experiences: Optional[List[Dict[str, Any]]],
    ) -> str:
        parts = [f"Goal: {goal}"]

        if context:
            parts.append(f"Context: {json.dumps(context, indent=2)[:500]}")

        if past_experiences:
            parts.append("\nRelevant past decompositions:")
            for exp in past_experiences[:3]:
                parts.append(f"  - {exp.get('content', '')[:200]}")

        return "\n".join(parts)

    def _fallback_decomposition(self, goal: str) -> Dict[str, Any]:
        """Fallback decomposition when LLM fails."""
        return {
            "plan_id": str(uuid.uuid4()),
            "goal": goal,
            "goal_summary": goal[:100],
            "subtasks": [
                {
                    "task_id": "task_1",
                    "description": f"Login to LinkedIn",
                    "agent": "auth_agent",
                    "depends_on": [],
                    "complexity": "low",
                    "estimated_actions": 5,
                    "can_parallelize": False,
                    "status": "pending",
                    "result": None,
                    "retries": 0,
                    "max_retries": 3,
                },
                {
                    "task_id": "task_2",
                    "description": goal,
                    "agent": "orchestrator",
                    "depends_on": ["task_1"],
                    "complexity": "high",
                    "estimated_actions": 20,
                    "can_parallelize": False,
                    "status": "pending",
                    "result": None,
                    "retries": 0,
                    "max_retries": 3,
                },
            ],
            "total_estimated_actions": 25,
            "requires_login": True,
            "linkedin_daily_limits": {"connections": 20, "messages": 10},
            "status": "planning",
        }
