"""
Meta Agent — Strategic goal manager inspired by AgentFactory (arXiv:2603.18000).

The MetaAgent is the top-level controller that:
  1. Receives a high-level goal (e.g., "Connect with 10 ML engineers in SF")
  2. Decomposes it into subtasks using GoalDecomposer
  3. Spawns specialized subagents for each subtask
  4. Saves successful workflows as reusable executable subagents (SKILL.md)
  5. Supersedes old subagents with improved versions
  6. Manages the self-evolution lifecycle

AgentFactory Actions (MetaAgent can perform):
  - create_subagent:         Create a new specialized subagent
  - run_subagent:            Execute a saved subagent
  - modify_subagent:         Improve an existing subagent
  - finish:                  Mark goal as complete
  - list_saved_subagents:    List all saved skills
  - get_skill_description:   Get details of a skill
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List, Optional

from loguru import logger

import json

from skills_utils import (
    save_skill,
    load_skill,
    list_skills,
    get_skill_description,
    supersede_skill,
    update_skill_stats,
    SkillMetadata,
)


# ── MetaAgent Actions ─────────────────────────────────────────────────────────

META_ACTIONS = [
    "create_subagent",
    "run_subagent",
    "modify_subagent",
    "finish",
    "list_saved_subagents",
    "get_skill_description",
]


class MetaAgent:
    """
    Strategic goal manager with AgentFactory-style subagent accumulation.

    Self-Evolution Loop:
      Goal → Decompose → Spawn subagents → Execute → Record outcomes
           → Save successful workflows as skills → Improve on next run
    """

    def __init__(
        self,
        llm=None,
        memory=None,
        orchestrator=None,
        skills_dir: str = "skills",
        workspace_dir: str = "workspace",
        agent_id: Optional[str] = None,
    ):
        self.llm = llm
        self.memory = memory
        self.orchestrator = orchestrator
        self.skills_dir = skills_dir
        self.workspace_dir = workspace_dir
        self.agent_id = agent_id or str(uuid.uuid4())[:8]

        self._goal: Optional[str] = None
        self._task_history: List[Dict[str, Any]] = []
        self._saved_skills: Dict[str, Any] = {}

        os.makedirs(workspace_dir, exist_ok=True)
        os.makedirs(skills_dir, exist_ok=True)

    # ── Main Entry Point ──────────────────────────────────────────────────────

    async def run(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        browser_pool=None,
    ) -> Dict[str, Any]:
        """
        Execute a high-level goal using the full AgentFactory lifecycle.

        Phases:
          1. Install:    Check for existing skills, load relevant ones
          2. Self-Evolve: Decompose goal, spawn subagents, execute
          3. Deploy:     Save successful workflows as reusable skills

        Args:
            goal:         High-level goal description
            context:      Optional context (persona, filters, etc.)
            browser_pool: BrowserPool for parallel execution

        Returns:
            {"success": bool, "goal": str, "result": dict, "skills_saved": list}
        """
        self._goal = goal
        logger.info(f"[MetaAgent:{self.agent_id}] Goal: {goal}")

        # ── Phase 1: Install (check existing skills) ──────────────────────────
        existing_skills = await self._find_relevant_skills(goal)
        if existing_skills:
            logger.info(
                f"[MetaAgent] Found {len(existing_skills)} relevant skills: "
                f"{[s['name'] for s in existing_skills]}"
            )

        # ── Phase 2: Self-Evolve (decompose + execute) ────────────────────────
        if self.orchestrator:
            result = await self.orchestrator.run(
                goal=goal,
                context=context or {},
                existing_skills=existing_skills,
                browser_pool=browser_pool,
            )
        else:
            result = {"success": False, "error": "No orchestrator configured"}

        # ── Phase 3: Deploy (save successful workflows as skills) ─────────────
        skills_saved = []
        if result.get("success") and result.get("workflow"):
            skill_name = await self._save_workflow_as_skill(
                goal=goal,
                workflow=result["workflow"],
                result=result,
            )
            if skill_name:
                skills_saved.append(skill_name)

        # Record to memory
        await self._record_goal_outcome(goal, result)

        return {
            "success": result.get("success", False),
            "goal": goal,
            "result": result,
            "skills_saved": skills_saved,
            "existing_skills_used": [s["name"] for s in existing_skills],
        }

    # ── AgentFactory Actions ──────────────────────────────────────────────────

    async def create_subagent(
        self,
        name: str,
        description: str,
        agent_code: str,
        skill_type: str = "subagent",
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create and save a new specialized subagent as a skill.

        The agent_code is executable Python that follows the subagent pattern:
            def main(query: str) -> dict:
                return {"answer": ..., "summary": ...}
        """
        metadata = SkillMetadata(
            name=name,
            description=description,
            skill_type=skill_type,
            tags=tags or [],
            entry_file=f"{name}.py",
        )

        success = save_skill(
            metadata=metadata,
            code=agent_code,
            skills_dir=self.skills_dir,
        )

        if success:
            self._saved_skills[name] = metadata
            logger.info(f"[MetaAgent] Created subagent: {name}")
            return {"success": True, "name": name, "path": f"{self.skills_dir}/subagents/{name}"}
        else:
            return {"success": False, "error": f"Failed to save subagent: {name}"}

    async def run_subagent(
        self,
        name: str,
        query: str,
        context: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Execute a saved subagent skill.

        Args:
            name:    Skill name
            query:   Query/task for the subagent
            context: Optional context dict

        Returns:
            {"answer": ..., "summary": ..., "success": bool}
        """
        skill = load_skill(name, skills_dir=self.skills_dir)
        if not skill:
            return {"success": False, "error": f"Skill '{name}' not found"}

        try:
            # Execute the skill's main() function
            import importlib.util
            import sys

            spec = importlib.util.spec_from_file_location(name, skill["entry_path"])
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if hasattr(module, "main"):
                result = module.main(query)
                logger.info(f"[MetaAgent] Ran subagent '{name}': {result.get('summary', '')}")
                return {"success": True, **result}
            else:
                return {"success": False, "error": f"Skill '{name}' has no main() function"}

        except Exception as e:
            logger.error(f"[MetaAgent] Error running subagent '{name}': {e}")
            return {"success": False, "error": str(e)}

    async def modify_subagent(
        self,
        name: str,
        new_code: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        Improve an existing subagent (supersede mechanism).

        The old version is archived, new version takes its place.
        """
        result = supersede_skill(
            name=name,
            new_code=new_code,
            reason=reason,
            skills_dir=self.skills_dir,
        )
        if result:
            logger.info(f"[MetaAgent] Modified subagent '{name}': {reason}")
            return {"success": True, "name": name, "reason": reason}
        return {"success": False, "error": f"Failed to modify '{name}'"}

    async def finish(
        self,
        summary: str,
        result: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Mark the current goal as complete."""
        logger.info(f"[MetaAgent] Goal finished: {summary}")
        return {
            "success": True,
            "goal": self._goal,
            "summary": summary,
            "result": result or {},
        }

    async def list_saved_subagents(self) -> List[Dict[str, Any]]:
        """List all saved skills/subagents."""
        return list_skills(skills_dir=self.skills_dir)

    async def get_skill_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Get detailed description of a skill."""
        return get_skill_description(name, skills_dir=self.skills_dir)

    # ── Self-Evolution ────────────────────────────────────────────────────────

    async def evolve_from_failures(self) -> List[str]:
        """
        Analyze failed actions from memory and generate improved strategies.
        Returns list of skills that were improved.
        """
        if not self.memory:
            return []

        improved = []
        try:
            # Get recent failures from memory
            failures = await self.memory.retrieve_failures(limit=10)

            for failure in failures:
                skill_name = failure.get("skill_name")
                if not skill_name:
                    continue

                # Ask LLM to suggest improvement
                if self.llm:
                    improvement = await self.llm.suggest_improvement(
                        failure_description=failure.get("description", ""),
                        error=failure.get("error", ""),
                        current_code=failure.get("code", ""),
                    )
                    if improvement.get("improved_code"):
                        await self.modify_subagent(
                            name=skill_name,
                            new_code=improvement["improved_code"],
                            reason=improvement.get("reason", "Auto-evolved from failure"),
                        )
                        improved.append(skill_name)

        except Exception as e:
            logger.error(f"[MetaAgent] Evolution from failures failed: {e}")

        return improved

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _find_relevant_skills(self, goal: str) -> List[Dict[str, Any]]:
        """
        Find existing skills relevant to the current goal.

        Memento-Skills approach: uses ChromaDB semantic search on the
        skills_index collection instead of brittle keyword overlap matching.
        Falls back to keyword matching if ChromaDB is unavailable.
        """
        # ── Primary: Semantic search via ChromaDB skills_index ────────────────
        if self.memory and self.memory.is_healthy():
            try:
                semantic_results = self.memory.recall(
                    query=goal,
                    collections=["skills_index"],
                    n_results=5,
                )
                if semantic_results:
                    relevant = []
                    for r in semantic_results:
                        score = r.get("similarity_score", 0)
                        if score >= 0.40:  # Minimum semantic similarity threshold
                            meta = r.get("metadata", {})
                            skill_name = meta.get("skill_name", "")
                            if skill_name:
                                relevant.append({
                                    "name": skill_name,
                                    "description": meta.get("description", ""),
                                    "skill_type": meta.get("skill_type", ""),
                                    "tags": json.loads(meta.get("tags", "[]")),
                                    "similarity_score": round(score, 3),
                                    "success_rate": float(meta.get("success_rate", 1.0)),
                                    "usage_count": int(meta.get("usage_count", 0)),
                                })
                    if relevant:
                        logger.info(
                            f"[MetaAgent] Semantic skill search: {len(relevant)} relevant skills "
                            f"for goal '{goal[:60]}' "
                            f"(top score={relevant[0]['similarity_score']:.2f})"
                        )
                        return relevant[:3]
            except Exception as e:
                logger.debug(f"[MetaAgent] Semantic skill search failed, falling back: {e}")

        # ── Fallback: keyword overlap matching ────────────────────────────────
        all_skills = list_skills(skills_dir=self.skills_dir)
        if not all_skills:
            return []

        goal_lower = goal.lower()
        relevant = []
        for skill in all_skills:
            skill_text = f"{skill.get('name', '')} {skill.get('description', '')}".lower()Perfect! Now implement semantic skill retrieval in `agents/meta_agent.py`:
<edit_file>
<path>Agents/agents/meta_agent.py</path>
<content>
<<<<<<< SEARCH
    async def _find_relevant_skills(self, goal: str) -> List[Dict[str, Any]]:
        """Find existing skills relevant to the current goal."""

    async def _save_workflow_as_skill(
        self,
        goal: str,
        workflow: Dict[str, Any],
        result: Dict[str, Any],
    ) -> Optional[str]:
        """Save a successful workflow as a reusable skill."""
        try:
            # Generate skill name from goal
            skill_name = goal.lower().replace(" ", "_")[:30]
            skill_name = "".join(c for c in skill_name if c.isalnum() or c == "_")

            # Generate executable Python code for the workflow
            code = self._workflow_to_code(skill_name, goal, workflow)

            metadata = SkillMetadata(
                name=skill_name,
                description=f"Auto-generated skill for: {goal}",
                skill_type="workflow",
                tags=["auto-generated", "linkedin"],
                entry_file=f"{skill_name}.py",
            )

            success = save_skill(
                metadata=metadata,
                code=code,
                skills_dir=self.skills_dir,
            )

            if success:
                logger.info(f"[MetaAgent] Saved workflow as skill: {skill_name}")
                return skill_name

        except Exception as e:
            logger.error(f"[MetaAgent] Failed to save workflow as skill: {e}")

        return None

    def _workflow_to_code(
        self,
        name: str,
        goal: str,
        workflow: Dict[str, Any],
    ) -> str:
        """Convert a workflow dict to executable Python code."""
        steps_json = json.dumps(workflow.get("steps", []), indent=4)
        return f'''"""
Auto-generated skill: {name}
Goal: {goal}
Generated by MetaAgent
"""

WORKFLOW_STEPS = {steps_json}


def main(query: str) -> dict:
    """
    Execute the {name} workflow.

    Args:
        query: Task-specific query or parameters

    Returns:
        {{"answer": str, "summary": str}}
    """
    # This skill was auto-generated from a successful workflow.
    # It can be improved by the MetaAgent's evolution engine.
    return {{
        "answer": f"Executing {name} workflow for: {{query}}",
        "summary": f"Workflow {name} completed",
        "steps": WORKFLOW_STEPS,
    }}
'''

    async def _record_goal_outcome(
        self,
        goal: str,
        result: Dict[str, Any],
    ) -> None:
        """Record goal outcome to memory for future learning."""
        if not self.memory:
            return
        try:
            await self.memory.record_action(
                agent="meta_agent",
                url="meta",
                action=f"goal: {goal[:50]}",
                success=result.get("success", False),
                duration=0,
                metadata={"goal": goal, "result_summary": str(result)[:200]},
            )
        except Exception as e:
            logger.debug(f"[MetaAgent] Failed to record goal outcome: {e}")
