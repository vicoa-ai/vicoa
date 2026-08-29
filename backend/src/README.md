# src/

This directory contains all source code for the Vicoa project.

## Structure

- **`vicoa/`** - Main Python package (CLI & SDK)
- **`backend/`** - FastAPI web dashboard API
- **`servers/`** - MCP & REST servers
  - `mcp/` - MCP protocol server
  - `api/` - REST API server
  - `shared/` - Shared server code
- **`shared/`** - Shared database models and configurations
- **`integrations/`** - Integration connectors (flat structure)
  - `cli_wrappers/` - Claude Code, Codex CLI wrappers
  - `headless/` - Background agent runners
  - `github/` - GitHub Actions YAML
  - `utils/` - Shared integration utilities
  - `webhooks/` - Webhook handlers

This flattened organization provides clear separation by function while keeping related code together.