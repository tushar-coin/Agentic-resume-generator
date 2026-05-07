from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RESUME_PATH = DATA_DIR / "resume.tex"
RESUME_TEMPLATE_PATH = DATA_DIR / "resume_template.tex"
DEFAULT_JOB_FILE = DATA_DIR / "sample.txt"
JOB_URLS_PATH = DATA_DIR / "job_urls.txt"
OUTPUT_RESUME_PATH = DATA_DIR / "optimized_resume.tex"
OUTPUT_RESUME_DIR = DATA_DIR / "optimized_resumes"
CHROMA_PATH = PROJECT_ROOT / ".chroma"

LLM_MODEL = "qwen2:7b"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
COLLECTION_NAME = "job_resume_knowledge_base"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
MAX_JUDGE_RETRIES = 2
LLM_TIMEOUT_SECONDS = 120
LLM_NUM_PREDICT = 1024
STRUCTURE_JD_MAX_CHARS = 6000
