"""PTY (Pseudo-Terminal) management for Claude CLI interaction.

This module handles creation and management of a pseudo-terminal for
interacting with the Claude CLI. It provides:
- PTY creation and process forking
- Terminal size management
- Non-blocking I/O operations
- Signal handling (Ctrl+Z)
"""

import errno
import os
import signal
import struct
import sys
import time
from typing import Callable, List, Optional, Tuple

# ``fcntl``/``pty``/``termios``/``tty`` are POSIX-only, but ``machine_daemon``
# imports this module on every platform (terminal RPC is wired unconditionally),
# so the import must not crash the Windows daemon binary. PTY creation itself is
# gated to POSIX in ``create_pty`` below; Windows ConPTY support is future work.
_POSIX = sys.platform != "win32"
if _POSIX:
    import fcntl
    import pty
    import termios
    import tty


class PTYManager:
    """Manages pseudo-terminal for Claude CLI interaction.

    This class handles all PTY-related operations including:
    - Creating PTY and forking Claude CLI process
    - Setting terminal size
    - Reading/writing to PTY with proper error handling
    - Signal handling for suspension (Ctrl+Z)
    """

    def __init__(self, log_func: Optional[Callable[[str], None]] = None):
        """Initialize PTY manager.

        Args:
            log_func: Optional logging function
        """
        self.log_func = log_func or (lambda msg: None)
        self.child_pid: Optional[int] = None
        self.master_fd: Optional[int] = None
        self.original_tty_attrs: Optional[list] = None

    def create_pty(self, cmd: List[str], env: Optional[dict] = None) -> Tuple[int, int]:
        """Create a PTY and fork the Claude CLI process.

        Args:
            cmd: Command and arguments to execute
            env: Optional environment variables to set

        Returns:
            Tuple of (child_pid, master_fd)

        Raises:
            RuntimeError: If PTY creation fails
        """
        if not _POSIX:
            raise RuntimeError(
                "PTY sessions are not supported on Windows yet "
                "(no ConPTY backend); terminal features are POSIX-only."
            )

        # Save original terminal settings
        try:
            self.original_tty_attrs = termios.tcgetattr(sys.stdin)
        except Exception as e:
            self.log_func(f"[WARNING] Could not save terminal attributes: {e}")
            self.original_tty_attrs = None

        # Get terminal size
        try:
            cols, rows = os.get_terminal_size()
            self.log_func(f"[INFO] Terminal size: {cols}x{rows}")
        except Exception:
            cols, rows = 80, 24
            self.log_func("[WARNING] Could not get terminal size, using default 80x24")

        # Create PTY
        self.child_pid, self.master_fd = pty.fork()

        if self.child_pid == 0:
            # Child process - exec Claude CLI
            if env:
                for key, value in env.items():
                    os.environ[key] = value

            try:
                os.execvp(cmd[0], cmd)
            except Exception as e:
                print(f"Failed to execute command: {e}", file=sys.stderr)
                sys.exit(1)

        # Parent process - set PTY size
        if self.child_pid > 0:
            self._set_terminal_size(rows, cols)
            self._set_nonblocking()

        return self.child_pid, self.master_fd

    def _set_terminal_size(self, rows: int, cols: int) -> None:
        """Set the terminal size for the PTY.

        Args:
            rows: Number of rows
            cols: Number of columns
        """
        if self.master_fd is None:
            return

        try:
            # TIOCSWINSZ constant differs by platform
            TIOCSWINSZ = 0x5414  # Linux
            if sys.platform == "darwin":
                TIOCSWINSZ = 0x80087467  # macOS

            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, TIOCSWINSZ, winsize)
            self.log_func(f"[INFO] Set PTY terminal size to {cols}x{rows}")
        except Exception as e:
            self.log_func(f"[WARNING] Failed to set terminal size: {e}")

    def _set_nonblocking(self) -> None:
        """Set non-blocking mode on the PTY master file descriptor."""
        if self.master_fd is None:
            return

        try:
            flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            self.log_func("[INFO] Set PTY to non-blocking mode")
        except Exception as e:
            self.log_func(f"[WARNING] Failed to set non-blocking mode: {e}")

    def set_raw_mode(self) -> None:
        """Set stdin to raw mode for pass-through input."""
        if self.original_tty_attrs:
            try:
                tty.setraw(sys.stdin)
                self.log_func("[INFO] Set stdin to raw mode")
            except Exception as e:
                self.log_func(f"[WARNING] Failed to set raw mode: {e}")

    def restore_terminal(self) -> None:
        """Restore terminal to original settings."""
        if self.original_tty_attrs:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.original_tty_attrs)
                self.log_func("[INFO] Restored terminal settings")
            except Exception as e:
                self.log_func(f"[WARNING] Failed to restore terminal: {e}")

    def write_to_pty(self, data: bytes) -> None:
        """Write data to the PTY master, handling partial writes.

        Args:
            data: Bytes to write to PTY

        Raises:
            RuntimeError: If PTY is not initialized
            OSError: If write fails (other than EAGAIN/EWOULDBLOCK)
        """
        if not data:
            return

        if self.master_fd is None:
            raise RuntimeError("PTY master file descriptor is not initialized")

        view = memoryview(data)
        total_written = 0

        while total_written < len(view):
            try:
                written = os.write(self.master_fd, view[total_written:])
                if written == 0:
                    time.sleep(0.01)
                    continue
                total_written += written
            except OSError as e:
                if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    time.sleep(0.01)
                    continue
                raise

    def read_from_pty(self, size: int = 4096) -> bytes:
        """Read data from PTY master (non-blocking).

        Args:
            size: Maximum number of bytes to read

        Returns:
            Bytes read from PTY (empty if no data available or child exited)

        Raises:
            RuntimeError: If PTY is not initialized
            OSError: If read fails (propagated to caller for exit detection)

        Note:
            - Returns empty bytes (b"") if EAGAIN/EWOULDBLOCK (no data ready)
            - Returns empty bytes (b"") if child has exited (EOF on PTY)
            - Raises OSError for other errors (caller should handle and exit)
        """
        if self.master_fd is None:
            raise RuntimeError("PTY master file descriptor is not initialized")

        try:
            data = os.read(self.master_fd, size)
            # os.read returns empty bytes when:
            # 1. PTY is closed (child exited) - this is what we want to detect
            # 2. No data available in non-blocking mode (shouldn't happen after select)
            return data
        except OSError as e:
            if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                # No data available (shouldn't happen if called after select)
                return b""
            # Other OSError (likely child exit or broken pipe) - propagate to caller
            raise

    def suspend_for_ctrl_z(self) -> None:
        """Handle Ctrl+Z: restore TTY, suspend child and self.

        This properly handles suspension when in raw mode.
        """
        try:
            self.log_func("[INFO] Ctrl+Z detected: suspending")

            # Restore terminal
            self.restore_terminal()

            # Send SIGTSTP to child process
            if self.child_pid:
                try:
                    os.kill(self.child_pid, signal.SIGTSTP)
                except Exception as e:
                    self.log_func(f"[WARNING] Failed to SIGTSTP child: {e}")

            # Suspend this process
            try:
                os.kill(os.getpid(), signal.SIGTSTP)
            except Exception as e:
                self.log_func(f"[WARNING] Failed to SIGTSTP self: {e}")

        except Exception as e:
            self.log_func(f"[ERROR] Error handling Ctrl+Z: {e}")

    def _signal_child(self, sig: int, kill_group: bool) -> None:
        """Deliver ``sig`` to the child, preferring its whole process group.

        The child is a session/process-group leader (``pty.fork`` calls
        ``setsid``), so signalling the group (``killpg``) reaches shell children
        that live in the leader's group — not just the shell itself. Foreground
        jobs that job-control put in their own group still get SIGHUP when the
        leader dies, so between the two a running command is reliably torn down.
        Best-effort: a ``ProcessLookupError`` just means it already exited.
        """
        if self.child_pid is None:
            return
        if kill_group:
            try:
                os.killpg(os.getpgid(self.child_pid), sig)
                return
            except ProcessLookupError:
                return
            except OSError as e:
                # Fall back to the bare pid (e.g. getpgid/killpg unsupported).
                self.log_func(f"[WARNING] killpg failed, using pid: {e}")
        try:
            os.kill(self.child_pid, sig)
        except ProcessLookupError:
            pass

    def close(self, kill_group: bool = False) -> None:
        """Close the PTY and clean up resources.

        ``kill_group`` signals the child's whole process group (used by the
        desktop terminal so a shell's running command dies with the tab); the
        default keeps the single-process behaviour the Claude wrapper relies on.
        """
        # Terminate child process first
        if self.child_pid is not None:
            try:
                self._signal_child(signal.SIGTERM, kill_group)
                self.log_func(f"[INFO] Sent SIGTERM to child process {self.child_pid}")
            except Exception as e:
                self.log_func(f"[WARNING] Error terminating child: {e}")

            # Wait up to 3s for graceful exit, then SIGKILL.
            exited = self.wait_for_child(timeout=3.0)
            if exited is None:
                try:
                    self._signal_child(signal.SIGKILL, kill_group)
                    self.log_func(
                        f"[INFO] Sent SIGKILL to child process {self.child_pid}"
                    )
                    self.wait_for_child(timeout=2.0)
                except Exception as e:
                    self.log_func(f"[WARNING] SIGKILL failed: {e}")
            else:
                self.log_func("[INFO] Child process exited cleanly")
            self.child_pid = None

        # Close master FD
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
                self.log_func("[INFO] Closed PTY master FD")
            except Exception as e:
                self.log_func(f"[WARNING] Error closing PTY: {e}")
            finally:
                self.master_fd = None

        # Restore terminal settings
        self.restore_terminal()

    def is_child_alive(self) -> bool:
        """Check if child process is still alive.

        Returns:
            True if child process is running, False otherwise
        """
        if self.child_pid is None:
            return False

        try:
            # Send signal 0 to check if process exists
            os.kill(self.child_pid, 0)
            return True
        except OSError:
            return False

    def wait_for_child(self, timeout: Optional[float] = None) -> Optional[int]:
        """Wait for child process to exit.

        Args:
            timeout: Optional timeout in seconds (None = wait indefinitely)

        Returns:
            Exit code of child process, or None if timeout
        """
        if self.child_pid is None:
            return None

        try:
            import time

            start_time = time.time()

            while True:
                # Try non-blocking wait
                pid, status = os.waitpid(self.child_pid, os.WNOHANG)

                if pid != 0:
                    # Child exited
                    exit_code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
                    self.log_func(f"[INFO] Child process exited with code {exit_code}")
                    return exit_code

                # Check timeout
                if timeout is not None and (time.time() - start_time) >= timeout:
                    self.log_func("[WARNING] Timeout waiting for child process")
                    return None

                time.sleep(0.1)

        except Exception as e:
            self.log_func(f"[WARNING] Error waiting for child: {e}")
            return None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - clean up resources."""
        self.close()
        return False
