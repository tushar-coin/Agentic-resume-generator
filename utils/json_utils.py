from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any


class JsonOutputError(ValueError):
    """Raised when an LLM response cannot be converted into valid schema JSON."""


def clean_json_output(raw: str) -> str:
    """Extract the first JSON object from a noisy LLM response."""
    text = raw.strip()
    text = re.sub(r"^```(?:json|JSON)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise JsonOutputError("No JSON object found in LLM output")

    candidate = text[start : end + 1]
    candidate = strip_json_line_comments(candidate)
    return candidate.strip()


def strip_json_line_comments(text: str) -> str:
    """Remove // comments while preserving // inside JSON strings."""
    output: list[str] = []
    in_string = False
    escaped = False
    index = 0

    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""

        if escaped:
            output.append(char)
            escaped = False
            index += 1
            continue

        if char == "\\" and in_string:
            output.append(char)
            escaped = True
            index += 1
            continue

        if char == '"':
            in_string = not in_string
            output.append(char)
            index += 1
            continue

        if not in_string and char == "/" and next_char == "/":
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue

        output.append(char)
        index += 1

    return "".join(output)


def parse_json_object(raw: str) -> dict[str, Any]:
    cleaned = clean_json_output(raw)
    try:
        parsed = json.loads(cleaned, strict=False)
        # 🔥 FIX: normalize BEFORE validation
        if isinstance(parsed, dict):
            exp = parsed.get("experience")

            if isinstance(exp, list):
                parsed["experience"] = " ".join(str(x) for x in exp)
            elif exp is None:
                parsed["experience"] = ""
    except json.JSONDecodeError as exc:
        raise JsonOutputError(f"Invalid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise JsonOutputError("JSON output must be an object")

    return parsed


def parse_json_with_retry(
    *,
    messages: list[dict[str, str]],
    call_llm: Callable[[list[dict[str, str]]], str],
    validate: Callable[[dict[str, Any]], dict[str, Any]],
    fallback: dict[str, Any],
    debug_name: str,
) -> dict[str, Any]:
    raw = call_llm(messages)
    try:
        return validate(parse_json_object(raw))
    except JsonOutputError as exc:
        print(f"DEBUG {debug_name}: JSON parse/validation failed: {exc}")
        print(f"DEBUG {debug_name}: raw response: {raw[:500]}")

    retry_messages = [
        *messages,
        {
            "role": "assistant",
            "content": raw,
        },
        {
            "role": "user",
            "content": (
                "Your previous output was invalid JSON. Fix it. "
                "Return ONLY valid JSON. Do not include markdown or explanations. "
                "The output must start with { and end with }."
            ),
        },
    ]
    retry_raw = call_llm(retry_messages)
    try:
        return validate(parse_json_object(retry_raw))
    except JsonOutputError as exc:
        print(f"DEBUG {debug_name}: retry JSON parse/validation failed: {exc}")
        print(f"DEBUG {debug_name}: retry raw response: {retry_raw[:500]}")
        return fallback
