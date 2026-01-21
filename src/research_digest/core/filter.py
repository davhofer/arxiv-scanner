"""Accurate filtering: LLM-based relevance determination."""

import json
from typing import Dict, Any

from research_digest.llm.provider import LLMProvider


SYSTEM_PROMPT = """You are an expert research assistant. Your task is to determine if a paper is relevant to a researcher's interests.

You will be given:
1. The researcher's topic of interest
2. A paper title and abstract

Your response must be a valid JSON object with these fields:
{
  "relevance_score": <float from 0.0 to 10.0>,
  "is_relevant": <boolean>,
  "reasoning": "<brief explanation in one sentence>"
}

Scoring guidelines:
- 8.0-10.0: Highly relevant, directly addresses the research topic
- 5.0-7.9: Moderately relevant, tangential but potentially useful
- 0.0-4.9: Not relevant, outside the scope of interest

Consider:
- Does the paper directly address the research topic?
- Are the methods and findings applicable to the researcher's interests?
- Is this paper something the researcher would want to read?

Be precise and objective in your assessment."""


def filter_paper(
    paper_title: str,
    paper_abstract: str,
    topic_description: str,
    llm_provider: LLMProvider
) -> Dict[str, Any]:
    """Determine if a paper is relevant to a research topic.
    
    Returns:
        Dictionary with relevance_score, is_relevant, and reasoning
    """
    prompt = f"""Research Topic: "{topic_description}"

Paper Title: "{paper_title}"

Paper Abstract: "{paper_abstract}"

Evaluate the relevance of this paper to the research topic and return your assessment as JSON.""" 
    
    try:
        response = llm_provider.generate(prompt, system_prompt=SYSTEM_PROMPT)
        
        # Try to parse JSON response
        try:
            result = json.loads(response)
            
            # Ensure required fields are present
            if not all(key in result for key in ["relevance_score", "is_relevant", "reasoning"]):
                raise ValueError("Missing required fields in response")
            
            # Validate and clean up the response
            result["relevance_score"] = float(result["relevance_score"])
            result["is_relevant"] = bool(result["is_relevant"])
            result["reasoning"] = str(result["reasoning"]).strip()
            
            return result
            
        except json.JSONDecodeError:
            # If JSON parsing fails, create a default response
            return {
                "relevance_score": 0.0,
                "is_relevant": False,
                "reasoning": "Failed to parse LLM response as valid JSON"
            }
            
    except Exception as e:
        # If anything goes wrong, return a safe default
        return {
            "relevance_score": 0.0,
            "is_relevant": False,
            "reasoning": f"Error during filtering: {str(e)}"
        }