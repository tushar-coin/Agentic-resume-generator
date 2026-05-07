from __future__ import annotations

import json
from typing import Any

from models.llm import call_llm
from utils.prompt_loader import build_agent_messages
from utils.json_utils import JsonOutputError, parse_json_with_retry


BUILDER_FALLBACK = {
    "project_id": None,
    "languages": [],
    "technologies": [],
}


def validate_builder_schema(data: dict[str, Any]) -> dict[str, Any]:
    """Validate resume builder JSON output schema."""
    missing = {"project_id", "languages", "technologies"} - data.keys()
    if missing:
        raise JsonOutputError(f"Missing builder fields: {sorted(missing)}")

    if not isinstance(data["project_id"], str) or not data["project_id"].strip():
        raise JsonOutputError("project_id must be non-empty string")
    
    if not isinstance(data["languages"], list):
        raise JsonOutputError("languages must be an array")
    
    if not isinstance(data["technologies"], list):
        raise JsonOutputError("technologies must be an array")
    
    # Validate all items are strings
    if not all(isinstance(item, str) for item in data["languages"]):
        raise JsonOutputError("all languages must be strings")
    
    if not all(isinstance(item, str) for item in data["technologies"]):
        raise JsonOutputError("all technologies must be strings")
    
    return {
        "project_id": data["project_id"].strip(),
        "languages": [s.strip() for s in data["languages"] if s.strip()],
        "technologies": [s.strip() for s in data["technologies"] if s.strip()],
    }


def select_project_fallback(
    job_data: dict[str, Any],
    projects: list[dict[str, Any]]
) -> str:
    """
    Fallback project selector using rule-based scoring.
    Matches job skills with project technologies.
    """
    if not projects:
        return None
    
    job_skills = set()
    job_skills.update(s.lower() for s in job_data.get("skills", []))
    job_skills.update(s.lower() for s in job_data.get("tools", []))
    
    best_project = None
    best_score = -1
    
    for project in projects:
        tech = set()
        tech.update(t.lower() for t in project.get("tech", []))
        tech.update(t.lower() for t in project.get("latex_tech", []))
        
        # Calculate overlap score
        overlap = len(job_skills & tech)
        
        if overlap > best_score:
            best_score = overlap
            best_project = project["id"]
    
    return best_project or projects[0]["id"]


def build_resume(
    job_data: dict[str, Any],
    resume_data: str,
    validation: dict[str, Any],
    candidate_profile: dict[str, Any] | None = None,
    previous_issues: list[str] | None = None,
) -> dict[str, Any]:
    """
    Generate structured resume decision (project + skills).
    Returns JSON only, no LaTeX generation.
    
    Returns:
        {
            "project_id": "...",
            "languages": [...],
            "technologies": [...]
        }
    """
    # Load projects JSON
    try:
        with open("data/project_data.json", "r") as f:
            projects_data = json.load(f)
            projects_list = projects_data.get("projects", [])
    except Exception as e:
        print(f"DEBUG builder: failed to load projects_json: {e}")
        projects_list = []
    
    messages = build_agent_messages(
        "resume_builder",
        job_data=json.dumps(job_data, indent=2),
        candidate_profile=json.dumps(candidate_profile or {}, indent=2),
        projects_json=json.dumps(projects_data, indent=2),
        validation=json.dumps(validation, indent=2),
        issues_text="\n".join(previous_issues or []),  # Convert list to string
        resume_data=resume_data,  # No longer needed for JSON mode
    )
    
    result = parse_json_with_retry(
        messages=messages,
        call_llm=call_llm,
        validate=validate_builder_schema,
        fallback=BUILDER_FALLBACK,
        debug_name="resume_builder",
    )
    
    # Validate selected project exists
    project_id = result.get("project_id")
    if project_id and not any(p["id"] == project_id for p in projects_list):
        print(f"DEBUG builder: project_id '{project_id}' not found, using fallback")
        project_id = select_project_fallback(job_data, projects_list)
    
    if not project_id:
        # Fallback to first project if available
        project_id = projects_list[0]["id"] if projects_list else None
    
    result["project_id"] = project_id
    
    print(f"DEBUG builder: selected project={project_id}, languages={result['languages']}, tech={result['technologies']}")
    return result
