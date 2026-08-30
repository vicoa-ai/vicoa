"""Build the ``instance_metadata.usage`` blob from agent stream events.

Two independent sub-structures ride the same blob:

* ``context`` — the per-conversation token fill (used / max) plus cumulative
  session cost. Refreshed on every assistant message, so it tracks a long turn
  instead of only landing once the turn ends.
* ``limits`` — the account's rate-limit windows (session / weekly, ...) plus an
  optional credit balance. Refreshed whenever the agent reports a change.

The data is captured **in-band** from data the headless integrations already
receive (Claude ``AssistantMessage`` / ``ResultMessage`` / ``RateLimitEvent``;
Codex ``thread/tokenUsage/updated`` / ``account/rateLimits/updated``) — nothing
here touches the network or the filesystem, so every function is trivially unit
testable. Deriving context from messages we already get is what lets the meter
update without an extra SDK round-trip that can time out and blank the ring.

``UsageState`` holds the merged blob for one session so that a context-only
update never clobbers last-known limits (and vice versa). Claude reports rate
limits one window at a time, so windows are upserted by id; Codex reports a full
snapshot, so :meth:`UsageState.set_limits` replaces them wholesale. A single
session only ever drives one agent, so the two never mix.

Shape (see plans/todos/usage-indicators.md for the canonical contract)::

    {
      "context": {"used_tokens": int, "max_tokens": int|None, "cost_usd": float|None},
      "limits": {
        "windows": [{"id": str, "label": str, "used_pct": float, "resets_at": str|None}],
        "credits": {"unit": "usd", "remaining": float}   # optional
      },
      "updated_at": "ISO-8601 UTC"
    }
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional

# ---------------------------------------------------------------------------
# Small coercion helpers (defensive against missing / mistyped stream fields)
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_from_epoch(epoch: Any) -> Optional[str]:
    """Convert a Unix epoch (seconds) into an ISO-8601 UTC string.

    Both Claude (``RateLimitInfo.resets_at``) and Codex (``resetsAt``) deliver
    reset times as epoch seconds. Returns ``None`` for missing or unparseable
    values rather than raising — a bad timestamp must never break a turn.
    """
    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat()
    except (OSError, ValueError, OverflowError, TypeError):
        return None


def _coerce_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _coerce_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Context window
# ---------------------------------------------------------------------------


def _context_blob(
    used_tokens: Optional[int],
    max_tokens: Optional[int],
    cost_usd: Optional[float],
) -> Optional[dict]:
    """Assemble the ``context`` sub-blob, or ``None`` if there's nothing to show.

    ``used_tokens`` of 0 is a real reading (a freshly compacted or brand-new
    conversation), so only ``None`` counts as absent.
    """
    if used_tokens is None and max_tokens is None and cost_usd is None:
        return None
    blob: Dict[str, Any] = {"used_tokens": int(used_tokens or 0)}
    blob["max_tokens"] = max_tokens
    blob["cost_usd"] = cost_usd
    return blob


def claude_context_used_tokens(usage: Optional[Mapping[str, Any]]) -> Optional[int]:
    """Context fill read from **one** request's usage dict.

    ``input_tokens + cache_creation + cache_read`` is the prompt the model just
    read — the entire conversation prefix, cached or not — and ``output_tokens``
    is what it appended. Together they're a point-in-time snapshot of the window,
    so the figure stays bounded by ``max_tokens``.

    Callers MUST overwrite with each new reading and never accumulate across a
    turn: summing re-counts the cached prefix once per round-trip and reports
    several times the window size (the 4M-token swings we shipped once already).
    An ``AssistantMessage.usage`` or one entry of ``ResultMessage.usage``'s
    ``iterations`` is a single request; the flat ``ResultMessage.usage`` is not.
    """
    if not isinstance(usage, Mapping):
        return None
    input_tokens = _coerce_int(usage.get("input_tokens"))
    if input_tokens is None or input_tokens < 0:
        return None
    total = input_tokens
    for key in (
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "output_tokens",
    ):
        value = _coerce_int(usage.get(key))
        if value and value > 0:
            total += value
    return total


def claude_context_used_from_result(
    usage: Optional[Mapping[str, Any]],
) -> Optional[int]:
    """Context fill from a ``ResultMessage.usage``, via its **last** iteration.

    ``iterations`` holds one entry per model request, so the last one is the
    final state of the window. The flat top-level dict is the turn's cumulative
    usage across every round-trip and is deliberately not used — summing it is
    exactly the over-reporting bug described in
    :func:`claude_context_used_tokens`.

    Only a backstop for turns whose assistant messages carried no usage; the
    per-message path is the primary source.
    """
    if not isinstance(usage, Mapping):
        return None
    iterations = usage.get("iterations")
    if not isinstance(iterations, list):
        return None
    for entry in reversed(iterations):
        if isinstance(entry, Mapping):
            used = claude_context_used_tokens(entry)
            if used is not None:
                return used
    return None


def claude_compaction_post_tokens(
    data: Optional[Mapping[str, Any]],
) -> Optional[int]:
    """Post-compaction context fill from a ``compact_boundary`` payload.

    The reading self-corrects on the next request anyway, but stamping it at the
    boundary avoids leaving a stale near-full meter on screen when a turn ends
    right after compacting. The CLI has shipped several spellings of both the
    metadata key and the token field, so accept the known variants.
    """
    if not isinstance(data, Mapping):
        return None
    for meta_key in ("compact_metadata", "compactMetadata", "compactionMetadata"):
        meta = data.get(meta_key)
        if not isinstance(meta, Mapping):
            continue
        for token_key in ("post_tokens", "postTokens"):
            value = _coerce_int(meta.get(token_key))
            if value is not None and value >= 0:
                return value
    return None


def claude_context_window_from_model_usage(
    model_usage: Optional[Mapping[str, Any]],
) -> Optional[int]:
    """Largest ``contextWindow`` across the models used this turn.

    ``ResultMessage.model_usage`` is keyed by model id. A turn that delegated to
    a smaller sub-model must not shrink the meter, so take the max rather than
    the first or last entry.
    """
    if not isinstance(model_usage, Mapping):
        return None
    best: Optional[int] = None
    for entry in model_usage.values():
        if not isinstance(entry, Mapping):
            continue
        window = _coerce_int(entry.get("contextWindow")) or _coerce_int(
            entry.get("context_window")
        )
        if window is None or window <= 0:
            continue
        best = window if best is None else max(best, window)
    return best


# Seed context-window sizes, used only until ``model_usage`` reports the real
# one. Keeping a seed means the ring renders on the first message of a session
# instead of staying blank until the first turn completes.
#
# These mirror Claude Code's window selection, NOT the API's model limits: the
# API serves 1M for every current Opus/Sonnet, but the CLI runs the bare id at
# 200k and only the explicit ``[1m]`` variant at 1M. Fable/Opus 5 are the
# exception — 1M is their default and only window, with no suffixed variant.
_CLAUDE_CONTEXT_WINDOWS: Dict[str, int] = {
    "claude-fable-5": 1_000_000,
    "claude-mythos-5": 1_000_000,
    "claude-opus-5": 1_000_000,
    "claude-opus-4-8[1m]": 1_000_000,
    "claude-opus-4-8": 200_000,
    "claude-sonnet-5[1m]": 1_000_000,
    "claude-sonnet-5": 200_000,
    "claude-opus-4-7[1m]": 1_000_000,
    "claude-opus-4-7": 200_000,
    "claude-opus-4-6[1m]": 1_000_000,
    "claude-opus-4-6": 200_000,
    "claude-sonnet-4-6[1m]": 1_000_000,
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5": 200_000,
}
_CLAUDE_DEFAULT_CONTEXT_WINDOW = 200_000


def claude_context_window_for_model(model: Optional[str]) -> Optional[int]:
    """Best-effort static window size for a Claude model id.

    Runtime ids carry a date suffix (and sometimes a provider prefix), so match
    on the longest known id contained in the string — longest-first matters
    because every ``[1m]`` id contains its own 200k base id.
    """
    if not model:
        return None
    needle = model.strip().lower()
    if not needle:
        return None
    for known in sorted(_CLAUDE_CONTEXT_WINDOWS, key=len, reverse=True):
        if known in needle:
            return _CLAUDE_CONTEXT_WINDOWS[known]
    return _CLAUDE_DEFAULT_CONTEXT_WINDOW if "claude" in needle else None


def codex_context(token_usage: Optional[Dict[str, Any]]) -> Optional[dict]:
    """Build ``context`` from a Codex ``thread/tokenUsage/updated`` payload.

    Uses the ``last`` breakdown (the current context size) for used tokens and
    ``modelContextWindow`` for the max, both camelCase per the app-server schema.
    """
    if not isinstance(token_usage, dict):
        return None
    breakdown = token_usage.get("last") or token_usage.get("total")
    used: Optional[int] = None
    if isinstance(breakdown, dict):
        used = _coerce_int(breakdown.get("totalTokens"))
    max_tokens = _coerce_int(token_usage.get("modelContextWindow"))
    return _context_blob(used, max_tokens, None)


# ---------------------------------------------------------------------------
# Rate-limit windows
# ---------------------------------------------------------------------------

# Claude ``RateLimitType`` -> display label. Keys mirror the SDK literal
# (claude_agent_sdk/types.py). Session/weekly wording matches the app UI.
_CLAUDE_WINDOW_LABELS = {
    "five_hour": "Session",
    "seven_day": "Weekly",
}


def claude_window(
    rate_limit_type: Optional[str],
    utilization: Optional[float],
    resets_at: Any,
) -> Optional[dict]:
    """Build one rate-limit window from a Claude ``RateLimitInfo``.

    ``utilization`` is a 0.0-1.0 fraction; we normalise to a 0-100 percentage.
    Only the Session (five_hour) and Weekly (seven_day) windows are surfaced;
    per-model and overage windows return ``None``, as does an event with no
    utilization to show.
    """
    label = _CLAUDE_WINDOW_LABELS.get(rate_limit_type or "")
    if label is None:
        return None
    pct = _coerce_float(utilization)
    if pct is None:
        return None
    return {
        "id": rate_limit_type,
        "label": label,
        "used_pct": round(pct * 100, 1),
        "resets_at": _iso_from_epoch(resets_at),
    }


def _codex_window(
    window: Optional[Dict[str, Any]], window_id: str, label: str
) -> Optional[dict]:
    if not isinstance(window, dict):
        return None
    pct = _coerce_float(window.get("usedPercent"))
    if pct is None:
        return None
    return {
        "id": window_id,
        "label": label,
        "used_pct": round(pct, 1),
        "resets_at": _iso_from_epoch(window.get("resetsAt")),
    }


def codex_limits(rate_limits: Optional[Dict[str, Any]]) -> Optional[dict]:
    """Build ``limits`` from a Codex ``account/rateLimits/updated`` snapshot.

    ``primary`` -> session window, ``secondary`` -> weekly window. ``credits``
    carries a USD balance as a string that we parse to a float.
    """
    if not isinstance(rate_limits, dict):
        return None
    windows: List[dict] = []
    session = _codex_window(rate_limits.get("primary"), "session", "Session")
    if session:
        windows.append(session)
    weekly = _codex_window(rate_limits.get("secondary"), "weekly", "Weekly")
    if weekly:
        windows.append(weekly)

    credits: Optional[dict] = None
    raw_credits = rate_limits.get("credits")
    if isinstance(raw_credits, dict):
        balance = _coerce_float(raw_credits.get("balance"))
        if balance is not None:
            credits = {"unit": "usd", "remaining": balance}

    if not windows and credits is None:
        return None
    limits: Dict[str, Any] = {"windows": windows}
    if credits is not None:
        limits["credits"] = credits
    return limits


# Anthropic ``/api/oauth/usage`` window keys -> display label, in display order.
# Only the two headline windows; per-model breakdowns are intentionally omitted.
_CLAUDE_OAUTH_WINDOWS = (
    ("five_hour", "Session"),
    ("seven_day", "Weekly"),
)


def _oauth_reset(value: Any) -> Optional[str]:
    """The OAuth usage API returns ``resets_at`` as an ISO string; older/other
    shapes may send epoch seconds. Accept both."""
    if isinstance(value, str):
        return value or None
    return _iso_from_epoch(value)


def claude_limits_from_oauth(response: Optional[Dict[str, Any]]) -> Optional[dict]:
    """Build ``limits`` from Anthropic's ``GET /api/oauth/usage`` response.

    Unlike the SDK's ``RateLimitEvent`` (fraction 0-1, epoch reset), this API
    returns ``utilization`` already as a 0-100 percent and ``resets_at`` as an
    ISO string. Only windows the account actually has are present. Returns
    ``None`` when there's nothing usable so callers can leave the section hidden.
    """
    if not isinstance(response, dict):
        return None
    windows: List[dict] = []
    for key, label in _CLAUDE_OAUTH_WINDOWS:
        entry = response.get(key)
        if not isinstance(entry, dict):
            continue
        pct = _coerce_float(entry.get("utilization"))
        if pct is None:
            continue
        windows.append(
            {
                "id": key,
                "label": label,
                "used_pct": round(pct, 1),
                "resets_at": _oauth_reset(entry.get("resets_at")),
            }
        )
    if not windows:
        return None
    return {"windows": windows}


# ---------------------------------------------------------------------------
# Rate-limit projection (server-side)
# ---------------------------------------------------------------------------


def _parse_iso(value: Any) -> Optional[datetime]:
    """Parse a ``resets_at`` ISO-8601 string back to an aware UTC datetime.

    The usage blob stores reset instants as ISO strings (``_iso_from_epoch`` /
    the OAuth path), so this is the inverse. Tolerant of a trailing ``Z`` and of
    a naive string (assumed UTC); returns ``None`` on anything unparseable — a
    bad reset time must never break the projection, it just means that window is
    not treated as blocking.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def project_rate_limited_until(
    usage: Optional[Mapping[str, Any]], *, buffer_s: int = 45
) -> Optional[datetime]:
    """Binding reset instant across maxed *time-window* limits, else ``None``.

    A session is blocked until the **latest** reset among the windows that are at
    or over their limit (``used_pct >= 100``) — continuing before that instant
    just re-hits the wall. Windows below the limit, and credit/money balances
    (which carry no ``resets_at`` and won't auto-lift on a timer), never
    contribute. This is a pure projection of the usage the daemon already
    PATCHes: a recovering turn whose windows have dropped back under 100 yields
    ``None``, which is how the ``rate_limited_until`` column clears itself.
    ``buffer_s`` pads the reset (~45s) to absorb clock/reset drift.
    """
    limits = (usage or {}).get("limits") or {}
    if not isinstance(limits, Mapping):
        return None
    resets: List[datetime] = []
    for window in limits.get("windows") or []:
        if not isinstance(window, Mapping):
            continue
        if (_coerce_float(window.get("used_pct")) or 0.0) < 100.0:
            continue
        reset = _parse_iso(window.get("resets_at"))
        if reset is not None:
            resets.append(reset)
    if not resets:
        return None
    return max(resets) + timedelta(seconds=buffer_s)


# ---------------------------------------------------------------------------
# Session-scoped state
# ---------------------------------------------------------------------------


@dataclass
class UsageState:
    """Merged usage blob for a single session.

    Mutators return ``True`` when they change the comparable core, so callers
    can skip a redundant PATCH (and its websocket broadcast). ``updated_at`` is
    deliberately excluded from the core so a no-op flush is detectable.
    """

    context: Optional[dict] = None
    windows: "OrderedDict[str, dict]" = field(default_factory=OrderedDict)
    credits: Optional[dict] = None
    # Sticky across the session: the window size and the running cost arrive on
    # different messages than the fill, and must survive updates that omit them.
    context_max_tokens: Optional[int] = None
    context_cost_usd: Optional[float] = None

    def set_context(self, context: Optional[dict]) -> bool:
        if context is None or context == self.context:
            return False
        self.context = context
        return True

    def latch_context_max(
        self, max_tokens: Optional[int], *, seed: bool = False
    ) -> bool:
        """Record the context-window size, re-stamping any fill already held.

        Sticky by design: a later ``None`` never clears it. Without this the
        percentage goes unknown whenever a message omits the size, and the web
        ring silently stops rendering (``lib/usage-view.ts`` needs a max to
        compute a percentage).

        ``seed=True`` marks a guess from a static per-model table: it fills the
        gap before the first authoritative reading but must never overwrite one,
        since a runtime model id can't always be told apart from its long-context
        variant.
        """
        if seed and self.context_max_tokens is not None:
            return False
        if (
            max_tokens is None
            or max_tokens <= 0
            or max_tokens == self.context_max_tokens
        ):
            return False
        self.context_max_tokens = max_tokens
        if self.context is not None:
            self.context = _context_blob(
                _coerce_int(self.context.get("used_tokens")),
                max_tokens,
                self.context_cost_usd,
            )
        return True

    def set_context_usage(
        self, used_tokens: Optional[int], cost_usd: Optional[float] = None
    ) -> bool:
        """Overwrite the context fill with a point-in-time reading.

        Never accumulates — see :func:`claude_context_used_tokens`. Cost only
        rides the end-of-turn result, so the last known value is carried forward
        rather than blanked by mid-turn updates.
        """
        if cost_usd is not None:
            self.context_cost_usd = cost_usd
        if used_tokens is None:
            return False
        return self.set_context(
            _context_blob(used_tokens, self.context_max_tokens, self.context_cost_usd)
        )

    def upsert_window(self, window: Optional[dict]) -> bool:
        """Merge a single window by id (Claude reports one window per event)."""
        if not window:
            return False
        window_id = window.get("id")
        if window_id is None:
            return False
        if self.windows.get(window_id) == window:
            return False
        self.windows[window_id] = window
        return True

    def set_limits(self, limits: Optional[dict]) -> bool:
        """Replace all windows + credits from a full snapshot (Codex)."""
        if limits is None:
            return False
        new_windows: "OrderedDict[str, dict]" = OrderedDict()
        for window in limits.get("windows", []):
            window_id = window.get("id")
            if window_id is not None:
                new_windows[window_id] = window
        new_credits = limits.get("credits")
        if new_windows == self.windows and new_credits == self.credits:
            return False
        self.windows = new_windows
        self.credits = new_credits
        return True

    def _limits(self) -> Optional[dict]:
        if not self.windows and self.credits is None:
            return None
        limits: Dict[str, Any] = {"windows": list(self.windows.values())}
        if self.credits is not None:
            limits["credits"] = self.credits
        return limits

    def core(self) -> Optional[dict]:
        """The comparable payload with no timestamp; ``None`` when empty."""
        limits = self._limits()
        if self.context is None and limits is None:
            return None
        core: Dict[str, Any] = {}
        if self.context is not None:
            core["context"] = self.context
        if limits is not None:
            core["limits"] = limits
        return core

    def blob(self) -> Optional[dict]:
        """The full blob to PATCH, timestamped; ``None`` when empty."""
        core = self.core()
        if core is None:
            return None
        return {**core, "updated_at": _now_iso()}
