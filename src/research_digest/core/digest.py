"""Summarization of relevant papers."""

import json
from typing import Dict, Any

from research_digest.llm.provider import LLMProvider


SYSTEM_PROMPT = """You are an expert research summarizer. Your task is to create concise, informative summaries of academic papers for researchers.

Focus on extracting the most important information that would help a researcher quickly understand:
1. What the paper is about in one sentence
2. The key contribution or finding
3. The methodology used
4. Relevant keywords/tags for categorization

Your response must be a valid JSON object with these fields:
{
  "tldr": "<one sentence summary>",
  "key_contribution": "<main contribution or finding in 2-3 sentences>",
  "methodology": "<brief description of methods used in 2-3 sentences>",
  "tags": ["<keyword1>", "<keyword2>", "<keyword3>", "<keyword4>", "<keyword5>"]
}

Keep summaries concise but informative. Focus on what makes this paper unique or valuable."""


def summarize_paper(
    paper_title: str,
    paper_abstract: str,
    llm_provider: LLMProvider
) -> Dict[str, Any]:
    """Generate a summary of a paper.
    
    Returns:
        Dictionary with tldr, key_contribution, methodology, and tags
    """
    prompt = f"""Paper Title: "{paper_title}"

Paper Abstract: "{paper_abstract}"

Create a comprehensive summary of this paper and return your response as JSON.""" 
    
    try:
        response = llm_provider.generate(prompt, system_prompt=SYSTEM_PROMPT)
        
        # Try to parse JSON response
        try:
            # Handle JSON wrapped in markdown code blocks
            if response.strip().startswith('```json'):
                # Extract JSON from between ```json and ```
                lines = response.strip().split('\n')
                if len(lines) >= 3:
                    json_content = '\n'.join(lines[1:-1]).strip()
                    result = json.loads(json_content)
                else:
                    result = json.loads(response)
            elif response.strip().startswith('```') and response.strip().endswith('```'):
                # Extract JSON from generic code blocks
                lines = response.strip().split('\n')
                if len(lines) >= 2:
                    json_content = '\n'.join(lines[1:-1]).strip()
                    result = json.loads(json_content)
                else:
                    result = json.loads(response)
            else:
                result = json.loads(response)
            
            # Ensure required fields are present
            if not all(key in result for key in ["tldr", "key_contribution", "methodology", "tags"]):
                raise ValueError("Missing required fields in response")
            
            # Validate and clean up the response
            result["tldr"] = str(result["tldr"]).strip()
            result["key_contribution"] = str(result["key_contribution"]).strip()
            result["methodology"] = str(result["methodology"]).strip()
            
            # Ensure tags is a list of strings
            tags = result["tags"]
            if isinstance(tags, str):
                # If it's a string, try to parse as JSON list
                try:
                    tags = json.loads(tags)
                except:
                    # If that fails, split by common separators
                    tags = [tag.strip() for tag in tags.replace(',', ';').split(';') if tag.strip()]
            elif not isinstance(tags, list):
                tags = [str(tags)]
            
            # Clean up tags and limit to 5
            result["tags"] = [str(tag).strip().lower() for tag in tags[:5] if str(tag).strip()]
            
            return result
            
        except json.JSONDecodeError:
            # If JSON parsing fails, create a default response
            return {
                "tldr": "Failed to generate summary",
                "key_contribution": "Unable to extract key contribution due to parsing error",
                "methodology": "Unable to extract methodology due to parsing error",
                "tags": ["error", "parsing-failed"]
            }
            
    except Exception as e:
        # If anything goes wrong, return a safe default
        return {
            "tldr": "Error generating summary",
            "key_contribution": f"Error during summarization: {str(e)}",
            "methodology": "Unable to extract methodology due to error",
            "tags": ["error", "generation-failed"]
        }