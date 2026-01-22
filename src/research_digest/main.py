"""CLI main entry point for Research Digest."""

import os
import time
import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from typing import Optional

from research_digest.config import Config
from research_digest.database import Database
from research_digest.llm.provider import create_llm_provider
from research_digest.llm.rate_limiter import RateLimitError
from research_digest.core.translate import translate_topic
from research_digest.core.ingest import fetch_papers
from research_digest.core.filter import filter_paper
from research_digest.core.digest import summarize_paper
from research_digest.models import Topic, PaperTopicLink, Paper

app = typer.Typer()
console = Console()


def get_database() -> Database:
    """Get database instance."""
    config = Config.load_from_file()
    return Database(config)


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
    db = get_database()

    console.print(f"[bold blue]Adding topic:[/bold blue] {name}")
    console.print(f"[dim]Description:[/dim] {description}")

    # Translate description to query
    with console.status("[bold green]Generating arXiv query..."):
        try:
            raw_query = translate_topic(description, llm_provider)
            console.print(f"[green]✓[/green] Generated query: [cyan]{raw_query}[/cyan]")
        except Exception as e:
            console.print(f"[red]✗[/red] Failed to generate query: {e}")
            raise typer.Exit(1)

    # Add to database
    with db.get_session_context() as session:
        try:
            topic = db.add_topic(session, name, description, raw_query)
            console.print(f"[green]✓[/green] Topic '{name}' added successfully!")
        except Exception as e:
            console.print(f"[red]✗[/red] Failed to add topic: {e}")
            raise typer.Exit(1)


@app.command()
def list_topics(
    show_queries: bool = typer.Option(
        False, "--show-queries", "-q", help="Show exact arXiv query strings"
    ),
):
    """List all research topics."""
    db = get_database()

    with db.get_session_context() as session:
        topics = session.query(Topic).all()

        if not topics:
            console.print("[yellow]No topics found.[/yellow]")
            return

        if show_queries:
            # Detailed view with queries
            for i, topic in enumerate(topics, 1):
                last_run = (
                    topic.last_run_at.strftime("%Y-%m-%d %H:%M") if topic.last_run_at else "Never"
                )
                status = "✓ Active" if topic.active else "✗ Inactive"
                
                console.print(f"\n[bold cyan]{i}. {topic.name}[/bold cyan] [dim](ID: {topic.id})[/dim]")
                console.print(f"   Status: {status}")
                console.print(f"   Last Run: {last_run}")
                console.print(f"   Description: {topic.description}")
                console.print(f"   Query: [green]{topic.raw_query}[/green]")
                console.print("-" * 60)
        else:
            # Compact table view
            table = Table(title="Research Topics")
            table.add_column("ID", style="cyan", width=4)
            table.add_column("Name", style="magenta")
            table.add_column("Description", style="white")
            table.add_column("Active", style="green", width=6)
            table.add_column("Last Run", style="blue", width=12)

            for topic in topics:
                last_run = (
                    topic.last_run_at.strftime("%Y-%m-%d") if topic.last_run_at else "Never"
                )
                table.add_row(
                    str(topic.id),
                    topic.name,
                    topic.description[:80] + "..."
                    if len(topic.description) > 80
                    else topic.description,
                    "✓" if topic.active else "✗",
                    last_run,
                )

            console.print(table)
            console.print("\n[dim]Use --show-queries to see exact arXiv query strings[/dim]")


@app.command()
def update(
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Run without output for cron jobs"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed output including skipped papers"
    ),
    since: str = typer.Option(
        None, "--since", help="Fetch papers since this date (dd-mm-yyyy)"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force reprocessing of all papers (ignore cache)"
    ),
    max_requests_per_minute: Optional[float] = typer.Option(
        None, "--max-requests-per-minute", help="Override rate limit: max LLM requests per minute"
    ),
):
    """Main update loop to fetch and process new papers."""
    config, llm_provider = get_config_and_llm()
    
    # Override rate limit config if specified
    if max_requests_per_minute:
        config.app.rate_limit.max_requests_per_minute = max_requests_per_minute
        # Recreate provider with new rate limit
        llm_provider = create_llm_provider(config)
    
    db = get_database()

    # Ensure tables exist
    db.create_tables()

    with db.get_session_context() as session:
        topics = db.get_active_topics(session)

        if not topics:
            if not quiet:
                console.print("[yellow]No active topics found.[/yellow]")
            return

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console if not quiet else Console(file=open(os.devnull, 'w')),
            disable=quiet
        ) as progress:
            
            topic_progress = progress.add_task("Processing topics...", total=len(topics))
            
            for topic in topics:
                progress.update(topic_progress, description=f"Processing {topic.name}...")
                
                # Fetch papers with progress
                fetch_task = progress.add_task(f"Fetching papers for {topic.name}...", total=None)
                new_papers, status = fetch_papers(topic, session, since)
                progress.update(fetch_task, completed=1)

                # 2. Zero Results Feedback
                if status == "ZERO_RESULTS":
                    if not quiet:
                        console.print(
                            f"[yellow]Warning: 0 results found for '{topic.name}'. Check your query: {topic.raw_query}[/yellow]"
                        )
                    progress.update(topic_progress, advance=1)
                    continue
                elif status.startswith("ERROR"):
                    if not quiet:
                        console.print(
                            f"[red]Error fetching papers for '{topic.name}': {status}[/red]"
                        )
                    progress.update(topic_progress, advance=1)
                    continue

                if not new_papers:
                    if not quiet:
                        console.print("[dim]No new papers found.[/dim]")
                else:
                    if not quiet:
                        console.print(f"[green]Found {len(new_papers)} new papers[/green]")

                # 3. Filter & Digest Loop with progress
                processed_count = 0
                skipped_count = 0
                
                if new_papers:
                    paper_progress = progress.add_task(f"Filtering papers for {topic.name}...", total=len(new_papers))
                    
                    for paper in new_papers:
                        try:
                            progress.update(paper_progress, description=f"Processing: {paper.title[:50]}...")
                            
                            # Filter for relevance
                            filter_result = filter_paper(
                                paper.title, paper.abstract, topic.description, llm_provider
                            )

                            # Create or update paper-topic link
                            link = (
                                session.query(PaperTopicLink)
                                .filter_by(paper_id=paper.id, topic_id=topic.id)
                                .first()
                            )

                            should_process = force or not link  # Process if force flag or no existing link
                            
                            if not link:
                                link = PaperTopicLink(
                                    paper_id=paper.id,
                                    topic_id=topic.id,
                                    relevance_score=filter_result["relevance_score"],
                                    is_relevant=filter_result["is_relevant"],
                                    tags="[]",
                                )
                                session.add(link)
                            elif should_process:
                                link.relevance_score = filter_result["relevance_score"]
                                link.is_relevant = filter_result["is_relevant"]

                            # If relevant and should process, generate summary
                            if filter_result["is_relevant"] and should_process:
                                summary = summarize_paper(
                                    paper.title, paper.abstract, llm_provider
                                )
                                link.digest = (
                                    f"**TL;DR**: {summary['tldr']}\n\n"
                                    f"**Key Contribution**: {summary['key_contribution']}\n\n"
                                    f"**Methodology**: {summary['methodology']}\n\n"
                                )
                                link.tags = str(summary["tags"])
                            elif not should_process and verbose and not quiet:
                                if filter_result["is_relevant"]:
                                    console.print(
                                        f"[dim]→[/dim] Already processed: {paper.title[:60]}..."
                                    )

                                if not quiet:
                                    console.print(
                                        f"[green]✓[/green] Relevant paper: {paper.title[:60]}..."
                                    )
                            else:
                                skipped_count += 1
                                if verbose and not quiet:
                                    console.print(
                                        f"[dim]✗[/dim] Skipped paper: {paper.title[:60]}..."
                                    )

                            processed_count += 1
                            progress.update(paper_progress, advance=1)

                        except RateLimitError as e:
                            if not quiet:
                                console.print(f"[yellow]Rate limit hit[/yellow]: {e.message}")
                                if e.retry_after:
                                    console.print(f"[dim]Will retry after {e.retry_after:.1f}s...[/dim]")
                            # For rate limit errors, we retry automatically in the rate limiter
                            # so we should continue processing
                            progress.update(paper_progress, advance=1)
                        except Exception as e:
                            if not quiet:
                                console.print(
                                    f"[red]Error processing paper '{paper.title}': {e}[/red]"
                                )
                            progress.update(paper_progress, advance=1)
                    
                    progress.update(paper_progress, completed=len(new_papers))

                # Update topic's last_run_at
                from datetime import datetime

                topic.last_run_at = datetime.utcnow()
                session.commit()

                if not quiet and processed_count > 0:
                    console.print(
                        f"[green]Processed {processed_count} papers for topic '{topic.name}'[/green]"
                    )
                    
                if verbose and not quiet and skipped_count > 0:
                    console.print(
                        f"[dim]Skipped {skipped_count} papers for topic '{topic.name}'[/dim]"
                    )

                progress.update(topic_progress, advance=1)

            # 4. Throttling
            if not quiet:
                delay = config.app.throttling_delay
                console.print(f"[dim]Sleeping {delay}s to respect API limits...[/dim]")
            time.sleep(config.app.throttling_delay)

        if not quiet:
            console.print("[bold green]Update complete![/bold green]")


@app.command()
def status(
    reset_topic: Optional[int] = typer.Option(
        None, "--reset-topic", help="Reset a specific topic ID (clear last_run_at)"
    ),
    show_rate_limit: bool = typer.Option(
        False, "--rate-limit", "-r", help="Show rate limiting statistics"
    ),
):
    """Show database status and optionally reset topics."""
    config, llm_provider = get_config_and_llm()
    db = get_database()
    
    with db.get_session_context() as session:
        # Database overview
        total_topics = session.query(Topic).count()
        active_topics = session.query(Topic).filter(Topic.active == True).count()
        total_papers = session.query(Paper).count()
        total_links = session.query(PaperTopicLink).count()
        relevant_papers = session.query(PaperTopicLink).filter(PaperTopicLink.is_relevant == True).count()
        
        console.print("\n[bold blue]Database Status[/bold blue]")
        console.print("=" * 40)
        console.print(f"Topics: {active_topics}/{total_topics} active")
        console.print(f"Total Papers: {total_papers}")
        console.print(f"Paper-Topic Links: {total_links}")
        console.print(f"Relevant Papers: {relevant_papers}")
        
        # Topic details
        topics = session.query(Topic).all()
        if topics:
            console.print(f"\n[bold blue]Topics Details[/bold blue]")
            console.print("=" * 40)
            
            for topic in topics:
                last_run = topic.last_run_at.strftime("%Y-%m-%d %H:%M") if topic.last_run_at else "Never"
                paper_count = session.query(PaperTopicLink).filter(PaperTopicLink.topic_id == topic.id).count()
                relevant_count = session.query(PaperTopicLink).filter(
                    PaperTopicLink.topic_id == topic.id, 
                    PaperTopicLink.is_relevant == True
                ).count()
                
                status_icon = "✓" if topic.active else "✗"
                console.print(f"{status_icon} Topic {topic.id}: {topic.name}")
                console.print(f"    Last run: {last_run}")
                console.print(f"    Papers: {relevant_count}/{paper_count} relevant")
                console.print(f"    Query: {topic.raw_query[:80]}...")
                console.print("")
        
        # Show rate limiting statistics
        if show_rate_limit:
            console.print(f"\n[bold blue]Rate Limiting Status[/bold blue]")
            console.print("=" * 40)
            
            if config.app.rate_limit.enabled:
                console.print(f"Rate limiting: [green]Enabled[/green]")
                console.print(f"Max requests per minute: {config.app.rate_limit.max_requests_per_minute}")
                
                # Try to get stats from rate-limited provider
                try:
                    from research_digest.llm.rate_limiter import RateLimitedLLMProvider
                    if isinstance(llm_provider, RateLimitedLLMProvider):
                        stats = llm_provider.get_stats()
                        console.print(f"Requests in last minute: {stats['requests_in_last_minute']}")
                        console.print(f"Remaining requests: {stats['remaining_requests']}")
                        console.print(f"Total requests made: {stats['total_requests']}")
                        console.print(f"Rate limit errors: {stats['rate_limit_errors']}")
                        if stats['error_rate'] > 0:
                            console.print(f"Error rate: [yellow]{stats['error_rate']:.1%}[/yellow]")
                        else:
                            console.print(f"Error rate: [green]{stats['error_rate']:.1%}[/green]")
                except Exception as e:
                    console.print(f"[dim]Could not fetch rate limit stats: {e}[/dim]")
            else:
                console.print(f"Rate limiting: [red]Disabled[/red]")
        
        # Handle reset
        if reset_topic:
            topic = session.query(Topic).filter(Topic.id == reset_topic).first()
            if topic:
                from datetime import datetime
                topic.last_run_at = None
                session.commit()
                console.print(f"[green]✓ Reset topic '{topic.name}' (ID: {topic.id})[/green]")
            else:
                console.print(f"[red]Topic with ID {reset_topic} not found[/red]")


@app.command()
def edit_topic(
    topic_id: int = typer.Argument(..., help="Topic ID to edit"),
    new_query: Optional[str] = typer.Option(None, "--query", help="New arXiv query string"),
    new_name: Optional[str] = typer.Option(None, "--name", help="New topic name"),
    new_description: Optional[str] = typer.Option(None, "--description", help="New topic description"),
    activate: bool = typer.Option(False, "--activate", help="Activate the topic"),
    deactivate: bool = typer.Option(False, "--deactivate", help="Deactivate the topic"),
):
    """Edit an existing topic's properties."""
    db = get_database()
    
    with db.get_session_context() as session:
        topic = session.query(Topic).filter(Topic.id == topic_id).first()
        if not topic:
            console.print(f"[red]Topic with ID {topic_id} not found.[/red]")
            raise typer.Exit(1)
            
        console.print(f"[bold blue]Editing topic:[/bold blue] {topic.name}")
        console.print(f"[dim]Current query:[/dim] {topic.raw_query}")
        
        # Validate new query if provided
        if new_query:
            config, llm_provider = get_config_and_llm()
            with console.status("[bold green]Validating new query..."):
                try:
                    # Test the query with arXiv API
                    import arxiv
                    client = arxiv.Client()
                    search = arxiv.Search(query=new_query, max_results=1)
                    next(client.results(search), None)
                    console.print(f"[green]✓[/green] Query validated successfully")
                except Exception as e:
                    console.print(f"[red]✗[/red] Query validation failed: {e}")
                    raise typer.Exit(1)
        
        # Apply changes
        changed = False
        if new_name:
            old_name = topic.name
            topic.name = new_name
            changed = True
            console.print(f"[green]✓[/green] Name changed: {old_name} → {new_name}")
            
        if new_description:
            old_desc = topic.description[:50] + "..." if len(topic.description) > 50 else topic.description
            topic.description = new_description
            changed = True
            console.print(f"[green]✓[/green] Description changed")
            
        if new_query:
            old_query = topic.raw_query[:50] + "..." if len(topic.raw_query) > 50 else topic.raw_query
            topic.raw_query = new_query
            changed = True
            console.print(f"[green]✓[/green] Query changed")
            
        if activate and not topic.active:
            topic.active = True
            changed = True
            console.print(f"[green]✓[/green] Topic activated")
            
        if deactivate and topic.active:
            topic.active = False
            changed = True
            console.print(f"[yellow]✓[/yellow] Topic deactivated")
            
        if not changed:
            console.print("[yellow]No changes made.[/yellow]")
            return
            
        session.commit()
        console.print(f"[bold green]Topic '{topic.name}' updated successfully![/bold green]")


@app.command()
def digest_report(
    topic_id: Optional[int] = typer.Argument(
        None, help="Topic ID (optional, shows all if not provided)"
    ),
    force_regenerate: bool = typer.Option(
        False, "--force", "-f", help="Force regeneration of all digests (reprocess all relevant papers)"
    ),
    max_requests_per_minute: Optional[float] = typer.Option(
        None, "--max-requests-per-minute", help="Override rate limit: max LLM requests per minute"
    ),
):
    """Generate a digest report for one or all topics."""
    config, llm_provider = get_config_and_llm()
    
    # Override rate limit config if specified
    if max_requests_per_minute:
        config.app.rate_limit.max_requests_per_minute = max_requests_per_minute
        # Recreate provider with new rate limit
        llm_provider = create_llm_provider(config)
    
    db = get_database()

    with db.get_session_context() as session:
        if topic_id:
            topic = session.query(Topic).filter(Topic.id == topic_id).first()
            if not topic:
                console.print(f"[red]Topic with ID {topic_id} not found.[/red]")
                raise typer.Exit(1)
            topics = [topic]
        else:
            topics = session.query(Topic).filter(Topic.active == True).all()

        for topic in topics:
            console.print(f"\n[bold blue]Digest for:[/bold blue] {topic.name}")
            console.print(f"[dim]{topic.description}[/dim]")
            console.print("=" * 50)

            if force_regenerate:
                # Get all relevant papers (regardless of whether they have digests)
                links = (
                    session.query(PaperTopicLink)
                    .join(Paper)
                    .filter(
                        PaperTopicLink.topic_id == topic.id,
                        PaperTopicLink.is_relevant == True,
                    )
                    .order_by(PaperTopicLink.created_at.desc())
                    .all()
                )
                
                if links:
                    console.print(f"[yellow]Regenerating {len(links)} digests...[/yellow]")
                    
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        BarColumn(),
                        TaskProgressColumn(),
                        console=console,
                    ) as progress:
                        
                        regen_progress = progress.add_task("Regenerating digests...", total=len(links))
                        
                        for link in links:
                            progress.update(regen_progress, description=f"Processing: {link.paper.title[:50]}...")
                            
                            try:
                                summary = summarize_paper(
                                    link.paper.title, link.paper.abstract, llm_provider
                                )
                                link.digest = (
                                    f"**TL;DR**: {summary['tldr']}\n\n"
                                    f"**Key Contribution**: {summary['key_contribution']}\n\n"
                                    f"**Methodology**: {summary['methodology']}\n\n"
                                )
                                link.tags = str(summary["tags"])
                                progress.update(regen_progress, advance=1)
                            except Exception as e:
                                console.print(f"[red]Error regenerating digest for '{link.paper.title}': {e}[/red]")
                                progress.update(regen_progress, advance=1)
                    
                    session.commit()
                    console.print(f"[green]✓ Regenerated {len(links)} digests[/green]")
            else:
                # Get relevant papers with existing digests
                links = (
                    session.query(PaperTopicLink)
                    .join(Paper)
                    .filter(
                        PaperTopicLink.topic_id == topic.id,
                        PaperTopicLink.is_relevant == True,
                        PaperTopicLink.digest.isnot(None),
                    )
                    .order_by(PaperTopicLink.created_at.desc())
                    .all()
                )

            if not links:
                console.print("[yellow]No relevant papers found.[/yellow]")
                continue

            for i, link in enumerate(links, 1):
                console.print(f"\n[bold green]{i}. {link.paper.title}[/bold green]")
                console.print(f"[dim]Authors: {link.paper.authors}[/dim]")
                console.print(
                    f"[dim]Published: {link.paper.published_at.strftime('%Y-%m-%d')}[/dim]"
                )
                console.print(
                    f"[dim]Relevance Score: {link.relevance_score:.1f}/10[/dim]"
                )
                console.print(f"\n{link.digest or ''}")
                console.print("-" * 30)


if __name__ == "__main__":
    app()

