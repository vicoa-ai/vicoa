import os
from pathlib import Path
from typing import List

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_port_from_env() -> int:
    """Get port from environment variables, handling potential string literals"""
    port_env = os.getenv("PORT")
    mcp_port_env = os.getenv("MCP_SERVER_PORT")

    # Handle case where PORT might be '$PORT' literal string
    if port_env and port_env != "$PORT":
        try:
            return int(port_env)
        except ValueError:
            pass

    if mcp_port_env and mcp_port_env != "$MCP_SERVER_PORT":
        try:
            return int(mcp_port_env)
        except ValueError:
            pass

    return 8080


class Settings(BaseSettings):
    # Environment Configuration
    environment: str = "development"
    development_db_url: str = os.getenv(
        "DEVELOPMENT_DB_URL",
        "postgresql://user:password@localhost:5432/agent_dashboard",
    )
    production_db_url: str = ""

    # Database URL - can be set directly or will use development/production URLs
    database_url: str = ""

    # MCP Server - use PORT env var if available (for Render), otherwise default
    mcp_server_port: int = get_port_from_env()

    # Backend API - use PORT env var if available (for Render), otherwise default
    api_port: int = int(os.getenv("PORT") or os.getenv("API_PORT") or "8000")

    # Session liveness thresholds. Agents and daemons heartbeat every 30s, so
    # "online" allows ~3 missed beats before we call a session stale. Between
    # the two thresholds the UI shows "reconnecting" rather than "offline", so
    # a brief network blip doesn't flip a healthy session to dead.
    liveness_online_threshold_seconds: int = 90
    liveness_stale_threshold_seconds: int = 300
    # A freshly spawned session hasn't heartbeated yet — the daemon still has to
    # launch the process, register the instance, and reach the first beat. Until
    # this much time has passed after started_at, silence means "starting", not
    # "dead". Generous because ACP bring-up (spawn, initialize, session/new) is
    # the slowest path.
    liveness_startup_grace_seconds: int = 120

    @field_validator("database_url", mode="after")
    @classmethod
    def set_database_url(cls, v, info):
        """Set database URL based on environment if not explicitly provided."""
        if v:  # If explicitly set, use it
            return v

        # Use info.data to access other fields
        environment = info.data.get("environment", "development").lower()

        if environment == "production":
            production_url = info.data.get("production_db_url")
            if production_url:
                return production_url

        development_url = info.data.get("development_db_url")
        if development_url:
            return development_url

        return "postgresql://user:password@localhost:5432/agent_dashboard"

    # Frontend URLs - expects JSON array in env var
    frontend_urls: List[str] = [
        "https://vicoa.ai",
        "https://vibecodeanywhere.com",
        "http://localhost:3000",
    ]

    # API Versioning
    api_v1_prefix: str = "/api/v1"

    # S3 credentials for message image attachments (the bucket name is a
    # code constant — shared.storage.ATTACHMENTS_BUCKET). These flow through
    # .env / Fly secrets like every other secret here: pydantic's env_file
    # does NOT export to os.environ, so boto3's default chain can't see a
    # plain .env — storage.py passes these explicitly. Empty values fall
    # back to boto3's default chain (IAM role, ~/.aws/credentials).
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = ""

    # WebSocket endpoint URL that clients connect to (websocket-migration §2.1).
    # The /ws endpoint lives on the agent-facing `server` process, which is
    # being split into its own Fly app `vicoa-server` on agents.vicoa.ai (see
    # plans/todos/server-app-split.md). This public URL is a per-environment
    # deploy artifact — the protocol never assumes it.
    # Production: wss://agents.vicoa.ai/ws. Staging / pre-split validation:
    # wss://api.vicoa.ai:8443/ws (the legacy server is still served there).
    vicoa_ws_url: str = ""

    # Whether this process mounts the WebSocket `/ws` endpoint and its
    # process-local ConnectionManager. Only the dedicated `vicoa-server` Fly
    # app sets this true; the legacy `server` process inside vicoa-backend
    # leaves it false so it stays SSE/REST-only (server-app-split.md dual-run).
    enable_websocket: bool = False

    # Whether the `backend` process runs the activation-nudge sweep — the
    # signup-anchored push + email re-engagement drip for users who never sent a
    # first message (src/cloud/activation/, closed overlay). Ships dark; flip to
    # true on one backend deploy once the app's `activation_nudge` deep-link is live.
    enable_activation_nudges: bool = False

    # Shared secret for the backend -> server `_internal/broadcast` bridge
    # (websocket-migration §2.11). High-entropy, rotated like any credential;
    # the endpoint 401s when it is unset or mismatched.
    internal_broadcast_token: str = ""

    # Full URL of the `server` process's `_internal/broadcast` endpoint, which
    # the backend POSTs to after a write commits so user/session-scoped WS
    # clients get the realtime update (websocket-migration §2.11). Per-
    # environment deploy artifact reached over Fly's private 6PN network, e.g.
    # http://vicoa-server.internal:8080/_internal/broadcast. Empty disables the
    # bridge (post_broadcast becomes a no-op).
    internal_broadcast_url: str = ""

    # Which identity provider verifies end-user (web/mobile/desktop) tokens:
    # "supabase" or "builtin". Empty means infer — Supabase when a project is
    # configured, otherwise the built-in provider, so the hosted deployment keeps
    # its existing env and a self-hosted one needs no auth config at all.
    # See shared/auth/provider.py.
    auth_provider: str = ""

    # Supabase Configuration
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    # Legacy HS256 signing secret, from the project's API settings. Present ->
    # access tokens are verified locally instead of by a network call to GoTrue.
    # It both signs and verifies, so treat it as a private key: never ship it to
    # a client, never log it. A project with asymmetric signing keys enabled
    # needs no secret here — verification uses the published JWKS instead.
    supabase_jwt_secret: str = ""

    # Whether a verified agent API key is also checked against `api_keys` (row
    # present, active, unexpired) before the request is served. Off, a revoked
    # key keeps working until `exp` — and most keys are minted without one.
    # Answers are cached briefly; see shared/auth/agent_tokens.py.
    enforce_api_key_revocation: bool = True

    # Built-in auth provider (AUTH_PROVIDER=builtin).
    # Turn signup off once a self-hosted instance's accounts are created — the
    # sign-up endpoint is otherwise open to anyone who can reach the server.
    builtin_allow_signup: bool = True
    # Requires a configured mail provider; off by default so a deployment
    # without one cannot lock itself out.
    builtin_require_email_verification: bool = False
    builtin_session_ttl_hours: int = 720  # 30 days

    # JWT Signing Keys for API Keys.
    #
    # PEM blocks are multi-line, which env files handle badly, so each key can
    # instead be pointed at a file — the Docker-secret convention. When the
    # direct value is empty and the `_file` path is set, the file is read at
    # startup (see the `_load_key_files` validator). docker-compose.selfhost.yml
    # uses this.
    jwt_private_key: str = ""
    jwt_private_key_file: str = ""
    jwt_public_key_file: str = ""

    # Anthropic API for LLM features (primary path for session titles —
    # see shared.llms.utils).
    anthropic_api_key: str = ""
    # OpenRouter — single-API multi-provider gateway. Used as the fallback
    # chain for session-title generation (DeepSeek v3.2 → Gemini-flash-lite)
    # when Anthropic is unavailable, and by the bench_title_models script.
    openrouter_api_key: str = ""
    jwt_public_key: str = ""
    deepgram_api_key: str = ""

    # Sentry Configuration
    sentry_dsn: str = ""

    # Billing Configuration
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # Stripe Price IDs (from your Stripe dashboard)
    # `stripe_pro_price_id` remains as a backward-compatible fallback for monthly Pro.
    stripe_pro_price_id: str = ""
    stripe_pro_monthly_price_id: str = ""
    stripe_pro_annual_price_id: str = ""
    stripe_pro_trial_days: int = 7

    # RevenueCat Configuration
    revenuecat_secret_key: str = ""  # Your RevenueCat secret API key
    revenuecat_webhook_auth_header: str = (
        ""  # Optional: Authorization header for webhook security
    )
    superwall_webhook_secret: str = ""  # Superwall whsec_ webhook signing secret
    superwall_api_token: str = ""  # Organization API key (bearer) for V2 REST API

    # Mailgun Configuration (primary transactional email sender)
    mailgun_api_key: str = ""
    mailgun_domain: str = ""
    mailgun_from_email: str = ""
    # BCC applied to lifecycle emails; empty disables BCC. Env-driven so the
    # open-source build ships no Vicoa address (deploy config supplies it).
    mailgun_bcc_email: str = ""

    # Inbox that receives support "report an issue" emails. Empty in the
    # open-source / self-host build — the /support/report-issue endpoint returns
    # 503 until it is configured; Vicoa's deploy sets SUPPORT_EMAIL.
    support_email: str = ""

    # Resend Configuration (dormant fallback; Mailgun is the primary sender)
    resend_api_key: str = ""
    resend_from_email: str = (
        ""  # e.g. "Vicoa <hi@vicoa.ai>"; falls back to mailgun_from_email
    )

    # Plan Configuration - informational only (subscription.agent_limit display);
    # not enforced, agent creation is never blocked by usage.
    free_plan_agent_limit: int = 10  # 10 total agents per month
    pro_plan_agent_limit: int = -1  # Unlimited
    pro_plan_price: float = 9
    enterprise_plan_agent_limit: int = -1  # Unlimited
    enterprise_plan_price: float = 500

    # Twilio Configuration
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_phone_number: str = ""  # Format: +1234567890
    twilio_sendgrid_api_key: str = ""  # For email notifications via SendGrid
    twilio_from_email: str = ""  # Sender email address

    # ConvertKit Configuration
    convertkit_api_key: str = ""  # ConvertKit API key

    # Listmonk Configuration (self-hosted marketing list; taking over from ConvertKit)
    listmonk_url: str = ""  # e.g. "https://mail.vicoa.ai"
    listmonk_api_user: str = ""  # Username of a Listmonk user of type "api"
    listmonk_api_token: str = ""  # That user's API token
    # Name of the target list (Listmonk ids renumber on rebuild, so the stable
    # name is the identifier; resolved to an id at runtime). Generic default for
    # self-host; Vicoa sets LISTMONK_LIST_NAME.
    listmonk_list_name: str = "users"

    # Firebase Cloud Messaging (FCM) Configuration
    fcm_service_account_key_path: str = ""  # Path to Firebase service account JSON file
    fcm_service_account_json: str = (
        ""  # Firebase service account JSON as string (alternative to file)
    )

    @model_validator(mode="after")
    def _load_key_files(self) -> "Settings":
        """Back a key with its `*_KEY_FILE` when the direct value is unset.

        Lets a self-hosted deployment mount PEM files (docker secrets, k8s
        secrets) instead of squeezing multi-line values into env vars. A
        configured-but-unreadable path is fatal: silently starting without a
        signing key would only fail later, at the first API-key mint.
        """
        for key_attr, path_attr in (
            ("jwt_private_key", "jwt_private_key_file"),
            ("jwt_public_key", "jwt_public_key_file"),
        ):
            path = getattr(self, path_attr)
            if getattr(self, key_attr) or not path:
                continue
            setattr(self, key_attr, Path(path).read_text(encoding="utf-8").strip())
        return self

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
