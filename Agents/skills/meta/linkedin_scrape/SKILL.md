---
name: linkedin_scrape
description: Scrape structured profile data (name, title, experience, education, skills) from LinkedIn profiles
skill_type: workflow
entry_file: linkedin_scrape.py
tags: [linkedin, scrape, data, profiles]
version: "1.0"
created_by: MetaAgent
---

# LinkedIn Scrape Skill

## Purpose
Extracts structured data from LinkedIn profiles:
- Basic info: name, headline, location, about
- Work experience: company, title, duration
- Education: school, degree, years
- Skills: top 10 skills
- Contact info (if visible)

## Instructions
- Requires active LinkedIn session
- Respects 5s delay between profile views
- Max 100 profile views/day
- Stores scraped data to ChromaDB for deduplication

## Usage
```python
from skills.meta.linkedin_scrape import main
result = main("https://linkedin.com/in/username OR search:ML engineers SF limit=20")
# Returns: {"answer": [{"name": ..., "experience": [...]}], "summary": "Scraped 20 profiles"}
```

## Output Schema
```json
{
  "name": "string",
  "headline": "string",
  "location": "string",
  "about": "string",
  "experience": [{"title": "...", "company": "...", "duration": "..."}],
  "education": [{"school": "...", "degree": "..."}],
  "skills": ["skill1", "skill2"],
  "url": "string"
}
