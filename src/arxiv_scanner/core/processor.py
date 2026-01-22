"""Core processing: Relevance evaluation and summarization in one step."""

import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert research assistant. Your task is to evaluate if an academic paper is relevant to a researcher's interests and, if so, provide a concise summary.

You will be given:
1. The researcher's topic of interest
2. A paper title and abstract

Your response must be a valid JSON object with these fields:
{
  "is_relevant": <boolean>,
  "relevance_score": <float from 0.0 to 10.0>,
  "reasoning": "<brief explanation of relevance>",
  "summary": {
    "tldr": "<one sentence summary>",
    "key_contribution": "<main finding in 1-2 sentences>",
    "tags": ["<tag1>", "<tag2>", "<tag3>"]
  }
}

If the paper is NOT relevant (is_relevant is false), you can leave the 'summary' fields with empty strings or empty lists.
Scoring: 8-10 is highly relevant, 5-7 is potentially relevant, <5 is not relevant."""

def process_paper(
    paper_title: str,
    paper_abstract: str,
    topic_description: str,
    llm_provider
) -> Dict[str, Any]:
    """Evaluate and summarize a paper in a single LLM call."""
    prompt = f"""Topic: {topic_description}
Title: {paper_title}
Abstract: {paper_abstract}

Evaluate relevance and summarize if applicable."""

    try:
        response = llm_provider.generate(prompt, system_prompt=SYSTEM_PROMPT)
        
        # Basic JSON extraction
        content = response.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        result = json.loads(content)
        
        # Ensure default structure
        if "is_relevant" not in result:
            result["is_relevant"] = result.get("relevance_score", 0) >= 7.0
            
        return result
    except Exception as e:
        logger.error(f"Error processing paper: {e}")
        return {
            "is_relevant": False,
            "relevance_score": 0,
            "reasoning": f"Error: {e}",
            "summary": {"tldr": "", "key_contribution": "", "tags": []}
        }
