"""
LinkedIn Agents — Specialized agents for LinkedIn automation.

Hierarchy:
  MetaAgent          → Strategic goal manager (AgentFactory pattern)
  Orchestrator       → Task decomposition + subagent spawning
  BaseAgent          → screenshot→retrieve→plan→act→reflect loop
  ReflectionAgent    → Evaluates every action outcome
  EvolutionAgent     → Rewrites strategies based on patterns

LinkedIn Subagents:
  AuthAgent          → Login + session persistence
  SearchAgent        → People search with filters
  ConnectionAgent    → Personalized connection requests
  ScraperAgent       → Profile data extraction
  MessageAgent       → Message existing connections
"""

from .base_agent import BaseAgent
from .meta_agent import MetaAgent
from .orchestrator import Orchestrator
from .auth_agent import AuthAgent
from .search_agent import SearchAgent
from .connection_agent import ConnectionAgent
from .scraper_agent import ScraperAgent
from .message_agent import MessageAgent

__all__ = [
    "BaseAgent",
    "MetaAgent",
    "Orchestrator",
    "AuthAgent",
    "SearchAgent",
    "ConnectionAgent",
    "ScraperAgent",
    "MessageAgent",
]
