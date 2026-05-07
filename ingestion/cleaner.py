from __future__ import annotations


JUNK_KEYWORDS = {
    "alert",
    "blog",
    "cookie",
    "privacy",
    "saved jobs",
    "search jobs",
    "share this job",
    "sign up",
    "terms of use",
}


def clean_text(text: str) -> str:
    """Keep meaningful content lines and remove common site chrome."""
    cleaned_lines: list[str] = []

    for raw_line in text.splitlines():
        line = " ".join(raw_line.strip().split())
        if len(line) <= 40:
            continue
        if any(keyword in line.lower() for keyword in JUNK_KEYWORDS):
            continue
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    print(f"DEBUG cleaner: kept {len(cleaned_lines)} lines")
    return cleaned
