# AGENTS.md — canonical instructions for Nova

This file orients any AI coding agent (or human) working in this repo. Nova is a multi-agent
productivity layer over **TaskFlow v9.1.0**; TaskFlow is the execution engine, Nova is its brain.

## What this project is
- A **router orchestrator** (ADK) over three specialists: `briefing` (read-only), `planning`
  (the only writer), `coach` (read-only).
- An **MCP server** (`nova/mcp/server.py`, stdio) exposing 8 typed TaskFlow tools.
- Built so the same tool logic (`nova/mcp/tools.py → NovaTools`) is callable both in-process by
  the agents and over MCP by external clients.

## Hard rules (do not break)
1. **Voice.** Nova talks like a thoughtful colleague who has read the research — never a
   motivational app. The Coach: (1) names the pattern with the number, (2) names the mechanism,
   (3) gives one concrete change. Never "don't worry" / "you've got this". No emoji. Judgment-free:
   "overdue is a starting point, not a scarlet letter."
2. **Grounded, not invented.** Agents must call the tools and reason over real data. Never
   fabricate a statistic or a pattern. If the data is thin, say so.
3. **Least privilege.** Coach and Briefing are read-only. Only Planning writes. Keep it that way.
4. **Local-first.** No new network calls except the chosen LLM, and only with consent
   (`nova_data_enabled`) and minimal derived context — never raw files. MCP stays stdio /
   loopback-only.
5. **Reads stay inside the data dir.** All file access goes through `TaskFlowReader` /
   `TaskFlowWriter` (path-contained, atomic). Don't parse `~/.taskflow` by hand elsewhere.
6. **Validate every write.** Route inputs through `nova/security/input_validator.py`, which
   reuses TaskFlow's own normalizers. Audit every write.

## Layout
```
nova/
  config.py                 env/key/model resolution
  orchestrator.py           ADK root router → 3 sub-agents
  main.py / __main__.py     `nova` CLI (brief|plan|coach|ask|mcp)
  agents/                   briefing · planning · coach · tools_adk (ADK function tools)
  mcp/                      taskflow_reader · taskflow_writer · tools (NovaTools) · server (FastMCP)
  security/                 input_validator · audit · data_guard
```

## How to run / verify
```bash
nova mcp --selftest                      # list MCP tools (no key)
TASKFLOW_DATA_PATH=docs/sample_taskflow nova brief    # brief on the sample data (needs key)
nova ask --mcp "what should I do now?"   # agents pull tools from the LIVE MCP server (stdio subprocess)
python -m nova.mcp.server                # serve MCP over stdio to any client
python eval/run_eval.py                  # key-free eval of the data layer + MCP least-privilege
```
Verification without a key covers a lot: imports, `nova mcp --selftest`, and building the
orchestrator (3 sub-agents + tool boundaries). The live LLM path needs `GEMINI_API_KEY`.

## Model
`gemini-2.5-flash` by default (`NOVA_GEMINI_MODEL`); `NOVA_MODEL_BACKEND=local` for an offline
Ollama backend.
