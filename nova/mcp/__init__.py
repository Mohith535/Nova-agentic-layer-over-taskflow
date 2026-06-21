"""Nova's MCP layer — the TaskFlow data boundary.

`taskflow_reader` (read-only, path-safe) lands first; `tools.py` (the MCP tool surface) and
`server.py` (localhost-only MCP server) build on it.
"""
