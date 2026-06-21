"""Nova evaluation harness.

The course covered *evaluating* agent workflows — most submissions skip this. These checks
assert the things that must be true for the agents to be trustworthy, and they run on the
committed sample so they're reproducible by a judge:

  1. The behavioral derivations are correct on known data (the Coach's evidence is real).
  2. The overdue-candidate ranking/exclusion is correct (the Briefing's recommendations).
  3. Least privilege holds *over MCP* — a read-only agent cannot reach write tools.
  4. (Optional, needs GEMINI_API_KEY) The live Coach grounds its answer in the real numbers
     and never lapses into cheerleading.

Run:  python eval/run_eval.py      (1–3 always run; 4 is skipped without a key)
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

SAMPLE = str(Path(__file__).resolve().parent.parent / "docs" / "sample_taskflow")
os.environ.setdefault("TASKFLOW_DATA_PATH", SAMPLE)

from nova.agents.mcp_backed import READ_ONLY_TOOLS, WRITE_TOOLS, mcp_toolset
from nova.mcp.tools import NovaTools

_results: list[tuple[str, bool]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    _results.append((name, bool(cond)))
    tag = "PASS" if cond else "FAIL"
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))


def _near(a: float, b: float, tol: float = 1e-3) -> bool:
    return abs(a - b) <= tol


def main() -> None:
    t = NovaTools(SAMPLE)

    print("1. Behavioral derivations (known sample):")
    bs = t.get_behavioral_stats()
    check("total tasks == 5", bs.total_tasks == 5, f"got {bs.total_tasks}")
    check("completion rate == 0.2", _near(bs.completion_rate, 0.2), f"got {bs.completion_rate}")
    check("deadline moves == 3", bs.deadline_moves == 3, f"got {bs.deadline_moves}")
    tags = {p.key: p.avg_postpone for p in bs.most_postponed}
    check("#course avg postpone == 4.0", _near(tags.get("course", -1), 4.0), f"got {tags.get('course')}")

    print("2. Today-context / overdue ranking:")
    ctx = t.get_today_context()
    check("overdue candidates capped at <=5", len(ctx.overdue_candidates) <= 5, f"{len(ctx.overdue_candidates)}")
    check("abandoned task (postpone>=5) excluded", all(c.id != 5 for c in ctx.overdue_candidates))

    print("3. Least privilege over MCP:")
    async def _mcp_names():
        ts = mcp_toolset(SAMPLE, READ_ONLY_TOOLS)
        try:
            return {getattr(x, "name", "?") for x in await ts.get_tools()}
        finally:
            try:
                await ts.close()
            except Exception:
                pass

    names = asyncio.run(_mcp_names())
    check("read-only agent sees exactly the 4 read tools", names == set(READ_ONLY_TOOLS), str(sorted(names)))
    check("write tools NOT exposed to a read-only agent", not (names & set(WRITE_TOOLS)))

    print("4. Live Coach grounding (optional — needs GEMINI_API_KEY):")
    from nova import config

    if not config.ensure_api_key():
        print("  [SKIP] no API key — skipping the live LLM check")
    else:
        from nova.agents.coach_agent import build_coach_agent
        from nova.main import _run_once

        out = _run_once(build_coach_agent(t), "What pattern should I fix? Be specific.").lower()
        check("coach cites a real signal (course / 0.2 / postpone)",
              any(k in out for k in ["course", "0.2", "postpone"]), out[:70])
        banned = ["you've got this", "you got this", "don't worry", "stay positive", "keep it up"]
        check("coach avoids cheerleading", not any(b in out for b in banned))

    passed = sum(1 for _, ok in _results if ok)
    print(f"\n{passed}/{len(_results)} checks passed.")
    sys.exit(0 if passed == len(_results) else 1)


if __name__ == "__main__":
    main()
