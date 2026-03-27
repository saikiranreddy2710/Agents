# Self-Evolving Agentic Browser

Experimental LinkedIn automation built with Playwright, ChromaDB-backed memory, and pluggable LLM providers.

This project combines a browser pool, task-specific agents, semantic memory, and reusable workflow skills. It can search LinkedIn profiles, scrape profile data, send connection requests, and run an evolution loop that stores successful workflows for reuse.

> [!WARNING]
> This repository is experimental. LinkedIn UI changes, CAPTCHA, 2FA, and account restrictions can interrupt or break automation flows.

## What It Does

- Reuses LinkedIn sessions when possible
- Searches LinkedIn people results and extracts profile URLs
- Scrapes structured profile data
- Sends connection requests with optional note templates
- Runs a message workflow entrypoint for existing connections
- Stores outcomes in ChromaDB for memory and skill reuse
- Supports `colab`, `ollama`, `gemini`, and `openai` providers

## Why It Is Useful

- Keeps browser automation logic organized by agent responsibility
- Adds a memory layer so repeated tasks can learn from prior runs
- Supports both local and hosted LLM workflows
- Exposes a practical Colab bridge for larger models without running them locally

## Project Layout

```text
Agents/
├── main.py                 # CLI entrypoint
├── requirements.txt        # Python dependencies
├── docker-compose.yml      # ChromaDB service
├── .env.example            # Environment template
├── colab.ipynb             # Google Colab notebook
├── colab_server.py         # OpenAI-compatible FastAPI server for Colab
├── colab_tests.py          # Colab-side capability checks
├── agent_browser/          # Playwright wrappers, tools, stealth helpers
├── agents/                 # Auth, search, connection, scraper, message agents
├── llm/                    # Provider adapters and orchestration
├── memory/                 # ChromaDB client, collections, memory manager
├── planning/               # Goal decomposition and replanning helpers
├── linkedin/               # Selectors and LinkedIn-specific actions
├── skills/                 # Built-in and saved workflow skills
└── workspace/              # Runtime sessions, logs, and generated state
```

## How It Works

`main.py` boots the browser pool, memory layer, LLM provider, and specialized agents. A `MetaAgent` routes work through the `Orchestrator`, which then runs one of the main workflows:

- `connect`: authenticate, search profiles, and send connection requests
- `scrape`: search profiles if needed, then scrape profile pages
- `message`: authenticate, open a profile or thread, and send a message
- `evolve`: review stored outcomes and improve saved strategies
- `stats`: show daily action usage
- `skills`: list saved skills

The browser layer is built on Playwright and wrapped by `PageController` plus eight atomic tools: navigate, screenshot, click, type, scroll, DOM extraction, JS evaluation, and wait.

## Quick Start

### Prerequisites

- Python 3.9 or later
- Chromium installed through Playwright
- Docker, if you want ChromaDB as a service
- One configured LLM provider

### Install

```bash
cd Agents
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

### Configure Environment

```bash
cp .env.example .env
```

Set the values you actually want to use in `.env`, especially:

- `LINKEDIN_EMAIL`
- `LINKEDIN_PASSWORD`
- `LLM_PROVIDER`
- Provider-specific API settings
- `CHROMA_HOST=localhost`
- `CHROMA_PORT=8000`

### Start Memory

```bash
docker-compose up -d
```

If ChromaDB is not reachable, the code falls back to local persistent storage in `./chroma_data`.

## LLM Providers

### Colab

Recommended when you want a larger model without running it locally.

1. Open [`colab.ipynb`](./colab.ipynb) in Google Colab.
2. Run the model-loading cells.
3. Optionally run [`colab_tests.py`](./colab_tests.py) in Colab.
4. Run [`colab_server.py`](./colab_server.py) to start the FastAPI server and ngrok tunnel.
5. Copy the ngrok URL into `COLAB_API_URL` in your local `.env`.
6. Set `LLM_PROVIDER=colab`.

The Colab server exposes:

- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/agent/decide`

### Ollama

Use Ollama for local runs:

```bash
ollama pull llava
```

Then set:

```bash
LLM_PROVIDER=ollama
OLLAMA_MODEL=llava
OLLAMA_TEXT_MODEL=llama3
```

### Gemini And OpenAI-Compatible APIs

The project also supports:

- `LLM_PROVIDER=gemini`
- `LLM_PROVIDER=openai`

Configure the matching API key and model fields in `.env`.

## CLI Usage

```bash
# Send connection requests
python main.py connect --query "ML engineer San Francisco" --limit 10

# Scrape profiles from search results
python main.py scrape --query "data scientist NYC" --limit 20

# Message existing connections
python main.py message --connections "url1,url2" --template "Hi {name}, ..."

# Run strategy evolution
python main.py evolve

# Show daily action limits and browser pool stats
python main.py stats

# List saved skills
python main.py skills
```

## Getting Help

- Review the repository task tracker in [`TODO.md`](./TODO.md)
- Check the environment template in [`.env.example`](./.env.example)
- Open an issue: <https://github.com/saikiranreddy2710/learning-cluade/issues>

## Maintainer

Maintained by [@saikiranreddy2710](https://github.com/saikiranreddy2710).

## Security Notes

- Do not commit live LinkedIn credentials or API keys
- Keep `.env` out of source control
- Before pushing config changes, make sure `.env.example` contains placeholders only
