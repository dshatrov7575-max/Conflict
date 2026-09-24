from django.contrib import admin

from .models import (
    Actor,
    ActorElementAssessment,
    ActorElementRole,
    ActorRelation,
    AnalyticalElement,
    AssessmentEvidence,
    AssessmentSet,
    AuditEvent,
    CalculationStrategyDefinition,
    ChatCitation,
    ChatConversation,
    ChatMessage,
    DataGap,
    Document,
    DocumentContent,
    DocumentVersion,
    EvidenceLink,
    EvidenceSource,
    Experiment,
    ExpertProfile,
    Fact,
    FactEvidence,
    GroupTensionRelation,
    HelpTopic,
    ImportRun,
    LegacyCompatibilityReceipt,
    LegacyTermMapping,
    ParameterDefinition,
    ParameterValue,
    ParameterValueEvidence,
    ParticipantGroup,
    PowerComponent,
    PowerComponentEvidence,
    PowerProfile,
    Project,
    ProjectDefinitionVersion,
    ProjectLock,
    ProjectPublication,
    ProjectSchemaVersion,
    Scenario,
    ScenarioOverride,
    Source,
    TextFragment,
    TerminologyEntry,
    TensionPoint,
    TimeSlice,
    UIHelpBinding,
    ProjectWorkspace,
)


class StableVersionedAdmin(admin.ModelAdmin):
    list_display = ("code", "version", "updated_at")
    search_fields = ("code",)
    readonly_fields = ("id", "created_at", "updated_at")


class ReadOnlyStructureAdmin(StableVersionedAdmin):
    """Prevent generic-admin bypass of the project structure policy."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class HiddenLegacyCompatibilityAdmin(ReadOnlyStructureAdmin):
    """Keep V1 storage importable without exposing deprecated constructs as current UI."""

    def has_module_permission(self, request):
        return False


admin.site.register(
    (
        Project,
        ProjectDefinitionVersion,
        ProjectPublication,
        ProjectWorkspace,
        ProjectLock,
        TimeSlice,
        Actor,
        ActorRelation,
        AnalyticalElement,
        ActorElementRole,
    ),
    ReadOnlyStructureAdmin,
)

admin.site.register(
    (
        AssessmentSet,
        ExpertProfile,
        Experiment,
        ActorElementAssessment,
        ParameterDefinition,
        ParameterValue,
        Source,
        Document,
        DataGap,
        PowerProfile,
        PowerComponent,
        ChatConversation,
    ),
    StableVersionedAdmin,
)

admin.site.register(
    (
        DocumentVersion,
        DocumentContent,
        TextFragment,
        Fact,
        FactEvidence,
        AssessmentEvidence,
        ParameterValueEvidence,
        PowerComponentEvidence,
        HelpTopic,
        UIHelpBinding,
        ChatMessage,
        ChatCitation,
        ImportRun,
        LegacyCompatibilityReceipt,
        TerminologyEntry,
        LegacyTermMapping,
    ),
    ReadOnlyStructureAdmin,
)

admin.site.register(
    (
        ProjectSchemaVersion,
        TensionPoint,
        ParticipantGroup,
        GroupTensionRelation,
        EvidenceSource,
        EvidenceLink,
        CalculationStrategyDefinition,
        Scenario,
        ScenarioOverride,
    ),
    HiddenLegacyCompatibilityAdmin,
)


@admin.register(AuditEvent)
class AuditEventAdmin(StableVersionedAdmin):
    list_display = (
        "code",
        "action",
        "actor_type",
        "actor_identifier",
        "entity_type",
        "occurred_at",
    )
    list_filter = ("action", "actor_type")
    search_fields = ("code", "actor_identifier", "entity_type")
    readonly_fields = StableVersionedAdmin.readonly_fields + ("occurred_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
