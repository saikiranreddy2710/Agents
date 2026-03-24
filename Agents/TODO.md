# 🚀 Hybrid Performance Enhancement — Implementation Tracker

## Research Sources Applied
- **Mooncake** (MoonshotAI, arXiv:2407.00079) — KVCache → Experience Cache + Prediction-based Skip
- **Attention-Residuals** (MoonshotAI) — Residual context → ResidualContextBuffer + ToT Integration
- **Memento-Skills** (Memento-Teams) — Semantic skill memory → Semantic Skill Retrieval + Skill Indexing
- **AgentFactory** (zzatpku) — Parallel execution → Parallel Scraping + A/B Testing Wire-up
- **MetaClaw** (aiming-lab) — Meta-learning → Evolved Strategy Injection + Proactive Evolution

---

## TIER 1 — Immediate Performance

- [ ] `requirements.txt` — Add `cachetools==5.3.3`
- [ ] `memory/collections.py` — Add `skills_index` ChromaDB collection
- [ ] `skills_utils.py` — Add `index_skill_to_chroma()` + wire into `save_skill()`
- [ ] `llm/experience_engine.py` — Add TTL experience cache (Mooncake KVCache)
- [ ] `agents/meta_agent.py` — Replace keyword matching with semantic search (Memento-Skills)
- [ ] `agents/orchestrator.py` — Add parallel scraping with semaphore (AgentFactory)

## TIER 2 — Adaptive Long-term

- [ ] `agents/base_agent.py` — Add `ResidualContextBuffer` + ToT integration (Attention-Residuals)
- [ ] `llm/enhanced_llm.py` — Wire `EvolutionEngine` + inject evolved strategy (MetaClaw)

## TIER 3 — Proactive Evolution

- [ ] `llm/evolution_engine.py` — Add `_predict_failure_risk()`, `should_skip_action()`, proactive trigger, A/B wire-up

## Follow-up Testing

- [ ] Verify `skills_index` collection created in ChromaDB
- [ ] Verify experience cache hits on repeated steps (check logs for "cache HIT")
- [ ] Verify parallel scraping: 3x faster scrape workflow
- [ ] Verify semantic skill retrieval: better skill matching accuracy
- [ ] Verify evolved strategy injection in LLM prompts
- [ ] Run: `python main.py connect --query "ML engineer SF" --limit 5`
- [ ] Run: `python main.py scrape --query "data scientist NYC" --limit 10`
- [ ] Run: `python main.py evolve`
