"""Main client for interacting with the Vicoa Agent Dashboard API."""

import logging
import os
import time
import uuid
from typing import Optional, Dict, Any, Union, List, Callable
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from vicoa.constants import DEFAULT_API_URL
from vicoa.machine_state import read_machine_id
from vicoa.utils import get_git_identity, get_worktree_name

from .exceptions import AuthenticationError, TimeoutError, APIError
from .models import (
    EndSessionResponse,
    CreateMessageResponse,
    PendingMessagesResponse,
    Message,
    RegisterAgentInstanceResponse,
)
from .utils import (
    validate_agent_instance_id,
    build_message_request_data,
)


class LoggingRetry(Retry):
    """Custom Retry class that logs retry attempts."""

    def __init__(self, *args, log_func=None, **kwargs):
        self._log_func = log_func
        super().__init__(*args, **kwargs)

    def new(self, **kw):
        """Ensure log_func is passed to new instances."""
        kw["log_func"] = self._log_func
        return super().new(**kw)

    def increment(
        self,
        method=None,
        url=None,
        response=None,
        error=None,
        _pool=None,
        _stacktrace=None,
    ):
        """Log retry attempts."""
        if self._log_func and error and self.total:
            remaining = self.total - 1 if self.total else 0
            if remaining >= 0:
                error_msg = str(error)
                if len(error_msg) > 100:
                    error_msg = error_msg[:100] + "..."
                self._log_func(
                    f"[WARNING] Retry attempt for {method} {url} (remaining: {remaining}) - {error_msg}"
                )
        return super().increment(method, url, response, error, _pool, _stacktrace)


class VicoaClient:
    """Client for interacting with the Vicoa Agent Dashboard API.

    Args:
        api_key: JWT API key for authentication
        base_url: Base URL of the API server (default: https://agents.vicoa.ai)
        timeout: Default timeout for requests in seconds (default: 30)
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_API_URL,
        timeout: int = 30,
        max_retries: int = 5,
        backoff_factor: float = 1.0,
        backoff_max: float = 60.0,
        log_func: Optional[Callable[[str], None]] = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.backoff_max = backoff_max
        self.log_func = log_func

        if not log_func:
            logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

        self.session = requests.Session()

        retry_class = LoggingRetry if self.log_func else Retry
        retry_kwargs = {
            "total": max_retries,
            "backoff_factor": backoff_factor,
            "backoff_max": backoff_max,
            "status_forcelist": [429, 500, 502, 503, 504],
            "allowed_methods": ["GET", "POST", "PUT", "DELETE", "PATCH"],
            "raise_on_status": False,
            "connect": max_retries,
            "read": max_retries,
            "other": max_retries,
        }
        if self.log_func:
            retry_kwargs["log_func"] = self.log_func
        retry_strategy = retry_class(**retry_kwargs)
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Set default headers
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "vicoa-python-sdk",
            }
        )

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def _make_request(
        self,
        method: str,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Make an HTTP request to the API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            json: JSON body for the request
            params: Query parameters for the request
            timeout: Request timeout in seconds

        Returns:
            Response JSON data

        Raises:
            AuthenticationError: If authentication fails
            APIError: If the API returns an error
            TimeoutError: If the request times out
        """
        url = urljoin(self.base_url, endpoint)
        timeout = timeout or self.timeout

        try:
            response = self.session.request(
                method=method, url=url, json=json, params=params, timeout=timeout
            )

            if response.status_code == 401:
                raise AuthenticationError("Invalid API key or authentication failed")

            if not response.ok:
                try:
                    error_detail = response.json().get("detail", response.text)
                except Exception:
                    error_detail = response.text
                raise APIError(response.status_code, error_detail)

            return response.json()

        except requests.exceptions.Timeout:
            raise TimeoutError(f"Request timed out after {timeout} seconds")
        except requests.exceptions.RequestException as e:
            raise APIError(0, f"Request failed: {str(e)}")

    def download_attachment(self, attachment_id: str) -> tuple[bytes, str]:
        """Download an image attachment's bytes.

        Returns:
            (data, mime_type) tuple.
        """
        url = urljoin(self.base_url, f"/api/v1/attachments/{attachment_id}")
        try:
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code == 401:
                raise AuthenticationError("Invalid API key or authentication failed")
            if not response.ok:
                raise APIError(response.status_code, response.text)
            mime_type = response.headers.get("Content-Type", "application/octet-stream")
            return response.content, mime_type
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Request timed out after {self.timeout} seconds")
        except requests.exceptions.RequestException as e:
            raise APIError(0, f"Request failed: {str(e)}")

    def send_message(
        self,
        content: str,
        agent_type: Optional[str] = None,
        agent_instance_id: Optional[Union[str, uuid.UUID]] = None,
        requires_user_input: bool = False,
        timeout_minutes: int = 1440,
        poll_interval: float = 10.0,
        send_push: Optional[bool] = None,
        send_email: Optional[bool] = None,
        send_sms: Optional[bool] = None,
        git_diff: Optional[str] = None,
        message_metadata: Optional[Dict[str, Any]] = None,
        poll_for_reply: Optional[bool] = None,
    ) -> CreateMessageResponse:
        """Send a message to the dashboard.

        Args:
            content: The message content (step description or question text)
            agent_type: Type of agent (required if agent_instance_id not provided)
            agent_instance_id: Existing agent instance ID (optional)
            requires_user_input: Whether this message requires user input (default: False).
                Drives the semantic side of the message: DB flag, dashboard
                "this needs an answer" indicator, notification template, and
                push/email/SMS defaults (user preference vs False).
            timeout_minutes: If polling, max time to wait in minutes (default: 1440)
            poll_interval: If polling, time between polls in seconds (default: 10.0)
            send_push: Send push notification (default: False for steps, user pref for questions)
            send_email: Send email notification (default: False for steps, user pref for questions)
            send_sms: Send SMS notification (default: False for steps, user pref for questions)
            git_diff: Git diff content to include (optional). This SDK encodes
                the diff in base64 for transmission; the server auto-detects and decodes.
            poll_for_reply: Whether ``send_message`` should long-poll
                ``/api/v1/messages/pending`` for a reply before returning.
                If ``None`` (default) it follows ``requires_user_input``
                (back-compat). See the async client for the full rationale.

        Returns:
            CreateMessageResponse. ``queued_user_messages`` is populated only
            when this call actually polls and a reply arrived.

        Raises:
            ValueError: If neither agent_type nor agent_instance_id is provided
            TimeoutError: If polling and no answer is received within timeout
        """
        # If no agent_instance_id provided, generate one client-side
        if not agent_instance_id:
            if not agent_type:
                raise ValueError("agent_type is required when creating a new instance")
            agent_instance_id = uuid.uuid4()

        # Validate and convert agent_instance_id to string
        agent_instance_id_str = validate_agent_instance_id(agent_instance_id)

        # Build request data using shared utility
        data = build_message_request_data(
            content=content,
            agent_instance_id=agent_instance_id_str,
            requires_user_input=requires_user_input,
            agent_type=agent_type,
            send_push=send_push,
            send_email=send_email,
            send_sms=send_sms,
            git_diff=git_diff,
            message_metadata=message_metadata,
        )

        # Send the message
        response = self._make_request("POST", "/api/v1/messages/agent", json=data)
        response_agent_instance_id = response["agent_instance_id"]
        message_id = response["message_id"]

        queued_contents = [
            msg["content"] if isinstance(msg, dict) else msg
            for msg in response.get("queued_user_messages", [])
        ]

        create_response = CreateMessageResponse(
            success=response["success"],
            agent_instance_id=response_agent_instance_id,
            message_id=message_id,
            queued_user_messages=queued_contents,
        )

        # See AsyncVicoaClient.send_message for the full rationale on
        # ``poll_for_reply``. Default keeps the historical behaviour
        # (poll iff ``requires_user_input`` is True).
        should_poll = (
            poll_for_reply if poll_for_reply is not None else requires_user_input
        )
        if not should_poll:
            return create_response

        # Otherwise, we need to poll for user response
        # Use the message ID we just created as our starting point
        last_read_message_id = message_id

        timeout_seconds = timeout_minutes * 60
        start_time = time.time()
        all_messages = []

        while time.time() - start_time < timeout_seconds:
            # Poll for pending messages
            pending_response = self.get_pending_messages(
                agent_instance_id_str, last_read_message_id
            )

            # If status is "stale", another process has read the messages
            if pending_response.status == "stale":
                raise TimeoutError("Another process has read the messages")

            # Check if we got any messages
            if pending_response.messages:
                # Collect all messages
                all_messages.extend(pending_response.messages)

                # Return the response with all collected messages
                create_response.queued_user_messages = [
                    msg.content for msg in all_messages
                ]
                return create_response

            time.sleep(poll_interval)

        raise TimeoutError(f"Question timed out after {timeout_minutes} minutes")

    def register_agent_instance(
        self,
        *,
        agent_type: str,
        transport: str = "ws",
        agent_instance_id: Optional[Union[str, uuid.UUID]] = None,
        name: Optional[str] = None,
        project: Optional[str] = None,
        home_dir: Optional[str] = None,
        source: Optional[str] = None,
        machine_id: Optional[str] = None,
        session_config: Optional[Dict[str, Any]] = None,
        worktree_name: Optional[str] = None,
        repo_root: Optional[str] = None,
        git_remote_url: Optional[str] = None,
        task_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> RegisterAgentInstanceResponse:
        """Register or update an agent instance for terminal relay sessions.

        Args:
            agent_type: Agent type identifier (e.g., "claude" or "codex")
            transport: Transport mechanism used by the instance
            agent_instance_id: Optional fixed UUID to reuse for reconnect scenarios
            name: Optional display name for the instance
            project: Optional project identifier (directory path or repository URL)
            home_dir: Optional home directory path for expanding tilde (~) in project paths
            source: Where the session was started from ("app" or "terminal").
                Defaults to the VICOA_SPAWN_SOURCE env var — set by the machine
                daemon on RPC spawns so an app-initiated instance is recorded
                without a machine_spawn_requests row.
            machine_id: Id of the machine this session runs on. Defaults to the
                daemon state file (read_machine_id); pass explicitly to override.
                Omitted from the request when unknown.
            worktree_name: Linked git worktree this session runs in. Defaults to
                probing `project` with git, so every caller reports it without
                per-wrapper edits (same rationale as machine_id). Stays absent
                for main checkouts and non-git dirs.
            task_id: Optional task to link this session to at spawn time. The
                task must belong to the caller; the server drives the task's
                status from the run's status once linked.
        """

        payload: Dict[str, Any] = {
            "agent_type": agent_type,
            "transport": transport,
        }

        target_instance_id: Optional[str] = None
        if agent_instance_id:
            target_instance_id = validate_agent_instance_id(agent_instance_id)
            payload["agent_instance_id"] = target_instance_id

        if name is not None:
            payload["name"] = name
        if project is not None:
            payload["project"] = project
        if home_dir is not None:
            payload["home_dir"] = home_dir
        # Probe git once per registration rather than editing all five wrapper
        # call sites. `project` is the session's cwd; falling back to the real
        # cwd keeps callers that omit it working.
        resolved_worktree = (
            worktree_name if worktree_name is not None else get_worktree_name(project)
        )
        if resolved_worktree:
            payload["worktree_name"] = resolved_worktree
        # Probe the repo root + origin remote once (alongside the worktree name)
        # so a worktree session — whose cwd sits outside the repo — can be
        # attributed to its project by repo root/remote rather than by cwd.
        if repo_root is None or git_remote_url is None:
            probed_root, probed_remote = get_git_identity(project)
            if repo_root is None:
                repo_root = probed_root
            if git_remote_url is None:
                git_remote_url = probed_remote
        if repo_root:
            payload["repo_root"] = repo_root
        if git_remote_url:
            payload["git_remote_url"] = git_remote_url
        resolved_source = source or os.environ.get("VICOA_SPAWN_SOURCE")
        if resolved_source:
            payload["source"] = resolved_source
        # Stamp the machine this session runs on (machine-management D8). Default
        # to the daemon state file so every SDK caller links its session without
        # per-wrapper edits; omit the key when unregistered so the server leaves
        # the link null rather than receiving an empty id. The lookup is scoped
        # to this client's base_url so a session against a custom backend links
        # to that backend's daemon registration, not the prod one.
        resolved_machine_id = machine_id or read_machine_id(self.base_url)
        if resolved_machine_id:
            payload["machine_id"] = resolved_machine_id
        # Only include session_config when the caller provided it. Omitting
        # the key preserves any value the spawn-request row already had on the
        # server (activate-existing branch uses field-present semantics).
        if session_config is not None:
            payload["session_config"] = session_config
        if task_id is not None:
            payload["task_id"] = str(task_id)

        try:
            response = self._make_request(
                "POST", "/api/v1/agent-instances", json=payload
            )
        except APIError as err:
            if err.status_code == 409 and target_instance_id:
                detail = self._make_request(
                    "GET",
                    f"/api/v1/agent-instances/{target_instance_id}",
                    params={"message_limit": 0},
                )
                return RegisterAgentInstanceResponse(
                    agent_instance_id=detail["id"],
                    agent_type_id=detail.get("agent_type_id"),
                    agent_type_name=detail.get("agent_type_name"),
                    status=detail.get("status", ""),
                    name=None,
                    instance_metadata=detail.get("instance_metadata"),
                    project=detail.get("project"),
                )
            raise

        instance_id = response.get("agent_instance_id") or response.get("id")
        if instance_id is None:
            raise KeyError("agent_instance_id")

        return RegisterAgentInstanceResponse(
            agent_instance_id=instance_id,
            agent_type_id=response.get("agent_type_id"),
            agent_type_name=response.get("agent_type_name"),
            status=response.get("status", ""),
            name=response.get("name"),
            instance_metadata=response.get("instance_metadata"),
            project=response.get("project"),
        )

    def get_pending_messages(
        self,
        agent_instance_id: Union[str, uuid.UUID],
        last_read_message_id: Optional[str] = None,
    ) -> PendingMessagesResponse:
        """Get pending user messages for an agent instance.

        Args:
            agent_instance_id: Agent instance ID
            last_read_message_id: The last message ID that was read (optional)

        Returns:
            PendingMessagesResponse with messages and status
        """
        # Validate and convert agent_instance_id to string
        agent_instance_id_str = validate_agent_instance_id(agent_instance_id)

        params = {"agent_instance_id": agent_instance_id_str}
        # Only include last_read_message_id if it's not None
        # Empty string is treated as None by the API
        if last_read_message_id is not None:
            params["last_read_message_id"] = last_read_message_id
        else:
            params["last_read_message_id"] = ""

        response = self._make_request("GET", "/api/v1/messages/pending", params=params)

        return PendingMessagesResponse(
            agent_instance_id=response["agent_instance_id"],
            messages=[Message(**msg) for msg in response["messages"]],
            status=response["status"],
        )

    def stream_user_messages(
        self,
        agent_instance_id: Union[str, uuid.UUID],
        connect_timeout: float = 10.0,
        read_timeout: float = 35.0,
    ):
        """Open an SSE stream for user messages on a given agent instance.

        Yields parsed SSE event dicts (keys: ``event``, ``data``).
        The caller is responsible for reconnecting on error.

        Args:
            agent_instance_id: The agent instance ID to stream messages for
            connect_timeout: Socket connect timeout in seconds (default: 10)
            read_timeout: Per-chunk read timeout in seconds (default: 35).
                Server sends a heartbeat every 15s; 35s gives a 2x buffer so
                a dead connection raises Timeout instead of hanging silently.
        """
        import sseclient

        agent_instance_id_str = validate_agent_instance_id(agent_instance_id)
        url = urljoin(
            self.base_url,
            f"/api/v1/agents/instances/{agent_instance_id_str}/stream",
        )
        response = self.session.get(
            url,
            stream=True,
            timeout=(connect_timeout, read_timeout),
            headers={"Accept": "text/event-stream"},
        )
        response.raise_for_status()
        # sseclient needs raw byte chunks WITH newlines so it can detect the
        # `\n\n` event separator. Passing `response.iter_lines()` strips the
        # newlines and breaks parsing — events never dispatch and the buffer
        # grows until the stream closes. Pass the response object directly.
        client = sseclient.SSEClient(response)  # pyright: ignore[reportArgumentType]
        for event in client.events():
            yield {"event": event.event, "data": event.data}

    def send_user_message(
        self,
        agent_instance_id: Union[str, uuid.UUID],
        content: str,
        mark_as_read: bool = True,
    ) -> Dict[str, Any]:
        """Send a user message to an agent instance.

        Args:
            agent_instance_id: The agent instance ID to send the message to
            content: Message content
            mark_as_read: Whether to mark as read (update last_read_message_id) (default: True)

        Returns:
            Dict containing:
                - success: Whether the message was created
                - message_id: ID of the created message
                - marked_as_read: Whether the message was marked as read

        Raises:
            ValueError: If agent instance not found or access denied
            APIError: If the API request fails
        """
        # Validate and convert agent_instance_id
        agent_instance_id = validate_agent_instance_id(agent_instance_id)

        data = {
            "agent_instance_id": str(agent_instance_id),
            "content": content,
            "mark_as_read": mark_as_read,
        }

        return self._make_request("POST", "/api/v1/messages/user", json=data)

    def request_user_input(
        self,
        message_id: Union[str, uuid.UUID],
        timeout_minutes: int = 1440,
        poll_interval: float = 10.0,
    ) -> List[str]:
        """Request user input for a previously sent agent message.

        This method updates an agent message to require user input and polls for responses.
        It's useful when you initially send a message without requiring input, but later
        decide you need user feedback.

        Args:
            message_id: The message ID to update (must be an agent message)
            timeout_minutes: Max time to wait for user response in minutes (default: 1440)
            poll_interval: Time between polls in seconds (default: 10.0)

        Returns:
            List of user message contents received as responses

        Raises:
            ValueError: If message not found, already requires input, or not an agent message
            TimeoutError: If no user response is received within timeout
            APIError: If the API request fails
        """
        # Convert message_id to string if it's a UUID
        message_id_str = str(message_id)

        # Call the endpoint to update the message
        response = self._make_request(
            "PATCH", f"/api/v1/messages/{message_id_str}/request-input"
        )

        agent_instance_id = response["agent_instance_id"]
        messages = response.get("messages", [])

        if messages:
            return [msg["content"] for msg in messages]

        # Otherwise, poll for user response
        timeout_seconds = timeout_minutes * 60
        start_time = time.time()
        all_messages = []

        while time.time() - start_time < timeout_seconds:
            # Poll for pending messages using the message_id as last_read
            pending_response = self.get_pending_messages(
                agent_instance_id, message_id_str
            )

            # If status is "stale", another process has read the messages
            if pending_response.status == "stale":
                raise TimeoutError("Another process has read the messages")

            # Check if we got any messages
            if pending_response.messages:
                # Collect all message contents
                all_messages.extend([msg.content for msg in pending_response.messages])
                return all_messages

            time.sleep(poll_interval)

        raise TimeoutError(f"No user response received after {timeout_minutes} minutes")

    def mark_message_requires_input(
        self, message_id: Union[str, uuid.UUID]
    ) -> List[Dict[str, Any]]:
        """Mark an agent message as requiring user input without polling.

        Args:
            message_id: The agent message ID to mark.

        Returns:
            Any already-queued user messages returned by the API as dicts
            (``{content, message_metadata, ...}``).
        """
        message_id_str = str(message_id)
        response = self._make_request(
            "PATCH", f"/api/v1/messages/{message_id_str}/request-input"
        )
        messages = response.get("messages", [])
        return [msg for msg in messages if isinstance(msg, dict)]

    def mark_message_consumed(self, message_id: Union[str, uuid.UUID]) -> None:
        """Mark a user message as consumed (picked up by the wrapper's turn).

        Sync twin of ``AsyncVicoaClient.mark_message_consumed``. Clears the
        ``message_metadata.queue`` stamp the API applies when a message lands
        on an already-ACTIVE instance, so the UI's queued-messages bar stops
        showing it once the agent actually starts the turn.
        """
        self._make_request("PATCH", f"/api/v1/messages/{str(message_id)}/consumed")

    def update_agent_instance_status(
        self, agent_instance_id: Union[str, uuid.UUID], status: str
    ) -> Dict[str, Any]:
        """Update the status of an existing agent instance."""

        agent_instance_id_str = validate_agent_instance_id(agent_instance_id)
        endpoint = f"/api/v1/agent-instances/{agent_instance_id_str}/status"
        return self._make_request("PUT", endpoint, json={"status": status})

    def patch_agent_instance(
        self,
        agent_instance_id: Union[str, uuid.UUID],
        *,
        name: Optional[str] = None,
        session_config: Optional[Dict[str, Any]] = None,
        instance_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Partial update of an agent instance row.

        Only kwargs the caller passes land in the PATCH body — absent kwargs
        leave the corresponding row field untouched (server-side uses Pydantic
        model_fields_set to honor field-present semantics). session_config and
        instance_metadata each merge into their existing JSONB column
        key-by-key; pass an empty dict to noop that write.

        Used by the Claude TUI wrapper's JSONLMonitor to report a
        post-init / mid-session model or permission_mode change observed in
        the Claude jsonl, and by the ACP wrapper to record the agent's own
        session id for later resume.
        """

        agent_instance_id_str = validate_agent_instance_id(agent_instance_id)
        payload: Dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if session_config is not None:
            payload["session_config"] = session_config
        if instance_metadata is not None:
            payload["instance_metadata"] = instance_metadata
        endpoint = f"/api/v1/agent-instances/{agent_instance_id_str}"
        return self._make_request("PATCH", endpoint, json=payload)

    def update_machine_recent_directory(
        self,
        machine_id: Union[str, uuid.UUID],
        cwd: str,
        *,
        cli_version: Optional[str] = None,
        python_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update a registered machine's recent directory list without heartbeating it."""

        machine_id_str = str(machine_id)
        payload: Dict[str, Any] = {"cwd": cwd}
        if cli_version is not None:
            payload["cli_version"] = cli_version
        if python_version is not None:
            payload["python_version"] = python_version

        endpoint = f"/api/v1/machines/{machine_id_str}/recent-directories"
        return self._make_request("PATCH", endpoint, json=payload)

    def end_session(
        self, agent_instance_id: Union[str, uuid.UUID]
    ) -> EndSessionResponse:
        """End an agent session and mark it as completed.

        Args:
            agent_instance_id: Agent instance ID to end

        Returns:
            EndSessionResponse with success status and final details
        """
        # Validate and convert agent_instance_id to string
        agent_instance_id_str = validate_agent_instance_id(agent_instance_id)

        data: Dict[str, Any] = {"agent_instance_id": agent_instance_id_str}
        response = self._make_request("POST", "/api/v1/sessions/end", json=data)

        return EndSessionResponse(
            success=response["success"],
            agent_instance_id=response["agent_instance_id"],
            final_status=response["final_status"],
        )

    def sync_commands(
        self, agent_type: str, commands: Dict[str, Dict[str, str]]
    ) -> Dict[str, Any]:
        """Sync slash commands from CLI to the backend.

        Args:
            agent_type: Agent type ('claude', 'codex', or 'opencode')
            commands: Dict of commands {command_name: {description: ...}}

        Returns:
            Dict with sync response data
        """
        data: Dict[str, Any] = {"agent_type": agent_type, "commands": commands}
        response = self._make_request("POST", "/api/v1/commands/sync", json=data)
        return response

    def sync_files(self, project_path: str, files: List[str]) -> Dict[str, Any]:
        """Sync project files from CLI to the backend for @ mentions.

        Args:
            project_path: Absolute path to the project directory
            files: List of relative file paths from project_path

        Returns:
            Dict with sync response data
        """
        data: Dict[str, Any] = {"project_path": project_path, "files": files}
        response = self._make_request("POST", "/api/v1/files/sync", json=data)
        return response

    def close(self):
        """Close the session and clean up resources."""
        self.session.close()
