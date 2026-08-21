from django.contrib import admin

from .models import (
    AssessmentSet,
    AuditEvent,
    CalculationStrategyDefinition,
    EvidenceLink,
    EvidenceSource,
    GroupTensionRelation,
    ParameterDefinition,
    ParameterValue,
    ParticipantGroup,
    Project,
    ProjectLock,
    ProjectSchemaVersion,
    Scenario,
    ScenarioOverride,
    TensionPoint,
    TimeSlice,
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


admin.site.register(
    (
        Project,
        ProjectSchemaVersion,
        ProjectLock,
        TimeSlice,
        TensionPoint,
        ParticipantGroup,
        GroupTensionRelation,
    ),
    ReadOnlyStructureAdmin,
)

admin.site.register(
    (
        AssessmentSet,
        ParameterDefinition,
        ParameterValue,
        EvidenceSource,
        EvidenceLink,
        CalculationStrategyDefinition,
        Scenario,
        ScenarioOverride,
    ),
    StableVersionedAdmin,
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
