"""
Database queries for AgentType operations.
"""

from datetime import datetime, timezone
from uuid import UUID

from shared.database import (
    AgentType,
    AgentInstance,
    AgentStatus,
    Message,
)
from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from ..models import UserAgentRequest
from .queries import format_agent_instance, _get_instance_message_stats


def create_user_agent(
    db: Session, user_id: UUID, request: UserAgentRequest
) -> dict | None:
    """Create a new user agent configuration"""

    # Check if non-deleted agent with same name already exists for this user
    existing = (
        db.query(AgentType)
        .filter(
            and_(
                AgentType.user_id == user_id,
                AgentType.name == request.name,
                AgentType.is_deleted.is_(False),
            )
        )
        .first()
    )

    if existing:
        return None

    agent_type = AgentType(
        user_id=user_id,
        name=request.name,
        is_active=request.is_active,
    )

    db.add(agent_type)
    db.commit()
    db.refresh(agent_type)

    return _format_user_agent(agent_type, db)


def get_user_agents(db: Session, user_id: UUID) -> list[dict]:
    """Get all non-deleted user agents for a specific user"""

    agent_types = (
        db.query(AgentType)
        .filter(and_(AgentType.user_id == user_id, AgentType.is_deleted.is_(False)))
        .all()
    )

    return [_format_user_agent(agent, db) for agent in agent_types]


def update_user_agent(
    db: Session, agent_id: UUID, user_id: UUID, request: UserAgentRequest
) -> dict | None:
    """Update an existing user agent configuration"""

    agent_type = (
        db.query(AgentType)
        .filter(
            and_(
                AgentType.id == agent_id,
                AgentType.user_id == user_id,
                AgentType.is_deleted.is_(False),
            )
        )
        .first()
    )

    if not agent_type:
        return None

    agent_type.name = request.name
    agent_type.is_active = request.is_active
    agent_type.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(agent_type)

    return _format_user_agent(agent_type, db)


def get_user_agent_instances(db: Session, agent_id: UUID, user_id: UUID) -> list | None:
    """Get all instances for a specific user agent"""

    # Verify the user agent exists, belongs to the user, and is not deleted
    agent_type = (
        db.query(AgentType)
        .filter(
            and_(
                AgentType.id == agent_id,
                AgentType.user_id == user_id,
                AgentType.is_deleted.is_(False),
            )
        )
        .first()
    )

    if not agent_type:
        return None

    # Get all instances for this user agent with relationships loaded
    instances = (
        db.query(AgentInstance)
        .options(
            joinedload(AgentInstance.agent_type),
        )
        .filter(AgentInstance.agent_type_id == agent_id)
        .order_by(AgentInstance.started_at.desc())
        .all()
    )

    # Get all instance IDs for bulk message stats query
    instance_ids = [instance.id for instance in instances]

    # Get message stats for all instances in one efficient query
    message_stats = _get_instance_message_stats(db, instance_ids)

    # Format instances using the same helper function used by other endpoints
    return [format_agent_instance(instance, message_stats) for instance in instances]


def delete_user_agent(db: Session, agent_id: UUID, user_id: UUID) -> bool:
    """Soft delete a user agent and mark its instances as deleted, while removing messages"""

    # First verify the user agent exists, belongs to the user, and is not already deleted
    agent_type = (
        db.query(AgentType)
        .filter(
            and_(
                AgentType.id == agent_id,
                AgentType.user_id == user_id,
                AgentType.is_deleted.is_(False),
            )
        )
        .first()
    )

    if not agent_type:
        return False

    # Get all agent instances for this user agent
    agent_instances = (
        db.query(AgentInstance).filter(AgentInstance.agent_type_id == agent_id).all()
    )

    # For each agent instance, delete all messages (for privacy/storage)
    for instance in agent_instances:
        db.query(Message).filter(Message.agent_instance_id == instance.id).delete()

    # Mark all agent instances as DELETED. A bulk .update() bypasses the
    # ORM's onupdate hook, so updated_at must be set explicitly — otherwise
    # the WebSocket mutable-entity merge (§2.6) would treat the row as
    # unchanged and drop the instance-update broadcast.
    db.query(AgentInstance).filter(AgentInstance.agent_type_id == agent_id).update(
        {
            "status": AgentStatus.DELETED,
            "updated_at": datetime.now(timezone.utc),
        }
    )

    # Soft delete the user agent
    agent_type.is_deleted = True
    agent_type.updated_at = datetime.now(timezone.utc)

    db.commit()

    return True


def _format_user_agent(agent_type: AgentType, db: Session) -> dict:
    """Helper function to format a user agent with instance counts"""

    # Get instance counts
    instance_count = (
        db.query(func.count(AgentInstance.id))
        .filter(AgentInstance.agent_type_id == agent_type.id)
        .scalar()
    )

    active_instance_count = (
        db.query(func.count(AgentInstance.id))
        .filter(
            and_(
                AgentInstance.agent_type_id == agent_type.id,
                AgentInstance.status == AgentStatus.ACTIVE,
            )
        )
        .scalar()
    )

    waiting_instance_count = (
        db.query(func.count(AgentInstance.id))
        .filter(
            and_(
                AgentInstance.agent_type_id == agent_type.id,
                AgentInstance.status == AgentStatus.AWAITING_INPUT,
            )
        )
        .scalar()
    )

    completed_instance_count = (
        db.query(func.count(AgentInstance.id))
        .filter(
            and_(
                AgentInstance.agent_type_id == agent_type.id,
                AgentInstance.status == AgentStatus.COMPLETED,
            )
        )
        .scalar()
    )

    error_instance_count = (
        db.query(func.count(AgentInstance.id))
        .filter(
            and_(
                AgentInstance.agent_type_id == agent_type.id,
                AgentInstance.status.in_([AgentStatus.FAILED, AgentStatus.KILLED]),
            )
        )
        .scalar()
    )

    return {
        "id": str(agent_type.id),
        "name": agent_type.name,
        "is_active": agent_type.is_active,
        "created_at": agent_type.created_at,
        "updated_at": agent_type.updated_at,
        "instance_count": instance_count or 0,
        "active_instance_count": active_instance_count or 0,
        "waiting_instance_count": waiting_instance_count or 0,
        "completed_instance_count": completed_instance_count or 0,
        "error_instance_count": error_instance_count or 0,
    }
