from django.db import models


class AssessmentKind(models.TextChoices):
    """Independent provenance lanes for assessments."""

    HUMAN = "HUMAN", "Human assessment"
    AI = "AI", "AI assessment"
    CONSENSUS = "CONSENSUS", "Consensus assessment"
    SCENARIO = "SCENARIO", "Scenario assessment"


class ValueStatus(models.TextChoices):
    """State of a value; absence is never encoded as numeric zero."""

    UNKNOWN = "UNKNOWN", "Unknown"
    NOT_APPLICABLE = "NOT_APPLICABLE", "Not applicable"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA", "Insufficient data"
    PROVISIONAL = "PROVISIONAL", "Provisional"
    CONFIRMED = "CONFIRMED", "Confirmed"
    OPEN_METHOD = "OPEN_METHOD", "Method not yet approved"


class TargetType(models.TextChoices):
    PROJECT = "PROJECT", "Project"
    TIME_SLICE = "TIME_SLICE", "Time slice"
    TENSION_POINT = "TENSION_POINT", "Tension point"
    PARTICIPANT_GROUP = "PARTICIPANT_GROUP", "Participant group"
    GROUP_TENSION_RELATION = (
        "GROUP_TENSION_RELATION",
        "Group-tension relation",
    )


class ParameterValueType(models.TextChoices):
    DECIMAL = "DECIMAL", "Decimal"
    INTEGER = "INTEGER", "Integer"
    BOOLEAN = "BOOLEAN", "Boolean"
    TEXT = "TEXT", "Text"
    JSON = "JSON", "JSON"


class EvidenceRelation(models.TextChoices):
    SUPPORTS = "SUPPORTS", "Supports"
    CONTRADICTS = "CONTRADICTS", "Contradicts"
    CONTEXT = "CONTEXT", "Context"


class StrategyStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    DEPRECATED = "DEPRECATED", "Deprecated"


class ScenarioStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    ARCHIVED = "ARCHIVED", "Archived"


class AuditAction(models.TextChoices):
    CREATE = "CREATE", "Create"
    UPDATE = "UPDATE", "Update"
    DELETE = "DELETE", "Delete"
    IMPORT = "IMPORT", "Import"
    LOCK = "LOCK", "Lock"
    UNLOCK = "UNLOCK", "Unlock"


class AuditActorType(models.TextChoices):
    HUMAN = "HUMAN", "Human"
    AI = "AI", "AI"
    SYSTEM = "SYSTEM", "System"
