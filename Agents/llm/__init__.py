"""
LLM Module — Pluggable LLM providers with self-evolving experience engine.

Components:
  base_model.py        → Ollama (LLaVA vision) + Gemini Flash (pluggable)
  prompt_engine.py     → Chain-of-thought + Tree-of-Thought + structured output
  experience_engine.py → RAG: retrieves past experiences from ChromaDB
  experience_recorder.py → Records action outcomes back to ChromaDB
  enhanced_llm.py      → Main wrapper: base_model + experience = self-evolving expert
  evolution_engine.py  → Rewrites strategies/prompts based on accumulated patterns
"""

from .base_model import BaseLLM, OllamaLLM, GeminiLLM, get_llm
from .enhanced_llm import EnhancedLLM

__all__ = [
    "BaseLLM",
    "OllamaLLM",
    "GeminiLLM",
    "get_llm",
    "EnhancedLLM",
]
