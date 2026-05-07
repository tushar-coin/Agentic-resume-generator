"""LaTeX resume renderer - fills template with project and skills data."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def escape_latex(text: str) -> str:
    """Escape special LaTeX characters in text.
    
    IMPORTANT: Process backslash FIRST to avoid double-escaping.
    E.g., if we escape # first to \#, then \\ to \textbackslash{},
    we'd end up with \textbackslash{}# instead of \#.
    """
    text = str(text)
    
    # MUST do backslash first, before any other character that uses backslash
    text = text.replace("\\", r"\textbackslash{}")
    
    # Now safe to escape other characters
    replacements = {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\^{}",
    }
    
    for char, escaped in replacements.items():
        text = text.replace(char, escaped)
    
    return text


def format_project_bullets(bullets: list[str]) -> str:
    """
    Format project bullets as LaTeX itemize.
    
    Example output:
    \\resumeItemListStart
    \\resumeItem{bullet 1}
    \\resumeItem{bullet 2}
    \\resumeItemListEnd
    """
    if not bullets:
        return ""
    
    items = "\n".join(
        f"\\resumeItem{{{escape_latex(bullet)}}}"
        for bullet in bullets
    )
    
    return f"\\resumeItemListStart\n{items}\n\\resumeItemListEnd"


def render_resume(
    template_path: str | None = None,
    output_path: str = "",
    project: dict[str, Any] | None = None,
    languages: list[str] | None = None,
    technologies: list[str] | None = None,
) -> str:
    """
    Render final resume by filling template with project and skills.
    
    Args:
        template_path: Path to LaTeX template file (e.g., resume_template.tex)
        output_path: Path to write final resume
        project: Project dict with id, name, tech, date, bullets
        languages: List of programming languages
        technologies: List of frameworks/tools
    
    Returns:
        Rendered resume LaTeX content.
    """
    from config.settings import RESUME_TEMPLATE_PATH
    
    if not template_path:
        template_path = str(RESUME_TEMPLATE_PATH)
    
    if not Path(template_path).exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    
    # Read template
    with open(template_path, "r") as f:
        content = f.read()
    
    # Extract text content from project dict
    project = project or {}
    project_name = project.get("name", "")
    project_tech = ", ".join(project.get("tech", []) or project.get("latex_tech", []))
    project_date = project.get("date", "")
    project_bullets = project.get("bullets", []) or project.get("latex_bullets", [])
    
    # Format bullets
    bullets_latex = format_project_bullets(project_bullets)
    
    # Format skills
    languages = languages or []
    technologies = technologies or []
    languages_str = ", ".join(languages) if languages else ""
    technologies_str = ", ".join(technologies) if technologies else ""
    
    # Replace placeholders
    # NOTE: Use str.replace for static placeholders to avoid backslash interpretation
    # in re.sub. re.sub treats backslashes in replacement as escape sequences.
    replacements = {
        "{{PROJECT_NAME}}": escape_latex(project_name),
        "{{PROJECT_TECH}}": escape_latex(project_tech),
        "{{PROJECT_DATE}}": escape_latex(project_date),
        "{{PROJECT_BULLETS}}": bullets_latex,
        "{{SKILLS_LANGUAGES}}": escape_latex(languages_str),
        "{{SKILLS_TECHNOLOGIES}}": escape_latex(technologies_str),
    }
    
    # Apply replacements using str.replace (safer for LaTeX backslashes)
    for placeholder, replacement in replacements.items():
        content = content.replace(placeholder, replacement)
    
    # Write output
    with open(output_path, "w") as f:
        f.write(content)
    
    return content


def validate_template(template_path: str) -> dict[str, Any]:
    """
    Validate that template has all required placeholders.
    
    Returns dict with validation results.
    """
    with open(template_path, "r") as f:
        content = f.read()
    
    required_placeholders = [
        "{{PROJECT_NAME}}",
        "{{PROJECT_TECH}}",
        "{{PROJECT_DATE}}",
        "{{PROJECT_BULLETS}}",
        "{{SKILLS_LANGUAGES}}",
        "{{SKILLS_TECHNOLOGIES}}",
    ]
    
    missing = [p for p in required_placeholders if p not in content]
    
    return {
        "valid": len(missing) == 0,
        "missing_placeholders": missing,
    }
