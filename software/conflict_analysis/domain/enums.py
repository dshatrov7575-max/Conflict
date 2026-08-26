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
    DISPUTED = "DISPUTED", "Disputed"
    RETROSPECTIVE_KNOWLEDGE = (
        "RETROSPECTIVE_KNOWLEDGE",
        "Retrospective knowledge",
    )


class PublicationStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    VALIDATED = "VALIDATED", "Validated"
    PUBLISHED = "PUBLISHED", "Published"
    RETIRED = "RETIRED", "Retired"


class ActorType(models.TextChoices):
    INDIVIDUAL = "INDIVIDUAL", "Individual"
    GROUP = "GROUP", "Group"
    ORGANIZATION = "ORGANIZATION", "Organization"
    INSTITUTION = "INSTITUTION", "Institution"
    STATE = "STATE", "State"
    OTHER = "OTHER", "Other"


class AnalyticalElementType(models.TextChoices):
    """The nine element types frozen by the Foundation contract."""

    CONFLICT_ISSUE = "CONFLICT_ISSUE", "Conflict issue"
    GRIEVANCE = "GRIEVANCE", "Grievance"
    STRUCTURAL_DRIVER = "STRUCTURAL_DRIVER", "Structural driver"
    PROXIMATE_DRIVER = "PROXIMATE_DRIVER", "Proximate driver"
    TRIGGER = "TRIGGER", "Trigger"
    PROCESS = "PROCESS", "Process"
    INSTITUTIONAL_RESPONSE = "INSTITUTIONAL_RESPONSE", "Institutional response"
    CONSEQUENCE = "CONSEQUENCE", "Consequence"
    PEACE_FACTOR = "PEACE_FACTOR", "Peace factor"


class ActorRoleType(models.TextChoices):
    PRIMARY = "PRIMARY", "Primary"
    SECONDARY = "SECONDARY", "Secondary"
    AFFECTED = "AFFECTED", "Affected"
    INTERMEDIARY = "INTERMEDIARY", "Intermediary"
    OBSERVER = "OBSERVER", "Observer"
    OTHER = "OTHER", "Other"


class ExperimentStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    FROZEN = "FROZEN", "Frozen"
    ARCHIVED = "ARCHIVED", "Archived"


class ExperimentType(models.TextChoices):
    ASSESSMENT = "ASSESSMENT", "Independent assessment"
    MODELING = "MODELING", "Modeling (reserved)"


class AssessmentRecordStatus(models.TextChoices):
    UNKNOWN = "UNKNOWN", "Unknown"
    PROVISIONAL = "PROVISIONAL", "Provisional"
    PROVISIONAL_PRE_METHOD_FREEZE = (
        "PROVISIONAL_PRE_METHOD_FREEZE",
        "Provisional before method freeze",
    )
    CONFIRMED = "CONFIRMED", "Confirmed"
    DISPUTED = "DISPUTED", "Disputed"


class ConfidenceLevel(models.TextChoices):
    UNKNOWN = "UNKNOWN", "Unknown"
    LOW = "LOW", "Low"
    MEDIUM = "MEDIUM", "Medium"
    HIGH = "HIGH", "High"


class EvidenceTemporalStatus(models.TextChoices):
    CONTEMPORANEOUS = "CONTEMPORANEOUS", "Contemporaneous"
    RETROSPECTIVE_KNOWLEDGE = (
        "RETROSPECTIVE_KNOWLEDGE",
        "Retrospective knowledge",
    )
    RETROSPECTIVE_CORROBORATION = (
        "RETROSPECTIVE_CORROBORATION",
        "Retrospective corroboration",
    )
    UNKNOWN = "UNKNOWN", "Unknown"


class AssessmentTemporalStatus(models.TextChoices):
    CONTEMPORANEOUS = "CONTEMPORANEOUS", "Contemporaneous"
    RETROSPECTIVE_KNOWLEDGE = (
        "RETROSPECTIVE_KNOWLEDGE",
        "Retrospective knowledge",
    )
    NO_DIRECT_POSITION = "NO_DIRECT_POSITION", "No direct position"
    UNKNOWN = "UNKNOWN", "Unknown"


class SourceIndependenceStatus(models.TextChoices):
    INDEPENDENT = "INDEPENDENT", "Independent"
    DEPENDENT = "DEPENDENT", "Dependent"
    UNKNOWN = "UNKNOWN", "Unknown"
    UNVERIFIED = "UNVERIFIED", "Unverified"


class DocumentVersionStatus(models.TextChoices):
    URL_ONLY = "URL_ONLY", "URL only"
    URL_CAPTURED_FULL_CONTENT_HASH_PENDING_INGEST = (
        "URL_CAPTURED_FULL_CONTENT_HASH_PENDING_INGEST",
        "URL captured; content hash pending ingest",
    )
    CONTENT_CAPTURED = "CONTENT_CAPTURED", "Content captured"
    VERIFIED = "VERIFIED", "Verified"


class AnchorStatus(models.TextChoices):
    EXACT = "EXACT", "Exact"
    HASH_RECORDED_PENDING_INGEST = (
        "HASH_RECORDED_PENDING_INGEST",
        "Fragment hash recorded; content pending ingest",
    )
    URL_ONLY = "URL_ONLY", "URL only"
    UNRESOLVED = "UNRESOLVED", "Unresolved"
    ANCHOR_MISMATCH = "ANCHOR_MISMATCH", "Anchor mismatch"


class FactType(models.TextChoices):
    OBSERVED_EVENT = "OBSERVED_EVENT", "Observed event"
    OFFICIAL_CLAIM = "OFFICIAL_CLAIM", "Official claim"
    ACTOR_CLAIM = "ACTOR_CLAIM", "Actor claim"
    EXPERT_INTERPRETATION = "EXPERT_INTERPRETATION", "Expert interpretation"
    DISPUTED_CLAIM = "DISPUTED_CLAIM", "Disputed claim"


class FactEvidenceRelation(models.TextChoices):
    SUPPORTS = "SUPPORTS", "Supports"
    REFUTES = "REFUTES", "Refutes"
    CONTEXT = "CONTEXT", "Context"
    CHALLENGES = "CHALLENGES", "Challenges"
    CONTEXTUALIZES = "CONTEXTUALIZES", "Contextualizes"


class FactOrigin(models.TextChoices):
    DOCUMENT_DERIVED = "DOCUMENT_DERIVED", "Document-derived"
    HUMAN_EXPERT_ASSERTION = "HUMAN_EXPERT_ASSERTION", "Human expert assertion"
    AI_ASSERTION = "AI_ASSERTION", "AI assertion"
    IMPORTED_COMMENT = "IMPORTED_COMMENT", "Imported comment"


class FactDirectness(models.TextChoices):
    DIRECT = "DIRECT", "Direct"
    INDIRECT = "INDIRECT", "Indirect"
    GROUP_INFERENCE = "GROUP_INFERENCE", "Group inference"
    UNKNOWN = "UNKNOWN", "Unknown"


class Visibility(models.TextChoices):
    WORKSPACE_SHARED = "WORKSPACE_SHARED", "Workspace shared"
    EXPERIMENT_PRIVATE = "EXPERIMENT_PRIVATE", "Experiment private"
    OWNER_ONLY = "OWNER_ONLY", "Owner only"


class AssessmentEvidenceRole(models.TextChoices):
    PRIMARY_SUPPORT = "PRIMARY_SUPPORT", "Primary support"
    SECONDARY_SUPPORT = "SECONDARY_SUPPORT", "Secondary support"
    COUNTEREVIDENCE = "COUNTEREVIDENCE", "Counterevidence"
    SUPPORTS_POSITION = "SUPPORTS_POSITION", "Supports position"
    SUPPORTS_SALIENCE = "SUPPORTS_SALIENCE", "Supports salience"
    SUPPORTS_POSITION_AND_SALIENCE = (
        "SUPPORTS_POSITION_AND_SALIENCE",
        "Supports position and salience",
    )
    CONTEXT = "CONTEXT", "Context"
    CONTRADICTS = "CONTRADICTS", "Contradicts"


class PowerDimension(models.TextChoices):
    FA = "FA", "Formal authority"
    ER = "ER", "Economic resources"
    OC = "OC", "Organizational capacity"
    CC = "CC", "Coercive capacity"
    AL = "AL", "Actor legitimacy"
    IC = "IC", "Information control"
    NI = "NI", "Network influence"
    EB = "EB", "External backing"


class ChatMessageRole(models.TextChoices):
    SYSTEM = "SYSTEM", "System"
    USER = "USER", "User"
    ASSISTANT = "ASSISTANT", "Assistant"
    TOOL = "TOOL", "Tool"


class ChatChannelType(models.TextChoices):
    PERSONAL = "PERSONAL", "Personal"
    PROJECT_SHARED = "PROJECT_SHARED", "Project shared"


class ChatMessageStatus(models.TextChoices):
    COMPLETE = "COMPLETE", "Complete"
    ERROR = "ERROR", "Error"


class TerminologyMappingStatus(models.TextChoices):
    RENAME_ONLY = "RENAME_ONLY", "Rename only"
    TRANSFER_WITH_REVIEW = "TRANSFER_WITH_REVIEW", "Transfer with review"
    METHOD_BLOCKED = "METHOD_BLOCKED", "Method blocked"
    RECODING_REQUIRED = "RECODING_REQUIRED", "Recoding required"


class HelpApplicationScope(models.TextChoices):
    STUDIO = "STUDIO", "Studio"
    PLAYER = "PLAYER", "Player"
    SHARED = "SHARED", "Shared"


class ImportRunStatus(models.TextChoices):
    PREVIEWED = "PREVIEWED", "Previewed"
    COMMITTED = "COMMITTED", "Committed"
    REJECTED = "REJECTED", "Rejected"
    FAILED = "FAILED", "Failed"


class ImportPackageScope(models.TextChoices):
    """Persistence boundary selected by one immutable import receipt."""

    WORKSPACE = "WORKSPACE", "Workspace"
    PROJECT_DEFINITION = "PROJECT_DEFINITION", "Project definition"


class CompatibilityStatus(models.TextChoices):
    MIGRATED = "MIGRATED", "Migrated"
    UNRESOLVED = "UNRESOLVED", "Unresolved"


class TargetType(models.TextChoices):
    PROJECT = "PROJECT", "Project"
    TIME_SLICE = "TIME_SLICE", "Time slice"
    TENSION_POINT = "TENSION_POINT", "Tension point"
    PARTICIPANT_GROUP = "PARTICIPANT_GROUP", "Participant group"
    GROUP_TENSION_RELATION = (
        "GROUP_TENSION_RELATION",
        "Group-tension relation",
    )
    ACTOR_ELEMENT_ASSESSMENT = (
        "ACTOR_ELEMENT_ASSESSMENT",
        "Actor-element assessment",
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
    VALIDATE = "VALIDATE", "Validate"
    PUBLISH = "PUBLISH", "Publish"
    FREEZE = "FREEZE", "Freeze"
    LOCK = "LOCK", "Lock"
    UNLOCK = "UNLOCK", "Unlock"
    BOOTSTRAP = "BOOTSTRAP", "Bootstrap"


class AuditScope(models.TextChoices):
    """Exactly one Foundation boundary attributed by an audit event."""

    WORKSPACE = "WORKSPACE", "Workspace"
    DEFINITION = "DEFINITION", "Project definition"


class AuditActorType(models.TextChoices):
    HUMAN = "HUMAN", "Human"
    AI = "AI", "AI"
    SYSTEM = "SYSTEM", "System"
