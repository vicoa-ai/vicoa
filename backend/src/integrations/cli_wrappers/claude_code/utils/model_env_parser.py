"""Normalize ANTHROPIC_MODEL into a catalog-matchable id.

Real-world ANTHROPIC_MODEL values come in three shapes:
- bare catalog id: ``claude-opus-4-7``
- region-prefixed: ``global.anthropic.claude-sonnet-4-6``
- Bedrock-versioned: ``us.anthropic.claude-haiku-4-5-20251001-v1:0``

We strip the optional ``<region>.anthropic.`` prefix and the optional
``-<8-digit-date>-v<n>:<m>`` suffix so the wrapper can pass a clean
``claude-*`` id into the spawn-time ``session_config``. Unknown shapes
fall through unchanged — the mobile pill's catalog reverse-lookup will
render the raw id rather than crashing.
"""

from __future__ import annotations

import re
from typing import Optional


_PREFIX_RE = re.compile(r"^(?:[a-z]+\.)?anthropic\.")
_BEDROCK_SUFFIX_RE = re.compile(r"-\d{8}-v\d+:\d+$")


def parse_anthropic_model_env(raw: Optional[str]) -> Optional[str]:
    """Return the catalog id for an ANTHROPIC_MODEL env value, or None.

    None / empty / whitespace inputs return None. Anything else has the
    region prefix and Bedrock suffix stripped (if present) before being
    returned.
    """
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    no_prefix = _PREFIX_RE.sub("", stripped)
    no_suffix = _BEDROCK_SUFFIX_RE.sub("", no_prefix)
    return no_suffix
