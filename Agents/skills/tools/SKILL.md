---
name: browser_tools
description: Core browser automation tools registry — navigate, screenshot, click, type, scroll, dom, evaluate, wait
skill_type: tools
entry_file: browser_tools.py
tags: [browser, tools, automation, playwright]
version: "1.0"
created_by: MetaAgent
---

# Browser Tools Skill

## Purpose
Provides the 8 atomic browser automation tools used by all agents.
Each tool is a standalone async function that operates on a Playwright page.

## Tools

| Tool       | Description                                      |
|------------|--------------------------------------------------|
| navigate   | Navigate to a URL, wait for load                 |
| screenshot | Capture page screenshot as base64 PNG            |
| click      | Click element by selector, text, or coordinates  |
| type_text  | Type text with human-like delays                 |
| scroll     | Scroll page in any direction                     |
| dom        | Extract text, HTML, links, buttons, inputs       |
| evaluate   | Execute JavaScript on the page                   |
| wait       | Wait for element, navigation, network, or time   |

## Usage
```python
from agent_browser.tools import execute_tool

result = await execute_tool("navigate", page, url="https://linkedin.com")
result = await execute_tool("screenshot", page)
result = await execute_tool("click", page, selector=".connect-btn")
result = await execute_tool("type_text", page, selector="#email", text="user@example.com")
result = await execute_tool("scroll", page, direction="down", amount=500)
result = await execute_tool("dom", page, action="text", selector=".profile-name")
result = await execute_tool("evaluate", page, script="() => document.title")
result = await execute_tool("wait", page, condition="element", selector=".feed")
```
