from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
    URLValidator,
)
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .enums import (
    AssessmentKind,
    AuditAction,
    AuditActorType,
    EvidenceRelation,
    ParameterValueType,
    ScenarioStatus,
    StrategyStatus,
    TargetType,
    ValueStatus,
)


CODE_VALIDATOR = RegexValidator(
    regex=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
    message=(
        "Codes must start with an ASCII letter or digit and contain only "
        "letters, digits, dot, underscore, colon, or hyphen."
    ),
)
SHA256_VALIDATOR = RegexValidator(
    regex=r"^[0-9a-f]{64}$",
    message="A manifest hash must be a lowercase hexadecimal SHA-256 digest.",
)

ABSENT_VALUE_STATUSES = (
    ValueStatus.UNKNOWN,
    ValueStatus.NOT_APPLICABLE,
    ValueStatus.INSUFFICIENT_DATA,
    ValueStatus.OPEN_METHOD,
)
PRESENT_VALUE_STATUSES = (
    ValueStatus.PROVISIONAL,
    ValueStatus.CONFIRMED,
)


def _stable_constraints(prefix: str) -> list[models.BaseConstraint]:
    return [
        models.CheckConstraint(
            condition=~Q(code=""),
            name=f"{prefix}_code_not_empty",
        ),
        models.CheckConstraint(
            condition=~Q(version=""),
            name=f"{prefix}_version_not_empty",
        ),
    ]


def _value_presence_constraint(prefix: str) -> models.CheckConstraint:
    """Keep missing-value statuses distinct from numeric (including zero) values."""

    return models.CheckConstraint(
        condition=(
            Q(status__in=tuple(ABSENT_VALUE_STATUSES), value__isnull=True)
            | Q(status__in=tuple(PRESENT_VALUE_STATUSES), value__isnull=False)
        ),
        name=f"{prefix}_status_value_consistent",
    )


def _assessment_metadata_constraint(prefix: str) -> models.CheckConstraint:
    """Require provenance metadata for values while keeping absent states empty."""

    return models.CheckConstraint(
        condition=(
            Q(
                status__in=tuple(ABSENT_VALUE_STATUSES),
                confidence__isnull=True,
                range_min__isnull=True,
                range_max__isnull=True,
            )
            | (
                Q(
                    status__in=tuple(PRESENT_VALUE_STATUSES),
                    confidence__isnull=False,
                    range_min__isnull=False,
                    range_max__isnull=False,
                )
                & ~Q(rationale="")
            )
        ),
        name=f"{prefix}_metadata_consistent",
    )


class StableVersionedModel(models.Model):
    """Identity fields shared by every persistent domain entity."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=128, validators=[CODE_VALIDATOR], db_index=True)
    version = models.CharField(max_length=64, default="1.0.0")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Project(StableVersionedModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("code",)
        constraints = [
            *_stable_constraints("domain_project"),
            models.UniqueConstraint(fields=("code",), name="domain_project_code_uniq"),
        ]

    def __str__(self) -> str:
        return f"{self.code}: {self.name}"


class ProjectSchemaVersion(StableVersionedModel):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="schema_versions",
    )
    is_current = models.BooleanField(default=False)
    manifest = models.JSONField(default=dict, blank=True)
    manifest_hash = models.CharField(
        max_length=64,
        blank=True,
        validators=[SHA256_VALIDATOR],
    )

    class Meta:
        ordering = ("project__code", "version")
        constraints = [
            *_stable_constraints("domain_schema_version"),
            models.UniqueConstraint(
                fields=("project", "code"),
                name="domain_schema_project_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("project", "version"),
                name="domain_schema_project_version_uniq",
            ),
            models.UniqueConstraint(
                fields=("project",),
                condition=Q(is_current=True),
                name="domain_schema_one_current",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.project.code} schema {self.version}"


class ProjectLock(StableVersionedModel):
    """Current project-structure policy; enforcement lives in the policy service."""

    project = models.OneToOneField(
        Project,
        on_delete=models.CASCADE,
        related_name="structure_lock",
    )
    is_structure_locked = models.BooleanField(default=False)
    ordinary_user_can_edit_structure = models.BooleanField(default=True)
    studio_can_edit_structure = models.BooleanField(default=True)
    reason = models.TextField(blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("project__code",)
        constraints = [
            *_stable_constraints("domain_project_lock"),
            models.UniqueConstraint(
                fields=("project", "code"),
                name="domain_lock_project_code_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    Q(is_structure_locked=False)
                    | Q(ordinary_user_can_edit_structure=False)
                ),
                name="domain_lock_blocks_ordinary",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.is_structure_locked and self.ordinary_user_can_edit_structure:
            raise ValidationError(
                {
                    "ordinary_user_can_edit_structure": (
                        "An ordinary user cannot edit the structure of a locked project."
                    )
                }
            )

    def __str__(self) -> str:
        state = "locked" if self.is_structure_locked else "unlocked"
        return f"{self.project.code}: {state}"


class TimeSlice(StableVersionedModel):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="time_slices",
    )
    name = models.CharField(max_length=255, blank=True)
    cutoff_date = models.DateField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("project__code", "order", "cutoff_date")
        constraints = [
            *_stable_constraints("domain_time_slice"),
            models.UniqueConstraint(
                fields=("project", "code"),
                name="domain_slice_project_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("project", "cutoff_date"),
                name="domain_slice_project_date_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.project.code}/{self.code}"


class TensionPoint(StableVersionedModel):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="tension_points",
    )
    name = models.CharField(max_length=500)
    short_name = models.CharField(max_length=255, blank=True)
    definition = models.TextField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("project__code", "order", "code")
        constraints = [
            *_stable_constraints("domain_tension_point"),
            models.UniqueConstraint(
                fields=("project", "code"),
                name="domain_tension_project_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("project", "order"),
                name="domain_tension_project_order_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code}: {self.name}"


class ParticipantGroup(StableVersionedModel):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="participant_groups",
    )
    name = models.CharField(max_length=500)
    short_name = models.CharField(max_length=255, blank=True)
    definition = models.TextField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("project__code", "order", "code")
        constraints = [
            *_stable_constraints("domain_participant_group"),
            models.UniqueConstraint(
                fields=("project", "code"),
                name="domain_group_project_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("project", "order"),
                name="domain_group_project_order_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code}: {self.name}"


def _validate_related_project(
    *,
    project_id: uuid.UUID | None,
    related_model: type[models.Model],
    related_id: uuid.UUID | None,
    field_name: str,
    errors: dict[str, str],
) -> None:
    if project_id is None or related_id is None:
        return
    related_project_id = (
        related_model._default_manager.filter(pk=related_id)
        .values_list("project_id", flat=True)
        .first()
    )
    if related_project_id is not None and related_project_id != project_id:
        errors[field_name] = "The referenced object belongs to a different project."


class GroupTensionRelation(StableVersionedModel):
    """Stable identity for a participant-group/tension-point pair."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="group_tension_relations",
    )
    participant_group = models.ForeignKey(
        ParticipantGroup,
        on_delete=models.RESTRICT,
        related_name="tension_relations",
    )
    tension_point = models.ForeignKey(
        TensionPoint,
        on_delete=models.RESTRICT,
        related_name="group_relations",
    )

    class Meta:
        ordering = (
            "project__code",
            "participant_group__order",
            "tension_point__order",
        )
        constraints = [
            *_stable_constraints("domain_group_tension"),
            models.UniqueConstraint(
                fields=("project", "code"),
                name="domain_relation_project_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("project", "participant_group", "tension_point"),
                name="domain_relation_pair_uniq",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        _validate_related_project(
            project_id=self.project_id,
            related_model=ParticipantGroup,
            related_id=self.participant_group_id,
            field_name="participant_group",
            errors=errors,
        )
        _validate_related_project(
            project_id=self.project_id,
            related_model=TensionPoint,
            related_id=self.tension_point_id,
            field_name="tension_point",
            errors=errors,
        )
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.participant_group.code}/{self.tension_point.code}"


class AssessmentSet(StableVersionedModel):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="assessment_sets",
    )
    kind = models.CharField(max_length=16, choices=AssessmentKind.choices)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ("project__code", "kind", "code")
        constraints = [
            *_stable_constraints("domain_assessment_set"),
            models.UniqueConstraint(
                fields=("project", "code"),
                name="domain_set_project_code_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.project.code}/{self.code} ({self.kind})"


class ParameterDefinition(StableVersionedModel):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="parameter_definitions",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    target_type = models.CharField(max_length=32, choices=TargetType.choices)
    value_type = models.CharField(
        max_length=16,
        choices=ParameterValueType.choices,
        default=ParameterValueType.DECIMAL,
    )
    scale_min = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
    )
    scale_max = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
    )
    scale_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("project__code", "code")
        constraints = [
            *_stable_constraints("domain_parameter_def"),
            models.UniqueConstraint(
                fields=("project", "code"),
                name="domain_parameter_project_code_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    Q(scale_min__isnull=True)
                    | Q(scale_max__isnull=True)
                    | Q(scale_min__lte=models.F("scale_max"))
                ),
                name="domain_parameter_scale_order",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if (
            self.scale_min is not None
            and self.scale_max is not None
            and self.scale_min > self.scale_max
        ):
            errors["scale_max"] = "Scale maximum must be greater than or equal to minimum."
        if self.value_type not in {
            ParameterValueType.DECIMAL,
            ParameterValueType.INTEGER,
        } and (self.scale_min is not None or self.scale_max is not None):
            errors["value_type"] = "Only numeric parameters can define a numeric scale."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.code} ({self.version})"


def _target_model(target_type: str) -> type[models.Model] | None:
    return {
        TargetType.PROJECT: Project,
        TargetType.TIME_SLICE: TimeSlice,
        TargetType.TENSION_POINT: TensionPoint,
        TargetType.PARTICIPANT_GROUP: ParticipantGroup,
        TargetType.GROUP_TENSION_RELATION: GroupTensionRelation,
    }.get(target_type)


def _validate_typed_target(
    *,
    project_id: uuid.UUID | None,
    target_type: str,
    target_id: uuid.UUID | None,
    errors: dict[str, str],
) -> models.Model | None:
    model = _target_model(target_type)
    if model is None or target_id is None:
        return None
    target = model._default_manager.filter(pk=target_id).first()
    if target is None:
        errors["target_id"] = f"No {target_type} target exists with this UUID."
        return None
    target_project_id = target.pk if model is Project else target.project_id
    if project_id is not None and target_project_id != project_id:
        errors["target_id"] = "The target belongs to a different project."
    return target


def _validate_status_and_value(
    *,
    status: str,
    value: Any,
    errors: dict[str, str],
) -> None:
    if status in ABSENT_VALUE_STATUSES and value is not None:
        errors["value"] = f"Status {status} requires a null value."
    elif status in PRESENT_VALUE_STATUSES and value is None:
        errors["value"] = f"Status {status} requires a value."


def _validate_parameter_value_type(
    *,
    definition: ParameterDefinition,
    value: Any,
    errors: dict[str, str],
) -> None:
    if value is None:
        return
    if definition.value_type == ParameterValueType.INTEGER:
        if isinstance(value, bool) or not isinstance(value, int):
            errors["value"] = "This parameter requires an integer value."
        numeric_value = Decimal(value) if isinstance(value, int) else None
    elif definition.value_type == ParameterValueType.DECIMAL:
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            errors["value"] = "This parameter requires a decimal-compatible value."
            numeric_value = None
        else:
            try:
                numeric_value = Decimal(str(value))
                if not numeric_value.is_finite():
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                errors["value"] = "This parameter requires a finite decimal value."
                numeric_value = None
    elif definition.value_type == ParameterValueType.BOOLEAN:
        numeric_value = None
        if not isinstance(value, bool):
            errors["value"] = "This parameter requires a boolean value."
    elif definition.value_type == ParameterValueType.TEXT:
        numeric_value = None
        if not isinstance(value, str):
            errors["value"] = "This parameter requires a text value."
    else:
        numeric_value = None

    if numeric_value is not None:
        if definition.scale_min is not None and numeric_value < definition.scale_min:
            errors["value"] = "The value is below the parameter scale minimum."
        if definition.scale_max is not None and numeric_value > definition.scale_max:
            errors["value"] = "The value is above the parameter scale maximum."


def _validate_assessment_metadata(
    *,
    definition: ParameterDefinition | None,
    status: str,
    value: Any,
    confidence: Decimal | None,
    range_min: Any,
    range_max: Any,
    rationale: str,
    errors: dict[str, str],
) -> None:
    """Validate confidence, rationale, and an admissible value range."""

    if status in ABSENT_VALUE_STATUSES:
        if confidence is not None:
            errors["confidence"] = f"Status {status} requires null confidence."
        if range_min is not None or range_max is not None:
            errors["range_min"] = f"Status {status} requires a null range."
        return

    if status not in PRESENT_VALUE_STATUSES:
        return
    if confidence is None:
        errors["confidence"] = "A present assessment requires confidence."
    elif confidence < Decimal("0") or confidence > Decimal("1"):
        errors["confidence"] = "Confidence must be between 0 and 1."
    if not rationale.strip():
        errors["rationale"] = "A present assessment requires a rationale."
    if range_min is None or range_max is None:
        errors["range_min"] = "A present assessment requires an admissible range."
        return
    if definition is None or definition.value_type not in {
        ParameterValueType.DECIMAL,
        ParameterValueType.INTEGER,
    }:
        return
    try:
        minimum = Decimal(str(range_min))
        maximum = Decimal(str(range_max))
        actual = Decimal(str(value))
        if not minimum.is_finite() or not maximum.is_finite() or not actual.is_finite():
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        errors["range_min"] = "The admissible range must contain finite numbers."
        return
    if minimum > maximum:
        errors["range_max"] = "Range maximum must be greater than or equal to minimum."
    elif actual < minimum or actual > maximum:
        errors["value"] = "The value must fall inside its admissible range."


class ParameterValue(StableVersionedModel):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="parameter_values",
    )
    time_slice = models.ForeignKey(
        TimeSlice,
        on_delete=models.RESTRICT,
        related_name="parameter_values",
    )
    assessment_set = models.ForeignKey(
        AssessmentSet,
        on_delete=models.RESTRICT,
        related_name="parameter_values",
    )
    parameter_definition = models.ForeignKey(
        ParameterDefinition,
        on_delete=models.RESTRICT,
        related_name="values",
    )
    target_type = models.CharField(max_length=32, choices=TargetType.choices)
    target_id = models.UUIDField()
    status = models.CharField(
        max_length=32,
        choices=ValueStatus.choices,
        default=ValueStatus.UNKNOWN,
    )
    value = models.JSONField(null=True, blank=True, default=None)
    note = models.TextField(blank=True)
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("1"))],
    )
    range_min = models.JSONField(null=True, blank=True, default=None)
    range_max = models.JSONField(null=True, blank=True, default=None)
    rationale = models.TextField(blank=True)

    class Meta:
        ordering = ("project__code", "time_slice__order", "code")
        constraints = [
            *_stable_constraints("domain_parameter_value"),
            models.UniqueConstraint(
                fields=("project", "code"),
                name="domain_value_project_code_uniq",
            ),
            models.UniqueConstraint(
                fields=(
                    "project",
                    "time_slice",
                    "assessment_set",
                    "parameter_definition",
                    "target_type",
                    "target_id",
                ),
                name="domain_value_context_target_uniq",
            ),
            _value_presence_constraint("domain_value"),
            _assessment_metadata_constraint("domain_value"),
        ]

    @property
    def target_object(self) -> models.Model | None:
        model = _target_model(self.target_type)
        if model is None or self.target_id is None:
            return None
        return model._default_manager.filter(pk=self.target_id).first()

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        _validate_related_project(
            project_id=self.project_id,
            related_model=TimeSlice,
            related_id=self.time_slice_id,
            field_name="time_slice",
            errors=errors,
        )
        _validate_related_project(
            project_id=self.project_id,
            related_model=AssessmentSet,
            related_id=self.assessment_set_id,
            field_name="assessment_set",
            errors=errors,
        )
        _validate_related_project(
            project_id=self.project_id,
            related_model=ParameterDefinition,
            related_id=self.parameter_definition_id,
            field_name="parameter_definition",
            errors=errors,
        )
        definition = None
        if self.parameter_definition_id is not None:
            definition = ParameterDefinition.objects.filter(
                pk=self.parameter_definition_id
            ).first()
        if definition is not None and definition.target_type != self.target_type:
            errors["target_type"] = (
                "The target type does not match the parameter definition."
            )
        _validate_typed_target(
            project_id=self.project_id,
            target_type=self.target_type,
            target_id=self.target_id,
            errors=errors,
        )
        _validate_status_and_value(status=self.status, value=self.value, errors=errors)
        if definition is not None:
            _validate_parameter_value_type(
                definition=definition,
                value=self.value,
                errors=errors,
            )
        _validate_assessment_metadata(
            definition=definition,
            status=self.status,
            value=self.value,
            confidence=self.confidence,
            range_min=self.range_min,
            range_max=self.range_max,
            rationale=self.rationale,
            errors=errors,
        )
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.assessment_set.code}/{self.parameter_definition.code}/{self.code}"


class EvidenceSource(StableVersionedModel):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="evidence_sources",
    )
    title = models.CharField(max_length=500)
    url = models.URLField(max_length=2048, blank=True)
    additional_urls = models.JSONField(default=list, blank=True)
    published_on = models.DateField(null=True, blank=True)
    accessed_on = models.DateField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("project__code", "code")
        constraints = [
            *_stable_constraints("domain_evidence_source"),
            models.UniqueConstraint(
                fields=("project", "code"),
                name="domain_source_project_code_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    Q(published_on__isnull=True)
                    | Q(accessed_on__isnull=True)
                    | Q(accessed_on__gte=models.F("published_on"))
                ),
                name="domain_source_access_after_publish",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if (
            self.published_on is not None
            and self.accessed_on is not None
            and self.accessed_on < self.published_on
        ):
            errors["accessed_on"] = "Access date cannot precede publication date."
        if not isinstance(self.additional_urls, list):
            errors["additional_urls"] = "Additional URLs must be a JSON list."
        else:
            validate_url = URLValidator()
            for item in self.additional_urls:
                try:
                    if not isinstance(item, str):
                        raise ValidationError("URL must be text.")
                    validate_url(item)
                except ValidationError:
                    errors["additional_urls"] = "Every additional URL must be valid."
                    break
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.code}: {self.title}"


class EvidenceLink(StableVersionedModel):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="evidence_links",
    )
    parameter_value = models.ForeignKey(
        ParameterValue,
        on_delete=models.CASCADE,
        related_name="evidence_links",
    )
    source = models.ForeignKey(
        EvidenceSource,
        on_delete=models.RESTRICT,
        related_name="value_links",
    )
    relation = models.CharField(
        max_length=16,
        choices=EvidenceRelation.choices,
        default=EvidenceRelation.SUPPORTS,
    )
    rationale = models.TextField()

    class Meta:
        ordering = ("project__code", "parameter_value__code", "code")
        constraints = [
            *_stable_constraints("domain_evidence_link"),
            models.UniqueConstraint(
                fields=("project", "code"),
                name="domain_link_project_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("parameter_value", "source"),
                name="domain_link_value_source_uniq",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        _validate_related_project(
            project_id=self.project_id,
            related_model=ParameterValue,
            related_id=self.parameter_value_id,
            field_name="parameter_value",
            errors=errors,
        )
        _validate_related_project(
            project_id=self.project_id,
            related_model=EvidenceSource,
            related_id=self.source_id,
            field_name="source",
            errors=errors,
        )
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.parameter_value.code} <- {self.source.code}"


class CalculationStrategyDefinition(StableVersionedModel):
    """Replaceable strategy registry metadata; intentionally contains no formula."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="calculation_strategies",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=StrategyStatus.choices,
        default=StrategyStatus.DRAFT,
    )
    input_schema = models.JSONField(default=dict, blank=True)
    output_schema = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("code", "version")
        constraints = [
            *_stable_constraints("domain_strategy"),
            models.UniqueConstraint(
                fields=("code", "version"),
                name="domain_strategy_code_version_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} ({self.version})"


class Scenario(StableVersionedModel):
    """Iteration-two schema placeholder; it performs no calculation."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="scenarios",
    )
    time_slice = models.ForeignKey(
        TimeSlice,
        on_delete=models.RESTRICT,
        related_name="scenarios",
    )
    assessment_set = models.OneToOneField(
        AssessmentSet,
        on_delete=models.RESTRICT,
        related_name="scenario",
    )
    base_assessment_set = models.ForeignKey(
        AssessmentSet,
        on_delete=models.RESTRICT,
        related_name="derived_scenarios",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=ScenarioStatus.choices,
        default=ScenarioStatus.DRAFT,
    )

    class Meta:
        ordering = ("project__code", "code")
        constraints = [
            *_stable_constraints("domain_scenario"),
            models.UniqueConstraint(
                fields=("project", "code"),
                name="domain_scenario_project_code_uniq",
            ),
            models.CheckConstraint(
                condition=~Q(assessment_set=models.F("base_assessment_set")),
                name="domain_scenario_distinct_sets",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        _validate_related_project(
            project_id=self.project_id,
            related_model=TimeSlice,
            related_id=self.time_slice_id,
            field_name="time_slice",
            errors=errors,
        )
        _validate_related_project(
            project_id=self.project_id,
            related_model=AssessmentSet,
            related_id=self.assessment_set_id,
            field_name="assessment_set",
            errors=errors,
        )
        _validate_related_project(
            project_id=self.project_id,
            related_model=AssessmentSet,
            related_id=self.base_assessment_set_id,
            field_name="base_assessment_set",
            errors=errors,
        )
        scenario_set = None
        if self.assessment_set_id is not None:
            scenario_set = AssessmentSet.objects.filter(pk=self.assessment_set_id).first()
        if scenario_set is not None and scenario_set.kind != AssessmentKind.SCENARIO:
            errors["assessment_set"] = (
                "A scenario must use a dedicated SCENARIO assessment set."
            )
        if self.assessment_set_id == self.base_assessment_set_id:
            errors["base_assessment_set"] = (
                "The scenario assessment set cannot also be its base set."
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.project.code}/{self.code}"


class ScenarioOverride(StableVersionedModel):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="scenario_overrides",
    )
    scenario = models.ForeignKey(
        Scenario,
        on_delete=models.CASCADE,
        related_name="overrides",
    )
    parameter_definition = models.ForeignKey(
        ParameterDefinition,
        on_delete=models.RESTRICT,
        related_name="scenario_overrides",
    )
    target_type = models.CharField(max_length=32, choices=TargetType.choices)
    target_id = models.UUIDField()
    status = models.CharField(
        max_length=32,
        choices=ValueStatus.choices,
        default=ValueStatus.UNKNOWN,
    )
    value = models.JSONField(null=True, blank=True, default=None)
    note = models.TextField(blank=True)
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("1"))],
    )
    range_min = models.JSONField(null=True, blank=True, default=None)
    range_max = models.JSONField(null=True, blank=True, default=None)
    rationale = models.TextField(blank=True)

    class Meta:
        ordering = ("project__code", "scenario__code", "code")
        constraints = [
            *_stable_constraints("domain_scenario_override"),
            models.UniqueConstraint(
                fields=("project", "code"),
                name="domain_override_project_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("scenario", "parameter_definition", "target_type", "target_id"),
                name="domain_override_context_target_uniq",
            ),
            _value_presence_constraint("domain_override"),
            _assessment_metadata_constraint("domain_override"),
        ]

    @property
    def target_object(self) -> models.Model | None:
        model = _target_model(self.target_type)
        if model is None or self.target_id is None:
            return None
        return model._default_manager.filter(pk=self.target_id).first()

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        _validate_related_project(
            project_id=self.project_id,
            related_model=Scenario,
            related_id=self.scenario_id,
            field_name="scenario",
            errors=errors,
        )
        _validate_related_project(
            project_id=self.project_id,
            related_model=ParameterDefinition,
            related_id=self.parameter_definition_id,
            field_name="parameter_definition",
            errors=errors,
        )
        definition = None
        if self.parameter_definition_id is not None:
            definition = ParameterDefinition.objects.filter(
                pk=self.parameter_definition_id
            ).first()
        if definition is not None and definition.target_type != self.target_type:
            errors["target_type"] = (
                "The target type does not match the parameter definition."
            )
        _validate_typed_target(
            project_id=self.project_id,
            target_type=self.target_type,
            target_id=self.target_id,
            errors=errors,
        )
        _validate_status_and_value(status=self.status, value=self.value, errors=errors)
        if definition is not None:
            _validate_parameter_value_type(
                definition=definition,
                value=self.value,
                errors=errors,
            )
        _validate_assessment_metadata(
            definition=definition,
            status=self.status,
            value=self.value,
            confidence=self.confidence,
            range_min=self.range_min,
            range_max=self.range_max,
            rationale=self.rationale,
            errors=errors,
        )
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.scenario.code}/{self.code}"


class AuditEvent(StableVersionedModel):
    """Append-only attribution record for assessment and structure changes."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="audit_events",
    )
    assessment_set = models.ForeignKey(
        AssessmentSet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    parameter_value = models.ForeignKey(
        ParameterValue,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    action = models.CharField(max_length=16, choices=AuditAction.choices)
    actor_type = models.CharField(max_length=16, choices=AuditActorType.choices)
    actor_identifier = models.CharField(max_length=255)
    entity_type = models.CharField(max_length=128)
    entity_id = models.UUIDField()
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ("-occurred_at", "code")
        constraints = [
            *_stable_constraints("domain_audit_event"),
            models.UniqueConstraint(
                fields=("project", "code"),
                name="domain_audit_project_code_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=("project", "entity_type", "entity_id"),
                name="domain_audit_entity_idx",
            ),
            models.Index(
                fields=("project", "occurred_at"),
                name="domain_audit_time_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        _validate_related_project(
            project_id=self.project_id,
            related_model=AssessmentSet,
            related_id=self.assessment_set_id,
            field_name="assessment_set",
            errors=errors,
        )
        _validate_related_project(
            project_id=self.project_id,
            related_model=ParameterValue,
            related_id=self.parameter_value_id,
            field_name="parameter_value",
            errors=errors,
        )
        if self.parameter_value_id is not None and self.assessment_set_id is not None:
            value_set_id = (
                ParameterValue.objects.filter(pk=self.parameter_value_id)
                .values_list("assessment_set_id", flat=True)
                .first()
            )
            if value_set_id is not None and value_set_id != self.assessment_set_id:
                errors["assessment_set"] = (
                    "The assessment set must match the audited parameter value."
                )
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.occurred_at.isoformat()} {self.action} {self.entity_type}"
