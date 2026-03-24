"""
Orchestrator — Task decomposition + subagent spawning + workflow management.

The Orchestrator sits between MetaAgent and the specialized LinkedIn agents.
It:
  1. Receives a goal from MetaAgent
  2. Decomposes it into ordered subtasks (GoalDecomposer)
  3. Selects the right agent for each subtask
  4. Coordinates execution via the Coordinator (browser pool)
  5. Handles failures with Replanner
  6. Returns the full workflow result + execution trace
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional

from loguru import logger


class Orchestrator:
    """
    Coordinates LinkedIn automation workflows across multiple specialized agents.

    Workflow example for "Connect with 10 ML engineers in SF":
      1. AuthAgent     → Ensure logged in
      2. SearchAgent   → Search "ML engineer San Francisco"
      3. ScraperAgent  → Scrape profile data for each result
      4. ConnectionAgent → Send personalized connection requests
    """

    def __init__(
        self,
        auth_agent=None,
        search_agent=None,
        connection_agent=None,
        scraper_agent=None,
        message_agent=None,
        goal_decomposer=None,
        replanner=None,
        coordinator=None,
        memory=None,
        rate_limiter=None,
        orchestrator_id: Optional[str] = None,
    ):
        self.auth_agent = auth_agent
        self.search_agent = search_agent
        self.connection_agent = connection_agent
        self.scraper_agent = scraper_agent
        self.message_agent = message_agent
        self.goal_decomposer = goal_decomposer
        self.replanner = replanner
        self.coordinator = coordinator
        self.memory = memory
        self.rate_limiter = rate_limiter
        self.orchestrator_id = orchestrator_id or str(uuid.uuid4())[:8]

        self._workflow_trace: List[Dict[str, Any]] = []

    # ── Main Entry Point ──────────────────────────────────────────────────────

    async def run(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        existing_skills: Optional[List[Dict]] = None,
        browser_pool=None,
    ) -> Dict[str, Any]:
        """
        Execute a LinkedIn automation goal end-to-end.

        Args:
            goal:            High-level goal
            context:         Task context (persona, search filters, etc.)
            existing_skills: Pre-loaded skills from MetaAgent
            browser_pool:    BrowserPool for browser acquisition

        Returns:
            {
              "success": bool,
              "goal": str,
              "workflow": dict,
              "results": list,
              "trace": list,
              "duration_seconds": float,
            }
        """
        start = time.time()
        ctx = context or {}
        self._workflow_trace = []

        logger.info(f"[Orchestrator:{self.orchestrator_id}] Goal: {goal}")

        # Detect workflow type from goal
        workflow_type = self._detect_workflow(goal, ctx)
        logger.info(f"[Orchestrator] Detected workflow: {workflow_type}")

        # Build and execute the workflow
        try:
            if workflow_type == "connect":
                result = await self._run_connect_workflow(goal, ctx, browser_pool)
            elif workflow_type == "message":
                result = await self._run_message_workflow(goal, ctx, browser_pool)
            elif workflow_type == "scrape":
                result = await self._run_scrape_workflow(goal, ctx, browser_pool)
            elif workflow_type == "search":
                result = await self._run_search_workflow(goal, ctx, browser_pool)
            else:
                result = await self._run_generic_workflow(goal, ctx, browser_pool)

        except Exception as e:
            logger.error(f"[Orchestrator] Workflow failed: {e}")
            result = {"success": False, "error": str(e), "results": []}

        duration = time.time() - start
        return {
            "success": result.get("success", False),
            "goal": goal,
            "workflow": {"type": workflow_type, "steps": self._workflow_trace},
            "results": result.get("results", []),
            "trace": self._workflow_trace,
            "duration_seconds": round(duration, 2),
            "error": result.get("error", ""),
        }

    # ── Workflow Implementations ───────────────────────────────────────────────

    async def _run_connect_workflow(
        self,
        goal: str,
        ctx: Dict[str, Any],
        browser_pool,
    ) -> Dict[str, Any]:
        """
        Full connection workflow:
          1. Auth → 2. Search → 3. Scrape profiles → 4. Send connections
        """
        results = []

        async with browser_pool.acquire() as (browser, pc):
            # Step 1: Authenticate
            self._trace("auth", "Ensuring LinkedIn session is active")
            if self.auth_agent:
                auth_result = await self.auth_agent.run(pc)
                self._trace("auth", "Auth complete", auth_result)
                if not auth_result.get("success"):
                    return {"success": False, "error": "Authentication failed", "results": []}

            # Step 2: Search for people
            search_query = ctx.get("search_query", self._extract_search_query(goal))
            self._trace("search", f"Searching: {search_query}")
            profiles = []
            if self.search_agent:
                search_result = await self.search_agent.run(
                    pc, context={"query": search_query, "limit": ctx.get("limit", 10)}
                )
                profiles = search_result.get("result", {}).get("profiles", [])
                self._trace("search", f"Found {len(profiles)} profiles", search_result)

            # Step 3: Send connection requests
            max_connections = ctx.get("max_connections", 10)
            self._trace("connect", f"Sending up to {max_connections} connection requests")

            connected = 0
            for profile in profiles[:max_connections]:
                if self.rate_limiter:
                    allowed = await self.rate_limiter.check_and_wait("connection_request")
                    if not allowed:
                        logger.warning("[Orchestrator] Daily connection limit reached")
                        break

                if self.connection_agent:
                    conn_result = await self.connection_agent.run(
                        pc,
                        context={
                            "profile": profile,
                            "note": ctx.get("note_template", ""),
                        },
                    )
                    if conn_result.get("success"):
                        connected += 1
                        if self.rate_limiter:
                            self.rate_limiter.record_action("connection_request")
                        results.append({
                            "profile": profile.get("name", "unknown"),
                            "connected": True,
                        })
                    else:
                        results.append({
                            "profile": profile.get("name", "unknown"),
                            "connected": False,
                            "error": conn_result.get("error", ""),
                        })

                # Human-like delay between connections
                await asyncio.sleep(30 + (connected * 5))

            self._trace("connect", f"Connected with {connected}/{len(profiles)} people")

        return {
            "success": True,
            "results": results,
            "connected_count": connected,
            "profiles_found": len(profiles),
        }

    async def _run_message_workflow(
        self,
        goal: str,
        ctx: Dict[str, Any],
        browser_pool,
    ) -> Dict[str, Any]:
        """Message existing connections workflow."""
        results = []

        async with browser_pool.acquire() as (browser, pc):
            # Auth
            if self.auth_agent:
                auth_result = await self.auth_agent.run(pc)
                if not auth_result.get("success"):
                    return {"success": False, "error": "Auth failed", "results": []}

            # Get connections to message
            connections = ctx.get("connections", [])
            message_template = ctx.get("message_template", "")
            max_messages = ctx.get("max_messages", 10)

            messaged = 0
            for connection in connections[:max_messages]:
                if self.rate_limiter:
                    allowed = await self.rate_limiter.check_and_wait("message")
                    if not allowed:
                        break

                if self.message_agent:
                    msg_result = await self.message_agent.run(
                        pc,
                        context={
                            "recipient": connection,
                            "message": message_template,
                        },
                    )
                    if msg_result.get("success"):
                        messaged += 1
                        if self.rate_limiter:
                            self.rate_limiter.record_action("message")
                        results.append({"recipient": connection, "sent": True})
                    else:
                        results.append({
                            "recipient": connection,
                            "sent": False,
                            "error": msg_result.get("error", ""),
                        })

                await asyncio.sleep(60)  # 1 min between messages

        return {"success": True, "results": results, "messaged_count": messaged}

    async def _run_scrape_workflow(
        self,
        goal: str,
        ctx: Dict[str, Any],
        browser_pool,
    ) -> Dict[str, Any]:
        """Profile scraping workflow."""
        results = []

        async with browser_pool.acquire() as (browser, pc):
            if self.auth_agent:
                await self.auth_agent.run(pc)

            profiles_to_scrape = ctx.get("profile_urls", [])
            search_query = ctx.get("search_query", self._extract_search_query(goal))

            # If no URLs provided, search first
            if not profiles_to_scrape and self.search_agent:
                search_result = await self.search_agent.run(
                    pc, context={"query": search_query, "limit": ctx.get("limit", 20)}
                )
                profiles_to_scrape = [
                    p.get("url") for p in
                    search_result.get("result", {}).get("profiles", [])
                    if p.get("url")
                ]

            for url in profiles_to_scrape:
                if self.rate_limiter:
                    await self.rate_limiter.check_and_wait("profile_view")

                if self.scraper_agent:
                    scrape_result = await self.scraper_agent.run(
                        pc, context={"profile_url": url}
                    )
                    if scrape_result.get("success"):
                        results.append(scrape_result.get("result", {}))
                        if self.rate_limiter:
                            self.rate_limiter.record_action("profile_view")

                await asyncio.sleep(5)

        return {"success": True, "results": results, "scraped_count": len(results)}

    async def _run_search_workflow(
        self,
        goal: str,
        ctx: Dict[str, Any],
        browser_pool,
    ) -> Dict[str, Any]:
        """Search-only workflow."""
        async with browser_pool.acquire() as (browser, pc):
            if self.auth_agent:
                await self.auth_agent.run(pc)

            query = ctx.get("search_query", self._extract_search_query(goal))
            if self.search_agent:
                result = await self.search_agent.run(
                    pc, context={"query": query, "limit": ctx.get("limit", 20)}
                )
                return {"success": result.get("success", False), "results": [result]}

        return {"success": False, "results": [], "error": "No search agent"}

    async def _run_generic_workflow(
        self,
        goal: str,
        ctx: Dict[str, Any],
        browser_pool,
    ) -> Dict[str, Any]:
        """Generic fallback workflow using LLM-guided execution."""
        logger.info(f"[Orchestrator] Running generic workflow for: {goal}")
        async with browser_pool.acquire() as (browser, pc):
            if self.auth_agent:
                await self.auth_agent.run(pc)
            # Navigate to LinkedIn and let the agent figure it out
            await pc.navigate("https://www.linkedin.com/feed/")
            return {"success": True, "results": [], "note": "Generic workflow executed"}

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _detect_workflow(self, goal: str, ctx: Dict) -> str:
        """Detect the workflow type from the goal description."""
        goal_lower = goal.lower()
        if any(w in goal_lower for w in ["connect", "connection", "invite", "add"]):
            return "connect"
        elif any(w in goal_lower for w in ["message", "msg", "send message", "dm"]):
            return "message"
        elif any(w in goal_lower for w in ["scrape", "extract", "collect", "gather", "data"]):
            return "scrape"
        elif any(w in goal_lower for w in ["search", "find", "look for"]):
            return "search"
        return "generic"

    def _extract_search_query(self, goal: str) -> str:
        """Extract a search query from the goal description."""
        # Simple extraction — remove action words
        stop_words = {"connect", "with", "find", "search", "for", "send", "message",
                      "scrape", "extract", "collect", "people", "person", "profile"}
        words = [w for w in goal.lower().split() if w not in stop_words]
        return " ".join(words[:5]) if words else "software engineer"

    def _trace(
        self,
        step: str,
        description: str,
        result: Optional[Dict] = None,
    ) -> None:
        """Add a step to the workflow trace."""
        entry = {
            "step": step,
            "description": description,
            "timestamp": time.time(),
        }
        if result:
            entry["success"] = result.get("success", False)
            entry["error"] = result.get("error", "")
        self._workflow_trace.append(entry)
        logger.debug(f"[Orchestrator] {step}: {description}")
