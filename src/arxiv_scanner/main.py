"""CLI main entry point for Research Digest."""

import os
import time
import typer
from rich.console import Console
from rich.table import Table
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
)
from typing import Optional

from arxiv_scanner.config import Config
from arxiv_scanner.storage import Storage
from arxiv_scanner.llm.provider import create_llm_provider
from arxiv_scanner.core.translate import translate_topic
from arxiv_scanner.core.ingest import fetch_papers, preview_papers
from arxiv_scanner.core.processor import process_paper

app = typer.Typer()
console = Console()


def get_storage() -> Storage:
    """Get storage instance."""
    config = Config.load_from_file()
    return Storage(config.app.db_path)


def get_config_and_llm():
    """Get config and LLM provider."""
    config = Config.load_from_file()
    llm_provider = create_llm_provider(config)
    return config, llm_provider


@app.command()
def add_topic(
    name: str = typer.Argument(..., help="Name of the research topic"),
    description: str = typer.Argument(
        ..., help="Natural language description of the research topic"
    ),
):
    """Add a new research topic."""
    config, llm_provider = get_config_and_llm()
    storage = get_storage()

    console.print(f"[bold blue]Adding topic:[/bold blue] {name}")

    query = ""
    with console.status("[bold green]Generating arXiv query..."):
        try:
            query = translate_topic(description, llm_provider)
            console.print(
                f"[green]✓[/green] Generated query: [cyan]{query}[/cyan]"
            )
        except Exception as e:
            console.print(f"[red]✗[/red] Failed to generate query: {e}")
            raise typer.Exit(code=1)

    # Preview results
    console.print("\n[bold]Previewing recent papers found by this query:[/bold]")
    previews = preview_papers(query)

    if not previews:
        console.print("[yellow]No recent papers found. The query might be too specific.[/yellow]")
    else:
        for p in previews:
            console.print(f"• [dim]{p['published_at']}[/dim] [bold]{p['title']}[/bold]")
            console.print(f"  [dim]{p['abstract']}[/dim]\n")

    if not typer.confirm("Do you want to save this topic?"):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Abort()

    try:
        storage.add_topic(name, description, query)
        console.print(
            f"[green]✓[/green] Topic added successfully!"
        )
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to add topic: {e}")


@app.command()
def list_topics():
    """List all research topics."""
    storage = get_storage()
    topics = storage.get_topics()

    if not topics:
        console.print("[yellow]No topics found.[/yellow]")
        return

    table = Table(title="Research Topics")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="magenta")
    table.add_column("Last Run", style="blue")

    for t in topics:
        table.add_row(str(t["id"]), t["name"], t["last_run_at"] or "Never")

    console.print(table)


@app.command()
def update(
    since: str = typer.Option(None, "--since", help="Fetch papers since (dd-mm-yyyy)"),
    force: bool = typer.Option(False, "--force", help="Force reprocessing"),
):
    """Fetch and process new papers."""
    config, llm_provider = get_config_and_llm()
    storage = get_storage()
    topics = storage.get_topics(active_only=True)

    for topic in topics:
        console.print(f"\n[bold blue]Processing topic:[/bold blue] {topic['name']}")

        new_papers, status = fetch_papers(topic, storage, since)
        if status != "SUCCESS":
            console.print(f"[red]{status}[/red]")
            continue

        console.print(f"[green]Found {len(new_papers)} new papers[/green]")

        for paper in new_papers:
            link = storage.get_paper_topic_link(paper["id"], topic["id"])
            if link and not force:
                continue

            console.print(f"Processing: {paper['title'][:70]}...")
            result = process_paper(
                paper["title"], paper["abstract"], topic["description"], llm_provider
            )
            storage.save_paper_topic_link(paper["id"], topic["id"], result)

            if result.get("is_relevant"):
                console.print(f"  [green]✓ Relevant![/green]")

        storage.update_topic_last_run(topic["id"])


@app.command()
def digest(topic_id: int = typer.Argument(..., help="Topic ID")):
    """Show relevant papers for a topic."""
    storage = get_storage()
    papers = storage.get_relevant_papers(topic_id)

    if not papers:
        console.print("[yellow]No relevant papers found.[/yellow]")
        return

    for p in papers:
        console.print(f"\n[bold green]{p['title']}[/bold green]")
        console.print(f"[dim]{p['url']}[/dim]")
        summary = p.get("summary", {})
        if summary:
            console.print(f"\n[bold]TL;DR:[/bold] {summary.get('tldr')}")
            console.print(
                f"[bold]Key Contribution:[/bold] {summary.get('key_contribution')}"
            )
            console.print(f"[dim]Tags: {', '.join(p.get('tags', []))}[/dim]")
        console.print("-" * 40)


if __name__ == "__main__":
    app()
