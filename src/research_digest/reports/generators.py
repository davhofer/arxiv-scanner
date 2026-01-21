"""Report generation for Research Digest."""

from jinja2 import Environment, FileSystemLoader, Template
from pathlib import Path
from typing import List, Dict, Any

from research_digest.models import Topic, PaperTopicLink, Paper


def setup_template_environment() -> Environment:
    """Set up Jinja2 environment with template directory."""
    template_dir = Path(__file__).parent / "templates"
    return Environment(loader=FileSystemLoader(template_dir))


def generate_markdown_digest(topic: Topic, paper_links: List[PaperTopicLink]) -> str:
    """Generate a markdown digest for a topic."""
    
    # Prepare data for template
    papers_data = []
    for link in paper_links:
        paper_data = {
            "title": link.paper.title,
            "authors": link.paper.authors,
            "published_date": link.paper.published_at.strftime("%Y-%m-%d"),
            "relevance_score": link.relevance_score,
            "digest": link.digest or "",
            "tags": eval(link.tags) if link.tags else [],
            "pdf_url": link.paper.pdf_url,
            "arxiv_id": link.paper.id
        }
        papers_data.append(paper_data)
    
    topic_data = {
        "name": topic.name,
        "description": topic.description,
        "papers": papers_data,
        "generated_date": paper_links[0].created_at.strftime("%Y-%m-%d %H:%M") if paper_links else "Unknown"
    }
    
    # Use default template if custom template doesn't exist
    template_str = """# Research Digest: {{ name }}

**Description:** {{ description }}

*Generated on: {{ generated_date }}*

---

{% for paper in papers %}
## {{ loop.index }}. {{ paper.title }}

**Authors:** {{ paper.authors }}  
**Published:** {{ paper.published_date }}  
**Relevance Score:** {{ "%.1f"|format(paper.relevance_score) }}/10  
**arXiv ID:** [{{ paper.arxiv_id }}]({{ paper.pdf_url }})

{{ paper.digest }}

{% if paper.tags %}
**Tags:** {{ paper.tags|join(', ') }}
{% endif %}

---

{% endfor %}

{% if not papers %}
*No relevant papers found in this digest.*
{% endif %}
"""
    
    template = Template(template_str)
    return template.render(**topic_data)


def save_markdown_digest(topic: Topic, paper_links: List[PaperTopicLink], output_path: Path = None) -> Path:
    """Generate and save markdown digest to file."""
    if output_path is None:
        output_path = Path(f"digest_{topic.name.replace(' ', '_').lower()}_{topic.id}.md")
    
    markdown_content = generate_markdown_digest(topic, paper_links)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(markdown_content)
    
    return output_path


def generate_html_digest(topic: Topic, paper_links: List[PaperTopicLink]) -> str:
    """Generate an HTML digest for a topic."""
    
    papers_data = []
    for link in paper_links:
        paper_data = {
            "title": link.paper.title,
            "authors": link.paper.authors,
            "published_date": link.paper.published_at.strftime("%Y-%m-%d"),
            "relevance_score": link.relevance_score,
            "digest": link.digest or "",
            "tags": eval(link.tags) if link.tags else [],
            "pdf_url": link.paper.pdf_url,
            "arxiv_id": link.paper.id
        }
        papers_data.append(paper_data)
    
    topic_data = {
        "name": topic.name,
        "description": topic.description,
        "papers": papers_data,
        "generated_date": paper_links[0].created_at.strftime("%Y-%m-%d %H:%M") if paper_links else "Unknown"
    }
    
    template_str = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Research Digest: {{ name }}</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }
        .header { border-bottom: 2px solid #e1e5e9; padding-bottom: 20px; margin-bottom: 30px; }
        .paper { border: 1px solid #e1e5e9; border-radius: 8px; padding: 20px; margin-bottom: 20px; background: #f8f9fa; }
        .paper h3 { color: #2c3e50; margin-top: 0; }
        .meta { color: #6c757d; font-size: 0.9em; margin-bottom: 15px; }
        .relevance { background: #28a745; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.8em; }
        .digest { margin: 15px 0; }
        .tags { margin-top: 15px; }
        .tag { background: #007bff; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.8em; margin-right: 5px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Research Digest: {{ name }}</h1>
        <p><strong>Description:</strong> {{ description }}</p>
        <p><em>Generated on: {{ generated_date }}</em></p>
    </div>

    {% for paper in papers %}
    <div class="paper">
        <h3>{{ loop.index }}. {{ paper.title }}</h3>
        <div class="meta">
            <p><strong>Authors:</strong> {{ paper.authors }}<br>
            <strong>Published:</strong> {{ paper.published_date }}<br>
            <strong>arXiv ID:</strong> <a href="{{ paper.pdf_url }}">{{ paper.arxiv_id }}</a><br>
            <span class="relevance">Relevance: {{ "%.1f"|format(paper.relevance_score) }}/10</span></p>
        </div>
        <div class="digest">
            {{ paper.digest|nl2br }}
        </div>
        {% if paper.tags %}
        <div class="tags">
            {% for tag in paper.tags %}
            <span class="tag">{{ tag }}</span>
            {% endfor %}
        </div>
        {% endif %}
    </div>
    {% endfor %}

    {% if not papers %}
    <div class="paper">
        <p>No relevant papers found in this digest.</p>
    </div>
    {% endif %}
</body>
</html>
"""
    
    template = Template(template_str)
    html_content = template.render(**topic_data)
    
    # Add nl2br filter for digest content
    html_content = html_content.replace('|nl2br', '')
    html_content = html_content.replace('{{ paper.digest|nl2br }}', '{{ paper.digest|replace("\\n", "<br>") }}')
    
    template = Template(html_content)
    return template.render(**topic_data)