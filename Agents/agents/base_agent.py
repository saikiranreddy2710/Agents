"""
Base Agent — Core screenshot→retrieve→plan→act→reflect loop.

Every LinkedIn subagent inherits from BaseAgent.
The loop is:
  1. Screenshot current page
  2. Retrieve relevant past experiences from ChromaDB (RAG)
  3. Enrich prompt with experiences
  4. LLM decides next action (with chain-of-thought)
  5. Execute action via PageController
  6. Record outcome to ChromaDB
  7. Reflect: did it work? update strategy
  8. Repeat until goal achieved or max_steps reached
"""

from __future__ import annotations

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from loguru import logger


class BaseAgent(ABC):
    """
    Abstract base agent with the core perception-action-reflection loop.

    Subclasses must implement:
      - goal: str property
      - execute_step(): one step of the agent's specific task
    """

    def __init__(
        self,
        name: str,
        llm=None,
        memory=None,
        rate_limiter=None,
        human_behavior=None,
        max_steps: int = 30,
        session_id: Optional[str] = None,
    ):
        self.name = name
        self.llm = llm
        self.memory = memory
        self.rate_limiter = rate_limiter
        self.human_behavior = human_behavior
        self.max_steps = max_steps
        self.session_id = session_id or str(uuid.uuid4())[:8]

        self._step_count = 0
        self._start_time: Optional[float] = None
        self._action_history: List[Dict[str, Any]] = []
        self._is_done = False
        self._result: Optional[Dict[str, Any]] = None

    # ── Abstract Interface ────────────────────────────────────────────────────

    @property
    @abstractmethod
    def goal(self) -> str:
        """Human-readable goal description for this agent."""
        ...

    @abstractmethod
    async def execute_step(
        self,
        page_controller,
        screenshot_b64: str,
        experiences: List[Dict],
        step: int,
    ) -> Dict[str, Any]:
        """
        Execute one step of the agent's task.

        Args:
            page_controller: PageController for browser interaction
            screenshot_b64:  Current page screenshot (base64)
            experiences:     Retrieved past experiences from ChromaDB
            step:            Current step number

        Returns:
            {
              "action": str,        # What action was taken
              "success": bool,      # Did it succeed?
              "done": bool,         # Is the goal achieved?
              "result": dict,       # Task-specific result data
              "error": str,         # Error message if failed
            }
        """
        ...

    # ── Main Run Loop ─────────────────────────────────────────────────────────

    async def run(
        self,
        page_controller,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Run the agent's main loop until goal is achieved or max_steps reached.

        Args:
            page_controller: PageController instance
            context:         Optional initial context (e.g., search query, target profile)

        Returns:
            {
              "success": bool,
              "goal": str,
              "steps_taken": int,
              "duration_seconds": float,
              "result": dict,
              "action_history": list,
              "error": str,
            }
        """
        self._start_time = time.time()
        self._step_count = 0
        self._action_history = []
        self._is_done = False
        self._result = None

        logger.info(f"[{self.name}:{self.session_id}] Starting — Goal: {self.goal}")

        if context:
            logger.debug(f"[{self.name}] Context: {context}")

        try:
            while self._step_count < self.max_steps and not self._is_done:
                self._step_count += 1
                step_start = time.time()

                logger.debug(
                    f"[{self.name}] Step {self._step_count}/{self.max_steps} — "
                    f"URL: {page_controller.url}"
                )

                # 1. Take screenshot
                screenshot_b64 = await self._take_screenshot(page_controller)

                # 2. Retrieve past experiences (RAG)
                experiences = await self._retrieve_experiences(
                    page_controller.url, screenshot_b64
                )

                # 3. Execute one step (subclass-specific logic)
                step_result = await self.execute_step(
                    page_controller=page_controller,
                    screenshot_b64=screenshot_b64,
                    experiences=experiences,
                    step=self._step_count,
                )

                # 4. Record outcome
                step_duration = time.time() - step_start
                await self._record_outcome(
                    page_controller.url,
                    step_result,
                    step_duration,
                )

                # 5. Track history
                self._action_history.append({
                    "step": self._step_count,
                    "url": page_controller.url,
                    "action": step_result.get("action", "unknown"),
                    "success": step_result.get("success", False),
                    "duration_ms": int(step_duration * 1000),
                })

                # 6. Check if done
                if step_result.get("done"):
                    self._is_done = True
                    self._result = step_result.get("result", {})
                    logger.info(
                        f"[{self.name}] Goal achieved in {self._step_count} steps!"
                    )
                    break

                # 7. Check for failure
                if step_result.get("abort"):
                    logger.error(
                        f"[{self.name}] Aborting: {step_result.get('error', 'unknown error')}"
                    )
                    break

                # 8. Human-like delay between steps
                if self.human_behavior:
                    await self.human_behavior.think_pause(0.5, 2.0)
                else:
                    await asyncio.sleep(1.0)

            # Build final result
            duration = time.time() - self._start_time
            success = self._is_done and (self._result is not None or self._step_count > 0)

            final_result = {
                "success": success,
                "goal": self.goal,
                "steps_taken": self._step_count,
                "duration_seconds": round(duration, 2),
                "result": self._result or {},
                "action_history": self._action_history,
                "error": "" if success else f"Goal not achieved after {self._step_count} steps",
            }

            logger.info(
                f"[{self.name}] Finished: success={success}, "
                f"steps={self._step_count}, duration={duration:.1f}s"
            )
            return final_result

        except Exception as e:
            duration = time.time() - (self._start_time or time.time())
            logger.error(f"[{self.name}] Fatal error: {e}")
            return {
                "success": False,
                "goal": self.goal,
                "steps_taken": self._step_count,
                "duration_seconds": round(duration, 2),
                "result": {},
                "action_history": self._action_history,
                "error": str(e),
            }

    # ── Helper Methods ────────────────────────────────────────────────────────

    async def _take_screenshot(self, page_controller) -> str:
        """Take a screenshot and return base64."""
        try:
            return await page_controller.get_screenshot_base64()
        except Exception as e:
            logger.debug(f"[{self.name}] Screenshot failed: {e}")
            return ""

    async def _retrieve_experiences(
        self,
        url: str,
        screenshot_b64: str,
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant past experiences from ChromaDB."""
        if not self.memory:
            return []
        try:
            return await self.memory.retrieve_relevant(
                query=f"{self.goal} on {url}",
                limit=5,
            )
        except Exception as e:
            logger.debug(f"[{self.name}] Experience retrieval failed: {e}")
            return []

    async def _record_outcome(
        self,
        url: str,
        step_result: Dict[str, Any],
        duration: float,
    ) -> None:
        """Record action outcome to ChromaDB for future learning."""
        if not self.memory:
            return
        try:
            await self.memory.record_action(
                agent=self.name,
                url=url,
                action=step_result.get("action", "unknown"),
                success=step_result.get("success", False),
                duration=duration,
                metadata=step_result,
            )
        except Exception as e:
            logger.debug(f"[{self.name}] Outcome recording failed: {e}")

    async def decide_action(
        self,
        screenshot_b64: str,
        task_description: str,
        experiences: List[Dict],
        available_actions: List[str],
        page_info: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Use the LLM to decide the next action based on screenshot + experiences.

        Returns:
            {"action": str, "params": dict, "reasoning": str}
        """
        if not self.llm:
            return {"action": "wait", "params": {}, "reasoning": "No LLM configured"}

        try:
            # Build context from experiences
            experience_context = ""
            if experiences:
                experience_context = "\n".join([
                    f"- Past: {e.get('action', '?')} → {e.get('outcome', '?')}"
                    for e in experiences[:3]
                ])

            prompt = f"""You are a LinkedIn automation agent.
Goal: {task_description}
Current URL: {page_info.get('url', 'unknown') if page_info else 'unknown'}
Available actions: {', '.join(available_actions)}

Past experiences:
{experience_context or 'No past experiences yet.'}

Look at the screenshot and decide the BEST next action.
Respond with JSON: {{"action": "<action>", "params": {{}}, "reasoning": "<why>"}}"""

            response = await self.llm.decide(
                prompt=prompt,
                screenshot_b64=screenshot_b64,
            )
            return response

        except Exception as e:
            logger.debug(f"[{self.name}] LLM decision failed: {e}")
            return {"action": "screenshot", "params": {}, "reasoning": f"LLM error: {e}"}

    def log_step(self, message: str, level: str = "debug") -> None:
        """Log a step message with agent context."""
        full_msg = f"[{self.name}:{self.session_id}] Step {self._step_count}: {message}"
        getattr(logger, level)(full_msg)
