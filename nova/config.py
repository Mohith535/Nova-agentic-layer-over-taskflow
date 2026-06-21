"""Runtime configuration — loaded once, from the environment (never hard-coded).

Secrets live in ``.env`` (gitignored). The Gemini key is read from ``GEMINI_API_KEY`` (what
TaskFlow's ecosystem uses) and mirrored to ``GOOGLE_API_KEY`` (what google-genai/ADK expect),
so the user only has to set one.
"""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv optional at runtime
    pass


def gemini_model() -> str:
    return os.environ.get("NOVA_GEMINI_MODEL", "gemini-2.5-flash")


def model_backend() -> str:
    return os.environ.get("NOVA_MODEL_BACKEND", "gemini").strip().lower()


def ensure_api_key() -> bool:
    """Return True if an API key is available; mirror GEMINI_API_KEY → GOOGLE_API_KEY."""
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if key:
        os.environ["GOOGLE_API_KEY"] = key
        # Avoid google-genai's "both keys set" warning — keep a single canonical var.
        os.environ.pop("GEMINI_API_KEY", None)
        return True
    return False


def data_dir() -> str | None:
    return os.environ.get("TASKFLOW_DATA_PATH")
