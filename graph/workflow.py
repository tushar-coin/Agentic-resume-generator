from __future__ import annotations

import json
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.judge import judge_project_and_skills
from agents.resume_builder import build_resume
from agents.validator import validate_candidate
from config.settings import MAX_JUDGE_RETRIES, OUTPUT_RESUME_PATH, RESUME_PATH, RESUME_TEMPLATE_PATH
from utils.latex_renderer import render_resume
from utils.skills_validator import validate_and_separate_skills, validate_builder_result


class ResumeGraphState(TypedDict, total=False):
    job_data: dict[str, Any]
    resume_data: str
    structured_jd: dict[str, Any]
    validation: dict[str, Any]
    generated_resume: str
    judge_result: dict[str, Any]
    iteration_count: int
    candidate_profile: Any
    builder_result: dict[str, Any]  # New: structured JSON from builder
    selected_project: dict[str, Any]  # New: resolved project data


def load_project_from_pool(project_id: str) -> dict[str, Any] | None:
    """Load project data from project_data.json."""
    try:
        with open("data/project_data.json", "r") as f:
            data = json.load(f)
            projects = data.get("projects", [])
            for p in projects:
                if p.get("id") == project_id:
                    return p
    except Exception as e:
        print(f"DEBUG workflow: failed to load project {project_id}: {e}")
    return None


def validator_node(state: ResumeGraphState) -> ResumeGraphState:
    validation = validate_candidate(state["structured_jd"], state["candidate_profile"])
    return {**state, "validation": validation}


def builder_node(state: ResumeGraphState) -> ResumeGraphState:
    """Builder returns structured JSON with project_id + skills."""
    iteration_count = state.get("iteration_count", 0) + 1
    
    result = build_resume(
        job_data=state["structured_jd"],
        resume_data=state["resume_data"],
        validation=state["validation"],
        candidate_profile=state["candidate_profile"],
    )
    
    # Validate result structure
    is_valid, issues = validate_builder_result(result)
    if not is_valid:
        print(f"DEBUG workflow: builder result validation failed: {issues}")
        result["validation_issues"] = issues
    
    # Clean and validate skills
    languages = result.get("languages", [])
    technologies = result.get("technologies", [])
    clean_langs, clean_techs = validate_and_separate_skills(languages, technologies)
    
    result["languages"] = clean_langs
    result["technologies"] = clean_techs
    
    return {**state, "builder_result": result, "iteration_count": iteration_count}


def renderer_node(state: ResumeGraphState) -> ResumeGraphState:
    """Load project and render final LaTeX resume from template."""
    builder_result = state.get("builder_result", {})
    project_id = builder_result.get("project_id")
    
    if not project_id:
        print("DEBUG workflow: no project_id from builder, cannot render")
        return state
    
    # Load project from pool
    project = load_project_from_pool(project_id)
    if not project:
        print(f"DEBUG workflow: project {project_id} not found in pool")
        return state
    
    # Render LaTeX
    try:
        languages = builder_result.get("languages", [])
        technologies = builder_result.get("technologies", [])
        
        if not languages and not technologies:
            print("DEBUG workflow: no valid skills after cleaning, cannot render")
            return state
        
        generated_resume = render_resume(
            template_path=str(RESUME_TEMPLATE_PATH),
            output_path=str(OUTPUT_RESUME_PATH),
            project=project,
            languages=languages,
            technologies=technologies,
        )
        print(f"DEBUG workflow: rendered resume to {OUTPUT_RESUME_PATH}")
        
        return {
            **state,
            "selected_project": project,
            "generated_resume": generated_resume,
        }
    except Exception as e:
        print(f"DEBUG workflow: failed to render resume: {e}")
        return state


def judge_node(state: ResumeGraphState) -> ResumeGraphState:
    """Judge validates project + skills alignment."""
    builder_result = state.get("builder_result", {})
    selected_project = state.get("selected_project", {})
    
    if not selected_project:
        return {**state, "judge_result": {"valid": False, "issues": ["no_project_rendered"]}}
    
    result = judge_project_and_skills(
        job_data=state["structured_jd"],
        selected_project=selected_project,
        languages=builder_result.get("languages", []),
        technologies=builder_result.get("technologies", []),
    )
    
    return {**state, "judge_result": result}


def route_after_validator(state: ResumeGraphState) -> str:
    if not state.get("validation", {}).get("eligible", False):
        print("DEBUG graph: candidate marked ineligible")
        return END
    return "builder"


def route_after_judge(state: ResumeGraphState) -> str:
    judge_result = state.get("judge_result", {})
    if judge_result.get("valid", False):
        print("DEBUG graph: judge accepted project + skills")
        return END
    if state.get("iteration_count", 0) < MAX_JUDGE_RETRIES:
        print("DEBUG graph: retrying builder")
        return "builder"
    print("DEBUG graph: max retries reached")
    return END


def build_workflow():
    graph = StateGraph(ResumeGraphState)
    graph.add_node("validator", validator_node)
    graph.add_node("builder", builder_node)
    graph.add_node("renderer", renderer_node)
    graph.add_node("judge", judge_node)

    graph.add_edge(START, "validator")
    graph.add_conditional_edges("validator", route_after_validator)
    graph.add_edge("builder", "renderer")
    graph.add_edge("renderer", "judge")
    graph.add_conditional_edges("judge", route_after_judge)

    return graph.compile()
