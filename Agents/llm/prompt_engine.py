"""
Prompt Engine — Chain-of-Thought, Tree-of-Thought, and structured output parsing.

Responsibilities:
  - Build enriched prompts with past experiences (RAG context)
  - Chain-of-Thought (CoT): step-by-step reasoning before action
  - Tree-of-Thought (ToT): explore multiple action paths, pick best
  - Structured output parser: extract <action>/<params> from LLM response
  - Action validation before execution
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

# ── System Prompts ────────────────────────────────────────────────────────────

META_AGENT_SYSTEM_PROMPT = """You are a Meta-Agent that orchestrates browser-based tasks by decomposing
complex goals and using specialized subagents as reusable tools.

## ⚠️ CRITICAL FIRST STEPS
1. REVIEW the list of available skills provided with the task
2. CALL get_skill_description ONE skill at a time — wait for the result before calling the next
3. ONLY AFTER reading a skill's description can you use that skill

## YOUR ROLE
- Decompose complex browser tasks into focused sub-problems
- Assign each sub-problem to a specialized subagent
- Call subagents multiple times with different focused queries
- Synthesize results to form the final answer
- Save successful subagents as reusable skills for future tasks

## ACTION FORMAT
```xml
<action>skill_name</action>
<params>{"param1": "value1", "param2": "value2"}</params>
```

## 🚨 ONE ACTION PER RESPONSE — THEN STOP 🚨
- NEVER output multiple <action> blocks in one response
- NEVER generate <response> tags — reserved for the system
- NEVER predict or simulate what the system will return
- After </params>, your turn is OVER — wait for the real result

## WORKFLOW
1. list_saved_subagents → check if suitable tools already exist
2. get_skill_description → learn each skill before using it
3. create_subagent → build specialized Python subagents
4. run_subagent → execute and get results
5. modify_subagent → fix issues surgically (prefer over rewriting)
6. finish → save reusable subagents, provide final answer

## SUBAGENT DESIGN RULES
- Must implement: def main(query: str) -> dict
- Must return: {"answer": "...", "summary": "..."}
- Must use call_llm() — avoid pure rule-based code
- Must be GENERAL — no hardcoded question-specific values
- Must have a reasoning loop (think → act → observe → iterate)

## SELF-EVOLUTION
After each task, successful subagents are saved to the skill library.
On future similar tasks, retrieve and reuse them — reducing effort by up to 57%.
"""

LINKEDIN_AGENT_SYSTEM_PROMPT = """You are a LinkedIn automation agent with deep expertise in
navigating LinkedIn's UI. You control a real browser via Playwright.

Your capabilities:
- Navigate LinkedIn pages (login, search, profiles, messages)
- Take screenshots and analyze the current page state
- Click elements, type text, scroll pages
- Extract profile information
- Send connection requests with personalized notes
- Send messages to existing connections

## DECISION PROCESS (for every action)
1. Take a screenshot to see current page state
2. Retrieve relevant past experiences from memory
3. Analyze: What is the current state? What needs to happen next?
4. Decide: What is the best action? (with confidence score)
5. Execute the action
6. Record the outcome (success/failure + what was learned)

## ANTI-DETECTION RULES
- Always add human-like delays between actions (2-8 seconds)
- Vary typing speed (don't type at constant speed)
- Scroll naturally before clicking
- Never send more than 20 connection requests per day
- Never send more than 10 messages per day

## ACTION FORMAT
```xml
<action>tool_name</action>
<params>{"param1": "value1"}</params>
```
"""

REFLECTION_PROMPT = """Analyze the following action and its outcome. Provide:
1. Was the action successful? (yes/no/partial)
2. What was learned from this outcome?
3. What pattern was recognized? (e.g., "LinkedIn login button is always at top-right")
4. Confidence score for this pattern (0.0-1.0)
5. Should this experience be stored for future reference? (yes/no)
6. Suggested improvement for next time

Respond in JSON:
{
  "success": true/false,
  "learned": "what was learned",
  "pattern": "recognized pattern",
  "confidence": 0.0-1.0,
  "store": true/false,
  "improvement": "suggestion"
}
"""

EVOLUTION_PROMPT = """You are analyzing a collection of past experiences to evolve the agent's strategy.

Review the following experiences and:
1. Identify the most successful patterns
2. Identify recurring failure modes
3. Suggest an improved strategy/prompt for this task type
4. Rate the improvement confidence (0.0-1.0)

Respond in JSON:
{
  "successful_patterns": ["pattern1", "pattern2"],
  "failure_modes": ["failure1", "failure2"],
  "evolved_strategy": "improved strategy description",
  "evolved_prompt_addition": "text to add to system prompt",
  "confidence": 0.0-1.0
}
"""


# ── Prompt Builder ────────────────────────────────────────────────────────────

class PromptEngine:
    """
    Builds enriched prompts with:
    - Past experience context (RAG)
    - Chain-of-Thought reasoning structure
    - Tree-of-Thought path exploration
    """

    def build_task_prompt(
        self,
        task: str,
        available_skills: List[Dict[str, str]],
        retrieved_experiences: Optional[List[Dict[str, Any]]] = None,
        current_url: Optional[str] = None,
        page_context: Optional[str] = None,
    ) -> str:
        """
        Build the initial task prompt for the MetaAgent.

        Includes:
        - Task description
        - Available skills list
        - Retrieved past experiences (RAG context)
        - Current page context (if any)
        """
        parts = [f"Task: {task}\n"]

        # Current page context
        if current_url:
            parts.append(f"Current URL: {current_url}")
        if page_context:
            parts.append(f"Current Page Context:\n{page_context}\n")

        # Available skills
        if available_skills:
            skill_lines = "\n".join(
                f"  - {s['name']} ({s.get('type', 'unknown')})" for s in available_skills
            )
            parts.append(f"Available Skills:\n{skill_lines}\n")

        # RAG: past experiences
        if retrieved_experiences:
            parts.append("📚 Relevant Past Experiences (from memory):")
            for i, exp in enumerate(retrieved_experiences[:5], 1):
                score = exp.get("similarity_score", 0)
                content = exp.get("content", "")
                parts.append(f"  [{i}] (similarity: {score:.2f}) {content[:300]}")
            parts.append("")

        # Instructions
        parts.append(
            "CRITICAL RULE: Each response must contain AT MOST ONE <action>...</action>"
            "<params>...</params> block, then STOP IMMEDIATELY.\n"
            "Use get_skill_description to view details of any skill before using it."
        )

        return "\n".join(parts)

    def build_vision_prompt(
        self,
        task: str,
        screenshot_description_request: str = "",
        retrieved_experiences: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Build a prompt for vision-based page analysis (LLaVA / Gemini vision).
        """
        parts = [
            "You are analyzing a browser screenshot to decide the next action.",
            f"\nCurrent Task: {task}",
        ]

        if retrieved_experiences:
            parts.append("\n📚 Relevant Past Experiences:")
            for exp in retrieved_experiences[:3]:
                parts.append(f"  - {exp.get('content', '')[:200]}")

        parts.append(
            "\nAnalyze the screenshot and answer:\n"
            "1. What page/state is currently shown?\n"
            "2. What elements are visible and interactable?\n"
            "3. What is the best next action to complete the task?\n"
            "4. What is your confidence (0.0-1.0)?\n"
            "\nRespond in JSON:\n"
            '{"page_state": "...", "visible_elements": [...], '
            '"recommended_action": {"type": "...", "params": {...}}, "confidence": 0.0}'
        )

        if screenshot_description_request:
            parts.append(f"\nAdditional context: {screenshot_description_request}")

        return "\n".join(parts)

    def build_cot_prompt(
        self,
        task: str,
        context: str = "",
        step_number: int = 1,
    ) -> str:
        """
        Build a Chain-of-Thought prompt that forces step-by-step reasoning.
        """
        return (
            f"Task: {task}\n"
            f"Step {step_number}:\n"
            f"{context}\n\n"
            "Think step by step:\n"
            "1. What is the current state?\n"
            "2. What is the goal?\n"
            "3. What are the possible actions?\n"
            "4. Which action is best and why?\n"
            "5. What could go wrong?\n\n"
            "After reasoning, output ONE action:\n"
            "<action>tool_name</action>\n"
            '<params>{"key": "value"}</params>'
        )

    def build_tot_prompt(
        self,
        task: str,
        context: str = "",
        num_paths: int = 3,
    ) -> str:
        """
        Build a Tree-of-Thought prompt that explores multiple action paths.
        """
        return (
            f"Task: {task}\n"
            f"Context: {context}\n\n"
            f"Explore {num_paths} different action paths:\n\n"
            + "\n".join(
                f"Path {i}:\n"
                f"  Action: <what action to take>\n"
                f"  Expected outcome: <what will happen>\n"
                f"  Risk: <what could go wrong>\n"
                f"  Score: <0-10>\n"
                for i in range(1, num_paths + 1)
            )
            + "\nBest path: Path <N> because <reason>\n\n"
            "Execute the best path:\n"
            "<action>tool_name</action>\n"
            '<params>{"key": "value"}</params>'
        )

    def build_reflection_prompt(
        self,
        action: Dict[str, Any],
        result: Dict[str, Any],
        page_context: str = "",
    ) -> str:
        """Build a reflection prompt to analyze action outcomes."""
        return (
            f"{REFLECTION_PROMPT}\n\n"
            f"Action taken: {json.dumps(action, indent=2)}\n"
            f"Result: {json.dumps(result, indent=2)}\n"
            f"Page context: {page_context[:500] if page_context else 'N/A'}"
        )

    def enrich_with_experiences(
        self,
        base_prompt: str,
        experiences: List[Dict[str, Any]],
        max_experiences: int = 5,
    ) -> str:
        """
        Enrich a prompt with retrieved past experiences (RAG).
        Inserts experience context before the action request.
        """
        if not experiences:
            return base_prompt

        exp_lines = ["📚 Relevant Past Experiences (use these to make better decisions):"]
        for i, exp in enumerate(experiences[:max_experiences], 1):
            score = exp.get("similarity_score", 0)
            content = exp.get("content", "")
            outcome = exp.get("outcome", "unknown")
            exp_lines.append(
                f"  [{i}] Score={score:.2f} | Outcome={outcome} | {content[:250]}"
            )
        exp_lines.append("")

        experience_block = "\n".join(exp_lines)
        return f"{experience_block}\n{base_prompt}"


# ── Structured Output Parser ──────────────────────────────────────────────────

class OutputParser:
    """
    Parses structured output from LLM responses.

    Handles:
    - <action>/<params> XML-style tags (AgentFactory format)
    - JSON extraction from responses
    - Hallucination detection (<response> tags)
    """

    def parse_action(self, response: str) -> Optional[Dict[str, Any]]:
        """
        Parse action from LLM response.

        Expected format:
            <action>skill_name</action>
            <params>{"param1": "value1"}</params>

        Returns:
            {"action": str, "params": dict} or None if not found
        """
        # Detect hallucinated <response> tags
        if "<response>" in response or "</response>" in response:
            logger.warning("Hallucination detected: LLM wrote <response> tags")
            return {"action": "__hallucination__", "params": {}, "hallucination": True}

        # Extract action
        action_match = re.search(r"<action>\s*(.*?)\s*</action>", response, re.DOTALL)
        if not action_match:
            return None

        action_type = action_match.group(1).strip()
        result: Dict[str, Any] = {"action": action_type, "params": {}}

        # Extract params (JSON)
        params_match = re.search(r"<params>\s*(.*)\s*</params>", response, re.DOTALL)
        if params_match:
            params_str = params_match.group(1).strip()
            if params_str:
                parsed_params, error = self._parse_json_safe(params_str)
                if error:
                    result["json_parse_error"] = error
                else:
                    result["params"] = parsed_params

        return result

    def _parse_json_safe(self, json_str: str) -> Tuple[Dict, Optional[str]]:
        """
        Safely parse JSON with fallback strategies.
        Returns (parsed_dict, error_message).
        """
        # Direct parse
        try:
            return json.loads(json_str), None
        except json.JSONDecodeError:
            pass

        # Find outermost { ... }
        brace_start = json_str.find("{")
        brace_end = json_str.rfind("}")
        if brace_start != -1 and brace_end > brace_start:
            try:
                return json.loads(json_str[brace_start : brace_end + 1]), None
            except json.JSONDecodeError as e:
                return {}, str(e)

        return {}, "No JSON object found in params"

    def parse_json_response(self, response: str) -> Optional[Dict[str, Any]]:
        """
        Extract and parse JSON from an LLM response.
        Handles responses with surrounding text.
        """
        # Try direct parse
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            pass

        # Find JSON block in markdown code fence
        code_fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        if code_fence:
            try:
                return json.loads(code_fence.group(1))
            except json.JSONDecodeError:
                pass

        # Find outermost { ... }
        brace_start = response.find("{")
        brace_end = response.rfind("}")
        if brace_start != -1 and brace_end > brace_start:
            try:
                return json.loads(response[brace_start : brace_end + 1])
            except json.JSONDecodeError:
                pass

        return None

    def extract_clean_response(self, response: str) -> str:
        """
        Remove hallucinated <response> tags and clean up the response.
        Returns content before any <response> tag.
        """
        for tag in ["<response>", "</response>"]:
            idx = response.find(tag)
            if idx != -1:
                response = response[:idx].rstrip()
        return response

    def validate_action(self, action: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate a parsed action before execution.

        Returns:
            (is_valid, error_message)
        """
        if not action:
            return False, "No action provided"

        action_type = action.get("action", "")
        if not action_type:
            return False, "Action type is empty"

        if action.get("hallucination"):
            return False, "Hallucination detected in response"

        if action.get("json_parse_error"):
            return False, f"JSON parse error in params: {action['json_parse_error']}"

        return True, None


# ── Module-level instances ────────────────────────────────────────────────────

prompt_engine = PromptEngine()
output_parser = OutputParser()
