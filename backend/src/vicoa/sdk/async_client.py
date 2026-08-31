"""Async client for interacting with the Vicoa Agent Dashboard API."""

import asyncio
import os
import ssl
import uuid
from typing import Optional, Dict, Any, Union, List, Callable
from urllib.parse import urljoin

import aiohttp
import certifi
from aiohttp import ClientTimeout

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


class AsyncVicoaClient:
    """Async client for interacting with the Vicoa Agent Dashboard API.

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
        max_retries: int = 6,
        backoff_factor: float = 1.0,
        backoff_max: float = 60.0,
        log_func: Optional[Callable[[str], None]] = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.backoff_max = backoff_max
        self.log_func = log_func
        self.session: Optional[aiohttp.ClientSession] = None

        # Default headers
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "vicoa-python-sdk",
        }

    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        if self.session is None or self.session.closed:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(
                ssl=ssl_context,
                limit=100,
                ttl_dns_cache=300,
            )

            self.session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=self.timeout,
                connector=connector,
            )

    async def close(self):
        """Close the aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Make an async HTTP request to the API with retry logic.

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
        await self._ensure_session()
        assert self.session is not None

        url = urljoin(self.base_url, endpoint)
        request_timeout = ClientTimeout(total=timeout) if timeout else self.timeout

        status_forcelist = {429, 500, 502, 503, 504}
        last_error = None

        for attempt in range(self.max_retries):
            try:
                async with self.session.request(
                    method=method,
                    url=url,
                    json=json,
                    params=params,
                    timeout=request_timeout,
                ) as response:
                    if response.status == 401:
                        raise AuthenticationError(
                            "Invalid API key or authentication failed"
                        )

                    if not response.ok:
                        try:
                            error_data = await response.json()
                            error_detail = error_data.get(
                                "detail", await response.text()
                            )
                        except Exception:
                            error_detail = await response.text()

                        if response.status in status_forcelist:
                            last_error = APIError(response.status, error_detail)
                        else:
                            raise APIError(response.status, error_detail)
                    else:
                        return await response.json()

            except (aiohttp.ClientConnectionError, aiohttp.ClientError) as e:
                last_error = APIError(0, f"Request failed: {str(e)}")
                if self.log_func and attempt < self.max_retries - 1:
                    error_msg = str(e)[:100] if len(str(e)) > 100 else str(e)
                    self.log_func(
                        f"[WARNING] Request failed (attempt {attempt + 1}/{self.max_retries}): {method} {url} - {error_msg}"
                    )
            except asyncio.TimeoutError:
                last_error = TimeoutError(
                    f"Request timed out after {timeout or self.timeout.total} seconds"
                )
                if self.log_func and attempt < self.max_retries - 1:
                    self.log_func(
                        f"[WARNING] Request timeout (attempt {attempt + 1}/{self.max_retries}): {method} {url}"
                    )
            except (AuthenticationError, APIError) as e:
                if isinstance(e, APIError) and e.status_code in status_forcelist:
                    last_error = e
                    if self.log_func and attempt < self.max_retries - 1:
                        self.log_func(
                            f"[WARNING] HTTP {e.status_code} error (attempt {attempt + 1}/{self.max_retries}): {method} {url}"
                        )
                else:
                    raise

            if attempt < self.max_retries - 1 and last_error:
                sleep_time = min(self.backoff_factor * (2**attempt), self.backoff_max)
                if self.log_func:
                    self.log_func(f"[INFO] Retrying in {sleep_time:.1f}s...")
                await asyncio.sleep(sleep_time)
            elif last_error:
                raise last_error

        raise APIError(0, "Unexpected retry exhaustion")

    async def download_attachment(self, attachment_id: str) -> tuple[bytes, str]:
        """Download an image attachment's bytes.

        Returns:
            (data, mime_type) tuple.
        """
        await self._ensure_session()
        assert self.session is not None
        url = urljoin(self.base_url, f"/api/v1/attachments/{attachment_id}")
        async with self.session.get(url) as response:
            if response.status == 401:
                raise AuthenticationError("Invalid API key or authentication failed")
            if not response.ok:
                raise APIError(response.status, await response.text())
            data = await response.read()
            mime_type = response.headers.get("Content-Type", "application/octet-stream")
            return data, mime_type

    async def send_message(
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
                Drives the semantic side of the message:
                  * database flag and dashboard "this needs an answer" indicator,
                  * notification template (question vs step), and
                  * push/email/SMS default-to-user-preferences (vs default-to-False).
            timeout_minutes: If polling, max time to wait in minutes (default: 1440)
            poll_interval: If polling, time between polls in seconds (default: 10.0)
            send_push: Send push notification (default: False for steps, user pref for questions)
            send_email: Send email notification (default: False for steps, user pref for questions)
            send_sms: Send SMS notification (default: False for steps, user pref for questions)
            git_diff: Git diff content to include (optional). This SDK encodes
                the diff in base64 for transmission; the server auto-detects and decodes.
            poll_for_reply: Whether ``send_message`` should long-poll
                ``/api/v1/messages/pending`` for a reply before returning.
                If ``None`` (default) it follows ``requires_user_input`` —
                preserving the historical behaviour. Set to ``False`` when the
                caller will resolve the reply through another channel (e.g. an
                SSE stream + an in-process asyncio.Future registry); this
                avoids advancing ``instance.last_read_message_id`` and so
                eliminates the §2g cursor race for that call. See
                ``docs/design/mcp-headless-refactor.md`` for the full rationale.

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
        response = await self._make_request("POST", "/api/v1/messages/agent", json=data)
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

        # Decide whether to long-poll for the reply. ``poll_for_reply``
        # defaults to ``requires_user_input`` for backward compatibility —
        # historically the two were a single flag. Callers that resolve the
        # reply elsewhere (e.g. via SSE + an in-process Future) pass
        # ``poll_for_reply=False`` while keeping ``requires_user_input=True``
        # to preserve push-notification routing.
        should_poll = (
            poll_for_reply if poll_for_reply is not None else requires_user_input
        )
        if not should_poll:
            return create_response

        # Otherwise, poll for the answer
        # Use the message ID we just created as our starting point
        last_read_message_id = message_id
        timeout_seconds = timeout_minutes * 60
        start_time = asyncio.get_event_loop().time()
        all_messages = []

        while asyncio.get_event_loop().time() - start_time < timeout_seconds:
            # Poll for pending messages
            pending_response = await self.get_pending_messages(
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

            await asyncio.sleep(poll_interval)

        raise TimeoutError(f"Question timed out after {timeout_minutes} minutes")

    async def register_agent_instance(
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
        # the link null rather than receiving an empty id. Scoped to this
        # client's base_url so a session against a custom backend links to that
        # backend's daemon registration, not the prod one.
        resolved_machine_id = machine_id or read_machine_id(self.base_url)
        if resolved_machine_id:
            payload["machine_id"] = resolved_machine_id
        # Only include session_config when the caller provided it. Omitting
        # the key preserves any pre-staged value on the server (activate-
        # existing branch uses field-present semantics).
        if session_config is not None:
            payload["session_config"] = session_config

        try:
            response = await self._make_request(
                "POST", "/api/v1/agent-instances", json=payload
            )
        except APIError as err:
            if err.status_code == 409 and target_instance_id:
                detail = await self._make_request(
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

    async def get_pending_messages(
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
        if last_read_message_id:
            params["last_read_message_id"] = last_read_message_id

        response = await self._make_request(
            "GET", "/api/v1/messages/pending", params=params
        )

        return PendingMessagesResponse(
            agent_instance_id=response["agent_instance_id"],
            messages=[Message(**msg) for msg in response["messages"]],
            status=response["status"],
        )

    async def get_pending_messages_raw(
        self,
        agent_instance_id: Union[str, uuid.UUID],
    ) -> tuple[list[dict], str]:
        """Fetch pending user messages as raw dicts (metadata preserved).

        ``get_pending_messages`` coerces each row into the ``Message``
        dataclass, which has no ``message_metadata`` field — so it drops
        attachments (and would ``TypeError`` on today's response, which does
        include ``message_metadata``). Callers that need to route a recovered
        message through the same path as a websocket ``new-message`` — e.g. the
        headless reconcile backstop resolving a stranded AskUserQuestion reply
        when the realtime broadcast was dropped — need the full row.

        Returns ``(messages, status)`` where each message is the server's raw
        ``MessageResponse`` dict (``id``/``content``/``sender_type``/
        ``requires_user_input``/``message_metadata``/…) and ``status`` is
        ``"ok"`` or ``"stale"``. Reads with no cursor, so the server returns
        everything unread and advances ``last_read_message_id`` to the tail.
        """
        agent_instance_id_str = validate_agent_instance_id(agent_instance_id)
        response = await self._make_request(
            "GET",
            "/api/v1/messages/pending",
            params={"agent_instance_id": agent_instance_id_str},
        )
        return response.get("messages", []), response.get("status", "ok")

    async def send_user_message(
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

        return await self._make_request("POST", "/api/v1/messages/user", json=data)

    async def request_user_input(
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
        response = await self._make_request(
            "PATCH", f"/api/v1/messages/{message_id_str}/request-input"
        )

        agent_instance_id = response["agent_instance_id"]
        messages = response.get("messages", [])

        if messages:
            return [msg["content"] for msg in messages]

        # Otherwise, poll for user response
        timeout_seconds = timeout_minutes * 60
        start_time = asyncio.get_event_loop().time()
        all_messages = []

        while asyncio.get_event_loop().time() - start_time < timeout_seconds:
            # Poll for pending messages using the message_id as last_read
            pending_response = await self.get_pending_messages(
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

            await asyncio.sleep(poll_interval)

        raise TimeoutError(f"No user response received after {timeout_minutes} minutes")

    async def stream_user_messages(
        self,
        agent_instance_id: Union[str, uuid.UUID],
    ):
        """Async generator that yields SSE events from the per-instance user-message stream.

        Yields parsed event dicts with keys ``event`` and ``data``.
        The caller is responsible for reconnecting on error.
        """
        agent_instance_id_str = validate_agent_instance_id(agent_instance_id)
        url = urljoin(
            self.base_url,
            f"/api/v1/agents/instances/{agent_instance_id_str}/stream",
        )
        await self._ensure_session()
        assert self.session is not None
        # sock_read=35s: server heartbeat every 15s → 2x buffer. Dead connections
        # raise asyncio.TimeoutError so the caller's reconnect loop fires reliably.
        async with self.session.get(
            url,
            headers={"Accept": "text/event-stream"},
            timeout=ClientTimeout(total=None, sock_read=35),
        ) as resp:
            resp.raise_for_status()
            event_type = "message"
            buffer = ""
            async for line_bytes in resp.content:
                line = line_bytes.decode("utf-8").rstrip("\r\n")
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    buffer = line[5:].strip()
                elif line == "":
                    if buffer:
                        yield {"event": event_type, "data": buffer}
                    event_type = "message"
                    buffer = ""

    async def mark_message_requires_input(
        self,
        message_id: Union[str, uuid.UUID],
    ) -> List[Dict[str, Any]]:
        """Mark an agent message as requiring user input without polling.

        Returns any already-queued user messages from the API response as
        dicts (``{content, message_metadata, ...}``).
        """
        message_id_str = str(message_id)
        response = await self._make_request(
            "PATCH", f"/api/v1/messages/{message_id_str}/request-input"
        )
        messages = response.get("messages", [])
        return [msg for msg in messages if isinstance(msg, dict)]

    async def mark_message_consumed(
        self,
        message_id: Union[str, uuid.UUID],
    ) -> None:
        """Mark a user message as consumed (picked up by the wrapper's turn)."""
        await self._make_request(
            "PATCH", f"/api/v1/messages/{str(message_id)}/consumed"
        )

    async def heartbeat_instance(
        self, agent_instance_id: Union[str, uuid.UUID]
    ) -> Dict[str, Any]:
        """Stamp ``last_heartbeat_at`` so the session reads as alive.

        Headless wrappers call this on a timer; without it an idle session is
        indistinguishable from a dead one (``last_heartbeat_at`` otherwise only
        moves when the agent posts a message).
        """
        agent_instance_id_str = validate_agent_instance_id(agent_instance_id)
        endpoint = f"/api/v1/agents/instances/{agent_instance_id_str}/heartbeat"
        return await self._make_request("POST", endpoint)

    async def get_agent_instance(
        self, agent_instance_id: Union[str, uuid.UUID]
    ) -> Dict[str, Any]:
        """Return the current agent instance data."""
        agent_instance_id_str = validate_agent_instance_id(agent_instance_id)
        endpoint = f"/api/v1/agent-instances/{agent_instance_id_str}"
        return await self._make_request("GET", endpoint)

    async def update_agent_instance_status(
        self, agent_instance_id: Union[str, uuid.UUID], status: str
    ) -> Dict[str, Any]:
        """Update the status of an existing agent instance."""

        agent_instance_id_str = validate_agent_instance_id(agent_instance_id)
        endpoint = f"/api/v1/agent-instances/{agent_instance_id_str}/status"
        return await self._make_request("PUT", endpoint, json={"status": status})

    async def patch_agent_instance(
        self,
        agent_instance_id: Union[str, uuid.UUID],
        *,
        name: Optional[str] = None,
        session_config: Optional[Dict[str, Any]] = None,
        instance_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Partial update of an agent instance row. See VicoaClient.patch_agent_instance.

        ``instance_metadata`` is shallow-merged server-side (keys present
        overwrite, absent keys preserved) — the same semantics as
        ``session_config``. Used by the headless runners to stamp the live
        ``usage`` blob (context window + rate limits) without a schema change.
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
        return await self._make_request("PATCH", endpoint, json=payload)

    async def end_session(
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
        response = await self._make_request("POST", "/api/v1/sessions/end", json=data)

        return EndSessionResponse(
            success=response["success"],
            agent_instance_id=response["agent_instance_id"],
            final_status=response["final_status"],
        )

    async def sync_commands(
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
        response = await self._make_request("POST", "/api/v1/commands/sync", json=data)
        return response
