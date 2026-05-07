"""Resume a processing run with stored job state."""

from __future__ import annotations

from typing import Any

from graph.workflow import build_workflow
from job_manager import load_jobs_by_run, save_job
from main import output_path_for_job
from utils.file_io import write_text
from utils.post_generation import post_process_resume, send_generation_failure_whatsapp


RETRYABLE_FAILED_ERRORS = {
    "'\"eligible\"'",
    "'\"valid\"'",
}


def should_resume_job(job: dict[str, Any]) -> bool:
    if job.get("status") == "waiting_input":
        return True

    if job.get("status") != "failed":
        return False

    if job.get("error") in RETRYABLE_FAILED_ERRORS and job.get("user_inputs"):
        print(f"DEBUG resume_run: retrying {job['job_id']} after prompt-format failure")
        return True

    return False


def continue_run(run_id: str) -> None:
    """
    Resume processing all jobs in a run that are waiting for input.
    
    This function:
    1. Loads all jobs for the given run_id
    2. Filters for jobs with status "waiting_input" and provided user inputs
    3. Re-runs the workflow with updated structured data
    4. Saves outputs and updates job status to "completed"
    
    Args:
        run_id: The run identifier to resume.
        
    Prints:
        Status messages for each job resumed or still waiting.
    """
    jobs = load_jobs_by_run(run_id)
    
    if not jobs:
        print(f"DEBUG resume_run: no jobs found for run_id={run_id}")
        return
    
    print(f"DEBUG resume_run: found {len(jobs)} jobs for run_id={run_id}")
    
    workflow = build_workflow()
    resumed_count = 0
    still_waiting = 0
    
    for job in jobs:
        job_id = job["job_id"]
        print(f"[RESUMED] {job['run_id']}")  # Add this line before the try block
        # Skip jobs that are neither waiting nor retryable failures.
        if not should_resume_job(job):
            print(f"DEBUG resume_run: skipping {job_id} (status={job['status']})")
            continue
        
        # Check if user provided missing fields
        if not job.get("user_inputs"):
            print(f"[STILL WAITING] {job_id} needs {job['missing_fields']}")
            still_waiting += 1
            continue
        
        # Merge structured data with user inputs
        structured = {**job["structured_jd"], **job["user_inputs"]}
        print(f"DEBUG resume_run: merged structured data for {job_id} with user inputs{structured}")    
        # Run workflow with complete data
        try:
            initial_state: dict[str, Any] = {
                "job_data": structured,
                "structured_jd": structured,
                "resume_data": job["resume_data"],
                "iteration_count": 0,
            }
            print(f'{initial_state}')
            final_state = workflow.invoke(initial_state)
            generated_resume = final_state.get("generated_resume", job["resume_data"])
            
            # Generate output path and save resume
            output_path = output_path_for_job(
                structured,
                job["url"],
                job["index"],
            )
            write_text(output_path, generated_resume)
            post_result = post_process_resume(output_path)
            
            # Update job status
            job["status"] = "completed"
            job["output_path"] = str(output_path)
            job["drive_file"] = post_result.get("drive_file")
            job["notification"] = post_result.get("notification")
            save_job(job)
            
            print(f"[RESUMED] {job_id} → {output_path}")
            resumed_count += 1
            
        except Exception as e:
            print(f"[ERROR] {job_id} failed during resume: {e}")
            output_path = output_path_for_job(
                structured,
                job["url"],
                job["index"],
            )
            job["status"] = "failed"
            job["error"] = str(e)
            job["output_path"] = str(output_path)
            job["failure_notification"] = send_generation_failure_whatsapp(
                output_path.name,
                str(e),
            )
            save_job(job)
    
    print(f"\nResume summary: {resumed_count} resumed, {still_waiting} still waiting")
