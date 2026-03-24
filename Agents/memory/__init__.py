"""
Memory Module — ChromaDB-backed 4-tier memory system.

Tiers:
  Working Memory    → In-RAM, current task context (fast, ephemeral)
  Episodic Memory   → Full session replays (ChromaDB)
  Semantic Memory   → Learned UI patterns + strategies (ChromaDB)
  Procedural Memory → Successful action sequences as macros (ChromaDB)

Collections:
  screenshot_patterns  → Visual UI patterns recognized from screenshots
  action_outcomes      → What worked/failed for each action type
  linkedin_profiles    → Profiles interacted with
  personalization      → Connection notes/messages that worked
  agent_context        → Agent state + evolved strategies
  procedural_memory    → Successful multi-step action sequences
"""

from .chroma_client import get_chroma_client, ChromaClientManager
from .collections import get_or_create_collections, COLLECTION_NAMES
from .memory_manager import MemoryManager

__all__ = [
    "get_chroma_client",
    "ChromaClientManager",
    "get_or_create_collections",
    "COLLECTION_NAMES",
    "MemoryManager",
]
