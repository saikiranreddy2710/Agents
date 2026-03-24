"""
Enhanced LLM — The self-evolving expert wrapper.

Combines:
  base_model       → Raw LLM (Ollama/LLaVA or Gemini Flash)
  experience_engine → RAG: retrieves past experiences before every decision
  experience_recorder → Records outcomes after every action
  prompt_engine    → Enriches prompts with CoT + retrieved experiences

This is the core intelligence layer. Every call:
  1. Retrieves relevant past experiences from ChromaDB
  2. Enriches the prompt with those experiences
  3. Calls the base LLM
  4. Returns the response (caller records outcome separately)

Usage:
    llm = EnhancedLLM()
    response = await llm.decide(
        task="Click the Connect button",
        messages=[...],
        screenshot_b64="...",
        page_url="https://linkedin.com/in/...",
    )
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from loguru import logger

from .base_model import BaseLLM, get_llm
from .experience_engine import ExperienceEngine
from .experience_recorder import ExperienceRecorder
from .prompt_engine import PromptEngine, OutputParser


class EnhancedLLM:
    """
    Self-evolving LLM wrapper.

    Every decision is enriched with past experiences from ChromaDB.
    Every outcome is recorded back to ChromaDB.
    The agent gets smarter with every interaction.
    """

    def __init__(
        self,
        llm: Optional[BaseLLM] = None,
        experience_engine: Optional[ExperienceEngine] = None,
        experience_recorder: Optional[ExperienceRecorder] = None,
        provider: Optional[str] = None,
    ):
        self.llm = llm or get_llm(provider)
        self.experience_engine = experience_engine or ExperienceEngine()
        self.experience_recorder = experience_recorder or ExperienceRecorder()
        self.prompt_engine = PromptEngine()
        self.output_parser = OutputParser()

    # ── Core Decision Method ──────────────────────────────────────────────────

    async def decide(
        self,
        task: str,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        screenshot_b64: Optional[str] = None,
        page_url: str = "",
        page_context: str = "",
        action_type: Optional[str] = None,
        n_experiences: int = 5,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Make a decision enriched with past experiences.

        Flow:
          1. Retrieve relevant past experiences (RAG)
          2. Enrich the last user message with experience context
          3. Call LLM (with vision if screenshot provided)
          4. Parse and validate the action from response
          5. Return enriched response

        Args:
            task:           Current task description
            messages:       Conversation history
            system:         System prompt override
            screenshot_b64: Base64 screenshot for vision analysis
            page_url:       Current page URL
            page_context:   DOM summary or page description
            action_type:    Hint for experience retrieval
            n_experiences:  Number of past experiences to retrieve
            max_tokens:     Override max tokens

        Returns:
            {
                "success": bool,
                "response": str,
                "action": dict | None,
                "retrieved_experiences": list,
                "error": str | None,
            }
        """
        # Step 1: Retrieve past experiences
        experiences = self.experience_engine.retrieve(
            query=task,
            context=page_context,
            page_url=page_url,
            action_type=action_type,
            n_results=n_experiences,
        )

        # Step 2: Enrich messages with experience context
        enriched_messages = self._enrich_messages(messages, experiences)

        # Step 3: Call LLM (vision or text)
        if screenshot_b64:
            llm_result = await self.llm.complete_with_vision(
                messages=enriched_messages,
                screenshot_b64=screenshot_b64,
                system=system,
                max_tokens=max_tokens,
            )
        else:
            llm_result = await self.llm.complete(
                messages=enriched_messages,
                system=system,
                max_tokens=max_tokens,
            )

        if not llm_result.get("success"):
            return {
                "success": False,
                "response": "",
                "action": None,
                "retrieved_experiences": experiences,
                "error": llm_result.get("error"),
            }

        response = llm_result["response"]

        # Step 4: Parse action from response
        action = self.output_parser.parse_action(response)
        is_valid, validation_error = self.output_parser.validate_action(action or {})

        return {
            "success": True,
            "response": response,
            "action": action if is_valid else None,
            "action_valid": is_valid,
            "validation_error": validation_error,
            "retrieved_experiences": experiences,
            "tokens_used": llm_result.get("tokens_used", 0),
            "model": llm_result.get("model", ""),
            "provider": llm_result.get("provider", ""),
            "error": None,
        }

    def decide_sync(
        self,
        task: str,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        screenshot_b64: Optional[str] = None,
        page_url: str = "",
        page_context: str = "",
        action_type: Optional[str] = None,
        n_experiences: int = 5,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Synchronous wrapper around decide()."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self.decide(
                            task, messages, system, screenshot_b64,
                            page_url, page_context, action_type,
                            n_experiences, max_tokens,
                        ),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.decide(
                        task, messages, system, screenshot_b64,
                        page_url, page_context, action_type,
                        n_experiences, max_tokens,
                    )
                )
        except Exception as e:
            return {"success": False, "response": "", "action": None, "error": str(e)}

    # ── Vision Analysis ───────────────────────────────────────────────────────

    async def analyze_screenshot(
        self,
        screenshot_b64: str,
        task: str,
        page_url: str = "",
        system: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze a screenshot to understand the current page state.

        Returns structured analysis:
        {
            "page_state": str,
            "visible_elements": list,
            "recommended_action": dict,
            "confidence": float,
        }
        """
        # Retrieve visual pattern experiences
        experiences = self.experience_engine.retrieve_for_screenshot(
            screenshot_description=task,
            page_url=page_url,
            n_results=3,
        )

        vision_prompt = self.prompt_engine.build_vision_prompt(
            task=task,
            retrieved_experiences=experiences,
        )

        messages = [{"role": "user", "content": vision_prompt}]

        llm_result = await self.llm.complete_with_vision(
            messages=messages,
            screenshot_b64=screenshot_b64,
            system=system,
            max_tokens=1024,
        )

        if not llm_result.get("success"):
            return {
                "success": False,
                "error": llm_result.get("error"),
                "page_state": "unknown",
            }

        # Parse JSON response
        parsed = self.output_parser.parse_json_response(llm_result["response"])
        if parsed:
            return {"success": True, **parsed, "raw_response": llm_result["response"]}

        return {
            "success": True,
            "page_state": llm_result["response"],
            "raw_response": llm_result["response"],
        }

    # ── Recording ─────────────────────────────────────────────────────────────

    def record_outcome(
        self,
        action_type: str,
        action_params: Dict[str, Any],
        outcome: str,
        page_url: str = "",
        page_title: str = "",
        page_context: str = "",
        error_message: str = "",
        learned_pattern: str = "",
        session_id: str = "",
    ) -> bool:
        """
        Record an action outcome to ChromaDB.
        Call this after every action execution.
        """
        return self.experience_recorder.record_action_outcome(
            action_type=action_type,
            action_params=action_params,
            outcome=outcome,
            page_url=page_url,
            page_title=page_title,
            page_context=page_context,
            error_message=error_message,
            learned_pattern=learned_pattern,
            session_id=session_id,
        )

    def record_pattern(
        self,
        pattern: str,
        page_url: str = "",
        selectors: Optional[List[str]] = None,
        confidence: float = 1.0,
        session_id: str = "",
    ) -> bool:
        """Record a visual UI pattern."""
        return self.experience_recorder.record_screenshot_pattern(
            pattern_description=pattern,
            page_url=page_url,
            element_selectors=selectors,
            confidence=confidence,
            session_id=session_id,
        )

    def record_personalization(
        self,
        profile_info: str,
        message: str,
        message_type: str,
        outcome: str,
        profile_url: str = "",
        session_id: str = "",
    ) -> bool:
        """Record a personalization outcome."""
        return self.experience_recorder.record_personalization(
            profile_info=profile_info,
            message_or_note=message,
            message_type=message_type,
            outcome=outcome,
            profile_url=profile_url,
            session_id=session_id,
        )

    # ── Prompt Building ───────────────────────────────────────────────────────

    def build_enriched_system_prompt(
        self,
        base_system: str,
        task: str,
        page_url: str = "",
    ) -> str:
        """
        Build a system prompt enriched with relevant past experiences.
        """
        experiences = self.experience_engine.retrieve(
            query=task,
            page_url=page_url,
            n_results=3,
        )

        if not experiences:
            return base_system

        exp_block = self.experience_engine.format_for_prompt(experiences, max_experiences=3)
        return f"{base_system}\n\n{exp_block}"

    # ── Internal Helpers ──────────────────────────────────────────────────────

    def _enrich_messages(
        self,
        messages: List[Dict[str, Any]],
        experiences: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Inject experience context into the last user message.
        """
        if not experiences or not messages:
            return messages

        exp_block = self.experience_engine.format_for_prompt(experiences)
        if not exp_block:
            return messages

        enriched = list(messages)
        # Find the last user message and prepend experience context
        for i in range(len(enriched) - 1, -1, -1):
            if enriched[i].get("role") == "user":
                original_content = enriched[i]["content"]
                if isinstance(original_content, str):
                    enriched[i] = {
                        **enriched[i],
                        "content": f"{exp_block}\n\n{original_content}",
                    }
                break

        return enriched

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_memory_stats(self) -> Dict[str, int]:
        """Return memory statistics from ChromaDB."""
        return self.experience_engine.get_memory_stats()
