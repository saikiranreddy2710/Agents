# Learning Cluade

Repository for experiments around agentic browser automation and LLM-driven LinkedIn workflows.

The active project currently lives in [`Agents/`](./Agents), where the browser automation system, Colab bridge, memory layer, and CLI entrypoints are implemented.

> [!NOTE]
> GitHub only surfaces a repository README from the root, `.github`, or `docs` directory. This file is the repository landing page. The detailed project guide is in [`Agents/README.md`](./Agents/README.md).

## What This Repository Contains

- A Playwright-based browser automation layer
- Task-specific agents for auth, search, scraping, connections, and messaging
- ChromaDB-backed memory for retrieval and skill reuse
- Pluggable LLM providers for local, hosted, and Colab-backed execution
- A Google Colab notebook plus a FastAPI bridge for remote model serving

## Why It Is Useful

- Gives you a concrete multi-agent browser automation codebase to study and extend
- Shows how to combine browser control, memory, and LLM routing in one project
- Supports several model deployment styles without changing the high-level workflow

## Quick Start

1. Open the detailed guide in [`Agents/README.md`](./Agents/README.md).
2. Copy [`Agents/.env.example`](./Agents/.env.example) to `.env` inside `Agents/` and fill in your values.
3. Install dependencies and Playwright from the `Agents/` directory.
4. Start ChromaDB with [`Agents/docker-compose.yml`](./Agents/docker-compose.yml), or let the app fall back to local persistent storage.
5. Run the CLI from [`Agents/main.py`](./Agents/main.py).

## Key Files

- [`Agents/README.md`](./Agents/README.md): Detailed usage and architecture overview
- [`Agents/main.py`](./Agents/main.py): CLI entrypoint
- [`Agents/colab.ipynb`](./Agents/colab.ipynb): Colab notebook for model hosting
- [`Agents/colab_server.py`](./Agents/colab_server.py): OpenAI-compatible Colab API server
- [`Agents/colab_tests.py`](./Agents/colab_tests.py): Colab-side capability tests
- [`Agents/TODO.md`](./Agents/TODO.md): Current implementation tracker

## Getting Help

- Use the detailed documentation in [`Agents/README.md`](./Agents/README.md)
- Review open tasks in [`Agents/TODO.md`](./Agents/TODO.md)
- Open an issue: <https://github.com/saikiranreddy2710/learning-cluade/issues>

## Maintainer

Maintained by [@saikiranreddy2710](https://github.com/saikiranreddy2710).
