# 🤖 Self-Evolving Agentic Browser

A self-improving, task-specialized agentic system for LinkedIn automation.
Inspired by **AgentFactory** (arXiv:2603.18000) — combines executable subagent accumulation,
ChromaDB semantic RAG memory, Playwright stealth browser, and LLM-guided decision making.

---

## 🧠 Architecture

```
Goal
 │
 ▼
MetaAgent ──────────────────────────────────────────────────────────┐
 │  (AgentFactory lifecycle: Install → Self-Evolve → Deploy)        │
 │                                                                   │
 ▼                                                                   │
Orchestrator                                                         │
 │  (Detects workflow type, coordinates agents)                      │
 │                                                                   ▼
 ├──► AuthAgent      → Login + session persistence            skills/
 ├──► SearchAgent    → People search with filters             subagents/
 ├──► ConnectionAgent→ Personalized connection requests       (executable
 ├──► ScraperAgent   → Profile data extraction                 Python)
 └──► MessageAgent   → Message existing connections
          │
          ▼
     PageController  (high-level browser actions)
          │
          ▼
     BrowserPool     (parallel Playwright instances)
          │
          ▼
     8 Atomic Tools: navigate | screenshot | click | type_text
                     scroll   | dom        | evaluate | wait
          │
          ▼
     Stealth Layer:  HumanBehavior | FingerprintRotator | RateLimiter
```

### Self-Evolution Loop

```
Screenshot → Retrieve past experiences (ChromaDB RAG)
           → Enrich prompt with learned patterns
           → LLM decides action (Ollama/LLaVA or Gemini Flash)
           → Execute via Playwright
           → ReflectionAgent records outcome
           → ChromaDB grows smarter
           → Successful workflows saved as executable subagents (SKILL.md)
           → EvolutionAgent rewrites failing strategies
```

---

## 📁 Project Structure

```
Agents/
├── main.py                          ← CLI entry point
├── requirements.txt                 ← Python dependencies
├── docker-compose.yml               ← ChromaDB container
├── .env.example                     ← Environment template
├── skills_utils.py                  ← SKILL.md read/write utilities
│
├── types/
│   └── agent_types.py               ← All Pydantic data models
│
├── llm/
│   ├── base_model.py                ← Ollama + Gemini + OpenAI (pluggable)
│   ├── prompt_engine.py             ← Chain-of-thought + output parser
│   ├── experience_engine.py         ← RAG: retrieve past experiences
│   ├── experience_recorder.py       ← Record outcomes to ChromaDB
│   ├── enhanced_llm.py              ← LLM + experience = expert model
│   └── evolution_engine.py          ← Strategy mutation engine
│
├── memory/
│   ├── chroma_client.py             ← ChromaDB client wrapper
│   ├── collections.py               ← 6 ChromaDB collections
│   ├── agent_context.py             ← Working memory + state tracking
│   └── memory_manager.py            ← Unified 4-tier memory system
│
├── planning/
│   ├── goal_decomposer.py           ← Break goals into subtasks
│   ├── tree_of_thought.py           ← Multi-path reasoning
│   ├── replanner.py                 ← Handle failures with new plans
│   └── backtracker.py               ← Checkpoint + rollback
│
├── agent_browser/
│   ├── tools/                       ← 8 atomic browser tools
│   │   ├── navigate.py
│   │   ├── screenshot.py            ← Returns base64 for LLM vision
│   │   ├── click.py
│   │   ├── type_text.py
│   │   ├── scroll.py
│   │   ├── dom.py
│   │   ├── evaluate.py
│   │   └── wait.py
│   ├── browser_instance.py          ← Single Playwright browser
│   ├── page_controller.py           ← High-level semantic actions
│   ├── browser_pool.py              ← Parallel browser instances
│   ├── coordinator.py               ← Task distribution
│   └── stealth/
│       ├── human_behavior.py        ← Mouse curves, random delays
│       ├── fingerprint_rotator.py   ← User agent + viewport rotation
│       └── rate_limiter.py          ← Learned LinkedIn rate limits
│
├── agents/
│   ├── base_agent.py                ← screenshot→retrieve→act→reflect loop
│   ├── meta_agent.py                ← AgentFactory strategic controller
│   ├── orchestrator.py              ← Workflow coordination
│   ├── reflection_agent.py          ← Outcome analysis + pattern extraction
│   ├── evolution_agent.py           ← Self-improvement engine
│   ├── auth_agent.py                ← LinkedIn login
│   ├── search_agent.py              ← People search
│   ├── connection_agent.py          ← Connection requests
│   ├── scraper_agent.py             ← Profile data extraction
│   └── message_agent.py             ← Message connections
│
├── linkedin/
│   ├── selectors.py                 ← All CSS selectors (centralized)
│   ├── actions.py                   ← High-level LinkedIn actions
│   └── persona_manager.py           ← Multi-account management
│
├── skills/
│   ├── meta/                        ← Workflow-level skills
│   │   ├── SKILL.md                 ← linkedin_connect skill
│   │   ├── linkedin_scrape/
│   │   └── linkedin_message/
│   ├── tools/                       ← Tool-level skills
│   │   └── SKILL.md
│   └── subagents/                   ← Auto-generated executable subagents
│
└── workspace/                       ← Runtime data (sessions, logs, state)
    ├── sessions/                    ← Browser session cookies
    ├── profiles/                    ← Browser fingerprint profiles
    ├── agent.log                    ← Full debug log
    ├── rate_limit_state.json        ← Daily action counts
    └── evolution_log.json           ← Evolution history
```

---

## 🚀 Quick Start

### 1. Prerequisites

```bash
# Python 3.11+
python --version

# Docker (for ChromaDB)
docker --version

# Ollama (optional, for local LLM)
ollama pull llava
```

### 2. Install Dependencies

```bash
cd Agents
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your LinkedIn credentials and LLM settings
```

### 4. Start ChromaDB

```bash
docker-compose up -d
```

### 5. Run

```bash
# Send connection requests
python main.py connect --query "ML engineer San Francisco" --limit 10

# Scrape profiles
python main.py scrape --query "data scientist NYC" --limit 20

# Message connections
python main.py message --connections "url1,url2" --template "Hi {name}, ..."

# Run evolution cycle
python main.py evolve

# View daily stats
python main.py stats

# List saved skills
python main.py skills
```

---

## ⚙️ Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LINKEDIN_EMAIL` | — | LinkedIn account email |
| `LINKEDIN_PASSWORD` | — | LinkedIn account password |
| `LLM_PROVIDER` | `ollama` | `ollama` \| `gemini` \| `openai` |
| `OLLAMA_MODEL` | `llava` | Ollama model name (vision capable) |
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `OPENAI_API_KEY` | — | OpenAI/OpenRouter API key |
| `BROWSER_HEADLESS` | `true` | Run browser headless |
| `BROWSER_POOL_SIZE` | `2` | Number of parallel browsers |
| `CHROMA_HOST` | `localhost` | ChromaDB host |
| `CHROMA_PORT` | `8000` | ChromaDB port |
| `LOG_LEVEL` | `INFO` | Logging level |

---

## 🛡️ Anti-Detection

The system implements multiple layers of bot detection avoidance:

| Layer | Implementation |
|-------|---------------|
| **Rate Limiting** | Max 20 connections/day, 10 messages/day |
| **Human Delays** | Gaussian-distributed 0.5–3s delays between actions |
| **Mouse Curves** | Bezier curve mouse movements |
| **Typing Speed** | Variable 30–300ms per keystroke |
| **Fingerprint Rotation** | Cycles through 5 browser profiles |
| **Stealth JS** | Removes `navigator.webdriver` flag |
| **Session Persistence** | Reuses cookies to avoid repeated logins |

---

## 🧬 Self-Evolution (AgentFactory Pattern)

The system evolves itself over time:

1. **Accumulation**: Every successful workflow is saved as an executable Python subagent in `skills/subagents/`
2. **Supersede**: When a better strategy is found, old subagents are archived and replaced
3. **RAG Learning**: ChromaDB stores every action outcome — future runs retrieve relevant past experiences
4. **Selector Evolution**: When LinkedIn updates its UI, `EvolutionAgent` generates new CSS selectors
5. **Note Optimization**: Connection note templates are improved based on acceptance rates

### ChromaDB Collections

| Collection | Purpose |
|-----------|---------|
| `screenshot_patterns` | Visual UI patterns from screenshots |
| `action_outcomes` | What worked / what failed |
| `linkedin_profiles` | Scraped profile data (deduplication) |
| `personalization` | Connection notes that got accepted |
| `agent_context` | Current agent state |
| `procedural_memory` | Step-by-step workflow procedures |

---

## 📊 Skill System (SKILL.md)

Each saved skill follows the AgentFactory format:

```markdown
---
name: skill_name
description: What this skill does
skill_type: workflow | subagent | tool
entry_file: skill_name.py
tags: [linkedin, connect]
version: "1.0"
---

# Instructions
...
```

Executable subagents follow the pattern:
```python
def main(query: str) -> dict:
    return {"answer": "...", "summary": "..."}
```

---

## 🔧 Extending

### Add a New LinkedIn Agent

```python
from agents.base_agent import BaseAgent

class MyAgent(BaseAgent):
    @property
    def goal(self) -> str:
        return "My specific goal"

    async def execute_step(self, page_controller, screenshot_b64, experiences, step):
        # Your logic here
        return {"action": "my_action", "success": True, "done": False}
```

### Add a New Browser Tool

```python
# agent_browser/tools/my_tool.py
async def my_tool(page, **kwargs) -> dict:
    return {"success": True, "result": ...}

# Register in agent_browser/tools/__init__.py
from .my_tool import my_tool
TOOL_REGISTRY["my_tool"] = my_tool
```

---

## 📄 License

MIT License — Use responsibly. Respect LinkedIn's Terms of Service.
