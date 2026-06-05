import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SESSION_FILE = PROJECT_ROOT / "data" / "sessions.json"


def load_sessions() -> dict[str, Any]:
    """
    Load existing issue-to-session mappings from data/sessions.json.
    """
    if not SESSION_FILE.exists():
        return {}

    with SESSION_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_sessions(sessions: dict[str, Any]) -> None:
    """
    Save issue-to-session mappings to data/sessions.json.
    """
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)

    with SESSION_FILE.open("w", encoding="utf-8") as file:
        json.dump(sessions, file, indent=2)
