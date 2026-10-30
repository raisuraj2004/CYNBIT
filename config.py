"""Application configuration and bounded resource limits."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
TRACKS_PATH = PROJECT_ROOT / "data" / "tracks.yaml"
SCHEMA_PATH = PROJECT_ROOT / "schema.sql"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "pathfinder.sqlite3"

MAX_ABOUT_CHARS = 800
MAX_INTERESTS = 10
MAX_KNOWN_ITEMS = 20
MAX_TRACK_CANDIDATES = 5
MAX_LLM_ATTEMPTS = 2
LLM_TIMEOUT_SECONDS = 12
MAX_REQUESTS_PER_HOUR = 10
MAX_LLM_CALLS_PER_DAY = 50
RATE_LIMIT_WINDOW_SECONDS = 60 * 60
PROMPT_VERSION = "1.0"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

RETRIEVAL_WEIGHTS = {
    "text": 0.35,
    "skills": 0.25,
    "interests": 0.20,
    "goal": 0.10,
    "education": 0.05,
    "time": 0.05,
}
