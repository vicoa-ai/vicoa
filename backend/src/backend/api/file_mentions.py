"""
File Mentions API endpoints for viewing project files.

These endpoints allow web and mobile apps to view files
that have been synced from CLI for @ mention autocomplete.
Files are read-only from web/mobile; syncing is only supported via CLI.
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from shared.database import FileMentions
from shared.database.session import get_db
from sqlalchemy.orm import Session

from ..auth.dependencies import get_current_user
from shared.database.models import User

router = APIRouter(tags=["file-mentions"])


class FileMentionsResponse(BaseModel):
    """Response model for file mentions."""

    project_path: str = Field(..., description="Absolute path to project directory")
    files: List[str] = Field(
        default_factory=list, description="List of relative file paths"
    )
    file_count: int = Field(..., description="Total number of files")


@router.get("/files", response_model=FileMentionsResponse)
def get_file_mentions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    project_path: str | None = Query(None, description="Project path to query"),
) -> FileMentionsResponse:
    """
    Get file mentions for a specific project path.

    Query parameters:
    - project_path: Optional project path to query

    Returns file list for the specified project, or empty if not found.
    """
    try:
        user_uuid = UUID(str(current_user.id))

        # If no project_path specified, return empty
        if not project_path:
            return FileMentionsResponse(
                project_path="",
                files=[],
                file_count=0,
            )

        file_mentions = (
            db.query(FileMentions)
            .filter(
                FileMentions.user_id == user_uuid,
                FileMentions.project_path == project_path,
            )
            .first()
        )

        if not file_mentions:
            return FileMentionsResponse(
                project_path=project_path,
                files=[],
                file_count=0,
            )

        return FileMentionsResponse(
            project_path=file_mentions.project_path,
            files=file_mentions.files,
            file_count=file_mentions.file_count,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve files: {str(e)}"
        )
