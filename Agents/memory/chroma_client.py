"""
ChromaDB Client — Wrapper for ChromaDB vector database connection.

Supports two modes:
  - HTTP client: connects to a running ChromaDB server (docker-compose)
  - Persistent client: local file-based storage (no Docker needed)

Auto-detects which mode to use based on CHROMA_HOST env var.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from loguru import logger

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class ChromaClientManager:
    """
    Singleton manager for ChromaDB client.
    Handles connection, reconnection, and health checks.
    """

    _instance: Optional["ChromaClientManager"] = None
    _client: Optional[Any] = None

    def __new__(cls) -> "ChromaClientManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_client(self) -> Any:
        """
        Get or create a ChromaDB client.

        Connection priority:
          1. HTTP client → CHROMA_HOST:CHROMA_PORT (Docker)
          2. Persistent client → CHROMA_PERSIST_DIR (local files)
        """
        if self._client is not None:
            return self._client

        self._client = self._create_client()
        return self._client

    def _create_client(self) -> Any:
        """Create a ChromaDB client based on environment configuration."""
        import chromadb

        chroma_host = os.getenv("CHROMA_HOST", "")
        chroma_port = int(os.getenv("CHROMA_PORT", "8000"))
        persist_dir = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")

        # Try HTTP client first (Docker mode)
        if chroma_host and chroma_host not in ("localhost", "127.0.0.1"):
            try:
                client = chromadb.HttpClient(
                    host=chroma_host,
                    port=chroma_port,
                )
                client.heartbeat()
                logger.info(f"Connected to ChromaDB HTTP server at {chroma_host}:{chroma_port}")
                return client
            except Exception as e:
                logger.warning(f"ChromaDB HTTP connection failed: {e}, falling back to persistent")

        # Try local HTTP (Docker on localhost)
        if chroma_host in ("localhost", "127.0.0.1", ""):
            try:
                client = chromadb.HttpClient(
                    host="localhost",
                    port=chroma_port,
                )
                client.heartbeat()
                logger.info(f"Connected to ChromaDB HTTP server at localhost:{chroma_port}")
                return client
            except Exception as e:
                logger.warning(f"ChromaDB localhost connection failed: {e}, using persistent storage")

        # Fall back to persistent local storage
        os.makedirs(persist_dir, exist_ok=True)
        client = chromadb.PersistentClient(path=persist_dir)
        logger.info(f"Using ChromaDB persistent storage at: {persist_dir}")
        return client

    def reset(self) -> None:
        """Reset the client (force reconnection on next get_client call)."""
        self._client = None

    def health_check(self) -> bool:
        """Check if ChromaDB is accessible."""
        try:
            client = self.get_client()
            client.heartbeat()
            return True
        except Exception as e:
            logger.error(f"ChromaDB health check failed: {e}")
            return False


# ── Module-level singleton ────────────────────────────────────────────────────

_manager = ChromaClientManager()


def get_chroma_client() -> Any:
    """
    Get the global ChromaDB client instance.

    Returns a connected ChromaDB client (HTTP or persistent).
    """
    return _manager.get_client()


def health_check() -> bool:
    """Check if ChromaDB is accessible."""
    return _manager.health_check()
