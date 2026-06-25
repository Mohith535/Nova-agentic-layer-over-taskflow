"""Runtime configuration — loaded once, from the environment (never hard-coded).

Secrets live in ``.env`` (gitignored). The Gemini key is read from ``GEMINI_API_KEY`` (what
TaskFlow's ecosystem uses) and mirrored to ``GOOGLE_API_KEY`` (what google-genai/ADK expect),
so the user only has to set one.

Model routing strategy
----------------------
Nova uses different model tiers based on task complexity and tracks quota exhaustion
in-memory so it never retries a dead model in the same session:

  COMPLEX  (plan, coach)  → most capable available: 2.5-flash → 2.0-flash
  SIMPLE   (ask, brief)   → cheapest available first: 2.0-flash-lite → 2.0-flash → 2.5-flash

Quota resets at midnight Pacific every day. On 429, the model is marked exhausted for
the session and the router automatically falls back to the next available tier.
"""

from __future__ import annotations

import os
import threading

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ---------- quota-aware model router ----------------------------------------

# Models in preference order for each tier.
# Override any with env vars; router skips exhausted ones automatically.
_COMPLEX_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"]   # plan, coach
_SIMPLE_MODELS  = ["gemini-2.0-flash-lite", "gemini-2.0-flash", "gemini-2.5-flash"]  # ask, brief

_exhausted: set[str] = set()   # quota-dead this session
_lock = threading.Lock()


def _env_override(env_key: str, fallbacks: list[str]) -> list[str]:
    """If an env override is set, put it first; keep the rest as fallbacks."""
    override = os.environ.get(env_key, "").strip()
    if override and override not in fallbacks:
        return [override] + fallbacks
    if override:
        return [override] + [m for m in fallbacks if m != override]
    return fallbacks


def best_model(mode: str) -> str:
    """Return the best non-exhausted model for this mode."""
    candidates = (
        _env_override("NOVA_GEMINI_MODEL", _COMPLEX_MODELS)
        if mode in ("plan", "coach")
        else _env_override("NOVA_FAST_MODEL", _SIMPLE_MODELS)
    )
    with _lock:
        for m in candidates:
            if m not in _exhausted:
                return m
    return candidates[-1]   # all exhausted — try the last one anyway


def mark_exhausted(model: str) -> None:
    """Call this when a 429/RESOURCE_EXHAUSTED is received for a model."""
    with _lock:
        _exhausted.add(model)


def exhausted_models() -> list[str]:
    """Current list of quota-dead models (for UI display / debugging)."""
    with _lock:
        return sorted(_exhausted)


# ---------- legacy helpers (kept for callers that import directly) -----------

def gemini_model() -> str:
    return best_model("plan")


def fast_gemini_model() -> str:
    return best_model("ask")


def model_backend() -> str:
    return os.environ.get("NOVA_MODEL_BACKEND", "gemini").strip().lower()


def ensure_api_key() -> bool:
    """Return True if an API key is available; mirror GEMINI_API_KEY → GOOGLE_API_KEY."""
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if key:
        os.environ["GOOGLE_API_KEY"] = key
        os.environ.pop("GEMINI_API_KEY", None)
        return True
    return False


def data_dir() -> str | None:
    return os.environ.get("TASKFLOW_DATA_PATH")
