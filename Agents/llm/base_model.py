"""
Base LLM Model — Pluggable interface for Ollama (LLaVA) and Gemini Flash.

Supports:
  - Ollama: local, free, LLaVA vision model for screenshot analysis
  - Gemini Flash: cheap cloud, no GPU needed, also supports vision
  - OpenAI-compatible: any OpenRouter / OpenAI endpoint

Usage:
    llm = get_llm()                          # uses LLM_PROVIDER from .env
    response = await llm.complete(messages)
    response = await llm.complete_with_vision(messages, screenshot_b64)
"""

from __future__ import annotations

import base64
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

# Load env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Type aliases ──────────────────────────────────────────────────────────────
Message = Dict[str, Any]


# ── Abstract Base ─────────────────────────────────────────────────────────────

class BaseLLM(ABC):
    """Abstract base class for all LLM providers."""

    def __init__(self, model: str, temperature: float = 0.1, max_tokens: int = 4096):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    @abstractmethod
    async def complete(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Send messages to the LLM and get a text response.

        Returns:
            {"success": bool, "response": str, "error": str|None, "tokens_used": int}
        """
        ...

    @abstractmethod
    async def complete_with_vision(
        self,
        messages: List[Message],
        screenshot_b64: str,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Send messages + screenshot to the LLM (vision model).

        Args:
            screenshot_b64: Base64-encoded PNG screenshot

        Returns:
            {"success": bool, "response": str, "error": str|None}
        """
        ...

    def sync_complete(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Synchronous wrapper around complete()."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run, self.complete(messages, system, max_tokens)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(self.complete(messages, system, max_tokens))
        except Exception as e:
            return {"success": False, "response": "", "error": str(e)}

    def sync_complete_with_vision(
        self,
        messages: List[Message],
        screenshot_b64: str,
        system: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synchronous wrapper around complete_with_vision()."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self.complete_with_vision(messages, screenshot_b64, system),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.complete_with_vision(messages, screenshot_b64, system)
                )
        except Exception as e:
            return {"success": False, "response": "", "error": str(e)}


# ── Ollama (LLaVA) ────────────────────────────────────────────────────────────

class OllamaLLM(BaseLLM):
    """
    Ollama local LLM — supports LLaVA for vision (screenshot analysis).

    Models:
      llava        → Vision + text (default for screenshot decisions)
      llama3       → Text only (faster for non-visual tasks)
      llava:13b    → Better vision quality
    """

    def __init__(
        self,
        model: str = "llava",
        text_model: str = "llama3",
        host: str = "http://localhost:11434",
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ):
        super().__init__(model, temperature, max_tokens)
        self.text_model = text_model
        self.host = host.rstrip("/")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def complete(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Text completion using Ollama."""
        try:
            import ollama as ollama_client

            # Build message list
            ollama_messages = []
            if system:
                ollama_messages.append({"role": "system", "content": system})
            ollama_messages.extend(messages)

            response = ollama_client.chat(
                model=self.text_model,
                messages=ollama_messages,
                options={
                    "temperature": self.temperature,
                    "num_predict": max_tokens or self.max_tokens,
                },
            )

            content = response["message"]["content"]
            return {
                "success": True,
                "response": content,
                "error": None,
                "tokens_used": response.get("eval_count", 0),
                "model": self.text_model,
                "provider": "ollama",
            }

        except Exception as e:
            logger.error(f"Ollama complete error: {e}")
            return {"success": False, "response": "", "error": str(e)}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def complete_with_vision(
        self,
        messages: List[Message],
        screenshot_b64: str,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Vision completion using LLaVA — analyzes screenshots."""
        try:
            import ollama as ollama_client

            ollama_messages = []
            if system:
                ollama_messages.append({"role": "system", "content": system})

            # Add screenshot to the last user message
            for i, msg in enumerate(messages):
                if i == len(messages) - 1 and msg["role"] == "user":
                    ollama_messages.append(
                        {
                            "role": "user",
                            "content": msg["content"],
                            "images": [screenshot_b64],
                        }
                    )
                else:
                    ollama_messages.append(msg)

            response = ollama_client.chat(
                model=self.model,  # LLaVA vision model
                messages=ollama_messages,
                options={
                    "temperature": self.temperature,
                    "num_predict": max_tokens or self.max_tokens,
                },
            )

            content = response["message"]["content"]
            return {
                "success": True,
                "response": content,
                "error": None,
                "tokens_used": response.get("eval_count", 0),
                "model": self.model,
                "provider": "ollama",
            }

        except Exception as e:
            logger.error(f"Ollama vision error: {e}")
            return {"success": False, "response": "", "error": str(e)}


# ── Gemini Flash ──────────────────────────────────────────────────────────────

class GeminiLLM(BaseLLM):
    """
    Google Gemini Flash — cheap cloud LLM with vision support.
    No GPU needed. Great for production use.

    Models:
      gemini-1.5-flash   → Fast, cheap, vision capable
      gemini-1.5-pro     → More capable, higher cost
    """

    def __init__(
        self,
        model: str = "gemini-1.5-flash",
        api_key: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ):
        super().__init__(model, temperature, max_tokens)
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")

    def _get_client(self):
        import google.generativeai as genai
        genai.configure(api_key=self.api_key)
        return genai

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def complete(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Text completion using Gemini Flash."""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)

            model = genai.GenerativeModel(
                model_name=self.model,
                system_instruction=system or "",
                generation_config=genai.GenerationConfig(
                    temperature=self.temperature,
                    max_output_tokens=max_tokens or self.max_tokens,
                ),
            )

            # Convert messages to Gemini format
            history = []
            last_user_msg = ""
            for msg in messages:
                role = "user" if msg["role"] == "user" else "model"
                content = msg["content"] if isinstance(msg["content"], str) else str(msg["content"])
                if msg == messages[-1] and msg["role"] == "user":
                    last_user_msg = content
                else:
                    history.append({"role": role, "parts": [content]})

            chat = model.start_chat(history=history)
            response = chat.send_message(last_user_msg or (messages[-1]["content"] if messages else ""))

            return {
                "success": True,
                "response": response.text,
                "error": None,
                "tokens_used": response.usage_metadata.total_token_count if hasattr(response, "usage_metadata") else 0,
                "model": self.model,
                "provider": "gemini",
            }

        except Exception as e:
            logger.error(f"Gemini complete error: {e}")
            return {"success": False, "response": "", "error": str(e)}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def complete_with_vision(
        self,
        messages: List[Message],
        screenshot_b64: str,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Vision completion using Gemini — analyzes screenshots."""
        try:
            import google.generativeai as genai
            from PIL import Image
            import io

            genai.configure(api_key=self.api_key)

            model = genai.GenerativeModel(
                model_name=self.model,
                system_instruction=system or "",
                generation_config=genai.GenerationConfig(
                    temperature=self.temperature,
                    max_output_tokens=max_tokens or self.max_tokens,
                ),
            )

            # Decode screenshot
            img_bytes = base64.b64decode(screenshot_b64)
            img = Image.open(io.BytesIO(img_bytes))

            # Build prompt with image
            last_msg = messages[-1]["content"] if messages else ""
            if isinstance(last_msg, list):
                last_msg = " ".join(
                    p.get("text", "") for p in last_msg if isinstance(p, dict)
                )

            response = model.generate_content([last_msg, img])

            return {
                "success": True,
                "response": response.text,
                "error": None,
                "tokens_used": response.usage_metadata.total_token_count if hasattr(response, "usage_metadata") else 0,
                "model": self.model,
                "provider": "gemini",
            }

        except Exception as e:
            logger.error(f"Gemini vision error: {e}")
            return {"success": False, "response": "", "error": str(e)}


# ── OpenAI-compatible ─────────────────────────────────────────────────────────

class OpenAILLM(BaseLLM):
    """
    OpenAI-compatible LLM — works with OpenAI, OpenRouter, or any compatible API.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ):
        super().__init__(model, temperature, max_tokens)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    def _get_client(self):
        from openai import AsyncOpenAI
        return AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def complete(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        try:
            client = self._get_client()
            all_messages = []
            if system:
                all_messages.append({"role": "system", "content": system})
            all_messages.extend(messages)

            response = await client.chat.completions.create(
                model=self.model,
                messages=all_messages,
                temperature=self.temperature,
                max_tokens=max_tokens or self.max_tokens,
            )

            return {
                "success": True,
                "response": response.choices[0].message.content,
                "error": None,
                "tokens_used": response.usage.total_tokens if response.usage else 0,
                "model": self.model,
                "provider": "openai",
            }
        except Exception as e:
            logger.error(f"OpenAI complete error: {e}")
            return {"success": False, "response": "", "error": str(e)}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def complete_with_vision(
        self,
        messages: List[Message],
        screenshot_b64: str,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        try:
            client = self._get_client()
            all_messages = []
            if system:
                all_messages.append({"role": "system", "content": system})

            for i, msg in enumerate(messages):
                if i == len(messages) - 1 and msg["role"] == "user":
                    all_messages.append(
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": msg["content"]},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{screenshot_b64}"
                                    },
                                },
                            ],
                        }
                    )
                else:
                    all_messages.append(msg)

            response = await client.chat.completions.create(
                model=self.model,
                messages=all_messages,
                temperature=self.temperature,
                max_tokens=max_tokens or self.max_tokens,
            )

            return {
                "success": True,
                "response": response.choices[0].message.content,
                "error": None,
                "tokens_used": response.usage.total_tokens if response.usage else 0,
                "model": self.model,
                "provider": "openai",
            }
        except Exception as e:
            logger.error(f"OpenAI vision error: {e}")
            return {"success": False, "response": "", "error": str(e)}


# ── Factory ───────────────────────────────────────────────────────────────────

def get_llm(provider: Optional[str] = None) -> BaseLLM:
    """
    Factory function — returns the configured LLM based on LLM_PROVIDER env var.

    Args:
        provider: Override provider ("ollama" | "gemini" | "openai")
                  Defaults to LLM_PROVIDER env var, then "ollama"

    Returns:
        Configured BaseLLM instance
    """
    provider = provider or os.getenv("LLM_PROVIDER", "ollama").lower()

    if provider == "ollama":
        return OllamaLLM(
            model=os.getenv("OLLAMA_MODEL", "llava"),
            text_model=os.getenv("OLLAMA_TEXT_MODEL", "llama3"),
            host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
        )
    elif provider == "gemini":
        return GeminiLLM(
            model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
            api_key=os.getenv("GEMINI_API_KEY"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
        )
    elif provider == "openai":
        return OpenAILLM(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
        )
    else:
        logger.warning(f"Unknown LLM provider '{provider}', defaulting to Ollama")
        return OllamaLLM()


# ── Convenience sync call (used by subagents) ─────────────────────────────────

def call_llm(
    system: str,
    messages: List[Message],
    provider: Optional[str] = None,
    max_tokens: int = 2048,
) -> Dict[str, Any]:
    """
    Synchronous LLM call — convenience function for use inside subagents.

    Args:
        system:    System prompt
        messages:  List of {"role": ..., "content": ...} dicts
        provider:  Override LLM provider
        max_tokens: Max tokens for response

    Returns:
        {"success": bool, "response": str, "error": str|None}
    """
    llm = get_llm(provider)
    return llm.sync_complete(messages, system=system, max_tokens=max_tokens)
