"""
Replanner — Dynamic replanning when tasks fail mid-execution.

When a subtask fails, the Replanner:
  1. Analyzes the failure reason
  2. Determines if the plan can be salvaged
  3. Generates an alternative approach
  4. Updates the plan with new subtasks
  5. Continues execution from the recovery point

Replanning strategies:
  - RETRY:      Try the same subtask again (transient errors)
  - WORKAROUND: Try a different approach to the same goal
  - SKIP:       Skip the failed subtask and continue
  - ABORT:      The plan cannot be salvaged
  - DECOMPOSE:  Break the failed subtask into smaller steps
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Dict, List, Optional

from loguru import logger

from llm.base_model import BaseLLM, get_llm
from llm.prompt_engine import OutputParser


class ReplanStrategy(str, Enum):
    RETRY = "retry"
    WORKAROUND = "workaround"
    SKIP = "skip"
    ABORT = "abort"
    DECOMPOSE = "decompose"


REPLAN_SYSTEM_PROMPT = """You are a recovery planner for a LinkedIn browser automation agent.

A subtask has failed. Analyze the failure and determine the best recovery strategy.

Strategies:
  - retry:      The failure is transient (network, timing). Try again.
  - workaround: Try a different approach to accomplish the same goal.
  - skip:       This subtask is optional. Skip it and continue.
  - abort:      The plan cannot be salvaged. Stop execution.
  - decompose:  Break the failed subtask into smaller, simpler steps.

Respond in JSON:
{
  "strategy": "retry|workaround|skip|abort|decompose",
  "reason": "why this strategy",
  "confidence": 0.0-1.0,
  "new_subtasks": [
    {
      "id": "recovery_1",
      "description": "recovery step",
      "agent": "agent_name",
      "depends_on": [],
      "complexity": "low"
    }
  ],
  "modified_subtask": {
    "description": "modified version of failed subtask",
    "agent": "agent_name"
  },
  "skip_reason": "why skipping is acceptable (if strategy=skip)"
}
"""


class Replanner:
    """
    Dynamic replanner that recovers from task failures.

    When a subtask fails, the Replanner analyzes the failure
    and generates a recovery plan to continue execution.
    """

    def __init__(
        self,
        llm: Optional[BaseLLM] = None,
        max_replan_attempts: int = 3,
    ):
        self.llm = llm or get_llm()
        self.max_replan_attempts = max_replan_attempts
        self.parser = OutputParser()
        self._replan_counts: Dict[str, int] = {}  # task_id → replan count

    async def replan(
        self,
        plan: Dict[str, Any],
        failed_subtask: Dict[str, Any],
        failure_reason: str,
        context: Optional[Dict[str, Any]] = None,
        past_experiences: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a recovery plan for a failed subtask.

        Args:
            plan:            The current execution plan
            failed_subtask:  The subtask that failed
            failure_reason:  Why it failed
            context:         Current agent context (URL, page state, etc.)
            past_experiences: Retrieved past experiences for similar failures

        Returns:
            {
                "strategy": ReplanStrategy,
                "updated_plan": dict,
                "recovery_subtasks": list,
                "should_continue": bool,
                "reason": str,
            }
        """
        task_id = failed_subtask.get("task_id", "unknown")

        # Check replan limit
        replan_count = self._replan_counts.get(task_id, 0)
        if replan_count >= self.max_replan_attempts:
            logger.warning(
                f"Subtask '{task_id}' has been replanned {replan_count} times. Aborting."
            )
            return self._abort_response(plan, failed_subtask, "Max replan attempts exceeded")

        self._replan_counts[task_id] = replan_count + 1

        # Build replan prompt
        prompt = self._build_replan_prompt(
            plan, failed_subtask, failure_reason, context, past_experiences
        )
        messages = [{"role": "user", "content": prompt}]

        result = await self.llm.complete(
            messages=messages,
            system=REPLAN_SYSTEM_PROMPT,
            max_tokens=1024,
        )

        if not result.get("success"):
            logger.error(f"Replanning LLM call failed: {result.get('error')}")
            return self._retry_response(plan, failed_subtask)

        parsed = self.parser.parse_json_response(result["response"])
        if not parsed:
            logger.warning("Could not parse replan response, defaulting to retry")
            return self._retry_response(plan, failed_subtask)

        strategy = ReplanStrategy(parsed.get("strategy", "retry"))
        logger.info(
            f"Replan strategy for '{task_id}': {strategy.value} "
            f"(confidence={parsed.get('confidence', 0):.2f})"
        )

        return self._apply_strategy(plan, failed_subtask, strategy, parsed)

    def replan_sync(
        self,
        plan: Dict[str, Any],
        failed_subtask: Dict[str, Any],
        failure_reason: str,
        context: Optional[Dict[str, Any]] = None,
        past_experiences: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Synchronous wrapper around replan()."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self.replan(plan, failed_subtask, failure_reason, context, past_experiences),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.replan(plan, failed_subtask, failure_reason, context, past_experiences)
                )
        except Exception as e:
            logger.error(f"Replan sync failed: {e}")
            return self._retry_response(plan, failed_subtask)

    def should_replan(
        self,
        failed_subtask: Dict[str, Any],
        failure_reason: str,
    ) -> bool:
        """
        Quick heuristic check: should we attempt replanning?
        Returns False for unrecoverable errors.
        """
        task_id = failed_subtask.get("task_id", "")
        replan_count = self._replan_counts.get(task_id, 0)

        if replan_count >= self.max_replan_attempts:
            return False

        # Unrecoverable errors
        unrecoverable_keywords = [
            "account suspended",
            "account restricted",
            "permanently banned",
            "authentication failed",
            "invalid credentials",
        ]
        failure_lower = failure_reason.lower()
        if any(kw in failure_lower for kw in unrecoverable_keywords):
            logger.warning(f"Unrecoverable error detected: {failure_reason[:100]}")
            return False

        return True

    def _apply_strategy(
        self,
        plan: Dict[str, Any],
        failed_subtask: Dict[str, Any],
        strategy: ReplanStrategy,
        parsed: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Apply the chosen recovery strategy to the plan."""
        updated_plan = dict(plan)
        task_id = failed_subtask.get("task_id", "")

        if strategy == ReplanStrategy.RETRY:
            # Reset the failed subtask to pending
            for st in updated_plan["subtasks"]:
                if st["task_id"] == task_id:
                    st["status"] = "pending"
                    st["retries"] = st.get("retries", 0) + 1
                    break
            return {
                "strategy": strategy,
                "updated_plan": updated_plan,
                "recovery_subtasks": [],
                "should_continue": True,
                "reason": parsed.get("reason", "Retrying failed subtask"),
            }

        elif strategy == ReplanStrategy.WORKAROUND:
            # Replace failed subtask with modified version
            modified = parsed.get("modified_subtask", {})
            for st in updated_plan["subtasks"]:
                if st["task_id"] == task_id:
                    if modified.get("description"):
                        st["description"] = modified["description"]
                    if modified.get("agent"):
                        st["agent"] = modified["agent"]
                    st["status"] = "pending"
                    st["retries"] = st.get("retries", 0) + 1
                    break
            return {
                "strategy": strategy,
                "updated_plan": updated_plan,
                "recovery_subtasks": [],
                "should_continue": True,
                "reason": parsed.get("reason", "Trying workaround approach"),
            }

        elif strategy == ReplanStrategy.DECOMPOSE:
            # Replace failed subtask with multiple smaller subtasks
            new_subtasks = parsed.get("new_subtasks", [])
            if not new_subtasks:
                return self._retry_response(plan, failed_subtask)

            # Mark original as skipped
            for st in updated_plan["subtasks"]:
                if st["task_id"] == task_id:
                    st["status"] = "skipped"
                    break

            # Insert new subtasks after the failed one
            recovery_subtasks = []
            for ns in new_subtasks:
                recovery_subtasks.append(
                    {
                        "task_id": ns.get("id", f"recovery_{task_id}"),
                        "description": ns.get("description", ""),
                        "agent": ns.get("agent", "orchestrator"),
                        "depends_on": ns.get("depends_on", []),
                        "complexity": ns.get("complexity", "medium"),
                        "estimated_actions": 5,
                        "can_parallelize": False,
                        "status": "pending",
                        "result": None,
                        "retries": 0,
                        "max_retries": 3,
                    }
                )

            updated_plan["subtasks"].extend(recovery_subtasks)
            return {
                "strategy": strategy,
                "updated_plan": updated_plan,
                "recovery_subtasks": recovery_subtasks,
                "should_continue": True,
                "reason": parsed.get("reason", "Decomposing into smaller steps"),
            }

        elif strategy == ReplanStrategy.SKIP:
            # Mark as skipped and continue
            for st in updated_plan["subtasks"]:
                if st["task_id"] == task_id:
                    st["status"] = "skipped"
                    break
            return {
                "strategy": strategy,
                "updated_plan": updated_plan,
                "recovery_subtasks": [],
                "should_continue": True,
                "reason": parsed.get("skip_reason", parsed.get("reason", "Skipping optional subtask")),
            }

        else:  # ABORT
            return self._abort_response(plan, failed_subtask, parsed.get("reason", "Aborting plan"))

    def _build_replan_prompt(
        self,
        plan: Dict[str, Any],
        failed_subtask: Dict[str, Any],
        failure_reason: str,
        context: Optional[Dict[str, Any]],
        past_experiences: Optional[List[Dict[str, Any]]],
    ) -> str:
        completed = [
            st["description"]
            for st in plan.get("subtasks", [])
            if st.get("status") == "done"
        ]
        remaining = [
            st["description"]
            for st in plan.get("subtasks", [])
            if st.get("status") == "pending"
        ]

        parts = [
            f"Goal: {plan.get('goal', 'Unknown')}",
            f"\nFailed subtask: {failed_subtask.get('description', '')}",
            f"Agent: {failed_subtask.get('agent', '')}",
            f"Failure reason: {failure_reason[:500]}",
            f"Replan attempt: {self._replan_counts.get(failed_subtask.get('task_id', ''), 0)}/{self.max_replan_attempts}",
            f"\nCompleted subtasks: {json.dumps(completed)}",
            f"Remaining subtasks: {json.dumps(remaining)}",
        ]

        if context:
            parts.append(f"\nCurrent context: {json.dumps(context)[:300]}")

        if past_experiences:
            parts.append("\nRelevant past failures:")
            for exp in past_experiences[:3]:
                if exp.get("outcome") == "failure":
                    parts.append(f"  - {exp.get('content', '')[:200]}")

        return "\n".join(parts)

    def _retry_response(
        self, plan: Dict[str, Any], failed_subtask: Dict[str, Any]
    ) -> Dict[str, Any]:
        updated_plan = dict(plan)
        task_id = failed_subtask.get("task_id", "")
        for st in updated_plan["subtasks"]:
            if st["task_id"] == task_id:
                st["status"] = "pending"
                st["retries"] = st.get("retries", 0) + 1
                break
        return {
            "strategy": ReplanStrategy.RETRY,
            "updated_plan": updated_plan,
            "recovery_subtasks": [],
            "should_continue": True,
            "reason": "Defaulting to retry",
        }

    def _abort_response(
        self, plan: Dict[str, Any], failed_subtask: Dict[str, Any], reason: str
    ) -> Dict[str, Any]:
        return {
            "strategy": ReplanStrategy.ABORT,
            "updated_plan": plan,
            "recovery_subtasks": [],
            "should_continue": False,
            "reason": reason,
        }
