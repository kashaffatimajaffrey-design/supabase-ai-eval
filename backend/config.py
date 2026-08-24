"""
config.py
Single source of truth for environment configuration.

Every backend module loads env vars through this module instead of calling
load_dotenv() directly. Rationale: a bare load_dotenv() resolves via
find_dotenv(), which walks up from the *calling file's* directory -- not the
shell's working directory. Because every module here lives in backend/, they
all silently resolved to backend/.env and never read the repo-root .env, even
when invoked from the repo root. That made credential updates appear to have
no effect. Pinning to the repo root removes the ambiguity.
"""
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = REPO_ROOT / ".env"

# override=True so a stale value already in the process environment cannot
# shadow the canonical file.
load_dotenv(ENV_PATH, override=True)
