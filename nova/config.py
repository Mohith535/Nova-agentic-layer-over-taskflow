"""Runtime configuration — loaded once, from the environment (never hard-coded).

Secrets live in ``.env`` (gitignored). The Gemini key is read from ``GEMINI_API_KEY`` (what
TaskFlow's ecosystem uses) and mirrored to ``GOOGLE_API_KEY`` (what google-genai/ADK expect),
so the user only has to set one.

Model routing strategy
----------------------
Nova uses different model tiers based on task complexity and tracks quota exhaustion
in-memory so it never retries a dead model in the same session:

  COMPLEX  (plan, coach)  → most capable available, then cheaper fallbacks
  SIMPLE   (ask, brief)   → cheapest available first

The free tier meters **per model per day** (the quota id is literally
``GenerateRequestsPerDayPerProjectPerModel-FreeTier``), so a chain of N live models is
N separate daily allowances. That makes the chain the whole quota strategy — which is
why it must not contain dead models.

2026-09-14: it did. The chain was ``2.5-flash → 2.0-flash`` and both 2.0 models had been
RETIRED (404: "no longer available"), so once 2.5-flash hit its 20/day cap there was
nothing live to fall back to and every agent call failed. Verified against the live
models.list() endpoint, not assumed.

Exhaustion is persisted to disk, not just held in memory: each CLI/bridge call is a fresh
process, so an in-memory set was always empty at startup and the router retried the dead
model first, every single time. Quota resets at midnight Pacific, so the file is keyed by
the Pacific date and self-expires.
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
# Verified live 2026-09-14 against models.list(); each entry is a SEPARATE daily quota.
# Ordered most-capable-first for complex work, cheapest-first for simple work. The `-latest`
# aliases sit at the end of each chain as a self-updating backstop: when these pinned names
# are retired in turn, the alias keeps Nova answering instead of 404-ing.
_COMPLEX_MODELS = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-2.5-flash",
                   "gemini-3.5-flash-lite", "gemini-flash-latest"]
_SIMPLE_MODELS  = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.6-flash",
                   "gemini-flash-lite-latest"]

_exhausted: set[str] = set()   # quota-dead today (loaded from disk on first use)
_lock = threading.Lock()
_loaded = False


def _pacific_day() -> str:
    """Gemini's free quota resets at midnight Pacific, so that is the key the file is
    stamped with. Computed as a fixed UTC-8 offset rather than via a tz database: being an
    hour out during DST just expires the record an hour early, which costs one wasted retry
    and never wrongly suppresses a model."""
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(hours=8)).strftime("%Y-%m-%d")


def _state_file():
    from pathlib import Path
    return Path(os.environ.get("TASKFLOW_DATA_PATH") or (Path.home() / ".taskflow")) / "nova_quota.json"


def _load_exhausted() -> None:
    """Read today's exhausted models from disk, once per process.

    Every `nova ask|plan|coach` and every EDI bridge call is a FRESH PROCESS. An in-memory
    set is therefore always empty at startup, so the router kept picking the model it had
    already learned was dead - relearning it, at the cost of a real failed call, every time.
    Failure here is always silent-and-safe: a missing or corrupt file just means "nothing
    known exhausted", which costs one retry, never a wrong refusal."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        import json
        d = json.loads(_state_file().read_text(encoding="utf-8"))
        if d.get("day") == _pacific_day():
            _exhausted.update(d.get("models", []))
    except Exception:
        pass


def _save_exhausted() -> None:
    try:
        import json
        f = _state_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({"day": _pacific_day(), "models": sorted(_exhausted)}),
                       encoding="utf-8")
        tmp.replace(f)      # atomic, same pattern TaskFlow uses for tasks.json
    except Exception:
        pass


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
        _load_exhausted()
        for m in candidates:
            if m not in _exhausted:
                return m
    return candidates[-1]   # all exhausted — try the last one anyway


def mark_exhausted(model: str) -> None:
    """Call this when a 429/RESOURCE_EXHAUSTED is received for a model."""
    with _lock:
        _load_exhausted()
        _exhausted.add(model)
        _save_exhausted()


def exhausted_models() -> list[str]:
    """Current list of quota-dead models (for UI display / debugging)."""
    with _lock:
        _load_exhausted()
        return sorted(_exhausted)


# ---------- legacy helpers (kept for callers that import directly) -----------

def gemini_model() -> str:
    return best_model("plan")


def fast_gemini_model() -> str:
    return best_model("ask")


def ensure_api_key() -> bool:
    """Return True if an API key is available; mirror GEMINI_API_KEY → GOOGLE_API_KEY."""
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if key:
        os.environ["GOOGLE_API_KEY"] = key
        os.environ.pop("GEMINI_API_KEY", None)
        return True
    return False


def validate_gemini_key(key: str, timeout: float = 15.0):
    """Fast liveness check for a Gemini key via a single REST call. Never raises. Returns:
      True  — the key works (HTTP 200 from the models endpoint)
      False — the key was explicitly rejected (HTTP 400 / 401 / 403 — invalid or unauthorized)
      None  — couldn't tell (network, timeout, or a transient server error) — don't alarm
    A plain GET to the public models endpoint is much faster than the SDK pager and gives
    unambiguous status codes, so validation feels instant instead of a multi-second hang."""
    if not key:
        return False
    try:
        import requests
        r = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": key, "pageSize": 1},
            timeout=timeout,
        )
        if r.status_code == 200:
            return True
        if r.status_code in (400, 401, 403):
            return False
        return None
    except Exception:
        return None


def data_dir() -> str | None:
    return os.environ.get("TASKFLOW_DATA_PATH")


def ensure_data_dir() -> str:
    """Guarantee a usable TaskFlow data directory exists — so Nova runs on a clean
    machine with zero setup (the judge / first-run experience).

    Precedence: TASKFLOW_DATA_PATH → ~/.taskflow. If the chosen directory has no
    tasks.json yet, it's seeded from the bundled demo data (never clobbering a real
    TaskFlow install — we only write when tasks.json is absent). Exports
    TASKFLOW_DATA_PATH so every downstream reader resolves to the same place.
    """
    import json as _json
    import shutil as _shutil
    from pathlib import Path as _Path

    explicit = os.environ.get("TASKFLOW_DATA_PATH")
    target = _Path(explicit).expanduser() if explicit else (_Path.home() / ".taskflow")
    target.mkdir(parents=True, exist_ok=True)

    seeded = False
    tasks = target / "tasks.json"
    if not tasks.exists():
        seed = _Path(__file__).resolve().parent / "seed" / "tasks.json"
        if seed.exists():
            _shutil.copyfile(seed, tasks)
            seeded = True
        else:
            tasks.write_text("[]", encoding="utf-8")

    cfg = target / "config.json"
    if not cfg.exists():
        cfg.write_text(_json.dumps({"nova_data_enabled": True, "first_run_complete": True},
                                   indent=2), encoding="utf-8")

    # Seed a demo Scout feed too (only if absent) so the Opportunities panel isn't empty
    # on a clean machine. A user with a live Opportunity Hunter points Nova at its output
    # via NOVA_OPPORTUNITIES_PATH instead (that env var wins over this file).
    opps = target / "opportunities.json"
    if not opps.exists():
        seed_opps = _Path(__file__).resolve().parent / "seed" / "opportunities.json"
        if seed_opps.exists():
            _shutil.copyfile(seed_opps, opps)

    os.environ["TASKFLOW_DATA_PATH"] = str(target)
    if seeded:
        print(f"[nova] Seeded a demo board into {target} — Nova is ready to explore.", flush=True)
        print("[nova] (The TaskFlow CLI is a separate, optional app; you do NOT need it. "
              "If you already use it, Nova reads your real board automatically.)", flush=True)
    return str(target)
