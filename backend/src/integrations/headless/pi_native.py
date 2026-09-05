#!/usr/bin/env python3
"""Daemon entry point for the Pi-family agents (``pi`` and ``omp``).

One module, two agents — which one is selected by ``--agent``::

    python -m integrations.headless.pi_native --agent omp \
        --api-key ... --base-url ... --project-path ... [--session-id ...]
        [--model ...] [--thinking-effort ...] [--permission-mode ...]
        [--prompt ...]

Everything lives in ``integrations.headless.pi_family``; this file only exists
so the daemon has a stable module to spawn, mirroring ``codex_native.py`` and
``generic_acp.py``.
"""

import sys

from integrations.headless.pi_family.runner import main


if __name__ == "__main__":
    sys.exit(main())
