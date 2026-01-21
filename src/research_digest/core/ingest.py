"""Paper ingestion from arXiv API with deduplication."""

import arxiv
import json
from datetime import datetime
from typing import List, Tuple, Optional

from sqlalchemy.orm import Session

from research_digest.models import Paper, Topic


def extract_base_id(arxiv_id: str) -> str:
    """Extract base ID from arXiv ID (remove version suffix)."""
    # Examples: "2310.00012v1" -> "2310.00012", "cs.AI/2310.00012v2" -> "cs.AI/2310.00012"
    if 'v' in arxiv_id and arxiv_id.rfind('v') > arxiv_id.rfind('.'):
        # Handle versioned papers
        parts = arxiv_id.split('v')
        if len(parts) >= 2 and parts[1].isdigit():
            return parts[0]
    return arxiv_id


def extract_version(arxiv_id: str) -> int:
    """Extract version number from arXiv ID."""
    if 'v' in arxiv_id and arxiv_id.rfind('v') > arxiv_id.rfind('.'):
        parts = arxiv_id.split('v')
        if len(parts) >= 2 and parts[1].isdigit():
            return int(parts[1])
    return 1


def fetch_papers(topic: Topic, session: Session, since: Optional[str] = None) -> Tuple[List[Paper], str]:
    """Fetch papers for a topic with date gating and deduplication.
    
    Args:
        topic: Topic to fetch papers for
        session: Database session
        since: Optional date string in dd-mm-yyyy format to override topic.last_run_at
    
    Returns:
        Tuple of (new_papers, status)
        Status can be: "SUCCESS", "ZERO_RESULTS", or "ERROR"
    """
    try:
        client = arxiv.Client()
        search = arxiv.Search(
            query=topic.raw_query,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending
        )
        
        new_papers = []
        total_results = 0
        
        for result in client.results(search):
            total_results += 1
            
            # Extract paper info
            base_id = extract_base_id(result.get_short_id())
            version = extract_version(result.get_short_id())
            published_at = result.published.date()
            updated_at = result.updated.date()
            
            # Date gate: stop if paper is older than the cutoff date
            cutoff_date = None
            if since:
                # Parse dd-mm-yyyy format
                try:
                    day, month, year = map(int, since.split('-'))
                    cutoff_date = datetime(year, month, day).date()
                except ValueError:
                    raise ValueError(f"Invalid date format: {since}. Expected dd-mm-yyyy")
            elif topic.last_run_at:
                cutoff_date = topic.last_run_at.date()
            
            if cutoff_date and published_at <= cutoff_date:
                break
            
            # Check if paper already exists
            existing_paper = session.query(Paper).filter(Paper.id == base_id).first()
            
            if existing_paper:
                # Update if newer version
                if updated_at > existing_paper.updated_at.date():
                    existing_paper.version = version
                    existing_paper.updated_at = datetime.combine(updated_at, datetime.min.time())
                    existing_paper.title = result.title
                    existing_paper.authors = json.dumps([author.name for author in result.authors])
                    existing_paper.abstract = result.summary
                    existing_paper.pdf_url = result.pdf_url or ""
                    session.commit()
                    new_papers.append(existing_paper)
                # If same version or older, skip
                continue
            else:
                # Create new paper
                paper = Paper(
                    id=base_id,
                    version=version,
                    title=result.title,
                    authors=json.dumps([author.name for author in result.authors]),
                    published_at=datetime.combine(published_at, datetime.min.time()),
                    updated_at=datetime.combine(updated_at, datetime.min.time()),
                    abstract=result.summary,
                    pdf_url=str(result.pdf_url) if result.pdf_url else "",
                )
                session.add(paper)
                new_papers.append(paper)
        
        session.commit()
        
        # Check for zero results on first run
        if total_results == 0 and not topic.last_run_at:
            return [], "ZERO_RESULTS"
        
        return new_papers, "SUCCESS"
        
    except Exception as e:
        return [], f"ERROR: {str(e)}"