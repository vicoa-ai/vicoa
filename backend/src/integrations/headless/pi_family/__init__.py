"""Native RPC integration for the Pi family of coding agents.

Two agents, one wrapper: **Pi** (``@earendil-works/pi-coding-agent``) and
**Oh My Pi** / ``omp`` (``@oh-my-pi/pi-coding-agent``, a fork of Pi). Their
stdio JSONL RPC protocols are the same shape; every difference is one row in
:data:`~integrations.headless.pi_family.spec.PI_FAMILY_AGENTS` rather than a
second wrapper tree.

Design and the measured protocol notes live in
``plans/todos/pi-oh-my-pi-integration.md``; the wire traces the parsers were
written against are archived under
``integrations/headless/tests/fixtures/omp/``.

Portions of the protocol handling are modelled on the ``pi`` / ``omp``
providers in `paseo <https://github.com/badlogic/paseo>`_ (Apache-2.0,
Copyright (c) 2025-present Mohamed Boudra). See ``NOTICE``.
"""

from integrations.headless.pi_family.spec import (
    PI_FAMILY_AGENTS,
    PiFamilySpec,
    resolve_agent_binary,
)

__all__ = ["PI_FAMILY_AGENTS", "PiFamilySpec", "resolve_agent_binary"]
