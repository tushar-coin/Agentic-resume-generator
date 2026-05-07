"""Manage job-level state and persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STATE_DIR = Path("state_store")
STATE_DIR.mkdir(exist_ok=True)


def job_path(job_id: str) -> Path:
    """
    Get the file path for a job's state file.
    
    Args:
        job_id: The unique job identifier.
        
    Returns:
        Path: Absolute path to the job state JSON file.
    """
    return STATE_DIR / f"{job_id}.json"


def save_job(job: dict[str, Any]) -> None:
    """
    Persist a job's state to JSON file.
    
    Args:
        job: Job dictionary containing job_id and state fields.
        
    Raises:
        KeyError: If job dict lacks required 'job_id' key.
    """
    if "job_id" not in job:
        raise KeyError("job dict must contain 'job_id' key")
    
    path = job_path(job["job_id"])
    path.write_text(json.dumps(job, indent=2, default=str), encoding="utf-8")


def load_job(job_id: str) -> dict[str, Any]:
    """
    Load a job's persisted state from JSON file.
    
    Args:
        job_id: The unique job identifier.
        
    Returns:
        dict: Job state dictionary.
        
    Raises:
        FileNotFoundError: If job state file does not exist.
        json.JSONDecodeError: If file contains invalid JSON.
    """
    path = job_path(job_id)
    if not path.exists():
        raise FileNotFoundError(f"Job state not found: {job_id}")
    
    return json.loads(path.read_text(encoding="utf-8"))


def load_jobs_by_run(run_id: str) -> list[dict[str, Any]]:
    """
    Load all jobs belonging to a specific run.
    
    Args:
        run_id: The run identifier to filter by.
        
    Returns:
        list: List of job dictionaries for the run, sorted by index.
    """
    jobs = []
    for file in STATE_DIR.glob("*.json"):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            if data.get("run_id") == run_id:
                jobs.append(data)
        except (json.JSONDecodeError, ValueError):
            # Skip malformed files
            print(f"DEBUG load_jobs_by_run: skipping malformed file {file.name}")
            continue
    print(f"DEBUG load_jobs_by_run: found {len(jobs)} jobs for run_id={run_id}")
    # Sort by index for consistent ordering
    return sorted(jobs, key=lambda j: j.get("index", 0))


def job_exists(job_id: str) -> bool:
    """
    Check if a job state file exists.
    
    Args:
        job_id: The unique job identifier.
        
    Returns:
        bool: True if job state exists, False otherwise.
    """
    return job_path(job_id).exists()


def delete_job(job_id: str) -> None:
    """
    Delete a job's state file.
    
    Args:
        job_id: The unique job identifier.
    """
    path = job_path(job_id)
    if path.exists():
        path.unlink()
