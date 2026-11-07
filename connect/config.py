"""Settings, read from the environment and an optional .env file. Keys are never logged."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env_files() -> None:
    """CONNECT_ENV_FILE can list several files, and the first one to set a value wins."""
    for name in os.environ.get("CONNECT_ENV_FILE", str(ROOT / ".env")).split(os.pathsep):
        path = Path(name)
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_env_files()

DATA_DIR = Path(os.environ.get("CONNECT_DATA_DIR", ROOT / "fonecta_data" / "FONECTA_CONNECT_SUGGESTS_2026"))
VAR_DIR = Path(os.environ.get("CONNECT_VAR_DIR", ROOT / "var"))
HOST = os.environ.get("CONNECT_HOST", "127.0.0.1")
PORT = int(os.environ.get("CONNECT_PORT", "8080"))
PUBLIC_URL = os.environ.get("CONNECT_PUBLIC_URL", f"http://127.0.0.1:{PORT}").rstrip("/")

# The challenge scenario: "today" is fixed, and the data stops the day before.
TODAY = date.fromisoformat(os.environ.get("CONNECT_TODAY", "2026-11-06"))

SANDBOX_URL = os.environ.get("YEXT_BASE_URL", "https://sbx-api.yextapis.com").rstrip("/")
SANDBOX_KEY = "" if os.environ.get("CONNECT_NO_SANDBOX") else os.environ.get("YEXT_API_KEY") or os.environ.get("API_KEY") or ""

# Suggestions at or above this confidence are stated. Below it, they are asked as a question.
SUGGEST_THRESHOLD = 0.90
# Standing permission only applies changes at or above this confidence, and never from peers alone.
AUTO_APPLY_THRESHOLD = 0.90
MAX_DATES_PER_MESSAGE = 8  # The largest bundle sent in the 2025 pilot.
BATCH_GAP_DAYS = 3  # Dates this close together go in one message.
