"""Paper ingestion from arXiv API."""

import arxiv
import json
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any

from arxiv_scanner.storage import Storage

def extract_base_id(arxiv_id: str) -> str:
    """Extract base ID from arXiv ID (remove version suffix)."""
    if 'v' in arxiv_id and arxiv_id.rfind('v') > arxiv_id.rfind('.'):
        parts = arxiv_id.split('v')
        if len(parts) >= 2 and parts[1].isdigit():
            return parts[0]
    return arxiv_id

def fetch_papers(topic: Dict[str, Any], storage: Storage, since: Optional[str] = None) -> Tuple[List[Dict[str, Any]], str]:
    """Fetch papers for a topic with date gating."""
    try:
        client = arxiv.Client()
        search = arxiv.Search(
            query=topic['query'],
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending
        )
        
        new_papers = []
        
        # Calculate cutoff date
        cutoff_date = None
        if since:
            day, month, year = map(int, since.split('-'))
            cutoff_date = datetime(year, month, day).date()
        elif topic.get('last_run_at'):
            cutoff_date = datetime.fromisoformat(topic['last_run_at']).date()
        
        for result in client.results(search):
            published_at = result.published.date()
            if cutoff_date and published_at <= cutoff_date:
                break
            
            paper_data = {
                'id': extract_base_id(result.get_short_id()),
                'title': result.title,
                'authors': [author.name for author in result.authors],
                'published_at': result.published.isoformat(),
                'abstract': result.summary,
                'url': str(result.pdf_url) if result.pdf_url else ""
            }
            
            storage.save_paper(paper_data)
            new_papers.append(paper_data)
            
        return new_papers, "SUCCESS"
    except Exception as e:
        return [], f"ERROR: {str(e)}"