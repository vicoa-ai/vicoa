"""Compatibility shim — ``PTYManager`` moved to ``vicoa.terminal.pty_manager``.

The class was extracted (file move, byte-identical behavior) so the desktop
app's local terminal service can reuse it without importing the Claude wrapper
(plans/todos/desktop-app-v1-implementation.md, architecture decision 6). This
module re-exports it so existing wrapper imports keep working unchanged.
"""

from vicoa.terminal.pty_manager import PTYManager

__all__ = ["PTYManager"]
