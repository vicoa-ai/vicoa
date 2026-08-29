import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from shared.config import settings
from shared.database.models import User

from ..auth.dependencies import get_current_user
from ..models import DeepgramTokenResponse

router = APIRouter(tags=["deepgram"])
logger = logging.getLogger(__name__)

_DEEPGRAM_TEMP_TOKEN_URL = "https://api.deepgram.com/v1/auth/grant"
_DEEPGRAM_TEMP_TOKEN_TTL_SECONDS = 300


@router.post("/deepgram/token", response_model=DeepgramTokenResponse)
async def create_deepgram_token(
    response: Response,
    current_user: User = Depends(get_current_user),
):
    """Return a short-lived Deepgram token for the authenticated user."""
    del current_user

    if not settings.deepgram_api_key:
        raise HTTPException(
            status_code=503,
            detail="Voice transcription is not configured.",
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            upstream_response = await client.post(
                _DEEPGRAM_TEMP_TOKEN_URL,
                headers={
                    "Authorization": f"Token {settings.deepgram_api_key}",
                    "Content-Type": "application/json",
                },
                json={"ttl_seconds": _DEEPGRAM_TEMP_TOKEN_TTL_SECONDS},
            )
            upstream_response.raise_for_status()
            data = upstream_response.json()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Deepgram token grant failed with status %s: %s",
            exc.response.status_code,
            exc.response.text[:500],
        )
        raise HTTPException(
            status_code=502,
            detail="Unable to create a voice transcription session.",
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("Deepgram token grant request failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Unable to create a voice transcription session.",
        ) from exc

    token = data.get("access_token")
    if not token:
        raise HTTPException(
            status_code=502,
            detail="Voice transcription provider returned an invalid response.",
        )

    response.headers["Cache-Control"] = "no-store"
    return DeepgramTokenResponse(token=token)
