"""
Agent Types — Pydantic models for the entire agentic browser system.
Covers: LLM config, browser config, agent state, actions, outcomes,
        experiences, LinkedIn profiles, skills, and memory records.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


# ============================================================
# Enums
# ============================================================

class LLMProvider(str, Enum):
    OLLAMA = "ollama"
    GEMINI = "gemini"
    OPENAI = "openai"


class BrowserType(str, Enum):
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


class ActionType(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    SCREENSHOT = "screenshot"
    WAIT = "wait"
    EVALUATE = "evaluate"
    DOM = "dom"
    FINISH = "finish"
    CREATE_SUBAGENT = "create_subagent"
    RUN_SUBAGENT = "run_subagent"
    MODIFY_SUBAGENT = "modify_subagent"
    LIST_SUBAGENTS = "list_saved_subagents"
    GET_SKILL_DESC = "get_skill_description"


class ActionStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    SKIPPED = "skipped"


class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    FINISHED = "finished"
    FAILED = "failed"
    EVOLVING = "evolving"


class SkillType(str, Enum):
    META = "meta"
    TOOL = "tool"
    SUBAGENT = "saved_subagent"


class LinkedInConnectionStatus(str, Enum):
    NOT_CONNECTED = "not_connected"
    PENDING = "pending"
    CONNECTED = "connected"
    FOLLOWING = "following"


class MemoryTier(str, Enum):
    WORKING = "working"       # In-RAM, current task
    EPISODIC = "episodic"     # Full session replays
    SEMANTIC = "semantic"     # Learned UI patterns + strategies
    PROCEDURAL = "procedural" # Successful action sequences


# ============================================================
# LLM Configuration
# ============================================================

class LLMConfig(BaseModel):
    provider: LLMProvider = LLMProvider.OLLAMA
    model: str = "llava"
    text_model: str = "llama3"
    base_url: Optional[str] = "http://localhost:11434"
    api_key: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 4096
    timeout: int = 120
    vision_enabled: bool = True  # LLaVA / Gemini vision


class LLMMessage(BaseModel):
    role: str  # "system" | "user" | "assistant"
    content: Union[str, List[Dict[str, Any]]]  # str or multimodal content


class LLMResponse(BaseModel):
    success: bool
    response: str = ""
    error: Optional[str] = None
    tokens_used: int = 0
    model: str = ""
    provider: LLMProvider = LLMProvider.OLLAMA


# ============================================================
# Browser Configuration
# ============================================================

class BrowserConfig(BaseModel):
    browser_type: BrowserType = BrowserType.CHROMIUM
    headless: bool = False
    slow_mo: int = 50
    viewport_width: int = 1280
    viewport_height: int = 800
    user_agent: Optional[str] = None
    locale: str = "en-US"
    timezone: str = "America/New_York"
    proxy: Optional[str] = None
    storage_state_path: Optional[str] = None  # For session persistence


class BrowserPoolConfig(BaseModel):
    pool_size: int = 3
    max_retries: int = 3
    browser_config: BrowserConfig = Field(default_factory=BrowserConfig)


# ============================================================
# Agent Actions
# ============================================================

class AgentAction(BaseModel):
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action_type: ActionType
    params: Dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""          # Why the agent chose this action
    confidence: float = 1.0      # 0.0 - 1.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ActionResult(BaseModel):
    action_id: str
    success: bool
    status: ActionStatus = ActionStatus.SUCCESS
    data: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    screenshot_path: Optional[str] = None
    duration_ms: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============================================================
# Experience & Memory Records
# ============================================================

class ExperienceRecord(BaseModel):
    """A single experience stored in ChromaDB for RAG retrieval."""
    experience_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    task_description: str = ""
    action_taken: ActionType = ActionType.CLICK
    action_params: Dict[str, Any] = Field(default_factory=dict)
    page_url: str = ""
    page_context: str = ""       # DOM summary or screenshot description
    outcome: ActionStatus = ActionStatus.SUCCESS
    outcome_details: str = ""
    learned_pattern: str = ""    # What pattern was recognized
    confidence_delta: float = 0.0  # How much confidence changed
    tags: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ActionOutcome(BaseModel):
    """Outcome of an action, used for recording to ChromaDB."""
    action: AgentAction
    result: ActionResult
    page_url: str = ""
    page_title: str = ""
    screenshot_base64: Optional[str] = None
    dom_snapshot: Optional[str] = None
    session_id: str = ""


class MemoryRecord(BaseModel):
    """Generic memory record across all 4 tiers."""
    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tier: MemoryTier
    content: str                 # Text content for embedding
    metadata: Dict[str, Any] = Field(default_factory=dict)
    embedding: Optional[List[float]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    ttl_seconds: Optional[int] = None  # None = permanent


class RetrievedExperience(BaseModel):
    """Experience retrieved from ChromaDB with similarity score."""
    record: ExperienceRecord
    similarity_score: float
    relevance_explanation: str = ""


# ============================================================
# Agent State
# ============================================================

class AgentState(BaseModel):
    """Full state of a running agent."""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str = ""
    status: AgentStatus = AgentStatus.IDLE
    current_task: str = ""
    current_url: str = ""
    iteration: int = 0
    max_iterations: int = 60
    messages: List[LLMMessage] = Field(default_factory=list)
    trajectory: List[Dict[str, Any]] = Field(default_factory=list)
    working_memory: Dict[str, Any] = Field(default_factory=dict)
    retrieved_experiences: List[RetrievedExperience] = Field(default_factory=list)
    created_subagents: List[str] = Field(default_factory=list)
    modified_subagents: Dict[str, Any] = Field(default_factory=dict)
    has_created_or_modified: bool = False
    viewed_skill_descriptions: List[str] = Field(default_factory=list)
    viewed_subagent_codes: List[str] = Field(default_factory=list)
    workspace_dir: str = ""
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None


class AgentContext(BaseModel):
    """Lightweight context passed between agents."""
    session_id: str
    parent_agent: Optional[str] = None
    task: str = ""
    url: str = ""
    iteration: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ============================================================
# Skills (AgentFactory SKILL.md pattern)
# ============================================================

class SkillMetadata(BaseModel):
    """Parsed from SKILL.md frontmatter."""
    name: str
    description: str
    skill_type: SkillType = SkillType.SUBAGENT
    entry_file: Optional[str] = None
    directory: str = ""
    instructions: str = ""


class SubagentSaveRequest(BaseModel):
    """Request to save a subagent as a skill."""
    entry_file: str
    description: str
    skill_name: Optional[str] = None    # Override derived name
    supersedes: Optional[str] = None    # Old skill to replace


class FinishParams(BaseModel):
    """Parameters for the finish action."""
    answer: str
    subagents: List[SubagentSaveRequest] = Field(default_factory=list)
    confirmation: Optional[str] = None  # Required if saving nothing after creating


# ============================================================
# LinkedIn Data Models
# ============================================================

class LinkedInProfile(BaseModel):
    """A LinkedIn profile scraped or interacted with."""
    profile_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    linkedin_url: str = ""
    name: str = ""
    headline: str = ""
    location: str = ""
    company: str = ""
    position: str = ""
    about: str = ""
    skills: List[str] = Field(default_factory=list)
    education: List[Dict[str, str]] = Field(default_factory=list)
    experience: List[Dict[str, str]] = Field(default_factory=list)
    connection_status: LinkedInConnectionStatus = LinkedInConnectionStatus.NOT_CONNECTED
    mutual_connections: int = 0
    scraped_at: Optional[datetime] = None
    contacted_at: Optional[datetime] = None
    connection_note: Optional[str] = None
    message_sent: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class LinkedInSearchQuery(BaseModel):
    """Parameters for a LinkedIn people search."""
    keywords: str = ""
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    industry: Optional[str] = None
    connection_degree: Optional[str] = None  # "1st", "2nd", "3rd"
    max_results: int = 20


class ConnectionRequest(BaseModel):
    """A connection request to send."""
    profile: LinkedInProfile
    note: str = ""              # Personalized connection note
    note_template: str = ""     # Template used to generate note
    sent_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    status: str = "pending"


class LinkedInMessage(BaseModel):
    """A message to send to an existing connection."""
    recipient_profile: LinkedInProfile
    message_body: str
    template_used: str = ""
    sent_at: Optional[datetime] = None
    status: str = "pending"


# ============================================================
# Persona
# ============================================================

class LinkedInPersona(BaseModel):
    """A persona for LinkedIn interactions."""
    persona_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    tone: str = "professional"   # professional | casual | friendly | formal
    intro_style: str = ""        # How this persona introduces itself
    connection_note_style: str = ""
    message_style: str = ""
    daily_connection_limit: int = 20
    daily_message_limit: int = 10
    active: bool = True


# ============================================================
# Planning
# ============================================================

class SubTask(BaseModel):
    """A decomposed subtask from a high-level goal."""
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    depends_on: List[str] = Field(default_factory=list)  # task_ids
    assigned_agent: Optional[str] = None
    status: str = "pending"  # pending | running | done | failed
    result: Optional[Dict[str, Any]] = None
    retries: int = 0
    max_retries: int = 3


class TaskPlan(BaseModel):
    """A full plan decomposed from a high-level goal."""
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal: str
    subtasks: List[SubTask] = Field(default_factory=list)
    current_subtask_index: int = 0
    status: str = "planning"  # planning | executing | replanning | done | failed
    created_at: datetime = Field(default_factory=datetime.utcnow)
    thought_paths: List[List[str]] = Field(default_factory=list)  # ToT paths


class ReplanRequest(BaseModel):
    """Request to replan after a failure."""
    original_plan: TaskPlan
    failed_subtask: SubTask
    failure_reason: str
    context: Dict[str, Any] = Field(default_factory=dict)


# ============================================================
# Evolution
# ============================================================

class StrategyRecord(BaseModel):
    """A strategy stored for evolution."""
    strategy_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_type: str = ""
    strategy_description: str = ""
    prompt_template: str = ""
    success_rate: float = 0.0
    usage_count: int = 0
    last_used: Optional[datetime] = None
    evolved_from: Optional[str] = None  # strategy_id of parent
    tags: List[str] = Field(default_factory=list)


class EvolutionResult(BaseModel):
    """Result of an evolution step."""
    original_strategy: StrategyRecord
    evolved_strategy: StrategyRecord
    improvement_reason: str = ""
    confidence: float = 0.0
