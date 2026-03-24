"""
ChromaDB Collections — Schema definitions for all 6 memory collections.

Collections:
  screenshot_patterns  → Visual UI patterns (what elements look like on each page)
  action_outcomes      → Every action result (success/failure + context + learned)
  linkedin_profiles    → Profiles interacted with (scraped, connected, messaged)
  personalization      → Connection notes/messages + their outcomes
  agent_context        → Agent state, evolved strategies, session metadata
  procedural_memory    → Successful multi-step action sequences (macros)

Each collection uses sentence-transformers embeddings for semantic search.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from loguru import logger

# ── Collection Names ──────────────────────────────────────────────────────────

COLLECTION_NAMES = {
    "screenshot_patterns": "screenshot_patterns",
    "action_outcomes": "action_outcomes",
    "linkedin_profiles": "linkedin_profiles",
    "personalization": "personalization",
    "agent_context": "agent_context",
    "procedural_memory": "procedural_memory",
    "skills_index": "skills_index",          # Memento-Skills: semantic skill retrieval
}

# ── Embedding Function ────────────────────────────────────────────────────────

def _get_embedding_function():
    """
    Get the embedding function for ChromaDB.

    Uses sentence-transformers (all-MiniLM-L6-v2) for fast, good-quality embeddings.
    Falls back to ChromaDB's default if sentence-transformers not available.
    """
    try:
        from chromadb.utils import embedding_functions
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
    except Exception as e:
        logger.warning(f"sentence-transformers not available: {e}, using default embeddings")
        return None


# ── Collection Schemas ────────────────────────────────────────────────────────

COLLECTION_SCHEMAS = {
    "screenshot_patterns": {
        "name": "screenshot_patterns",
        "metadata": {"hnsw:space": "cosine"},
        "description": (
            "Visual UI patterns recognized from browser screenshots. "
            "Stores descriptions of page elements, layouts, and interaction patterns. "
            "Used to recognize familiar UI states and apply known interaction strategies."
        ),
        "example_document": (
            "Visual Pattern: LinkedIn login button is at top-right with class 'nav__button-secondary'\n"
            "Page: LinkedIn Homepage (https://linkedin.com)\n"
            "Selectors: .nav__button-secondary, button[data-tracking-control-name='guest_homepage-basic_nav-header-signin']\n"
            "Confidence: 0.95"
        ),
        "metadata_fields": [
            "pattern_description",  # str: human-readable pattern description
            "page_url",             # str: URL where pattern was observed
            "page_title",           # str: page title
            "selectors",            # JSON str: list of CSS/XPath selectors
            "confidence",           # float: pattern confidence score
            "session_id",           # str: session that discovered this pattern
            "timestamp",            # str: ISO datetime
        ],
    },

    "action_outcomes": {
        "name": "action_outcomes",
        "metadata": {"hnsw:space": "cosine"},
        "description": (
            "Records of every action taken and its outcome. "
            "Stores what worked, what failed, and what was learned. "
            "Used to avoid repeating mistakes and reinforce successful strategies."
        ),
        "example_document": (
            "Action: click\n"
            "Params: {\"selector\": \".connect-button\", \"text\": \"Connect\"}\n"
            "Outcome: success\n"
            "Page: John Doe - LinkedIn (https://linkedin.com/in/johndoe)\n"
            "Learned: Connect button on profile pages has class 'connect-button' or aria-label 'Connect with'"
        ),
        "metadata_fields": [
            "action_type",      # str: click, type, navigate, scroll, etc.
            "outcome",          # str: success, failure, partial
            "page_url",         # str: URL where action was performed
            "page_title",       # str: page title
            "error_message",    # str: error details if failed
            "learned_pattern",  # str: what was learned from this outcome
            "session_id",       # str: session ID
            "tags",             # JSON str: list of tags
            "timestamp",        # str: ISO datetime
        ],
    },

    "linkedin_profiles": {
        "name": "linkedin_profiles",
        "metadata": {"hnsw:space": "cosine"},
        "description": (
            "LinkedIn profiles that have been viewed, scraped, connected with, or messaged. "
            "Prevents duplicate outreach and tracks relationship history."
        ),
        "example_document": (
            "Name: Jane Smith\n"
            "Headline: Senior Software Engineer at Google\n"
            "Company: Google\n"
            "Location: San Francisco, CA\n"
            "Interaction: connected\n"
            "URL: https://linkedin.com/in/janesmith"
        ),
        "metadata_fields": [
            "name",              # str: full name
            "headline",          # str: LinkedIn headline
            "company",           # str: current company
            "location",          # str: location
            "linkedin_url",      # str: profile URL
            "interaction_type",  # str: viewed, connected, messaged, scraped
            "session_id",        # str: session ID
            "timestamp",         # str: ISO datetime
        ],
    },

    "personalization": {
        "name": "personalization",
        "metadata": {"hnsw:space": "cosine"},
        "description": (
            "Personalized connection notes and messages sent to LinkedIn profiles, "
            "along with their outcomes (accepted, replied, ignored). "
            "Used to learn which personalization styles work best for different profile types."
        ),
        "example_document": (
            "Type: connection_note\n"
            "Profile: Senior ML Engineer at OpenAI, Stanford CS grad\n"
            "Message: Hi Sarah, I came across your work on transformer architectures and found it fascinating. "
            "I'm also working in the ML space and would love to connect!\n"
            "Outcome: accepted\n"
            "Template: ml_engineer_v2"
        ),
        "metadata_fields": [
            "message_type",   # str: connection_note, message
            "outcome",        # str: accepted, replied, ignored, pending
            "profile_url",    # str: recipient's LinkedIn URL
            "template_used",  # str: template name used
            "message_length", # int: character count
            "session_id",     # str: session ID
            "timestamp",      # str: ISO datetime
        ],
    },

    "agent_context": {
        "name": "agent_context",
        "metadata": {"hnsw:space": "cosine"},
        "description": (
            "Agent state, session metadata, and evolved strategies. "
            "Stores the agent's current understanding of its environment "
            "and the strategies it has evolved over time."
        ),
        "example_document": (
            "Evolved strategy for: linkedin_connect\n"
            "Patterns: Always scroll to see full profile before connecting, "
            "Use mutual connections in note when available\n"
            "Failures: Clicking Connect without scrolling sometimes misses the button\n"
            "Strategy: Scroll profile → check mutual connections → personalize note → connect"
        ),
        "metadata_fields": [
            "type",         # str: evolved_strategy, session_summary, agent_state
            "task_type",    # str: task type this context applies to
            "strategy_json",# str: JSON-encoded strategy dict
            "confidence",   # float: strategy confidence
            "session_id",   # str: session ID
            "timestamp",    # str: ISO datetime
        ],
    },

    "procedural_memory": {
        "name": "procedural_memory",
        "metadata": {"hnsw:space": "cosine"},
        "description": (
            "Successful multi-step action sequences stored as reusable macros. "
            "When a similar task is encountered, the agent can replay a known-good sequence "
            "instead of figuring it out from scratch."
        ),
        "example_document": (
            "Task: LinkedIn login\n"
            "Steps: navigate → fill_email → fill_password → click_signin → wait_for_feed\n"
            "Total steps: 5\n"
            "Success: True\n"
            "Duration: 8.3s"
        ),
        "metadata_fields": [
            "task_description",  # str: what task this sequence accomplishes
            "steps_summary",     # str: action_type1 → action_type2 → ...
            "action_sequence",   # JSON str: full action sequence
            "success",           # bool: whether sequence succeeded
            "total_steps",       # int: number of steps
            "duration_seconds",  # float: how long it took
            "session_id",        # str: session ID
            "timestamp",         # str: ISO datetime
        ],
    },

    # ── Memento-Skills: Semantic Skill Index ──────────────────────────────────
    "skills_index": {
        "name": "skills_index",
        "metadata": {"hnsw:space": "cosine"},
        "description": (
            "Semantic index of all saved skills (meta, tool, subagent). "
            "Enables semantic skill retrieval by MetaAgent instead of brittle keyword matching. "
            "Indexed automatically when a skill is saved via skills_utils.save_skill(). "
            "Inspired by Memento-Skills structured skill memory architecture."
        ),
        "example_document": (
            "Skill: linkedin_connect\n"
            "Type: workflow\n"
            "Description: Search LinkedIn for people matching a query and send personalized "
            "connection requests\n"
            "Tags: linkedin, connect, networking"
        ),
        "metadata_fields": [
            "skill_name",    # str: unique skill name
            "skill_type",    # str: meta | tool | subagent | workflow
            "description",   # str: human-readable skill description
            "tags",          # JSON str: list of tag strings
            "entry_file",    # str: entry Python file name
            "version",       # str: skill version string
            "success_rate",  # float: historical success rate (0.0–1.0), updated on use
            "usage_count",   # int: number of times this skill has been executed
            "timestamp",     # str: ISO datetime when last indexed
        ],
    },
}


# ── Collection Factory ────────────────────────────────────────────────────────

def get_or_create_collections(client: Any) -> Dict[str, Any]:
    """
    Get or create all 6 ChromaDB collections.

    Args:
        client: ChromaDB client instance

    Returns:
        Dict mapping collection name → ChromaDB collection object
    """
    embedding_fn = _get_embedding_function()
    collections: Dict[str, Any] = {}

    for name, schema in COLLECTION_SCHEMAS.items():
        try:
            kwargs: Dict[str, Any] = {
                "name": schema["name"],
                "metadata": schema["metadata"],
            }
            if embedding_fn is not None:
                kwargs["embedding_function"] = embedding_fn

            collection = client.get_or_create_collection(**kwargs)
            collections[name] = collection
            logger.debug(f"Collection ready: {name} ({collection.count()} records)")

        except Exception as e:
            logger.error(f"Failed to create collection '{name}': {e}")
            collections[name] = None

    logger.info(
        f"ChromaDB collections initialized: "
        f"{sum(1 for c in collections.values() if c is not None)}/{len(COLLECTION_SCHEMAS)} ready"
    )
    return collections


def get_collection(client: Any, collection_name: str) -> Optional[Any]:
    """
    Get a single collection by name.

    Args:
        client:          ChromaDB client
        collection_name: One of the COLLECTION_NAMES keys

    Returns:
        ChromaDB collection or None if not found
    """
    if collection_name not in COLLECTION_SCHEMAS:
        logger.error(f"Unknown collection: '{collection_name}'. "
                     f"Valid names: {list(COLLECTION_NAMES.keys())}")
        return None

    embedding_fn = _get_embedding_function()
    schema = COLLECTION_SCHEMAS[collection_name]

    try:
        kwargs: Dict[str, Any] = {
            "name": schema["name"],
            "metadata": schema["metadata"],
        }
        if embedding_fn is not None:
            kwargs["embedding_function"] = embedding_fn

        return client.get_or_create_collection(**kwargs)
    except Exception as e:
        logger.error(f"Failed to get collection '{collection_name}': {e}")
        return None


def get_collection_stats(collections: Dict[str, Any]) -> Dict[str, int]:
    """Return record counts for all collections."""
    stats = {}
    for name, collection in collections.items():
        if collection is not None:
            try:
                stats[name] = collection.count()
            except Exception:
                stats[name] = -1
        else:
            stats[name] = -1
    return stats
