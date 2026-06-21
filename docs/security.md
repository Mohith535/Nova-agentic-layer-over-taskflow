# Security

Nova handles personal behavioral data for a Concierge-track agent, so security is designed in, not
bolted on. The threat model and the mitigation for each:

| Threat | Mitigation | Where |
|---|---|---|
| Network exposure of personal data | MCP runs over **stdio** — no socket. HTTP transport (if ever enabled) refuses any non-loopback bind. | `mcp/server.py`, `security/data_guard.py` |
| Path traversal (read or write outside the data dir) | Every file path is resolved and verified inside the data dir via `realpath` + `commonpath`; escapes raise. | `mcp/taskflow_reader.py`, `taskflow_writer.py` |
| Injection / malformed writes from an LLM or prompt | Fail-closed input validation: control-char stripping, length caps, enum/normalizer routing through TaskFlow's own `normalize_*`. | `security/input_validator.py` |
| Silent / unaccountable mutation | Every write is appended to a local `nova_audit.log` (append-only). | `security/audit.py`, `mcp/tools.py` |
| Data exfiltration to the model | Only *derived* context is sent to the LLM (never raw files), gated by TaskFlow's `nova_data_enabled` consent toggle. `NOVA_MODEL_BACKEND=local` removes the cloud call entirely. | `agents/*`, `security/data_guard.py` |
| Over-privileged agents | Least privilege by composition: Coach + Briefing get read-only tools; only Planning gets write tools. | `agents/tools_adk.py`, `orchestrator.py` |
| Data corruption under concurrent writes | Atomic temp+replace + in-process write lock (matches TaskFlow's own guarantee). | `mcp/taskflow_writer.py` |
| Secret leakage | API key from env / `.env` (gitignored); `.env.example` committed; no key in code. | `config.py`, `.gitignore` |

## The honest boundary

Nova is **local-first, not air-gapped** (unless you choose the local model backend). TaskFlow's
files never leave your machine; what *does* leave — only when you've enabled behavioral data — is
the minimal derived context an agent needs to reason, sent to your chosen LLM. We state this
plainly rather than claim "no data ever leaves," because a security claim is only worth anything if
it's true. For a zero-egress setup, set `NOVA_MODEL_BACKEND=local`.

## Inherited posture

Nova builds on TaskFlow v9.0.0's shipped hardening: CSRF + Host-header validation and a CSP on the
dashboard, output escaping for user content, `/static/` path-traversal containment, removal of the
last CDN (verified-offline), and private (0700) data-dir permissions on POSIX.
