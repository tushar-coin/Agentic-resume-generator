"""Utilities for managing job state and user input."""

from __future__ import annotations

from typing import Any

from job_manager import load_job, save_job


def inject_user_input(job_id: str, user_input: dict[str, Any]) -> None:
    """
    Inject user-provided missing fields into a job.
    
    This allows users to provide values for fields that were missing
    when the job description was initially processed.
    
    Args:
        job_id: The unique job identifier.
        user_input: Dictionary of field name → value mappings.
        
    Raises:
        FileNotFoundError: If job state file does not exist.
    """
    job = load_job(job_id)
    job["user_inputs"].update(user_input)
    save_job(job)
    print(f"DEBUG job_utils: injected {len(user_input)} inputs into {job_id}")


def get_job_status(job_id: str) -> str:
    """
    Get the current status of a job.
    
    Args:
        job_id: The unique job identifier.
        
    Returns:
        str: Current job status (pending, processing, waiting_input, completed, failed).
        
    Raises:
        FileNotFoundError: If job state file does not exist.
    """
    job = load_job(job_id)
    return job.get("status", "unknown")


def list_waiting_jobs(run_id: str) -> list[dict[str, Any]]:
    """
    Get all jobs in a run that are waiting for user input.
    
    Args:
        run_id: The run identifier to filter by.
        
    Returns:
        list: Jobs with status "waiting_input", including missing fields.
    """
    from job_manager import load_jobs_by_run
    
    jobs = load_jobs_by_run(run_id)
    return [j for j in jobs if j.get("status") == "waiting_input"]
