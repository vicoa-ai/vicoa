"""Re-export shim — the canonical agent catalog lives in ``protocol.agent_catalog``.

The catalog is a wire-format contract (served via ``GET /api/v1/agent-catalog``,
consumed by the CLI daemon, web, and mobile), so it lives in the top-level
``protocol/`` package rather than ``shared/`` — which is reserved for the
backend↔servers DB and infra and is intentionally not shipped in the CLI wheel.
Backend callers can keep importing ``from shared.agent_catalog`` unchanged
via this module.
"""

from __future__ import annotations

from protocol.agent_catalog import (
    AGENT_CATALOG,
    AGENT_CATALOG_ETAG,
    AGENT_CATALOG_JSON,
    PERMISSION_MODES,
    REASONING_EFFORTS,
    THINKING_EFFORTS,
)

__all__ = [
    "AGENT_CATALOG",
    "AGENT_CATALOG_ETAG",
    "AGENT_CATALOG_JSON",
    "PERMISSION_MODES",
    "REASONING_EFFORTS",
    "THINKING_EFFORTS",
]
