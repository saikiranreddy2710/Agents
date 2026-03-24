---
name: linkedin_connect
description: Search LinkedIn for people matching a query and send personalized connection requests
skill_type: workflow
entry_file: linkedin_connect.py
tags: [linkedin, connect, networking]
version: "1.0"
created_by: MetaAgent
---

# LinkedIn Connect Skill

## Purpose
Automates the full LinkedIn connection workflow:
1. Search for people matching a query
2. Scrape their profile data
3. Generate personalized connection notes
4. Send connection requests (respecting daily limits)

## Instructions
- Requires LINKEDIN_EMAIL and LINKEDIN_PASSWORD in .env
- Respects daily limit of 20 connection requests
- Adds 30-60s delay between requests to avoid detection
- Saves successful connection notes to ChromaDB for learning

## Usage
```python
from skills.meta.linkedin_connect import main
result = main("ML engineers in San Francisco, limit=10")
# Returns: {"answer": "Sent 8/10 connection requests", "summary": "..."}
```

## Parameters
- query: Search query (e.g., "ML engineer San Francisco")
- limit: Max connections to send (default: 10, max: 20)
- note_template: Optional custom note template

## Anti-Detection
- Max 20 connections/day
- 30-60s between requests
- Human-like mouse movements
- Random delays
