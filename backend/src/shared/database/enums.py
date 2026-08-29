from enum import Enum


class AgentStatus(str, Enum):
    STARTING = "STARTING"
    ACTIVE = "ACTIVE"
    AWAITING_INPUT = "AWAITING_INPUT"
    PAUSED = "PAUSED"
    STALE = "STALE"
    COMPLETED = "COMPLETED"
    REVIEWED = "REVIEWED"
    FAILED = "FAILED"
    KILLED = "KILLED"
    DISCONNECTED = "DISCONNECTED"
    DELETED = "DELETED"


class SenderType(str, Enum):
    AGENT = "AGENT"
    USER = "USER"


class InstanceAccessLevel(str, Enum):
    READ = "READ"
    WRITE = "WRITE"


class TeamRole(str, Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"
