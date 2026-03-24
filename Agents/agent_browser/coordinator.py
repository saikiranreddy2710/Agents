"""
Coordinator — Distributes tasks to subagents across the browser pool.

The Coordinator is the bridge between the MetaAgent's task plan
and the BrowserPool's execution capacity.

Responsibilities:
  - Receive subtasks from the Orchestrator
  - Assign each subtask to an available browser instance
  - Run parallel subtasks concurrently
  - Collect and aggregate results
  - Report progress back to the Orchestrator
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from .browser_pool import BrowserPool


class TaskResult:
    """Result of a coordinated task execution."""

    def __init__(
        self,
        task_id: str,
        success: bool,
        result: Optional[Dict[str, Any]] = None,
        error: str = "",
        duration_seconds: float = 0.0,
    ):
        self.task_id = task_id
        self.success = success
        self.result = result or {}
        self.error = error
        self.duration_seconds = duration_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
        }


class Coordinator:
    """
    Coordinates task execution across the browser pool.

    Supports both sequential and parallel task execution.
    """

    def __init__(
        self,
        pool: BrowserPool,
        max_concurrent: int = 3,
        task_timeout: int = 300,
    ):
        self.pool = pool
        self.max_concurrent = max_concurrent
        self.task_timeout = task_timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._results: Dict[str, TaskResult] = {}
        self._progress_callback: Optional[Callable] = None

    def set_progress_callback(self, callback: Callable) -> None:
        """Set a callback to receive progress updates."""
        self._progress_callback = callback

    async def run_task(
        self,
        task_id: str,
        task_fn: Callable,
        task_description: str = "",
        **kwargs,
    ) -> TaskResult:
        """
        Run a single task using a browser from the pool.

        Args:
            task_id:          Unique task identifier
            task_fn:          Async function: async def fn(browser, page_controller, **kwargs) -> dict
            task_description: Human-readable description for logging
            **kwargs:         Additional arguments passed to task_fn

        Returns:
            TaskResult
        """
        import time
        start = time.time()

        async with self._semaphore:
            logger.info(f"[Coordinator] Starting task '{task_id}': {task_description}")
            self._notify_progress(task_id, "started", task_description)

            try:
                async with self.pool.acquire() as (browser, page_controller):
                    result = await asyncio.wait_for(
                        task_fn(browser, page_controller, **kwargs),
                        timeout=self.task_timeout,
                    )

                duration = time.time() - start
                task_result = TaskResult(
                    task_id=task_id,
                    success=result.get("success", True),
                    result=result,
                    duration_seconds=duration,
                )
                self._results[task_id] = task_result
                self._notify_progress(task_id, "completed", task_description, result)
                logger.info(
                    f"[Coordinator] Task '{task_id}' completed in {duration:.1f}s"
                )
                return task_result

            except asyncio.TimeoutError:
                duration = time.time() - start
                error = f"Task timed out after {self.task_timeout}s"
                logger.error(f"[Coordinator] Task '{task_id}' timed out")
                task_result = TaskResult(
                    task_id=task_id, success=False,
                    error=error, duration_seconds=duration,
                )
                self._results[task_id] = task_result
                self._notify_progress(task_id, "failed", task_description, error=error)
                return task_result

            except Exception as e:
                duration = time.time() - start
                error = str(e)
                logger.error(f"[Coordinator] Task '{task_id}' failed: {error}")
                task_result = TaskResult(
                    task_id=task_id, success=False,
                    error=error, duration_seconds=duration,
                )
                self._results[task_id] = task_result
                self._notify_progress(task_id, "failed", task_description, error=error)
                return task_result

    async def run_sequential(
        self,
        tasks: List[Dict[str, Any]],
    ) -> List[TaskResult]:
        """
        Run tasks sequentially (one after another).

        Args:
            tasks: List of {"task_id": str, "fn": callable, "description": str, **kwargs}

        Returns:
            List of TaskResult in order
        """
        results = []
        for task in tasks:
            task_id = task["task_id"]
            task_fn = task["fn"]
            description = task.get("description", "")
            kwargs = {k: v for k, v in task.items() if k not in ("task_id", "fn", "description")}

            result = await self.run_task(task_id, task_fn, description, **kwargs)
            results.append(result)

            # Stop on critical failure
            if not result.success and task.get("critical", False):
                logger.warning(f"Critical task '{task_id}' failed. Stopping sequential execution.")
                break

        return results

    async def run_parallel(
        self,
        tasks: List[Dict[str, Any]],
    ) -> List[TaskResult]:
        """
        Run tasks in parallel (up to max_concurrent at a time).

        Args:
            tasks: List of {"task_id": str, "fn": callable, "description": str, **kwargs}

        Returns:
            List of TaskResult (order matches input tasks)
        """
        coroutines = []
        for task in tasks:
            task_id = task["task_id"]
            task_fn = task["fn"]
            description = task.get("description", "")
            kwargs = {k: v for k, v in task.items() if k not in ("task_id", "fn", "description")}
            coroutines.append(self.run_task(task_id, task_fn, description, **kwargs))

        results = await asyncio.gather(*coroutines, return_exceptions=False)
        return list(results)

    async def run_plan(
        self,
        plan: Dict[str, Any],
        agent_registry: Dict[str, Any],
    ) -> Dict[str, TaskResult]:
        """
        Execute a full task plan from the GoalDecomposer.

        Respects task dependencies and parallelizes where possible.

        Args:
            plan:             Plan dict from GoalDecomposer.decompose()
            agent_registry:   Dict mapping agent_name → agent instance

        Returns:
            Dict mapping task_id → TaskResult
        """
        from planning.goal_decomposer import GoalDecomposer
        decomposer = GoalDecomposer.__new__(GoalDecomposer)

        all_results: Dict[str, TaskResult] = {}
        max_iterations = len(plan["subtasks"]) * 3  # Safety limit
        iteration = 0

        while not decomposer.is_plan_complete(plan) and iteration < max_iterations:
            iteration += 1

            # Get ready subtasks
            ready = decomposer.get_ready_subtasks(plan)
            if not ready:
                if decomposer.is_plan_failed(plan):
                    logger.error("Plan failed: no ready subtasks and plan is not complete")
                    break
                await asyncio.sleep(0.5)
                continue

            # Group by parallelizability
            parallel_group = [st for st in ready if st.get("can_parallelize")]
            sequential = [st for st in ready if not st.get("can_parallelize")]

            # Run parallel group
            if parallel_group:
                tasks = self._subtasks_to_task_dicts(parallel_group, agent_registry)
                results = await self.run_parallel(tasks)
                for result in results:
                    all_results[result.task_id] = result
                    if result.success:
                        decomposer.mark_subtask_done(plan, result.task_id, result.result)
                    else:
                        decomposer.mark_subtask_failed(plan, result.task_id, result.error)

            # Run sequential one at a time
            for st in sequential:
                tasks = self._subtasks_to_task_dicts([st], agent_registry)
                results = await self.run_sequential(tasks)
                for result in results:
                    all_results[result.task_id] = result
                    if result.success:
                        decomposer.mark_subtask_done(plan, result.task_id, result.result)
                    else:
                        decomposer.mark_subtask_failed(plan, result.task_id, result.error)

        return all_results

    def get_results(self) -> Dict[str, TaskResult]:
        """Get all task results."""
        return dict(self._results)

    def get_summary(self) -> Dict[str, Any]:
        """Get execution summary."""
        results = list(self._results.values())
        return {
            "total": len(results),
            "successful": sum(1 for r in results if r.success),
            "failed": sum(1 for r in results if not r.success),
            "total_duration": sum(r.duration_seconds for r in results),
            "tasks": [r.to_dict() for r in results],
        }

    def _subtasks_to_task_dicts(
        self,
        subtasks: List[Dict[str, Any]],
        agent_registry: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Convert plan subtasks to coordinator task dicts."""
        task_dicts = []
        for st in subtasks:
            agent_name = st.get("agent", "orchestrator")
            agent = agent_registry.get(agent_name)
            if agent is None:
                logger.warning(f"Agent '{agent_name}' not found in registry, skipping task")
                continue

            async def make_task_fn(agent_instance, subtask):
                async def task_fn(browser, page_controller, **kwargs):
                    return await agent_instance.execute(
                        subtask["description"],
                        page_controller=page_controller,
                        **kwargs,
                    )
                return task_fn

            task_dicts.append({
                "task_id": st["task_id"],
                "fn": asyncio.coroutine(make_task_fn(agent, st)),
                "description": st["description"],
            })

        return task_dicts

    def _notify_progress(
        self,
        task_id: str,
        status: str,
        description: str = "",
        result: Optional[Dict] = None,
        error: str = "",
    ) -> None:
        """Notify progress callback if set."""
        if self._progress_callback:
            try:
                self._progress_callback({
                    "task_id": task_id,
                    "status": status,
                    "description": description,
                    "result": result,
                    "error": error,
                })
            except Exception:
                pass
