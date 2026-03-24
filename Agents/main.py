"""
main.py — Entry point for the Self-Evolving Agentic Browser System.

Usage:
    # Connect with people
    python main.py connect --query "ML engineer San Francisco" --limit 10

    # Scrape profiles
    python main.py scrape --query "data scientist NYC" --limit 20

    # Send messages
    python main.py message --connections url1,url2 --template "Hi {name}..."

    # Run evolution cycle (improve strategies from past failures)
    python main.py evolve

    # Show daily stats
    python main.py stats

    # List saved skills
    python main.py skills

Environment:
    Copy .env.example to .env and fill in your credentials.
    Start ChromaDB: docker-compose up -d
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
from loguru import logger
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

# Load environment variables
load_dotenv()

console = Console()


# ── System Bootstrap ──────────────────────────────────────────────────────────

async def bootstrap():
    """Initialize all system components and return them."""
    from llm.base_model import get_llm
    from llm.enhanced_llm import EnhancedLLM
    from memory.memory_manager import MemoryManager
    from agent_browser.browser_pool import BrowserPool
    from agent_browser.stealth.rate_limiter import RateLimiter
    from agent_browser.stealth.human_behavior import HumanBehavior
    from agents.auth_agent import AuthAgent
    from agents.search_agent import SearchAgent
    from agents.connection_agent import ConnectionAgent
    from agents.scraper_agent import ScraperAgent
    from agents.message_agent import MessageAgent
    from agents.orchestrator import Orchestrator
    from agents.meta_agent import MetaAgent
    from agents.reflection_agent import ReflectionAgent
    from agents.evolution_agent import EvolutionAgent

    console.print(Panel.fit(
        "[bold cyan]🤖 Self-Evolving Agentic Browser[/bold cyan]\n"
        "[dim]Powered by Playwright + ChromaDB + Ollama/Gemini[/dim]",
        border_style="cyan",
    ))

    # ── LLM ──────────────────────────────────────────────────────────────────
    provider = os.getenv("LLM_PROVIDER", "ollama")
    console.print(f"[dim]LLM provider: {provider}[/dim]")

    try:
        base_llm = get_llm(provider=provider)
    except Exception as e:
        console.print(f"[yellow]⚠ LLM init failed ({e}), running without LLM[/yellow]")
        base_llm = None

    # ── Memory (ChromaDB) ─────────────────────────────────────────────────────
    console.print("[dim]Connecting to ChromaDB...[/dim]")
    try:
        memory = MemoryManager()
        await memory.initialize()
        console.print("[green]✓ ChromaDB connected[/green]")
    except Exception as e:
        console.print(f"[yellow]⚠ ChromaDB unavailable ({e}), running without memory[/yellow]")
        memory = None

    # ── Enhanced LLM (LLM + Memory) ───────────────────────────────────────────
    enhanced_llm = EnhancedLLM(base_llm=base_llm, memory=memory) if base_llm else None

    # ── Stealth Components ────────────────────────────────────────────────────
    rate_limiter = RateLimiter()
    human_behavior = HumanBehavior()

    # ── Browser Pool ──────────────────────────────────────────────────────────
    headless = os.getenv("BROWSER_HEADLESS", "true").lower() == "true"
    pool_size = int(os.getenv("BROWSER_POOL_SIZE", "2"))
    console.print(f"[dim]Starting browser pool (size={pool_size}, headless={headless})...[/dim]")

    browser_pool = BrowserPool(
        size=pool_size,
        headless=headless,
        storage_state_dir="workspace/sessions",
    )
    await browser_pool.start()
    console.print(f"[green]✓ Browser pool ready ({pool_size} instances)[/green]")

    # ── Agents ────────────────────────────────────────────────────────────────
    common_kwargs = dict(
        llm=enhanced_llm,
        memory=memory,
        rate_limiter=rate_limiter,
        human_behavior=human_behavior,
    )

    auth_agent       = AuthAgent(**common_kwargs)
    search_agent     = SearchAgent(**common_kwargs)
    connection_agent = ConnectionAgent(**common_kwargs)
    scraper_agent    = ScraperAgent(**common_kwargs)
    message_agent    = MessageAgent(**common_kwargs)
    reflection_agent = ReflectionAgent(llm=enhanced_llm, memory=memory)
    evolution_agent  = EvolutionAgent(llm=enhanced_llm, memory=memory)

    orchestrator = Orchestrator(
        auth_agent=auth_agent,
        search_agent=search_agent,
        connection_agent=connection_agent,
        scraper_agent=scraper_agent,
        message_agent=message_agent,
        memory=memory,
        rate_limiter=rate_limiter,
    )

    meta_agent = MetaAgent(
        llm=enhanced_llm,
        memory=memory,
        orchestrator=orchestrator,
    )

    evolution_agent.meta_agent = meta_agent

    console.print("[green]✓ All agents initialized[/green]\n")

    return {
        "browser_pool": browser_pool,
        "meta_agent": meta_agent,
        "orchestrator": orchestrator,
        "evolution_agent": evolution_agent,
        "rate_limiter": rate_limiter,
        "memory": memory,
    }


# ── Commands ──────────────────────────────────────────────────────────────────

async def cmd_connect(args, components):
    """Run the LinkedIn connection workflow."""
    console.print(f"\n[bold]🔗 Connect Workflow[/bold]")
    console.print(f"Query: [cyan]{args.query}[/cyan]")
    console.print(f"Limit: [cyan]{args.limit}[/cyan]")
    if args.note:
        console.print(f"Note template: [cyan]{args.note[:50]}...[/cyan]")

    result = await components["meta_agent"].run(
        goal=f"Connect with {args.limit} people: {args.query}",
        context={
            "search_query": args.query,
            "max_connections": args.limit,
            "note_template": args.note or "",
        },
        browser_pool=components["browser_pool"],
    )

    _print_result(result)
    return result


async def cmd_scrape(args, components):
    """Run the LinkedIn profile scraping workflow."""
    console.print(f"\n[bold]🔍 Scrape Workflow[/bold]")
    console.print(f"Query: [cyan]{args.query}[/cyan]")
    console.print(f"Limit: [cyan]{args.limit}[/cyan]")

    result = await components["meta_agent"].run(
        goal=f"Scrape {args.limit} LinkedIn profiles: {args.query}",
        context={
            "search_query": args.query,
            "limit": args.limit,
        },
        browser_pool=components["browser_pool"],
    )

    _print_result(result)

    # Print scraped profiles table
    profiles = result.get("result", {}).get("results", [])
    if profiles:
        table = Table(title=f"Scraped {len(profiles)} Profiles")
        table.add_column("Name", style="cyan")
        table.add_column("Title", style="white")
        table.add_column("Company", style="green")
        table.add_column("Location", style="dim")
        for p in profiles[:20]:
            table.add_row(
                p.get("name", ""),
                p.get("headline", "")[:40],
                (p.get("experience") or [{}])[0].get("company", ""),
                p.get("location", ""),
            )
        console.print(table)

    return result


async def cmd_message(args, components):
    """Run the LinkedIn messaging workflow."""
    connections = args.connections.split(",") if args.connections else []
    console.print(f"\n[bold]💬 Message Workflow[/bold]")
    console.print(f"Recipients: [cyan]{len(connections)}[/cyan]")
    console.print(f"Template: [cyan]{args.template[:60]}...[/cyan]")

    result = await components["meta_agent"].run(
        goal=f"Message {len(connections)} LinkedIn connections",
        context={
            "connections": connections,
            "message_template": args.template,
            "max_messages": args.limit,
        },
        browser_pool=components["browser_pool"],
    )

    _print_result(result)
    return result


async def cmd_evolve(args, components):
    """Run the evolution cycle."""
    console.print("\n[bold]🧬 Evolution Cycle[/bold]")
    console.print("[dim]Analyzing failure patterns and improving strategies...[/dim]")

    result = await components["evolution_agent"].evolve()

    console.print(f"\n[green]✓ Evolution complete[/green]")
    console.print(f"  Patterns analyzed: [cyan]{result['patterns_analyzed']}[/cyan]")
    console.print(f"  Improvements made: [cyan]{result['improvements_made']}[/cyan]")
    console.print(f"  Skills updated:    [cyan]{len(result['skills_updated'])}[/cyan]")
    if result["skills_updated"]:
        console.print(f"  Updated: {', '.join(result['skills_updated'])}")

    return result


async def cmd_stats(args, components):
    """Show daily usage statistics."""
    console.print("\n[bold]📊 Daily Statistics[/bold]")

    rate_limiter = components["rate_limiter"]
    summary = rate_limiter.get_daily_summary()

    table = Table(title="Today's Action Counts")
    table.add_column("Action", style="cyan")
    table.add_column("Used", style="yellow")
    table.add_column("Limit", style="white")
    table.add_column("Remaining", style="green")
    table.add_column("Usage %", style="dim")

    for action, data in summary.items():
        table.add_row(
            action,
            str(data["used"]),
            str(data["limit"]),
            str(data["remaining"]),
            f"{data['percentage']}%",
        )

    console.print(table)

    # Browser pool stats
    pool_stats = components["browser_pool"].get_stats()
    console.print(f"\n[bold]Browser Pool:[/bold] {pool_stats['available']}/{pool_stats['total']} available")

    return summary


async def cmd_skills(args, components):
    """List all saved skills."""
    console.print("\n[bold]🛠 Saved Skills[/bold]")

    skills = await components["meta_agent"].list_saved_subagents()

    if not skills:
        console.print("[dim]No skills saved yet. Skills are created automatically after successful workflows.[/dim]")
        return []

    table = Table(title=f"{len(skills)} Saved Skills")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="yellow")
    table.add_column("Description", style="white")
    table.add_column("Tags", style="dim")

    for skill in skills:
        table.add_row(
            skill.get("name", ""),
            skill.get("skill_type", ""),
            skill.get("description", "")[:50],
            ", ".join(skill.get("tags", [])),
        )

    console.print(table)
    return skills


# ── Helpers ───────────────────────────────────────────────────────────────────

def _print_result(result: dict) -> None:
    """Print a workflow result summary."""
    success = result.get("success", False)
    icon = "✅" if success else "❌"
    color = "green" if success else "red"

    console.print(f"\n[{color}]{icon} {'Success' if success else 'Failed'}[/{color}]")

    if result.get("error"):
        console.print(f"[red]Error: {result['error']}[/red]")

    duration = result.get("result", {}).get("duration_seconds", 0)
    if duration:
        console.print(f"[dim]Duration: {duration:.1f}s[/dim]")

    # Show skills saved
    if result.get("skills_saved"):
        console.print(f"[green]💾 Skills saved: {', '.join(result['skills_saved'])}[/green]")


# ── CLI Parser ────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Self-Evolving Agentic Browser — LinkedIn Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py connect --query "ML engineer San Francisco" --limit 10
  python main.py scrape  --query "data scientist NYC" --limit 20
  python main.py message --connections "url1,url2" --template "Hi {name}..."
  python main.py evolve
  python main.py stats
  python main.py skills
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # connect
    p_connect = subparsers.add_parser("connect", help="Send LinkedIn connection requests")
    p_connect.add_argument("--query", required=True, help="Search query (e.g. 'ML engineer SF')")
    p_connect.add_argument("--limit", type=int, default=10, help="Max connections to send (default: 10)")
    p_connect.add_argument("--note", default="", help="Custom connection note template")

    # scrape
    p_scrape = subparsers.add_parser("scrape", help="Scrape LinkedIn profiles")
    p_scrape.add_argument("--query", required=True, help="Search query")
    p_scrape.add_argument("--limit", type=int, default=20, help="Max profiles to scrape (default: 20)")

    # message
    p_message = subparsers.add_parser("message", help="Message existing connections")
    p_message.add_argument("--connections", required=True, help="Comma-separated profile URLs")
    p_message.add_argument("--template", required=True, help="Message template with {name} placeholders")
    p_message.add_argument("--limit", type=int, default=10, help="Max messages to send (default: 10)")

    # evolve
    subparsers.add_parser("evolve", help="Run evolution cycle to improve strategies")

    # stats
    subparsers.add_parser("stats", help="Show daily usage statistics")

    # skills
    subparsers.add_parser("skills", help="List all saved skills")

    return parser


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Configure logging
    log_level = os.getenv("LOG_LEVEL", "INFO")
    logger.remove()
    logger.add(sys.stderr, level=log_level, format="<dim>{time:HH:mm:ss}</dim> | <level>{level: <8}</level> | {message}")
    logger.add("workspace/agent.log", level="DEBUG", rotation="10 MB", retention="7 days")

    # Bootstrap system
    components = await bootstrap()

    try:
        # Dispatch command
        command_map = {
            "connect": cmd_connect,
            "scrape":  cmd_scrape,
            "message": cmd_message,
            "evolve":  cmd_evolve,
            "stats":   cmd_stats,
            "skills":  cmd_skills,
        }

        handler = command_map.get(args.command)
        if handler:
            await handler(args, components)
        else:
            console.print(f"[red]Unknown command: {args.command}[/red]")
            parser.print_help()

    finally:
        # Clean shutdown
        console.print("\n[dim]Shutting down browser pool...[/dim]")
        await components["browser_pool"].stop()
        console.print("[dim]Done.[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
