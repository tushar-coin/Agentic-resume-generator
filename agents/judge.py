from __future__ import annotations

import json
from typing import Any

from models.llm import call_llm
from utils.prompt_loader import build_agent_messages
from utils.json_utils import JsonOutputError, parse_json_with_retry


JUDGE_FALLBACK = {
    "valid": False,
    "issues": ["judge_evaluation_failed"],
}


def validate_judge_schema(data: dict[str, Any]) -> dict[str, Any]:
    """Validate judge JSON output schema."""
    missing = {"valid", "issues"} - data.keys()
    if missing:
        raise JsonOutputError(f"Missing judge fields: {sorted(missing)}")

    if not isinstance(data["valid"], bool):
        raise JsonOutputError("judge.valid must be boolean")
    if not isinstance(data["issues"], list) or not all(
        isinstance(item, str) for item in data["issues"]
    ):
        raise JsonOutputError("judge.issues must be a list of strings")

    return {
        "valid": data["valid"],
        "issues": data["issues"],
    }


def judge_project_and_skills(
    job_data: dict[str, Any],
    selected_project: dict[str, Any],
    languages: list[str],
    technologies: list[str],
) -> dict[str, object]:
    """
    Validate whether selected project and skills match job requirements.
    
    This replaces the old judge_resume which evaluated full LaTeX resume.
    Now we only evaluate:
    - Job description
    - Selected project relevance
    - Extracted skills alignment
    
    Args:
        job_data: Structured job description
        selected_project: Selected project from project pool
        languages: Extracted programming languages
        technologies: Extracted frameworks/tools
    
    Returns:
        {"valid": bool, "issues": [str]}
    """
    messages = build_agent_messages(
        "judge",
        job_data=json.dumps(job_data, indent=2),
        selected_project=json.dumps(selected_project, indent=2),
        languages=", ".join(languages) if languages else "None",
        technologies=", ".join(technologies) if technologies else "None",
    )
    
    result = parse_json_with_retry(
        messages=messages,
        call_llm=call_llm,
        validate=validate_judge_schema,
        fallback=JUDGE_FALLBACK,
        debug_name="judge",
    )
    
    # Add validation for non-empty skills
    if not languages and not technologies:
        result["issues"].append("no_skills_extracted")
        result["valid"] = False
    
    print(f"DEBUG judge: valid={result['valid']}, issues={result['issues']}")
    return result
