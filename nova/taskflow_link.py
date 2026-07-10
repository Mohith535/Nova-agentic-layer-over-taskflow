"""Hand the user a link straight to a task in TaskFlow — or the CLI command if the UI is closed.

This is the other half of a bridge TaskFlow already built: its dashboard opens Nova with
``127.0.0.1:8765/?ask=…&mode=operator``. Nova had no way to send the user back.

Two lessons, learned the hard way, are baked in:

* **Probe with a socket, from the server.** The dashboard's CSP is ``connect-src 'self'``, so a
  browser ``fetch`` to another origin is silently blocked and *always* reports "down". Nova is a
  process, not a page, so it can just open a TCP connection and know the truth.
* **Degrade honestly.** If the dashboard isn't running, say so and give the command that works
  (``taskflow view <id>``) rather than handing over a link that opens a dead tab.
"""
from __future__ import annotations

import socket
from dataclasses import dataclass

DASHBOARD_HOST = "127.0.0.1"   # never "localhost": on Windows it resolves to ::1 first, where
DASHBOARD_PORT = 18083         # nothing is listening, and the probe wrongly reports "down".
PROBE_TIMEOUT_SECONDS = 1.0


def dashboard_is_running(host: str = DASHBOARD_HOST, port: int = DASHBOARD_PORT) -> bool:
    """True if something is accepting connections on TaskFlow's dashboard port."""
    try:
        with socket.create_connection((host, port), timeout=PROBE_TIMEOUT_SECONDS):
            return True
    except OSError:
        return False


@dataclass(frozen=True)
class TaskPointer:
    """How to reach one task, given what is actually running right now."""

    task_id: int
    url: str | None          # set when the dashboard is up
    command: str             # always set — the fallback that works with nothing running

    @property
    def is_clickable(self) -> bool:
        return self.url is not None

    def render(self) -> str:
        """One line to drop into an agent's answer."""
        if self.is_clickable:
            return f"Open it: {self.url}"
        return f"The dashboard isn't running — see it with:  {self.command}"


def taskflow_link(task_id: int, *, probe=dashboard_is_running) -> TaskPointer:
    """Point at a task the best way currently available.

    ``probe`` is injected so this is testable without binding a port.
    """
    if not isinstance(task_id, int) or isinstance(task_id, bool) or task_id <= 0:
        raise ValueError(f"task_id must be a positive integer, got {task_id!r}")

    command = f"taskflow view {task_id}"
    if probe():
        return TaskPointer(task_id, f"http://{DASHBOARD_HOST}:{DASHBOARD_PORT}/?task={task_id}", command)
    return TaskPointer(task_id, None, command)
