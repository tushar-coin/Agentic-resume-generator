from __future__ import annotations

from pathlib import Path
from typing import Any

PROMPT_ROOT = Path(__file__).resolve().parents[1] / "prompts"


def load_prompt(agent_name: str, role: str) -> str:
    prompt_file = PROMPT_ROOT / agent_name / f"{role}.txt"
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
    return prompt_file.read_text(encoding="utf-8").strip()


def format_prompt(template: str, /, **variables: Any) -> str:
    return template.format(**variables)


def build_agent_messages(agent_name: str, **variables: Any) -> list[dict[str, str]]:
    system_prompt = load_prompt(agent_name, "system")
    user_prompt = format_prompt(load_prompt(agent_name, "user"), **variables)

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
