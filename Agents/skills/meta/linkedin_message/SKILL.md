---
name: linkedin_message
description: Send personalized messages to existing LinkedIn connections
skill_type: workflow
entry_file: linkedin_message.py
tags: [linkedin, message, outreach]
version: "1.0"
created_by: MetaAgent
---

# LinkedIn Message Skill

## Purpose
Sends personalized messages to existing LinkedIn connections.
Useful for follow-ups, outreach campaigns, and relationship building.

## Instructions
- Only works with existing connections (not cold outreach)
- Max 10 messages/day to avoid spam detection
- 60s minimum delay between messages
- Message templates are personalized using profile data from ChromaDB

## Usage
```python
from skills.meta.linkedin_message import main
result = main("message:Hi {name}, following up on our connection. message_template='...' connections=['url1','url2']")
# Returns: {"answer": "Sent 8/10 messages", "summary": "..."}
```

## Parameters
- connections: List of profile URLs to message
- message_template: Message template with {name}, {company}, {title} placeholders
- max_messages: Max messages to send (default: 10)

## Anti-Detection
- Max 10 messages/day
- 60s between messages
- Personalized content (not identical messages)
- Human-like typing speed
