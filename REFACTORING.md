# Resume Generator: Run & Job State Management

## Architecture Overview

This refactored system introduces **run-level** and **job-level** state management while preserving backward compatibility with the existing LangGraph workflow.

### Key Concepts

- **Run ID**: Unique identifier for a batch execution (one per script invocation)
- **Job ID**: Unique identifier for a single job (one per URL/file)
- **State Store**: JSON files in `state_store/` directory
- **Status Tracking**: pending → processing → waiting_input/completed/failed

---

## New Modules

### 1. `run_manager.py`
Generates unique run IDs combining timestamp and UUID.

```python
from run_manager import create_run_id

run_id = create_run_id()  # "run_20260502_143022_abc123"
```

### 2. `job_manager.py`
Persists and retrieves job state from JSON files.

```python
from job_manager import save_job, load_job, load_jobs_by_run

# Save a job
job = {
    "job_id": "run_123_job_1",
    "run_id": "run_123",
    "status": "pending",
    "url": "https://job.example.com/123",
    "structured_jd": {},
    "missing_fields": [],
    "user_inputs": {}
}
save_job(job)

# Load a job
job = load_job("run_123_job_1")

# Load all jobs for a run
jobs = load_jobs_by_run("run_123")
```

### 3. `resume_run.py`
Resumes processing jobs that were waiting for user input.

```python
from resume_run import continue_run

continue_run("run_20260502_143022_abc123")
```

### 4. `job_utils.py`
Helper utilities for user input injection and job status queries.

```python
from job_utils import inject_user_input, get_job_status, list_waiting_jobs

# Inject missing fields
inject_user_input("run_123_job_1", {
    "job_title": "Senior Engineer",
    "skills": ["Python", "LangGraph"],
    "responsibilities": ["Design systems", "Code review"]
})

# Check job status
status = get_job_status("run_123_job_1")  # "completed"

# List waiting jobs
waiting = list_waiting_jobs("run_123")
```

---

## Updated `main.py`

### New CLI Arguments

```bash
# Resume a full run
python main.py --continue-run run_20260502_143022_abc123

# Resume a specific job
python main.py --continue-job run_20260502_143022_abc123_job_1
```

### Workflow Flow

#### First Run (Fresh Execution)

```bash
$ python main.py --url-file data/job_urls.txt
DEBUG main: run_id=run_20260502_143022_abc123
[... processing jobs ...]
[WAITING INPUT] run_20260502_143022_abc123_job_1, missing=['job_title', 'skills']
[... processing more jobs ...]
Generated resumes:
- data/optimized_resumes/company_job_123.md
```

Jobs are created with state:
```json
{
  "job_id": "run_20260502_143022_abc123_job_1",
  "run_id": "run_20260502_143022_abc123",
  "status": "waiting_input",
  "url": "https://...",
  "missing_fields": ["job_title", "skills"],
  "user_inputs": {}
}
```

#### Resume After User Input

User provides missing fields programmatically:

```python
from job_utils import inject_user_input

inject_user_input("run_20260502_143022_abc123_job_1", {
    "job_title": "Senior Software Engineer",
    "skills": ["Python", "Machine Learning", "LangGraph"],
})
```

Then resume:

```bash
$ python main.py --continue-run run_20260502_143022_abc123
DEBUG main: run_id=run_20260502_143022_abc123
[RESUMED] run_20260502_143022_abc123_job_1 → data/optimized_resumes/company_senior_eng.md
Resume summary: 1 resumed, 0 still waiting
```

---

## Job Lifecycle

```
┌─────────────┐
│   pending   │  (initial state)
└──────┬──────┘
       │
       ├─────────────────────────────────────────────┐
       │                                             │
       v                                             v
┌──────────────┐                            ┌──────────────────┐
│  processing  │                            │ waiting_input    │
└──────┬───────┘                            │ (missing fields) │
       │                                    └────────┬─────────┘
       │                                            │
       │                              (user provides input)
       │                                            │
       ├──────────────────────────────────────────  │
       │                                             │
       v                                             v
┌──────────────┐                                 (retry)
│ completed    │                                     │
│ (or failure) │◄────────────────────────────────────┘
└──────────────┘
```

---

## State Store Structure

```
state_store/
├── run_20260502_143022_abc123_job_1.json
├── run_20260502_143022_abc123_job_2.json
├── run_20260502_143022_abc123_job_3.json
└── ...
```

Each file contains:

```json
{
  "job_id": "run_20260502_143022_abc123_job_1",
  "run_id": "run_20260502_143022_abc123",
  "status": "completed",
  "url": "https://example.com/job/123",
  "index": 1,
  "resume_data": "# My Resume\n...",
  "structured_jd": {
    "company": "Example Inc",
    "job_title": "Senior Engineer",
    "skills": ["Python", "LangGraph"],
    "responsibilities": ["Design", "Review"],
    "tools": ["Git", "Docker"]
  },
  "missing_fields": [],
  "user_inputs": {},
  "output_path": "data/optimized_resumes/example_senior_engineer.md",
  "validation": {},
  "judge_result": {}
}
```

---

## Backward Compatibility

All changes are **backward compatible**:

- ✅ Existing `process_job()` calls work unchanged (job_id defaults to "")
- ✅ State tracking is optional (only activated when job_id provided)
- ✅ Resume functionality is opt-in (--continue-run flag)
- ✅ No database required (JSON file storage)

---

## Error Handling

All modules include proper error handling:

- **Missing file**: `FileNotFoundError` with descriptive message
- **Malformed JSON**: Graceful skip with logging
- **Invalid job**: Clear error messages
- **Workflow failure**: Job marked as "failed" with error details

---

## Future Enhancements

Potential improvements (non-breaking):

1. **SQLite backend**: Replace JSON with database
2. **Web dashboard**: View job status and inject input
3. **Batch operations**: Resume multiple runs simultaneously
4. **Retry logic**: Automatic retry with exponential backoff
5. **Email notifications**: Alert user when input needed

---

## Usage Examples

### Example 1: Basic Batch Processing

```bash
python main.py
```

### Example 2: Resume Specific Run

```bash
python main.py --continue-run run_20260502_143022_abc123
```

### Example 3: Programmatic Input Injection

```python
from job_utils import inject_user_input, list_waiting_jobs, get_job_status
from subprocess import run

# Find waiting jobs
waiting = list_waiting_jobs("run_20260502_143022_abc123")
for job in waiting:
    print(f"Job {job['job_id']} needs: {job['missing_fields']}")
    
    # Simulate user providing input
    inject_user_input(job['job_id'], {
        "job_title": "Inferred from URL",
        "skills": ["Python"],
        "responsibilities": ["General engineering"]
    })

# Resume the run
run(["python", "main.py", "--continue-run", "run_20260502_143022_abc123"])
```

### Example 4: Check Job Status

```python
from job_manager import load_job

job = load_job("run_20260502_143022_abc123_job_1")
print(f"Status: {job['status']}")
print(f"Output: {job.get('output_path')}")
print(f"Validation: {job.get('validation')}")
```

---

## Testing

All new modules include comprehensive error handling and logging.

To test:

```bash
# Run normally
python main.py --url "https://example.com/job"

# Find the run_id from output
# Then resume:
python main.py --continue-run run_XXXXX
```

