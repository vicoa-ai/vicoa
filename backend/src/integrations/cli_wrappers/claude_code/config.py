"""
Configuration module for Claude Code Wrapper.

This module contains all configuration constants, patterns, and configuration classes
used by the Claude Code wrapper. Centralizing configuration makes it easy to:
- Find and update patterns when Claude CLI changes
- Test configuration in isolation
- Document configuration options clearly
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple


# ==================== Paths and Directories ====================

CLAUDE_LOG_BASE = Path.home() / ".claude" / "projects"
VICOA_WRAPPER_LOG_DIR = Path.home() / ".vicoa" / "claude_wrapper"


# ==================== Permission Mode Configuration ====================

# Keywords that map to each permission mode (case-insensitive matching)
PERMISSION_MODE_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "plan": ("plan",),
    "acceptEdits": (
        "accept edits",
        "auto accept",
        "accept-edits",
        "acceptedits",
        "acceptEdits",
    ),
    "default": (
        "default",
        "manual",
        "shortcuts",
        "standard",
    ),
    "bypassPermissions": (
        "bypass permissions",
        "bypass-permissions",
        "bypassPermissions",
        "bypasspermissions",
    ),
    "auto": ("auto mode", "auto"),
}

# Display labels for each permission mode. These are user-facing — they
# appear in feedback messages like "Permission mode changed to <label>".
# Detection keywords (PERMISSION_MODE_KEYWORDS above) stay verbatim so the
# TUI's "⏵⏵ bypass permissions on" status line still maps to the slug.
PERMISSION_MODE_LABELS: Dict[str, str] = {
    "default": "default mode",
    "plan": "plan mode",
    "acceptEdits": "accept edits",
    "bypassPermissions": "Yolo",
    "auto": "auto mode",
}


# ==================== Thinking Toggle Configuration ====================

# Pattern to detect thinking toggle in terminal output
THINKING_TOGGLE_PATTERN = re.compile(
    r"Thinking (on|off)\s*\(tab to toggle\)", re.IGNORECASE
)

# Keywords that map to thinking states (case-insensitive matching)
THINKING_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "on": ("on", "enabled", "active"),
    "off": ("off", "disabled", "inactive"),
}

# Display labels for thinking toggle
THINKING_LABELS: Dict[str, str] = {
    "on": "thinking on",
    "off": "thinking off",
}


# ==================== Detection Patterns ====================

# Control command pattern - detects JSON control commands in terminal output
CONTROL_JSON_PATTERN = re.compile(r'\{[^}]*"type"\s*:\s*"control"[^}]*\}')

# Permission mode pattern - detects permission mode display in terminal
PERMISSION_MODE_PATTERN = re.compile(
    r"([^\n\r]+?)\s*(?:\(shift\+tab to cycle\)|\?\s+for\s+shortcuts)",
    re.IGNORECASE,
)


# ==================== Terminal Configuration ====================

# Maximum terminal buffer size (bytes) to keep in memory
TERMINAL_BUFFER_MAX_SIZE = 200000  # 200KB

# Default idle delay (seconds) before considering Claude idle
DEFAULT_IDLE_DELAY = 3.5

# Heartbeat interval (seconds) for keepalive pings
DEFAULT_HEARTBEAT_INTERVAL = 30.0


# ==================== Toggle Configuration ====================


@dataclass
class ToggleConfig:
    """Configuration for a single toggle setting (permission_mode or thinking)."""

    # Current state (slug/normalized value)
    current_slug: Optional[str] = None

    # Last display text seen in terminal
    last_display: Optional[str] = None

    # Target value we're trying to set
    pending_target: Optional[str] = None

    # Cycle order for this toggle
    cycle: Tuple[str, ...] = field(default_factory=tuple)

    # Key sequence to send to Claude to toggle
    key_sequence: bytes = b""

    # Keyword mapping for detecting values
    keywords: Dict[str, Tuple[str, ...]] = field(default_factory=dict)

    # Display labels for values
    labels: Dict[str, str] = field(default_factory=dict)


# ==================== Wrapper Configuration ====================


@dataclass
class ClaudeWrapperConfig:
    """Main configuration for ClaudeWrapper.

    This dataclass contains all configuration options for the Claude Code wrapper.
    It provides validation and sensible defaults.
    """

    # ===== Authentication =====
    api_key: Optional[str] = None
    base_url: str = ""  # Will be set from DEFAULT_API_URL

    # ===== Agent Configuration =====
    name: str = "Claude Code"
    agent_instance_id: str = ""  # Will be set to UUID if empty
    is_resuming: bool = False

    # ===== Permission Configuration =====
    permission_mode: Optional[str] = None
    dangerously_skip_permissions: bool = False

    # ===== Timing Configuration =====
    idle_delay: float = DEFAULT_IDLE_DELAY
    heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL

    # ===== Terminal Configuration =====
    terminal_buffer_max_size: int = TERMINAL_BUFFER_MAX_SIZE

    # ===== Logging Configuration =====
    log_dir: Path = VICOA_WRAPPER_LOG_DIR

    # ===== Git Tracking =====
    enable_git_tracking: bool = True

    def __post_init__(self):
        """Validate configuration after initialization."""
        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Ensure agent_instance_id is set
        if not self.agent_instance_id:
            import uuid

            self.agent_instance_id = str(uuid.uuid4())

        # Validate idle_delay
        if self.idle_delay < 0:
            raise ValueError("idle_delay must be non-negative")

        # Validate heartbeat_interval
        if self.heartbeat_interval <= 0:
            raise ValueError("heartbeat_interval must be positive")

        # Validate terminal buffer size
        if self.terminal_buffer_max_size <= 0:
            raise ValueError("terminal_buffer_max_size must be positive")

    @classmethod
    def from_args(
        cls,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        permission_mode: Optional[str] = None,
        dangerously_skip_permissions: bool = False,
        name: str = "Claude Code",
        idle_delay: float = DEFAULT_IDLE_DELAY,
        agent_instance_id: Optional[str] = None,
        is_resuming: bool = False,
        **kwargs,
    ) -> "ClaudeWrapperConfig":
        """Create configuration from command-line arguments.

        This factory method handles environment variable fallbacks and provides
        a convenient way to construct the config from parsed arguments.
        """
        import os
        from vicoa.constants import DEFAULT_API_URL

        return cls(
            api_key=api_key or os.environ.get("VICOA_API_KEY"),
            base_url=base_url or os.environ.get("VICOA_BASE_URL", DEFAULT_API_URL),
            permission_mode=permission_mode,
            dangerously_skip_permissions=dangerously_skip_permissions,
            name=os.environ.get("VICOA_AGENT_DISPLAY_NAME") or name,
            idle_delay=idle_delay,
            agent_instance_id=agent_instance_id
            or os.environ.get("VICOA_AGENT_INSTANCE_ID")
            or "",
            is_resuming=is_resuming,
            **kwargs,
        )


# ==================== Toggle Initialization ====================


def create_default_toggles() -> Dict[str, ToggleConfig]:
    """Create default toggle configuration for permission_mode and thinking.

    Returns:
        Dictionary mapping toggle names to their configurations
    """
    return {
        "permission_mode": ToggleConfig(
            current_slug=None,
            last_display=None,
            pending_target=None,
            cycle=("default", "acceptEdits", "plan"),
            key_sequence=b"\x1b[Z",  # Shift+Tab
            keywords=PERMISSION_MODE_KEYWORDS,
            labels=PERMISSION_MODE_LABELS,
        ),
        "thinking": ToggleConfig(
            current_slug=None,  # Unknown initially
            last_display=None,
            pending_target=None,
            cycle=("off", "on"),
            key_sequence=b"\t",  # Tab
            keywords=THINKING_KEYWORDS,
            labels=THINKING_LABELS,
        ),
    }
