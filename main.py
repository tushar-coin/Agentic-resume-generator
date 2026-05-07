from __future__ import annotations

import argparse
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse
from datetime import datetime

from config.settings import (
    DEFAULT_JOB_FILE,
    JOB_URLS_PATH,
    OUTPUT_RESUME_DIR,
    RESUME_PATH,
    STRUCTURE_JD_MAX_CHARS,
)
from graph.workflow import ResumeGraphState, build_workflow
from ingestion.chunker import chunk_text
from ingestion.cleaner import clean_text
from ingestion.scraper import scrape_job_description
from job_manager import load_job, load_jobs_by_run, save_job
from models.llm import call_llm
from run_manager import create_run_id
from utils.file_io import read_text, write_text
from utils.json_utils import JsonOutputError, parse_json_with_retry
from utils.post_generation import post_process_resume, send_generation_failure_whatsapp
from utils.prompt_loader import build_agent_messages
from vectorstore.chroma_db import add_document

# Required fields for job data validation
REQUIRED_JD_FIELDS = ["job_title", "skills", "responsibilities"]



STRUCTURE_JD_FALLBACK = {
    "company_name": "",
    "job_id": "",
    "job_title": "",
    "languages": [],
    "skills": [],
    "responsibilities": [],
    "tools": [],
    "experience": "",
    "important_details": [],
}


PROGRAMMING_LANGUAGE_PATTERNS = {
    "Java": r"\bJava\b",
    "Python": r"\bPython\b",
    "JavaScript": r"\b(?:JavaScript|Javascript|JS)\b",
    "TypeScript": r"\b(?:TypeScript|Typescript|TS)\b",
    "C++": r"(?<!\w)(?:C\+\+|CPP)(?!\w)",
    "C#": r"(?<!\w)(?:C#|CSharp|C-Sharp)(?!\w)",
    "Go": r"\b(?:Go|Golang)\b",
    "Rust": r"\bRust\b",
    "Swift": r"\bSwift\b",
    "Objective-C": r"\bObjective-C\b",
    "Kotlin": r"\bKotlin\b",
    "Ruby": r"\bRuby\b",
    "PHP": r"\bPHP\b",
    "Scala": r"\bScala\b",
}

TECHNOLOGY_PATTERNS = {
    "React": r"\bReact\b",
    "Next.js": r"\bNext\.?js\b",
    "Node.js": r"\bNode\.?js\b",
    "Spring Boot": r"\bSpring Boot\b",
    "Spring": r"\bSpring\b",
    "REST APIs": r"\bREST(?:ful)? APIs?\b",
    "WebSockets": r"\bWebSocket(?:s|-based)?\b",
    "GraphQL": r"\bGraphQL\b",
    "gRPC": r"\bgRPC\b",
    "AWS": r"\bAWS\b",
    "Docker": r"\bDocker\b",
    "Kubernetes": r"\bKubernetes|K8s\b",
    "CI/CD": r"\bCI/CD\b",
    "SQL": r"\bSQL\b",
    "NoSQL": r"\bNoSQL\b",
    "Android": r"\bAndroid\b",
    "iOS": r"\biOS\b",
    "HTML5": r"\bHTML5\b",
    "CSS3": r"\bCSS3\b",
    "Maya": r"\bMaya\b",
    "Blender": r"\bBlender\b",
    "Video Encoding": r"\bvideo encoding\b",
    "Streaming Media": r"\bstreaming media\b",
    "Distributed Systems": r"\bdistributed systems?\b",
    "Design Patterns": r"\bdesign patterns?\b",
    "System Design": r"\bsystem design\b",
    "Scalability": r"\bscal(?:e|ing|ability)\b",
    "Reliability": r"\breliability\b",
}


# --- Candidate profile extraction from LaTeX resume ---
def extract_candidate_profile(resume_text: str) -> dict[str, Any]:
    """
    Extract structured candidate profile from LaTeX resume.
    This reduces LLM input size and improves validator accuracy.
    """
    profile: dict[str, Any] = {
        "years_of_experience": 0,
        "skills": [],
        "roles": [],
        "education": {"degree": "", "year": None},
        "companies": [],
    }

    # ---- Extract skills ----
    skills_match = re.search(r"Languages:\s*(.+)", resume_text)
    if skills_match:
        profile["skills"].extend([s.strip() for s in skills_match.group(1).split(",")])

    tech_match = re.search(r"Technologies/Framework[s]?:\s*(.+)", resume_text)
    if tech_match:
        profile["skills"].extend([s.strip() for s in tech_match.group(1).split(",")])

    profile["skills"] = list(set(profile["skills"]))

    def _clean_token(s: str) -> str:
        return s.strip().strip("{}\\ ")

    def _normalize_skill(s: str) -> str:
        s = s.strip()
        mapping = {
            "rest api": "REST APIs",
            "rest apis": "REST APIs",
            "aws services": "AWS",
            "next": "Next.js",
        }
        return mapping.get(s.lower(), s)

    profile["skills"] = list(set(_normalize_skill(_clean_token(s)) for s in profile["skills"]))

    # ---- Extract education ----
    edu_match = re.search(r"(\d{4})\s*-\s*(\d{4})", resume_text)
    if edu_match:
        profile["education"]["year"] = int(edu_match.group(2))
        profile["education"]["degree"] = "B.Tech Computer Science"

    # ---- Extract experience (companies + roles) ----
    exp_matches = re.findall(
        r"\\resumeSubheading\s*\{([^}]+)\}\{([^}]+)\}\{([^}]+)\}\{([^}]+)\}",
        resume_text,
    )

    companies = []
    roles = []

    for match in exp_matches:
        companies.append(match[0].strip())
        roles.append(match[3].strip())

    profile["companies"] = list(set(companies))
    profile["roles"] = list(set(roles))

    # Fallback extraction for companies if regex fails
    if not profile["companies"]:
        if "amazon" in resume_text.lower():
            profile["companies"].append("Amazon")
        if "cvent" in resume_text.lower():
            profile["companies"].append("Cvent")

    # ---- Estimate years of experience ----
    total_years = 0
    date_ranges = re.findall(r"([A-Za-z]{3})\s*(\d{2})\s*[-–]\s*(Present|[A-Za-z]{3}\s*\d{2})", resume_text)

    for _, start_year, end in date_ranges:
        start_year = int("20" + start_year)

        if "Present" in end:
            end_year = datetime.now().year
        else:
            end_year = int("20" + end.split()[-1])

        total_years += max(0, end_year - start_year)

    profile["years_of_experience"] = total_years

    return profile


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        cleaned = " ".join(str(item).strip().split())
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _extract_pattern_terms(text: str, patterns: dict[str, str]) -> list[str]:
    matches: list[tuple[int, str]] = []
    for label, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            matches.append((match.start(), label))
    return [label for _, label in sorted(matches)]


def extract_job_id(text: str) -> str:
    patterns = [
        r"\bJob\s*ID\s*[:#-]?\s*([A-Za-z0-9_-]+)",
        r"\bJob\s*Id\s*[:#-]?\s*([A-Za-z0-9_-]+)",
        r"\bReq(?:uisition)?\s*ID\s*[:#-]?\s*([A-Za-z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def extract_company_name(text: str) -> str:
    job_id_line = re.search(r"\bJob\s*ID\s*[:#-]?\s*[A-Za-z0-9_-]+\s*\|\s*([^\n]+)", text, flags=re.IGNORECASE)
    if job_id_line:
        company = job_id_line.group(1).strip()
        company = re.sub(r"\s+Apply\s+now.*$", "", company, flags=re.IGNORECASE)
        return company

    for line in text.splitlines()[:12]:
        if re.search(r"\bAmazon\b", line):
            return "Amazon"
    return ""


def extract_job_title(text: str) -> str:
    lines = [" ".join(line.strip().split()) for line in text.splitlines() if line.strip()]
    skip_patterns = (
        r"amazon jobs home page",
        r"amazon never asks",
        r"job id",
        r"apply now",
        r"description",
        r"\bposted:",
        r"\bupdated\b",
        r"\b\d[\d,]*\.\d{2}\s*-\s*\d[\d,]*\.\d{2}\b",
        r"\b(?:usa|ind),\s*[a-z]{2}",
    )
    for line in lines[:20]:
        if any(re.search(pattern, line, flags=re.IGNORECASE) for pattern in skip_patterns):
            continue
        seeking_match = re.search(
            r"\b(?:seeking|looking for)\s+(?:a|an)\s+(.+?)\s+to\s+join\b",
            line,
            flags=re.IGNORECASE,
        )
        if seeking_match:
            return seeking_match.group(1).strip()
        if 3 <= len(line.split()) <= 14 and not line.startswith("-"):
            return line
    return ""


def extract_experience_requirements(text: str) -> str:
    requirement_lines = []
    for line in text.splitlines():
        stripped = " ".join(line.strip().lstrip("-").split())
        if not stripped:
            continue
        if re.search(r"\b(\d+\+?\s*years?|Bachelor'?s degree|degree in computer science|equivalent)\b", stripped, flags=re.IGNORECASE):
            requirement_lines.append(stripped)
    return "; ".join(_dedupe_preserve_order(requirement_lines))


def extract_important_details(text: str) -> list[str]:
    detail_patterns = (
        r"\blow[- ]latency\b",
        r"\bsub-\d+ms\b",
        r"\breal[- ]time\b",
        r"\btelemetry\b",
        r"\brobotics?\b",
        r"\bcross[- ]border\b",
        r"\binternational shopping\b",
        r"\bpersonalized recommendations?\b",
        r"\bpricing, delivery, legal\b",
        r"\bcustomer-facing systems?\b",
        r"\bhighly-available\b",
        r"\bfull stack\b",
        r"\bcontrol interfaces?\b",
        r"\bdashboards?\b",
    )
    details = []
    for line in text.splitlines():
        stripped = " ".join(line.strip().lstrip("-").split())
        if not stripped or len(stripped) > 180:
            continue
        if any(re.search(pattern, stripped, flags=re.IGNORECASE) for pattern in detail_patterns):
            details.append(stripped)
    return _dedupe_preserve_order(details)[:12]


def enrich_structured_jd(data: dict[str, Any], source_text: str) -> dict[str, Any]:
    """Fill high-confidence JD fields with deterministic extraction."""
    enriched = dict(data)

    detected_languages = _extract_pattern_terms(source_text, PROGRAMMING_LANGUAGE_PATTERNS)
    detected_tools = _extract_pattern_terms(source_text, TECHNOLOGY_PATTERNS)
    detected_details = extract_important_details(source_text)

    if not enriched.get("job_id"):
        enriched["job_id"] = extract_job_id(source_text)
    if not enriched.get("company_name"):
        enriched["company_name"] = extract_company_name(source_text)
    if not enriched.get("job_title"):
        enriched["job_title"] = extract_job_title(source_text)
    if not enriched.get("experience"):
        enriched["experience"] = extract_experience_requirements(source_text)

    enriched["languages"] = _dedupe_preserve_order(
        [*enriched.get("languages", []), *detected_languages]
    )
    enriched["tools"] = _dedupe_preserve_order([*enriched.get("tools", []), *detected_tools])
    enriched["skills"] = _dedupe_preserve_order(
        [
            *enriched.get("skills", []),
            *detected_languages,
            *detected_tools,
        ]
    )
    enriched["important_details"] = _dedupe_preserve_order(
        [*enriched.get("important_details", []), *detected_details]
    )

    return enriched



def compress_jd(text: str, max_chars: int = 4000) -> str:
    import re

    keywords = [
        "skills", "requirements", "responsibilities", "qualifications",
        "experience", "tools", "technologies", "job id", "job title",
        "basic qualifications", "preferred qualifications"
    ]

    # Expanded skill detection (this is the key upgrade)
    SKILL_PATTERNS = [
        # languages
        r"\b(java|python|c\+\+|go|rust|typescript|c#)\b",

        # infra / backend
        r"\b(aws|docker|kubernetes|sql|nosql|rest|ci/cd|graphql)\b",

        # core CS
        r"\b(data structures|algorithms|oop|object-oriented)\b",

        # databases / systems
        r"\b(kafka|redis|mongodb|postgresql|mysql)\b",

        # frameworks
        r"\b(next\.js|react|node\.js|spring|spring boot)\b",
    ]

    important_lines: list[str] = []

    for line_no, line in enumerate(text.splitlines()):
        stripped = " ".join(line.strip().split())
        if not stripped:
            continue

        normalized = stripped.lower()

        if (
            line_no < 12
            or any(keyword in normalized for keyword in keywords)
            or any(re.search(p, normalized) for p in SKILL_PATTERNS)
            or stripped.startswith("-")   # ✅ keep bullet points (VERY IMPORTANT)
            or re.search(r"\bjob\s*id\b", normalized)
            or re.search(r"\b(real[- ]time|low[- ]latency|telemetry|robotics|cross[- ]border|distributed systems?)\b", normalized)
        ):
            important_lines.append(stripped)

    compressed = "\n".join(important_lines)

    # fallback: ensure we don't lose important info
    if len(compressed) < 1500:
        compressed += "\n" + text[:2000]

    return compressed[:max_chars]


def llm_compress_jd(text: str) -> str:
    prompt = f"""
Extract the most important information from this job description.

Keep ONLY:
- job title
- skills
- responsibilities
- tools/technologies
- experience requirements

Remove:
- company descriptions
- marketing content
- repetitive text

Return plain text only.

Job Description:
{text}
"""
    return call_llm([{"role": "user", "content": prompt}])


def validate_structure_jd_schema(data: dict[str, Any]) -> dict[str, Any]:
    # Backward-compatible defaults if the LLM omits newer optional fields.
    data.setdefault("languages", [])
    data.setdefault("important_details", [])

    required = {
        "company_name",
        "job_id",
        "job_title",
        "languages",
        "skills",
        "responsibilities",
        "tools",
        "experience",
        "important_details",
    }
    missing = required - data.keys()
    if missing:
        raise JsonOutputError(f"Missing structure_jd fields: {sorted(missing)}")

    # Only enforce string type for core fields; experience can be flexible
    for field in ("company_name", "job_id", "job_title"):
        if not isinstance(data[field], str):
            raise JsonOutputError(f"structure_jd.{field} must be a string")

    # Normalize experience if model returns list or None
    exp = data.get("experience")
    if isinstance(exp, list):
        data["experience"] = " ".join(str(x) for x in exp)
    elif exp is None:
        data["experience"] = ""

    for field in ("languages", "skills", "responsibilities", "tools", "important_details"):
        if not isinstance(data[field], list) or not all(
            isinstance(item, str) for item in data[field]
        ):
            raise JsonOutputError(f"structure_jd.{field} must be a list of strings")

    return {
        "company_name": data["company_name"],
        "job_id": data["job_id"],
        "job_title": data["job_title"],
        "languages": data["languages"],
        "skills": data["skills"],
        "responsibilities": data["responsibilities"],
        "tools": data["tools"],
        "experience": data["experience"],
        "important_details": data["important_details"],
    }


def structure_jd(text: str) -> dict[str, Any]:
    """
    Extract and structure job description into standardized JSON format.
    
    Uses the LLM to parse job description and return structured data
    with company, job title, required skills, responsibilities, etc.
    
    Args:
        text: Raw job description text.
        
    Returns:
        dict: Structured job data with fields: company, job_id, job_title,
              skills, responsibilities, tools, experience.
    """
    compressed_text = compress_jd(text, min(STRUCTURE_JD_MAX_CHARS, 4000))
    print(
        "DEBUG structure_jd: "
        f"original_chars={len(text)}, compressed_chars={len(compressed_text)}"
    )

    prompt = f"""
You are an expert job description parser.

Your task is to extract structured hiring information from a job description.

STRICT RULES:
- Extract ONLY explicitly mentioned technologies, qualifications, and responsibilities.
- NEVER infer technologies.
- NEVER infer programming languages.
- NEVER extract soft skills.
- NEVER extract marketing phrases.
- NEVER extract company culture statements.
- NEVER extract vague engineering phrases.

DO NOT extract phrases like:
- entrepreneurial mindset
- startup culture
- world class engineering
- tech prowess
- customer obsession

ONLY extract concrete technical information.

Good examples:
- React
- AWS
- Kubernetes
- REST APIs
- Python
- Distributed systems
- Scalability
- Design patterns

Return STRICT JSON only.

Schema:
{{
  "company_name": "",
  "job_id": "",
  "job_title": "",
  "languages": [],
  "skills": [],
  "responsibilities": [],
  "tools": [],
  "experience": "",
  "important_details": []
}}

Job Description:
{text}
"""

    messages = [
        {
            "role": "user",
            "content": prompt,
        }
    ]
    structured = parse_json_with_retry(
        messages=messages,
        call_llm=call_llm,
        validate=validate_structure_jd_schema,
        fallback={**STRUCTURE_JD_FALLBACK, "responsibilities": [text[:1000]]},
        debug_name="structure_jd",
    )
    structured = validate_structure_jd_schema(enrich_structured_jd(structured, text))

    print(f"DEBUG main: structured JD keys={list(structured.keys())}")
    return structured


def ingest_source(source_id: str, text: str) -> None:
    for index, chunk in enumerate(chunk_text(text)):
        add_document(
            doc_id=f"{source_id}_{index}",
            text=chunk,
            metadata={"source": source_id},
        )


def load_job_text(url: str | None, file_path: str | None) -> str:
    if url:
        scraped = scrape_job_description(url)
        if scraped:
            return scraped
        print("DEBUG main: URL scrape failed, falling back to file")

    path = resolve_path(file_path) if file_path else DEFAULT_JOB_FILE
    return read_text(path)


def load_urls(path: Path) -> list[str]:
    if not path.exists():
        print(f"DEBUG main: URL file not found: {path}")
        return []

    urls: list[str] = []
    for line in read_text(path).splitlines():
        clean_line = line.strip()
        if not clean_line or clean_line.startswith("#"):
            continue
        urls.append(clean_line)

    print(f"DEBUG main: loaded {len(urls)} URLs from {path}")
    return urls


def resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return DEFAULT_JOB_FILE.parent.parent / path


def slugify(value: str, fallback: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = value.strip("_")
    return value or fallback


def optional_slug(value: Any) -> str:
    if value is None:
        return ""
    return slugify(str(value), "")


def fallback_job_id_from_url(url: str) -> str:
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]

    for part in reversed(path_parts):
        if re.search(r"\d", part):
            return part

    if path_parts:
        return path_parts[-1]

    return parsed.netloc or "job"


def fallback_company_from_url(url: str) -> str:
    parsed = urlparse(url)
    domain = parsed.netloc.lower().removeprefix("www.")
    if not domain:
        return "company"
    return domain.split(".")[0]


def output_path_for_job(structured_jd: dict[str, Any], url: str, index: int) -> Path:
    company = optional_slug(
        structured_jd.get("company_name") or structured_jd.get("company")
    )
    job_id = optional_slug(structured_jd.get("job_id"))
    generated_date = datetime.now().strftime("%Y%m%d")

    filename_parts = [part for part in (company, job_id, generated_date) if part]
    if not filename_parts:
        filename_parts = [f"job_{index}"]

    filename = "_".join(filename_parts) + ".tex"
    return OUTPUT_RESUME_DIR / filename


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local LangGraph resume optimizer.")
    parser.add_argument("--url", default="", help="Job description URL to scrape.")
    parser.add_argument(
        "--url-file",
        default=str(JOB_URLS_PATH),
        help="File containing one job URL per line.",
    )
    parser.add_argument("--job-file", default="", help="Local job description file.")
    parser.add_argument("--resume-file", default=str(RESUME_PATH), help="Input resume LaTeX path.")
    parser.add_argument("--output", default="", help="Output resume LaTeX path.")
    parser.add_argument("--continue-run", default="", help="Resume a run by run_id.")
    parser.add_argument("--continue-job", default="", help="Resume a specific job_id.")
    return parser.parse_args()


def process_job(
    resume_data: str,
    *,
    url: str = "",
    job_file: str = "",
    output_path: Path | None = None,
    index: int = 1,
    job_id: str = "",
) -> Path | None:
    """
    Process a single job: structure JD, detect missing fields, run workflow.
    
    Args:
        resume_data: Candidate's resume in LaTeX format.
        url: Job description URL (optional).
        job_file: Local job file path (optional).
        output_path: Custom output path (optional).
        index: Job index for naming.
        job_id: Unique job identifier for state tracking.
        
    Returns:
        Path to generated LaTeX resume, or None if waiting for user input.
    """
    structured_jd: dict[str, Any] = {}
    final_output_path = output_path or output_path_for_job(structured_jd, url or job_file, index)

    try:
        raw_job_text = load_job_text(url, job_file)
        cleaned_job_text = clean_text(raw_job_text)
        print(f"DEBUG main: raw_job_text={raw_job_text}")
        print(f"DEBUG main: cleaned_job_text={cleaned_job_text}")
        source_id = f"job_description_{index}"
        ingest_source(source_id, raw_job_text)
        structured_jd = structure_jd(raw_job_text)
        final_output_path = output_path or output_path_for_job(structured_jd, url or job_file, index)
        candidate_profile = extract_candidate_profile(resume_data)
        print(f"DEBUG main: candidate_profile={candidate_profile}")
        print(f"DEBUG main: structured_jd={structured_jd}")
        # If tracking this job, update its state
        if job_id:
            job = load_job(job_id)
            job["structured_jd"] = structured_jd
            
            def _is_missing(val):
                if val is None:
                    return True
                if isinstance(val, str) and not val.strip():
                    return True
                if isinstance(val, list) and len(val) == 0:
                    return True
                return False

            missing = [f for f in REQUIRED_JD_FIELDS if _is_missing(structured_jd.get(f))]
            if missing:
                job["status"] = "waiting_input"
                job["missing_fields"] = missing
                save_job(job)
                print(f"[WAITING INPUT] job_id={job_id}, missing={missing}")
                return None
            
            job["status"] = "processing"
            save_job(job)

        workflow = build_workflow()
        initial_state: ResumeGraphState = {
            "job_data": structured_jd,
            "structured_jd": structured_jd,
            "resume_data": resume_data,
            "candidate_profile": candidate_profile,
            "iteration_count": 0,
        }

        final_state = workflow.invoke(initial_state)
        generated_resume = final_state.get("generated_resume", resume_data)
        write_text(final_output_path, generated_resume)
        post_result = post_process_resume(final_output_path)

        if job_id:
            job = load_job(job_id)
            job["status"] = "completed"
            job["output_path"] = str(final_output_path)
            job["drive_file"] = post_result.get("drive_file")
            job["notification"] = post_result.get("notification")
            job["validation"] = final_state.get("validation", {})
            job["judge_result"] = final_state.get("judge_result", {})
            save_job(job)

        print("DEBUG main: final validation:", final_state.get("validation"))
        print("DEBUG main: final judge:", final_state.get("judge_result"))
        print(f"Generated resume: {final_output_path}")
        return final_output_path
    except Exception as exc:
        failure_notification = send_generation_failure_whatsapp(final_output_path.name, str(exc))
        if job_id:
            job = load_job(job_id)
            job["status"] = "failed"
            job["output_path"] = str(final_output_path)
            job["error"] = str(exc)
            job["failure_notification"] = failure_notification
            save_job(job)
        raise


def main() -> None:
    """Main entry point for resume generation."""
    args = parse_args()

    # Handle resume requests
    if args.continue_run:
        from resume_run import continue_run
        continue_run(args.continue_run)
        return

    if args.continue_job:
        from resume_run import continue_run
        try:
            job = load_job(args.continue_job)
            continue_run(job["run_id"])
        except FileNotFoundError:
            print(f"ERROR: job_id not found: {args.continue_job}")
        return

    # Generate a unique run ID for this execution
    run_id = create_run_id()
    print(f"DEBUG main: run_id={run_id}")

    resume_data = read_text(resolve_path(args.resume_file) if args.resume_file else RESUME_PATH)

    if args.url:
        job_id = f"{run_id}_single_url"
        job = {
            "job_id": job_id,
            "run_id": run_id,
            "status": "pending",
            "url": args.url,
            "index": 1,
            "resume_data": resume_data,
            "structured_jd": {},
            "missing_fields": [],
            "user_inputs": {},
        }
        save_job(job)
        process_job(
            resume_data,
            url=args.url,
            output_path=resolve_path(args.output) if args.output else None,
            job_id=job_id,
        )
        return

    if args.job_file:
        job_id = f"{run_id}_single_file"
        job = {
            "job_id": job_id,
            "run_id": run_id,
            "status": "pending",
            "url": "",
            "index": 1,
            "resume_data": resume_data,
            "structured_jd": {},
            "missing_fields": [],
            "user_inputs": {},
        }
        save_job(job)
        process_job(
            resume_data,
            job_file=args.job_file,
            output_path=resolve_path(args.output) if args.output else None,
            job_id=job_id,
        )
        return

    urls = load_urls(resolve_path(args.url_file))
    if not urls:
        print("DEBUG main: no URLs found, falling back to default sample job file")
        job_id = f"{run_id}_default"
        job = {
            "job_id": job_id,
            "run_id": run_id,
            "status": "pending",
            "url": "",
            "index": 1,
            "resume_data": resume_data,
            "structured_jd": {},
            "missing_fields": [],
            "user_inputs": {},
        }
        save_job(job)
        process_job(
            resume_data,
            job_file=str(DEFAULT_JOB_FILE),
            output_path=resolve_path(args.output) if args.output else None,
            job_id=job_id,
        )
        return

    # Process multiple URLs with state tracking
    generated_paths = []

    for index, url in enumerate(urls, start=1):
        job_id = f"{run_id}_job_{index}"
        job = {
            "job_id": job_id,
            "run_id": run_id,
            "status": "pending",
            "url": url,
            "index": index,
            "resume_data": resume_data,
            "structured_jd": {},
            "missing_fields": [],
            "user_inputs": {},
        }
        save_job(job)

        result = process_job(resume_data, url=url, index=index, job_id=job_id)
        if result:
            generated_paths.append(result)

    print("Generated resumes:")
    for path in generated_paths:
        print(f"- {path}")


if __name__ == "__main__":
    main()
