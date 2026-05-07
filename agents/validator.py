from __future__ import annotations

import json
from typing import Any

from models.llm import call_llm
from utils.prompt_loader import build_agent_messages
from utils.json_utils import JsonOutputError, parse_json_with_retry


VALIDATOR_FALLBACK = {
    "eligible": False,
    "score": 0.0,
    "missing_skills": ["invalid_input"],
}


def validate_validator_schema(data: dict[str, Any]) -> dict[str, Any]:
    missing = {"eligible", "score", "missing_skills"} - data.keys()
    if missing:
        raise JsonOutputError(f"Missing validator fields: {sorted(missing)}")

    if not isinstance(data["eligible"], bool):
        raise JsonOutputError("validator.eligible must be boolean")
    if not isinstance(data["score"], int | float):
        raise JsonOutputError("validator.score must be number")
    if not isinstance(data["missing_skills"], list) or not all(
        isinstance(item, str) for item in data["missing_skills"]
    ):
        raise JsonOutputError("validator.missing_skills must be a list of strings")

    return {
        "eligible": data["eligible"],
        "score": float(data["score"]),
        "missing_skills": data["missing_skills"],
    }


def validate_candidate(job_data: dict[str, Any], candidate_profile: dict[str, Any]) -> dict[str, Any]:
    messages = build_agent_messages(
        "validator",
        job_data=json.dumps(job_data, indent=2),
        resume_data=json.dumps(candidate_profile, indent=2),
    )
    result = parse_json_with_retry(
        messages=messages,
        call_llm=call_llm,
        validate=validate_validator_schema,
        fallback=VALIDATOR_FALLBACK,
        debug_name="validator",
    )
    print(f"DEBUG validator: {result}")
    return result
