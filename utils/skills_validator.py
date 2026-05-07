"""Skills validation and cleaning utilities."""

from __future__ import annotations

import re
from typing import Any


# Soft skills and generic terms to exclude
INVALID_SKILLS = {
    # Soft skills
    "problem-solving",
    "problem solving",
    "teamwork",
    "team player",
    "communication",
    "collaboration",
    "collaboration skills",
    "leadership",
    "negotiation",
    "time management",
    "attention to detail",
    # Generic tech terms
    "scalable",
    "scalability",
    "high-performance",
    "performance",
    "modern",
    "innovative",
    "innovation",
    "efficient",
    "efficiency",
    "quality",
    "best practices",
    "agile",
    "agile development",
    "cloud",
    "cloud-native",
    "microservices",  # Often used as vague term
    "api",  # Use "REST APIs" instead
    "rest",
    "distributed",
    "production-ready",
    # Non-technical
    "learning",
    "research",
    "development",
    "process",
    "approach",
}

# Programming languages to recognize
KNOWN_LANGUAGES = {
    "python",
    "java",
    "javascript",
    "typescript",
    "go",
    "rust",
    "c++",
    "c",
    "cpp",
    "c#",
    "csharp",
    "ruby",
    "php",
    "swift",
    "kotlin",
    "scala",
    "haskell",
    "clojure",
    "elixir",
    "erlang",
    "r",
    "matlab",
    "julia",
    "groovy",
    "perl",
    "lua",
    "dart",
    "ocaml",
    "f#",
    "fsharp",
    "lisp",
    "scheme",
}

# Technology categories to recognize
KNOWN_TECHS = {
    # Frameworks & Libraries
    "react",
    "angular",
    "vue",
    "vue.js",
    "next.js",
    "next",
    "nuxt",
    "svelte",
    "ember",
    "backbone",
    "jquery",
    "express",
    "fastapi",
    "django",
    "flask",
    "rails",
    "spring",
    "spring boot",
    "spring-boot",
    "asp.net",
    "asp",
    ".net",
    "dotnet",
    "laravel",
    "symphony",
    "wordpress",
    "drupal",
    # Data & Databases
    "sql",
    "mysql",
    "postgresql",
    "postgres",
    "mongodb",
    "cassandra",
    "redis",
    "elasticsearch",
    "dynamodb",
    "firestore",
    "oracle",
    "sqlite",
    "mariadb",
    "influxdb",
    "timescaledb",
    "neo4j",
    # Cloud & Infrastructure
    "aws",
    "azure",
    "gcp",
    "google cloud",
    "heroku",
    "vercel",
    "netlify",
    "digitalocean",
    "linode",
    # DevOps & Tools
    "docker",
    "kubernetes",
    "k8s",
    "jenkins",
    "gitlab",
    "gitlab ci",
    "github actions",
    "terraform",
    "ansible",
    "vagrant",
    "prometheus",
    "grafana",
    "datadog",
    "consul",
    "vault",
    # Message Queues & Streaming
    "kafka",
    "rabbitmq",
    "redis",
    "kinesis",
    "nats",
    # APIs & Protocols
    "rest apis",
    "rest",
    "graphql",
    "websockets",
    "grpc",
    "soap",
    "mqtt",
    # Other Important Tech
    "git",
    "ci/cd",
    "http/2",
    "xml",
    "json",
    "yaml",
    "protobuf",
    "jwt",
    "oauth",
    "ssl",
    "ssl/tls",
    "tls",
}


def is_valid_skill(skill: str) -> bool:
    """Check if skill is valid (not a soft skill or generic term)."""
    skill_lower = skill.strip().lower()
    
    # Check against invalid list
    if skill_lower in INVALID_SKILLS:
        return False
    
    # Check if it's just a generic word
    if len(skill_lower) < 2:
        return False
    
    # Contains "skill" or similar meta-terms
    if "skill" in skill_lower or "ability" in skill_lower:
        return False
    
    return True


def categorize_skill(skill: str) -> str | None:
    """
    Categorize skill as language or technology.
    Returns 'language' or 'technology' or None if invalid.
    """
    skill_lower = skill.strip().lower()
    
    if not is_valid_skill(skill):
        return None
    
    if skill_lower in KNOWN_LANGUAGES:
        return "language"
    
    if skill_lower in KNOWN_TECHS:
        return "technology"
    
    # Try to match with fuzzy logic for slightly modified terms
    # e.g., "REST API" vs "REST APIs"
    normalized = re.sub(r"s$", "", skill_lower)  # Remove trailing 's'
    if normalized in KNOWN_TECHS:
        return "technology"
    
    # If not in known list, default to technology
    # (LLM should have filtered, so unknown valid skills are likely tech)
    return "technology"


def validate_and_separate_skills(
    languages: list[str],
    technologies: list[str]
) -> tuple[list[str], list[str]]:
    """
    Validate and separate skills, removing invalid ones.
    
    Returns:
        (valid_languages, valid_technologies)
    """
    valid_languages = []
    valid_technologies = []
    
    # Clean and validate languages
    for lang in languages:
        if is_valid_skill(lang):
            category = categorize_skill(lang)
            if category == "language":
                valid_languages.append(lang.strip())
            elif category == "technology":
                # Misclassified as language but valid tech
                valid_technologies.append(lang.strip())
    
    # Clean and validate technologies
    for tech in technologies:
        if is_valid_skill(tech):
            category = categorize_skill(tech)
            if category == "technology":
                valid_technologies.append(tech.strip())
            elif category == "language":
                # Misclassified as tech but valid language
                valid_languages.append(tech.strip())
    
    # Remove duplicates while preserving order
    valid_languages = list(dict.fromkeys(valid_languages))
    valid_technologies = list(dict.fromkeys(valid_technologies))
    
    return valid_languages, valid_technologies


def validate_builder_result(result: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate builder result before rendering.
    
    Returns:
        (is_valid, list_of_issues)
    """
    issues = []
    
    # Check required fields
    if not result.get("project_id"):
        issues.append("missing_project_id")
    
    languages = result.get("languages", [])
    technologies = result.get("technologies", [])
    
    if not languages:
        issues.append("no_languages_extracted")
    
    if not technologies:
        issues.append("no_technologies_extracted")
    
    # Validate skills aren't empty after cleaning
    valid_langs, valid_techs = validate_and_separate_skills(languages, technologies)
    
    if not valid_langs and not valid_techs:
        issues.append("no_valid_skills_after_cleaning")
    
    return len(issues) == 0, issues
