from __future__ import annotations


REQUIRED_RESUME_SECTIONS = [
    "summary",
    "skills",
    "experience",
    "projects",
    "education",
]


def has_markdown_heading(text: str, section: str) -> bool:
    """
    Check if a section heading exists in the resume text.
    Supports both markdown (#) and LaTeX (\section{}) formats.
    
    Args:
        text: Resume content in markdown or LaTeX format.
        section: Section name to search for.
        
    Returns:
        bool: True if section heading is found.
    """
    target = section.lower()
    for line in text.splitlines():
        stripped = line.strip().lower()
        
        # Check for markdown heading (# Section)
        if stripped.startswith("#") and target in stripped:
            return True
        
        # Check for LaTeX section (\section{Section})
        if "\\section{" in stripped and target in stripped:
            return True
    
    return False
