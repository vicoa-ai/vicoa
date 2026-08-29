# Wire-format contracts shared between the backend (which serves them) and
# CLI / web / mobile clients (which consume them). Kept as a standalone
# top-level package — separate from `shared/` (backend↔servers DB and infra)
# — so the CLI wheel can ship contract modules without dragging server-side
# infrastructure into the user-facing distribution.
