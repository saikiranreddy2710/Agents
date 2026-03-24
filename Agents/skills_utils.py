"""
Skills Utilities — Manages the three-level skill library.

Three levels of skills (AgentFactory pattern):
  Meta Skills    → Built-in orchestration primitives (create_subagent, run_subagent, etc.)
  Tool Skills    → Built-in browser tools (navigate, click, screenshot, etc.)
  Subagent Skills → Dynamically accumulated Python modules (grow over time)

Three-level loading pattern:
  Level 1: Metadata (name, description)   — loaded at startup, lightweight
  Level 2: Instructions (full SKILL.md)   — loaded on demand
  Level 3: Execution                      — run the actual skill code
"""

import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional

# ── Directory layout ──────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.join(SCRIPT_DIR, "skills")
META_SKILLS_DIR = os.path.join(SKILLS_DIR, "meta")
TOOLS_SKILLS_DIR = os.path.join(SKILLS_DIR, "tools")
SUBAGENT_SKILLS_DIR = os.path.join(SKILLS_DIR, "subagents")
WORKSPACE_DIR = os.path.join(SCRIPT_DIR, "workspace")


# ── SKILL.md Parser ───────────────────────────────────────────────────────────

def parse_skill_md(skill_path: str) -> Optional[Dict[str, Any]]:
    """
    Parse a SKILL.md file and extract metadata + instructions.

    Expected format:
        ---
        name: skill_name
        description: One-line description
        entry_file: subagent.py          # optional, for subagent skills
        ---

        # skill_name
        ... full instructions ...

    Returns:
        Dict with keys: name, description, instructions, entry_file (optional)
        None if parsing fails.
    """
    if not os.path.exists(skill_path):
        return None

    with open(skill_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Parse YAML frontmatter between --- delimiters
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
    if not match:
        return None

    frontmatter = match.group(1)
    instructions = match.group(2).strip()

    name_match = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE)
    desc_match = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE)
    entry_file_match = re.search(r"^entry_file:\s*(.+)$", frontmatter, re.MULTILINE)

    if not name_match or not desc_match:
        return None

    result: Dict[str, Any] = {
        "name": name_match.group(1).strip(),
        "description": desc_match.group(1).strip(),
        "instructions": instructions,
    }
    if entry_file_match:
        result["entry_file"] = entry_file_match.group(1).strip()

    return result


def get_skill_metadata(skill_path: str) -> Optional[Dict[str, str]]:
    """
    Get only Level-1 metadata (name + description) from a SKILL.md.
    Lightweight — used for listing skills at startup.
    """
    parsed = parse_skill_md(skill_path)
    if parsed:
        return {
            "name": parsed["name"],
            "description": parsed["description"],
        }
    return None


# ── Listing Skills ────────────────────────────────────────────────────────────

def list_meta_skills() -> List[Dict[str, str]]:
    """List all meta skills (orchestration primitives)."""
    return _list_skills_in_dir(META_SKILLS_DIR, skill_type="meta")


def list_tool_skills() -> List[Dict[str, str]]:
    """List all tool skills (browser tools)."""
    return _list_skills_in_dir(TOOLS_SKILLS_DIR, skill_type="tool")


def list_subagent_skills() -> List[Dict[str, str]]:
    """List all saved subagent skills (dynamically accumulated)."""
    return _list_skills_in_dir(SUBAGENT_SKILLS_DIR, skill_type="saved_subagent")


def list_all_skills() -> List[Dict[str, str]]:
    """
    List ALL available skills (meta + tool + saved subagents).
    Returns list of dicts with 'name' and 'type' keys.
    Used by MetaAgent to discover available skills at task start.
    """
    all_skills: List[Dict[str, str]] = []

    for skill in list_meta_skills():
        all_skills.append({"name": skill["name"], "type": "meta"})

    for skill in list_tool_skills():
        all_skills.append({"name": skill["name"], "type": "tool"})

    for skill in list_subagent_skills():
        all_skills.append({"name": skill["name"], "type": "saved_subagent"})

    return all_skills


def _list_skills_in_dir(directory: str, skill_type: str) -> List[Dict[str, str]]:
    """Helper: list all skills in a directory."""
    skills: List[Dict[str, str]] = []
    if not os.path.exists(directory):
        return skills

    for dirname in sorted(os.listdir(directory)):
        skill_dir = os.path.join(directory, dirname)
        if not os.path.isdir(skill_dir):
            continue
        skill_md = os.path.join(skill_dir, "SKILL.md")
        metadata = get_skill_metadata(skill_md)
        if metadata:
            skills.append(
                {
                    "name": metadata["name"],
                    "description": metadata["description"],
                    "directory": dirname,
                    "type": skill_type,
                }
            )
    return skills


# ── Getting Skill Instructions (Level 2) ─────────────────────────────────────

def get_skill_instructions(skill_name: str) -> Optional[str]:
    """
    Get full instructions for any skill (meta, tool, or saved subagent).
    Unified function — tries all three directories.
    """
    for getter in [
        get_meta_skill_instructions,
        get_tool_skill_instructions,
        get_subagent_skill_instructions,
    ]:
        instructions = getter(skill_name)
        if instructions:
            return instructions
    return None


def get_meta_skill_instructions(skill_name: str) -> Optional[str]:
    return _get_instructions_from_dir(META_SKILLS_DIR, skill_name)


def get_tool_skill_instructions(skill_name: str) -> Optional[str]:
    return _get_instructions_from_dir(TOOLS_SKILLS_DIR, skill_name)


def get_subagent_skill_instructions(skill_name: str) -> Optional[str]:
    return _get_instructions_from_dir(SUBAGENT_SKILLS_DIR, skill_name)


def _get_instructions_from_dir(directory: str, skill_name: str) -> Optional[str]:
    """Helper: find and return instructions for a skill in a directory."""
    if not os.path.exists(directory):
        return None

    for dirname in os.listdir(directory):
        skill_dir = os.path.join(directory, dirname)
        if not os.path.isdir(skill_dir):
            continue
        skill_md = os.path.join(skill_dir, "SKILL.md")
        parsed = parse_skill_md(skill_md)
        if parsed and (parsed["name"] == skill_name or dirname == skill_name):
            return parsed["instructions"]
    return None


def get_skill_description(skill_name: str) -> Dict[str, Any]:
    """
    Get full description + instructions for a skill.
    Returns dict with success, skill_name, description, instructions.
    Used by MetaAgent.execute_action() for get_skill_description action.
    """
    # Search all directories
    for directory, skill_type in [
        (META_SKILLS_DIR, "meta"),
        (TOOLS_SKILLS_DIR, "tool"),
        (SUBAGENT_SKILLS_DIR, "saved_subagent"),
    ]:
        if not os.path.exists(directory):
            continue
        for dirname in os.listdir(directory):
            skill_dir = os.path.join(directory, dirname)
            if not os.path.isdir(skill_dir):
                continue
            skill_md = os.path.join(skill_dir, "SKILL.md")
            parsed = parse_skill_md(skill_md)
            if parsed and (parsed["name"] == skill_name or dirname == skill_name):
                return {
                    "success": True,
                    "skill_name": parsed["name"],
                    "description": parsed["description"],
                    "type": skill_type,
                    "instructions": parsed["instructions"],
                    "entry_file": parsed.get("entry_file"),
                }

    return {
        "success": False,
        "error": f"Skill '{skill_name}' not found. "
                 f"Use list_saved_subagents to see available subagent skills.",
    }


# ── Skill Directory Lookup ────────────────────────────────────────────────────

def get_skill_directory(skill_name: str) -> Optional[str]:
    """
    Get the directory path for a skill by name.
    Searches meta, tools, and subagents directories.
    """
    for directory in [META_SKILLS_DIR, TOOLS_SKILLS_DIR, SUBAGENT_SKILLS_DIR]:
        if not os.path.exists(directory):
            continue
        for dirname in os.listdir(directory):
            skill_dir = os.path.join(directory, dirname)
            if not os.path.isdir(skill_dir):
                continue
            skill_md = os.path.join(skill_dir, "SKILL.md")
            parsed = parse_skill_md(skill_md)
            if parsed and (parsed["name"] == skill_name or dirname == skill_name):
                return skill_dir
    return None


# ── Skill Execution (Level 3) ─────────────────────────────────────────────────

def run_skill(
    skill_name: str,
    query: str,
    workspace: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute a saved subagent skill.

    Runs the skill's entry_file Python script with `query` as argument.
    The script must implement: def main(query: str) -> dict

    Returns:
        Dict with success, answer, summary (from subagent's return value)
    """
    skill_dir = get_skill_directory(skill_name)
    if skill_dir is None:
        return {"success": False, "error": f"Skill '{skill_name}' not found."}

    skill_md = os.path.join(skill_dir, "SKILL.md")
    parsed = parse_skill_md(skill_md)
    if not parsed:
        return {"success": False, "error": f"Could not parse SKILL.md for '{skill_name}'."}

    entry_file = parsed.get("entry_file", "subagent.py")
    entry_path = os.path.join(skill_dir, entry_file)

    if not os.path.exists(entry_path):
        return {
            "success": False,
            "error": f"Entry file '{entry_file}' not found in skill directory '{skill_dir}'.",
        }

    return _run_python_file(entry_path, query, cwd=workspace or skill_dir)


def run_python_file(
    file_path: str,
    query: str,
    cwd: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run a Python file (subagent) with a query argument.
    The file must implement: def main(query: str) -> dict
    """
    return _run_python_file(file_path, query, cwd=cwd)


def _run_python_file(
    file_path: str,
    query: str,
    cwd: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Internal: execute a Python subagent file.

    Wraps the file in a runner that calls main(query) and prints JSON output.
    Captures stdout/stderr and parses the result.
    """
    import json
    import tempfile

    runner_code = f"""
import sys
import json
import os

# Add the skill directory to path so imports work
sys.path.insert(0, {repr(os.path.dirname(file_path))})
if {repr(cwd)} and {repr(cwd)} not in sys.path:
    sys.path.insert(0, {repr(cwd)})

# Import and run the subagent
spec_dir = {repr(os.path.dirname(file_path))}
sys.path.insert(0, spec_dir)

import importlib.util
spec = importlib.util.spec_from_file_location("subagent", {repr(file_path)})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

query = {repr(query)}
result = module.main(query)

if isinstance(result, dict):
    print("__RESULT__:" + json.dumps(result, ensure_ascii=False))
else:
    print("__RESULT__:" + json.dumps({{"answer": str(result), "summary": ""}}))
"""

    # Write runner to a temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(runner_code)
        runner_path = tmp.name

    try:
        result = subprocess.run(
            [sys.executable, runner_path],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=cwd or os.path.dirname(file_path),
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        # Parse result from stdout
        for line in stdout.split("\n"):
            if line.startswith("__RESULT__:"):
                try:
                    import json as _json
                    data = _json.loads(line[len("__RESULT__:"):])
                    return {"success": True, **data}
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"Failed to parse subagent output: {e}",
                        "stdout": stdout,
                        "stderr": stderr,
                    }

        # No result marker found
        if result.returncode != 0:
            return {
                "success": False,
                "error": f"Subagent exited with code {result.returncode}",
                "stdout": stdout[-3000:] if stdout else "",
                "stderr": stderr[-3000:] if stderr else "",
            }

        return {
            "success": False,
            "error": "Subagent did not return a result. Make sure main() returns a dict.",
            "stdout": stdout[-3000:] if stdout else "",
            "stderr": stderr[-3000:] if stderr else "",
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Subagent timed out after 300 seconds."}
    except Exception as e:
        return {"success": False, "error": f"Failed to run subagent: {e}"}
    finally:
        try:
            os.unlink(runner_path)
        except Exception:
            pass


# ── Skill Saving ──────────────────────────────────────────────────────────────

def save_subagent_skill(
    workspace_dir: str,
    entry_file: str,
    description: str,
    skill_name: Optional[str] = None,
    supersedes: Optional[str] = None,
    skills_used: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Save a successful subagent as a reusable skill.

    Copies all .py files from workspace_dir to a new skill directory,
    creates SKILL.md with metadata, and optionally removes a superseded skill.

    Args:
        workspace_dir:  Directory containing the subagent .py files
        entry_file:     Main .py filename (e.g. "linkedin_connector.py")
        description:    Human-readable description of what this skill does
        skill_name:     Override the derived skill name (default: entry_file minus .py)
        supersedes:     Name of an old skill to replace (will be deleted)
        skills_used:    List of tool skill names used by this subagent

    Returns:
        Dict with success, skill_name, message
    """
    import json
    import shutil
    from datetime import datetime

    os.makedirs(SUBAGENT_SKILLS_DIR, exist_ok=True)

    # Validate entry file exists
    entry_path = os.path.join(workspace_dir, entry_file)
    if not os.path.exists(entry_path):
        available = [f for f in os.listdir(workspace_dir) if f.endswith(".py")]
        return {
            "success": False,
            "error": f"Entry file '{entry_file}' not found in workspace. "
                     f"Available .py files: {available}",
        }

    # Handle supersedes: remove old skill before saving new one
    superseded_msg = ""
    if supersedes:
        old_dir = os.path.join(SUBAGENT_SKILLS_DIR, supersedes)
        if os.path.exists(old_dir):
            shutil.rmtree(old_dir)
            superseded_msg = f" (superseded '{supersedes}')"
        else:
            superseded_msg = f" (note: '{supersedes}' not found, nothing removed)"

    # Derive skill name from entry_file
    if not skill_name:
        base = entry_file[:-3] if entry_file.endswith(".py") else entry_file
        skill_name = re.sub(r"[^\w\-]", "_", base).lower()

    # Avoid name collision — append timestamp if needed
    skill_dir = os.path.join(SUBAGENT_SKILLS_DIR, skill_name)
    if os.path.exists(skill_dir):
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        skill_name = f"{skill_name}_{ts}"
        skill_dir = os.path.join(SUBAGENT_SKILLS_DIR, skill_name)

    os.makedirs(skill_dir, exist_ok=True)

    # Copy all .py files from workspace
    copied = []
    for fname in os.listdir(workspace_dir):
        if fname.endswith(".py"):
            shutil.copy2(os.path.join(workspace_dir, fname), os.path.join(skill_dir, fname))
            copied.append(fname)

    # Build SKILL.md
    short_desc = description.split("\n")[0][:200]
    skills_str = ", ".join(skills_used) if skills_used else "playwright, screenshot"

    supersedes_section = ""
    if supersedes:
        supersedes_section = (
            f"\n## Supersedes\nThis skill replaces `{supersedes}`.\n"
        )

    skill_md = f"""---
name: {skill_name}
description: {short_desc}
entry_file: {entry_file}
---

# {skill_name}
{supersedes_section}
## Description
{description}

## Skills Used
{skills_str}

## Usage

**Entry file**: `{entry_file}`

**Query type**: Pass a focused task description as the query.

**How to call**:
```xml
<action>run_subagent</action>
<params>{{"skill_name": "{skill_name}", "query": "<your focused task description>"}}</params>
```
"""

    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(skill_md)

    return {
        "success": True,
        "skill_name": skill_name,
        "skill_dir": skill_dir,
        "copied_files": copied,
        "message": f"Skill '{skill_name}' saved to {skill_dir}{superseded_msg}",
    }


# ── Workspace Management ──────────────────────────────────────────────────────

def create_workspace(session_id: str, task_index: int = 0) -> str:
    """Create an isolated workspace directory for a task."""
    workspace = os.path.join(WORKSPACE_DIR, session_id, f"task_{task_index}")
    os.makedirs(workspace, exist_ok=True)
    return workspace


def write_file(path: str, content: str) -> Dict[str, Any]:
    """Write content to a file, creating parent directories as needed."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"success": True, "path": path}
    except Exception as e:
        return {"success": False, "error": str(e)}


def read_file(path: str) -> Dict[str, Any]:
    """Read content from a file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"success": True, "content": content, "path": path}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Initialization ────────────────────────────────────────────────────────────

def ensure_skill_directories() -> None:
    """Create all skill directories if they don't exist."""
    for d in [SKILLS_DIR, META_SKILLS_DIR, TOOLS_SKILLS_DIR, SUBAGENT_SKILLS_DIR, WORKSPACE_DIR]:
        os.makedirs(d, exist_ok=True)


# Auto-create directories on import
ensure_skill_directories()


# ── Memento-Skills: Semantic Skill Indexing ───────────────────────────────────

def index_skill_to_chroma(
    skill_name: str,
    description: str,
    skill_type: str,
    tags: Optional[List[str]] = None,
    entry_file: str = "",
    version: str = "1.0",
) -> bool:
    """
    Index a skill into ChromaDB's skills_index collection for semantic retrieval.

    Inspired by Memento-Skills: instead of brittle keyword matching, skills are
    embedded and stored so MetaAgent can retrieve them via semantic similarity search.

    Called automatically by save_skill() and save_subagent_skill().

    Args:
        skill_name:  Unique skill identifier
        description: Human-readable description (used for embedding)
        skill_type:  meta | tool | subagent | workflow
        tags:        List of tag strings
        entry_file:  Entry Python file name
        version:     Skill version string

    Returns:
        True on success, False if ChromaDB unavailable
    """
    try:
        import json as _json
        import uuid as _uuid
        from datetime import datetime as _dt

        from memory.chroma_client import get_chroma_client
        from memory.collections import get_or_create_collections

        client = get_chroma_client()
        collections = get_or_create_collections(client)
        skills_col = collections.get("skills_index")

        if skills_col is None:
            return False

        # Build the document text that will be embedded for semantic search
        doc_text = (
            f"Skill: {skill_name}\n"
            f"Type: {skill_type}\n"
            f"Description: {description}\n"
            f"Tags: {', '.join(tags or [])}"
        )

        metadata = {
            "skill_name": skill_name,
            "skill_type": skill_type,
            "description": description,
            "tags": _json.dumps(tags or []),
            "entry_file": entry_file,
            "version": version,
            "success_rate": 1.0,
            "usage_count": 0,
            "timestamp": _dt.utcnow().isoformat(),
        }

        # Remove any existing index entry for this skill (upsert behaviour)
        try:
            existing = skills_col.get(where={"skill_name": skill_name})
            if existing and existing.get("ids"):
                skills_col.delete(ids=existing["ids"])
        except Exception:
            pass  # Collection may be empty — that's fine

        record_id = f"skill_{skill_name}_{str(_uuid.uuid4())[:8]}"
        skills_col.add(
            documents=[doc_text],
            metadatas=[metadata],
            ids=[record_id],
        )
        return True

    except Exception as e:
        # Non-fatal: skill is still saved to disk even if indexing fails
        import traceback
        print(f"[skills_utils] Warning: could not index skill '{skill_name}' to ChromaDB: {e}")
        return False


def update_skill_stats(
    skill_name: str,
    success: bool,
) -> None:
    """
    Update a skill's success_rate and usage_count in the skills_index collection.
    Call this after every skill execution to keep performance metrics current.

    Args:
        skill_name: Skill to update
        success:    Whether the execution succeeded
    """
    try:
        import json as _json
        from memory.chroma_client import get_chroma_client
        from memory.collections import get_or_create_collections

        client = get_chroma_client()
        collections = get_or_create_collections(client)
        skills_col = collections.get("skills_index")
        if skills_col is None:
            return

        existing = skills_col.get(where={"skill_name": skill_name})
        if not existing or not existing.get("ids"):
            return

        ids = existing["ids"]
        metas = existing.get("metadatas", [{}])
        docs = existing.get("documents", [""])

        if not ids:
            return

        meta = dict(metas[0]) if metas else {}
        usage_count = int(meta.get("usage_count", 0)) + 1
        old_rate = float(meta.get("success_rate", 1.0))
        # Exponential moving average for success rate
        new_rate = old_rate * 0.9 + (1.0 if success else 0.0) * 0.1
        meta["usage_count"] = usage_count
        meta["success_rate"] = round(new_rate, 4)

        skills_col.update(
            ids=ids[:1],
            metadatas=[meta],
        )
    except Exception:
        pass  # Non-fatal


# ── AgentFactory-compatible API ───────────────────────────────────────────────
# These functions match the imports used by meta_agent.py

from dataclasses import dataclass, field
from typing import List as _List


@dataclass
class SkillMetadata:
    """Metadata for a skill (AgentFactory SKILL.md format)."""
    name: str
    description: str
    skill_type: str = "subagent"          # workflow | subagent | tool
    entry_file: str = "main.py"
    tags: _List[str] = field(default_factory=list)
    version: str = "1.0"
    created_by: str = "MetaAgent"


def save_skill(
    metadata: SkillMetadata,
    code: str,
    skills_dir: str = None,
) -> bool:
    """
    Save a skill with SKILL.md + executable Python code.

    Args:
        metadata:   SkillMetadata instance
        code:       Python source code for the skill's entry_file
        skills_dir: Root skills directory (default: SUBAGENT_SKILLS_DIR)

    Returns:
        True on success, False on failure
    """
    import shutil

    target_dir = skills_dir or SUBAGENT_SKILLS_DIR
    skill_dir = os.path.join(target_dir, "subagents", metadata.name)
    os.makedirs(skill_dir, exist_ok=True)

    try:
        # Write SKILL.md
        tags_str = ", ".join(metadata.tags) if metadata.tags else ""
        skill_md_content = f"""---
name: {metadata.name}
description: {metadata.description}
skill_type: {metadata.skill_type}
entry_file: {metadata.entry_file}
tags: [{tags_str}]
version: "{metadata.version}"
created_by: {metadata.created_by}
---

# {metadata.name}

## Description
{metadata.description}

## Usage
```python
from skills.subagents.{metadata.name}.{metadata.entry_file[:-3]} import main
result = main("your query here")
```
"""
        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(skill_md_content)

        # Write the executable Python code
        entry_path = os.path.join(skill_dir, metadata.entry_file)
        with open(entry_path, "w", encoding="utf-8") as f:
            f.write(code)

        # Auto-index to ChromaDB for semantic retrieval (Memento-Skills)
        index_skill_to_chroma(
            skill_name=metadata.name,
            description=metadata.description,
            skill_type=metadata.skill_type,
            tags=metadata.tags,
            entry_file=metadata.entry_file,
            version=metadata.version,
        )

        return True

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False


def load_skill(
    name: str,
    skills_dir: str = None,
) -> Optional[Dict[str, Any]]:
    """
    Load a skill by name.

    Returns:
        Dict with name, description, entry_path, metadata — or None if not found
    """
    target_dir = skills_dir or SUBAGENT_SKILLS_DIR
    subagents_dir = os.path.join(target_dir, "subagents")

    # Search in subagents dir
    skill_dir = os.path.join(subagents_dir, name)
    if os.path.isdir(skill_dir):
        skill_md = os.path.join(skill_dir, "SKILL.md")
        parsed = parse_skill_md(skill_md)
        if parsed:
            entry_file = parsed.get("entry_file", "main.py")
            return {
                "name": parsed["name"],
                "description": parsed["description"],
                "entry_path": os.path.join(skill_dir, entry_file),
                "skill_dir": skill_dir,
                "metadata": parsed,
            }

    # Also search in the broader skills tree
    result = get_skill_description(name)
    if result.get("success"):
        skill_dir_found = get_skill_directory(name)
        entry_file = result.get("entry_file", "main.py")
        return {
            "name": result["skill_name"],
            "description": result["description"],
            "entry_path": os.path.join(skill_dir_found, entry_file) if skill_dir_found else None,
            "skill_dir": skill_dir_found,
            "metadata": result,
        }

    return None


def list_skills(skills_dir: str = None) -> List[Dict[str, Any]]:
    """
    List all skills (meta + tools + subagents).

    Args:
        skills_dir: Root skills directory (default: SKILLS_DIR)

    Returns:
        List of skill metadata dicts
    """
    target_dir = skills_dir or SKILLS_DIR

    all_skills = []

    # Walk all subdirectories looking for SKILL.md files
    for root, dirs, files in os.walk(target_dir):
        if "SKILL.md" in files:
            skill_md_path = os.path.join(root, "SKILL.md")
            parsed = parse_skill_md(skill_md_path)
            if parsed:
                # Determine skill type from path
                rel_path = os.path.relpath(root, target_dir)
                if rel_path.startswith("meta"):
                    skill_type = "meta"
                elif rel_path.startswith("tools"):
                    skill_type = "tool"
                else:
                    skill_type = "subagent"

                all_skills.append({
                    "name": parsed["name"],
                    "description": parsed["description"],
                    "skill_type": skill_type,
                    "tags": [],
                    "directory": root,
                    "entry_file": parsed.get("entry_file", ""),
                })

    return all_skills


def supersede_skill(
    name: str,
    new_code: str,
    reason: str = "",
    skills_dir: str = None,
) -> bool:
    """
    Replace an existing skill with improved code (supersede mechanism).

    Archives the old version and writes the new code.

    Args:
        name:       Skill name to supersede
        new_code:   New Python source code
        reason:     Why this skill is being superseded
        skills_dir: Root skills directory

    Returns:
        True on success
    """
    import shutil
    from datetime import datetime

    target_dir = skills_dir or SUBAGENT_SKILLS_DIR
    subagents_dir = os.path.join(target_dir, "subagents")
    skill_dir = os.path.join(subagents_dir, name)

    if not os.path.isdir(skill_dir):
        # Skill doesn't exist yet — just create it
        os.makedirs(skill_dir, exist_ok=True)

    try:
        # Archive old version
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_dir = os.path.join(skill_dir, f"_archive_{ts}")
        if os.path.exists(skill_dir):
            os.makedirs(archive_dir, exist_ok=True)
            for fname in os.listdir(skill_dir):
                if fname.endswith(".py") and not fname.startswith("_"):
                    shutil.copy2(
                        os.path.join(skill_dir, fname),
                        os.path.join(archive_dir, fname),
                    )

        # Write new code
        entry_path = os.path.join(skill_dir, "main.py")
        with open(entry_path, "w", encoding="utf-8") as f:
            f.write(f"# Superseded: {reason}\n# Timestamp: {ts}\n\n")
            f.write(new_code)

        # Update SKILL.md with supersede note
        skill_md_path = os.path.join(skill_dir, "SKILL.md")
        if os.path.exists(skill_md_path):
            with open(skill_md_path, "a", encoding="utf-8") as f:
                f.write(f"\n## Supersede History\n- {ts}: {reason}\n")

        return True

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False
