"""Firebase Cloud Messaging (FCM) push notification service for Flutter apps"""

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from uuid import UUID
from sqlalchemy import func
from sqlalchemy.orm import Session
import json

from firebase_admin import credentials, messaging, initialize_app
from firebase_admin.exceptions import FirebaseError
import firebase_admin

from shared.database import AgentInstance, AgentStatus, PushToken, User
from shared.config import settings
from .notification_base import NotificationServiceBase

logger = logging.getLogger(__name__)


class FCMNotificationService(NotificationServiceBase):
    """Service for sending push notifications via Firebase Cloud Messaging (FCM)"""

    def __init__(self):
        self.app = None
        self._initialize_firebase()

    def _calculate_backoff_with_jitter(
        self, attempt: int, base_delay: float = 1.0, max_delay: float = 32.0
    ) -> float:
        """Calculate exponential backoff delay with jittering to prevent thundering herd"""
        # Exponential backoff: delay = base_delay * 2^attempt
        delay = min(base_delay * (2**attempt), max_delay)
        # Add jitter: ±25% random variation
        jitter = delay * 0.25 * (2 * random.random() - 1)
        return max(0.1, delay + jitter)

    def _should_smooth_traffic(self) -> float:
        """Add small random delay to smooth traffic and avoid spikes"""
        # Firebase recommends smoothing traffic over at least an hour
        # Add 0-2 second random delay for basic traffic smoothing
        return random.uniform(0, 2.0)

    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK"""
        try:
            # Check if Firebase is already initialized
            if firebase_admin._apps:
                self.app = firebase_admin.get_app()
                logger.info("Using existing Firebase app instance")
                return

            # Initialize Firebase with service account credentials
            if settings.fcm_service_account_key_path:
                # From file path
                cred = credentials.Certificate(settings.fcm_service_account_key_path)
                self.app = initialize_app(cred)
                logger.info("Firebase initialized with service account file")
            elif settings.fcm_service_account_json:
                # From JSON string (environment variable)
                service_account_info = json.loads(settings.fcm_service_account_json)
                cred = credentials.Certificate(service_account_info)
                self.app = initialize_app(cred)
                logger.info("Firebase initialized with service account JSON")
            else:
                logger.warning("No FCM credentials configured, FCM service disabled")
                self.app = None

        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            self.app = None

    def _is_fcm_token_valid(self, token: str) -> bool:
        """Validate FCM token format"""
        # FCM tokens are typically 152+ characters and contain alphanumeric chars, hyphens, underscores
        if not token or len(token) < 100:
            return False

        # Basic format check - FCM tokens are base64-like strings
        import re

        pattern = r"^[A-Za-z0-9_:-]+$"
        return bool(re.match(pattern, token))

    def _awaiting_input_count(self, db: Session, user_id: UUID) -> int:
        """Number of the user's sessions currently waiting on their input.

        This is the value surfaced as the app-icon badge: agent instances the
        user owns whose status is AWAITING_INPUT (the agent asked a question
        that hasn't been answered yet). Recomputed on every push so the badge
        self-corrects — including clearing to 0 — no matter which device the
        user answered on. Backed by the (user_id, status) composite index.
        """
        return (
            db.query(func.count(AgentInstance.id))
            .filter(
                AgentInstance.user_id == user_id,
                AgentInstance.status == AgentStatus.AWAITING_INPUT,
            )
            .scalar()
        ) or 0

    async def send_notification(
        self,
        db: Session,
        user_id: UUID,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send push notification to all user's FCM devices"""
        if not self.app:
            logger.warning("FCM not configured, skipping notification")
            return False

        try:
            # Check if user has push notifications enabled
            user = db.query(User).filter(User.id == user_id).first()
            if not user or not user.push_notifications_enabled:
                logger.info(f"Push notifications disabled for user {user_id}")
                return False

            # Get user's active FCM push tokens (filter by platform)
            tokens = (
                db.query(PushToken)
                .filter(
                    PushToken.user_id == user_id,
                    PushToken.is_active,
                    PushToken.platform.in_(
                        ["android", "ios", "web"]
                    ),  # Support Flutter tokens
                )
                .all()
            )

            if not tokens:
                logger.info(f"No FCM tokens found for user {user_id}")
                return False

            # Deduplicate tokens and validate format
            valid_tokens = []
            for token in tokens:
                if self._is_fcm_token_valid(token.token) and token.token not in [
                    t.token for t in valid_tokens
                ]:
                    valid_tokens.append(token)

            logger.info(
                f"Found {len(tokens)} total tokens, {len(valid_tokens)} valid FCM tokens for user {user_id}"
            )

            if not valid_tokens:
                logger.warning("No valid FCM tokens to send to")
                return False

            # App-icon badge = the user's sessions currently awaiting input.
            # Sent on every push so the OS renders/updates it in the background
            # (iOS applies aps.badge automatically) and the Flutter foreground
            # handler can mirror it from the data payload.
            badge_count = self._awaiting_input_count(db, user_id)

            # Prepare FCM message
            notification = messaging.Notification(title=title, body=body)

            # Prepare data payload (FCM requires string values)
            fcm_data = {}
            if data:
                for key, value in data.items():
                    fcm_data[key] = str(value) if not isinstance(value, str) else value

            # Add default data
            fcm_data.update(
                {
                    "click_action": "FLUTTER_NOTIFICATION_CLICK",
                    "sound": "default",
                    "badge": str(badge_count),
                }
            )

            # Android-specific configuration
            android_config = messaging.AndroidConfig(
                notification=messaging.AndroidNotification(
                    channel_id="agent-questions",
                    priority="high",
                    default_sound=True,
                    default_vibrate_timings=True,
                    notification_count=badge_count,
                ),
                priority="high",
            )

            # iOS-specific configuration
            apns_config = messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        alert=messaging.ApsAlert(title=title, body=body),
                        sound="default",
                        badge=badge_count,
                        content_available=True,
                    )
                )
            )

            # Send to FCM in batches with retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        logger.info(
                            f"FCM notification retry attempt {attempt + 1} of {max_retries}"
                        )

                    # Send in batches (FCM supports up to 500 tokens per batch)
                    batch_size = 500
                    success_count = 0

                    for i in range(0, len(valid_tokens), batch_size):
                        batch_tokens = [
                            t.token for t in valid_tokens[i : i + batch_size]
                        ]

                        # Skip empty batches
                        if not batch_tokens:
                            logger.warning("Skipping empty token batch")
                            continue

                        logger.info(
                            f"Sending FCM batch with {len(batch_tokens)} tokens"
                        )

                        # Apply traffic smoothing to prevent spikes (Firebase best practice)
                        if len(valid_tokens) > 10:  # Only smooth for larger batches
                            smoothing_delay = self._should_smooth_traffic()
                            logger.debug(
                                f"Applying traffic smoothing delay: {smoothing_delay:.2f}s"
                            )
                            await asyncio.sleep(smoothing_delay)

                        # Use modern send_each_for_multicast for better reliability
                        multicast_message = messaging.MulticastMessage(
                            notification=notification,
                            data=fcm_data,
                            tokens=batch_tokens,
                            android=android_config,
                            apns=apns_config,
                        )

                        try:
                            # firebase_admin's SDK is sync; running it on the
                            # event loop blocks every other coroutine on this
                            # process (vicoa-server is workers=1, single-pinned
                            # per fly.server.toml §2.10), so even a routine
                            # 0.5–2s call freezes WS frames, SSE generators,
                            # the asyncpg LISTEN keepalive, and /health.
                            # Offload to the default threadpool.
                            # wait_for caps the await even though the underlying
                            # thread keeps running until the SDK's own deadline
                            # — without this, a Firebase regional hiccup goes
                            # from a visible loop-freeze (pre-to_thread) to a
                            # silent threadpool leak. 10s is well above p99 for
                            # a healthy send and a clear "something is wrong"
                            # signal otherwise.
                            batch_response = await asyncio.wait_for(
                                asyncio.to_thread(
                                    messaging.send_each_for_multicast,
                                    multicast_message,
                                ),
                                timeout=10.0,
                            )
                            success_count += batch_response.success_count

                            # Handle failed tokens
                            if batch_response.failure_count > 0:
                                for idx, send_response in enumerate(
                                    batch_response.responses
                                ):
                                    if not send_response.success:
                                        token_obj = valid_tokens[i + idx]
                                        error = send_response.exception

                                        # Check for invalid registration tokens.
                                        # The Python SDK wraps FCM REST errors into typed
                                        # exceptions; the `.code` attribute is the canonical
                                        # Google API code (e.g. "NOT_FOUND"), NOT the FCM REST
                                        # string ("UNREGISTERED"). Match by class instead.
                                        if isinstance(
                                            error,
                                            (
                                                messaging.UnregisteredError,
                                                messaging.SenderIdMismatchError,
                                            ),
                                        ):
                                            logger.warning(
                                                f"Deactivating invalid FCM token: {token_obj.token}"
                                            )
                                            token_obj.is_active = False
                                            token_obj.updated_at = datetime.now(
                                                timezone.utc
                                            )
                                            # Commit is deferred to the
                                            # function-level finally so a
                                            # batch with N stale tokens does
                                            # one PG round-trip, not N.
                                        else:
                                            logger.error(
                                                f"FCM error for token {token_obj.token}: {error}"
                                            )

                        except asyncio.TimeoutError:
                            logger.warning(
                                "FCM batch send timed out after 10s "
                                f"(batch_size={len(batch_tokens)}, user_id={user_id}); "
                                "skipping batch"
                            )
                            continue
                        except FirebaseError as batch_error:
                            logger.error(f"Firebase batch error: {batch_error}")

                            # Handle specific error codes according to Firebase best practices
                            error_code = getattr(batch_error, "code", None)
                            if error_code in [
                                "INVALID_ARGUMENT",
                                "UNAUTHENTICATED",
                                "PERMISSION_DENIED",
                                "NOT_FOUND",
                            ]:
                                # 400/401/403/404: Abort, do not retry
                                logger.error(
                                    f"Non-retryable error {error_code}, aborting batch"
                                )
                                continue
                            elif error_code == "QUOTA_EXCEEDED":
                                # 429: Retry after delay (with exponential backoff)
                                retry_after = (
                                    getattr(batch_error, "retry_after", None) or 60
                                )
                                logger.warning(
                                    f"Rate limited, waiting {retry_after}s before retry"
                                )
                                await asyncio.sleep(retry_after)
                                continue
                            elif error_code == "INTERNAL" or "500" in str(batch_error):
                                # 500: Retry with exponential backoff
                                logger.warning(
                                    f"Server error, will retry: {batch_error}"
                                )
                                # Will be handled by outer retry loop
                                raise
                            else:
                                # Other errors: continue to next batch
                                logger.warning(
                                    f"Unexpected error, continuing: {batch_error}"
                                )
                                continue

                    if success_count > 0:
                        logger.info(
                            f"Successfully sent {success_count} FCM notifications to user {user_id}"
                        )
                        return True
                    else:
                        logger.warning(
                            f"No FCM notifications sent successfully for user {user_id}"
                        )
                        return False

                except FirebaseError as e:
                    logger.error(f"Firebase error: {str(e)}")
                    if attempt < max_retries - 1:
                        # Use proper exponential backoff with jittering
                        wait_time = self._calculate_backoff_with_jitter(attempt)
                        logger.warning(f"Retrying FCM notification in {wait_time:.2f}s")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        return False

                except Exception as e:
                    # Check if this is a connection-related error that should be retried
                    is_connection_error = (
                        isinstance(e, (ConnectionError, OSError))
                        or "connection" in str(e).lower()
                        or "timeout" in str(e).lower()
                    )

                    if is_connection_error and attempt < max_retries - 1:
                        wait_time = self._calculate_backoff_with_jitter(attempt)
                        logger.warning(
                            f"FCM attempt {attempt + 1} failed, retrying in {wait_time:.2f}s: {type(e).__name__}: {e}"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(
                            f"Unexpected error sending FCM notification: {type(e).__name__}: {e}"
                        )
                        return False

            return False

        except Exception as e:
            logger.error(
                f"Unexpected error in FCM send_notification: {type(e).__name__}: {e}"
            )
            return False
        finally:
            # Persist any token deactivations accumulated during the batch
            # loop in a single commit. SQLAlchemy's dirty tracking flushes
            # all mutated PushToken rows in one round-trip; no-op when no
            # tokens went stale this call.
            try:
                db.commit()
            except Exception:
                logger.exception("Failed to persist FCM token deactivations")
                db.rollback()

    async def send_question_notification(
        self,
        db: Session,
        user_id: UUID,
        instance_id: str,
        agent_name: str,
        question_text: str,
    ) -> bool:
        """Send FCM notification for new agent question"""
        # Format agent name for display
        display_name = agent_name.replace("_", " ").title()
        title = f"{display_name} needs your input"

        # Truncate question text for notification
        body = question_text
        if len(body) > 100:
            body = body[:97] + "..."

        data = {
            "type": "new_question",
            "instanceId": instance_id,
        }

        return await self.send_notification(
            db=db,
            user_id=user_id,
            title=title,
            body=body,
            data=data,
        )

    async def send_step_notification(
        self,
        db: Session,
        user_id: UUID,
        instance_id: str,
        agent_name: str,
        step_description: str,
    ) -> bool:
        """Send FCM notification for new agent step"""
        # Format agent name for display
        display_name = agent_name.replace("_", " ").title()
        title = f"{display_name} - New Step"

        # Truncate step description for notification
        body = step_description
        if len(body) > 100:
            body = body[:97] + "..."

        data = {
            "type": "new_step",
            "instanceId": instance_id,
        }

        return await self.send_notification(
            db=db,
            user_id=user_id,
            title=title,
            body=body,
            data=data,
        )


# Singleton instance
fcm_service = FCMNotificationService()
