"""Guards that keep personal data on the machine.

Nova's posture is **local-first by construction**:

- The MCP server runs over **stdio** by default — there is no socket, so there is no network
  surface to attack. This is the strongest possible answer to "could my task data leak?"
- If an HTTP/SSE transport is ever enabled, `assert_local_host` refuses any bind address
  other than loopback, so the server can never be exposed to the network.
- The only outbound call Nova makes is to the chosen LLM, and only with the user's consent
  (TaskFlow's `nova_data_enabled` gate) and only *derived* context — never the raw files.
"""

from __future__ import annotations

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


class SecurityError(RuntimeError):
    pass


def assert_local_host(host: str) -> str:
    """Refuse any non-loopback bind address (defense against 0.0.0.0 exposure)."""
    if host not in _LOOPBACK:
        raise SecurityError(
            f"Refusing to bind Nova to {host!r}. The MCP server is localhost-only."
        )
    return host
