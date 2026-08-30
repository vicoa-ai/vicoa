"""Vicoa-owned terminal primitives.

``PTYManager`` moved here from the Claude wrapper (file move, byte-identical
behavior — the old path re-exports it). ``TerminalService`` hosts
renderer-driven PTY sessions for the desktop terminal tab; it is used only by
the local server (``vicoa.local_server``).
"""

from .pty_manager import PTYManager
from .service import TerminalService

__all__ = ["PTYManager", "TerminalService"]
