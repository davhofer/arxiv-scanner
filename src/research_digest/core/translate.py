"""Topic translation: Natural language to arXiv query string."""

import arxiv
from tenacity import retry, stop_after_attempt, retry_if_exception_type

from research_digest.llm.provider import LLMProvider


class QueryValidationError(Exception):
    """Raised when generated query fails validation."""

    pass


# TODO: can we improve this translation query?

SYSTEM_PROMPT = """You are an expert in the arXiv API query syntax.
Convert the user's research topic into a SINGLE line raw query string.

Syntax Rules:
- Fields: ti (Title), abs (Abstract), cat (Category), au (Author).
- Operators: AND, OR, ANDNOT.
- Grouping: Use parentheses (...) for logic.
- Exact phrases: Use double quotes "..." for multi-word terms.

Common Categories:
- cs.AI (Artificial Intelligence), cs.CL (Computation & Language), cs.LG (Machine Learning)
- cs.SE (Software Eng), stat.ML (Machine Learning), cs.CV (Computer Vision)

Example:
User: "Large language models for medical diagnosis"
Output: (ti:"large language model" OR abs:"large language model" OR ti:LLM) AND (ti:medical OR abs:diagnosis) AND (cat:cs.CL OR cat:cs.AI)

Return ONLY the query string. No markdown, no explanations."""


@retry(stop=stop_after_attempt(3), retry=retry_if_exception_type(QueryValidationError))
def generate_valid_query(topic_description: str, llm_provider: LLMProvider) -> str:
    """Generate a valid arXiv query string from natural language description."""

    # Generate query using LLM
    raw_query = llm_provider.generate(topic_description, system_prompt=SYSTEM_PROMPT)

    # Validate query by testing with arXiv API
    try:
        client = arxiv.Client()
        search = arxiv.Search(query=raw_query, max_results=1)
        # Try to get one result to validate the query
        next(client.results(search), None)
    except Exception as e:
        raise QueryValidationError(f"Arxiv API rejected query: {e}")

    return raw_query.strip()


def translate_topic(topic_description: str, llm_provider) -> str:
    """Translate a natural language topic description into a validated arXiv query."""
    return generate_valid_query(topic_description, llm_provider)

