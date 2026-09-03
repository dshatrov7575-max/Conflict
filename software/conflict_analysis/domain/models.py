from __future__ import annotations

import hashlib
import json
import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal, InvalidOperation
from typing import Any, Iterator

from django.core.exceptions import ValidationError
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
    URLValidator,
)
from django.db import IntegrityError, models, transaction
from django.db.models import Q
from django.db.models.utils import resolve_callables
from django.utils import timezone

from .enums import (
    ActorRoleType,
    ActorType,
    AnalyticalElementType,
    AnchorStatus,
    AssessmentEvidenceRole,
    AssessmentKind,
    AssessmentRecordStatus,
    AssessmentTemporalStatus,
    AuditAction,
    AuditActorType,
    AuditScope,
    ChatChannelType,
    ChatMessageRole,
    ChatMessageStatus,
    CompatibilityStatus,
    ConfidenceLevel,
    DocumentVersionStatus,
    EvidenceRelation,
    EvidenceTemporalStatus,
    ExperimentStatus,
    ExperimentType,
    FactDirectness,
    FactEvidenceRelation,
    FactOrigin,
    FactType,
    HelpApplicationScope,
    ImportPackageScope,
    ImportRunStatus,
    ParameterValueType,
    PowerDimension,
    PublicationStatus,
    ScenarioStatus,
    SourceIndependenceStatus,
    StrategyStatus,
    TargetType,
    TerminologyMappingStatus,
    ValueStatus,
    Visibility,
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
LOCALE_VALIDATOR = RegexValidator(
    regex=r"^[a-z]{2,3}(?:-[A-Z]{2})?$",
    message="Locale must be a BCP-47 language tag such as en or ru-RU.",
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
    ValueStatus.DISPUTED,
    ValueStatus.RETROSPECTIVE_KNOWLEDGE,
)


# Runtime writes for typed Studio definitions and their publication receipts
# must pass through the canonical service boundary.  Migrations deliberately
# use historical models, so they neither import nor need this private runtime
# scope.  Separate authorities keep a definition write from accidentally
# authorizing a publication receipt (or vice versa) in callbacks.
_STUDIO_CANONICAL_WRITE_AUTHORITIES: ContextVar[frozenset[str]] = ContextVar(
    "studio_canonical_write_authorities",
    default=frozenset(),
)


@contextmanager
def _canonical_studio_write(*authorities: str) -> Iterator[None]:
    current = _STUDIO_CANONICAL_WRITE_AUTHORITIES.get()
    token = _STUDIO_CANONICAL_WRITE_AUTHORITIES.set(
        current | frozenset(authorities)
    )
    try:
        yield
    finally:
        _STUDIO_CANONICAL_WRITE_AUTHORITIES.reset(token)


def _studio_write_is_authorized(authority: str) -> bool:
    return authority in _STUDIO_CANONICAL_WRITE_AUTHORITIES.get()


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


def _assessment_metadata_constraint(
    prefix: str,
    *,
    allow_assessment_header: bool = False,
) -> models.CheckConstraint:
    """Require provenance metadata and optional ranges supplied as a pair."""

    present_metadata = Q(confidence__isnull=False) & ~Q(rationale="")
    if allow_assessment_header:
        present_metadata |= Q(actor_element_assessment__isnull=False)
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
                )
                & present_metadata
                & (
                    Q(range_min__isnull=True, range_max__isnull=True)
                    | Q(range_min__isnull=False, range_max__isnull=False)
                )
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


class ValidatedStableVersionedModel(StableVersionedModel):
    """Canonical mutable record whose write path always enforces model contracts."""

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)


class RevisionedQuerySet(models.QuerySet):
    """Prevent bulk edits that would bypass explicit correction lineage."""

    def bulk_create(
        self,
        objs: Any,
        batch_size: int | None = None,
        ignore_conflicts: bool = False,
        update_conflicts: bool = False,
        update_fields: Any = None,
        unique_fields: Any = None,
    ) -> Any:
        objects = list(objs)
        if ignore_conflicts or update_conflicts:
            raise ValidationError(
                "Analytical bulk inserts cannot ignore or rewrite identity conflicts."
            )
        with transaction.atomic(using=self.db):
            for obj in objects:
                obj.full_clean()
            return super().bulk_create(
                objects,
                batch_size=batch_size,
                ignore_conflicts=False,
                update_conflicts=False,
                update_fields=update_fields,
                unique_fields=unique_fields,
            )

    def update(self, **kwargs: Any) -> int:
        raise ValidationError("Analytical corrections require a successor record.")

    def bulk_update(
        self,
        objs: Any,
        fields: Any,
        batch_size: int | None = None,
    ) -> int:
        raise ValidationError("Analytical corrections require a successor record.")


class RevisionedManager(models.Manager.from_queryset(RevisionedQuerySet)):
    pass


class RevisionedStableVersionedModel(StableVersionedModel):
    """Immutable-after-insert analytical record with explicit successor lineage."""

    objects = RevisionedManager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        if self.pk and type(self)._default_manager.filter(pk=self.pk).exists():
            previous = type(self)._default_manager.get(pk=self.pk)
            changed = [
                field.name
                for field in self._meta.concrete_fields
                if field.name not in {"created_at", "updated_at"}
                and getattr(previous, field.attname) != getattr(self, field.attname)
            ]
            if changed:
                raise ValidationError(
                    {name: "Analytical corrections require a successor record." for name in changed}
                )
        super().save(*args, **kwargs)


class ProjectPrimaryLanguageAssignment(models.TextChoices):
    EXPLICIT = "EXPLICIT", "Explicit"
    LEGACY_UNKNOWN = "LEGACY_UNKNOWN", "Legacy unknown"


_PROJECT_LANGUAGE_FIELDS = frozenset(
    {"primary_language_tag", "primary_language_assignment"}
)
_PROJECT_LANGUAGE_LOOKUP_PREFIXES = (
    "primary_language_tag__",
    "primary_language_assignment__",
)


def _project_language_error(
    field: str,
    message: str,
    *,
    code: str,
) -> ValidationError:
    return ValidationError({field: ValidationError(message, code=code)})


class ProjectQuerySet(models.QuerySet):
    """Guard the immutable Project language pair on every bulk/upsert path."""

    @classmethod
    def _project_expression_depends_on_language(
        cls,
        expression: Any,
        query: Any,
        seen_annotations: set[str] | None = None,
        seen_queries: set[int] | None = None,
    ) -> bool:
        """Find language dependencies without resolving or executing a query."""

        seen_annotations = seen_annotations or set()
        seen_queries = seen_queries or set()
        expression_name = expression.__class__.__name__
        if expression_name in {"RawSQL", "ExtraWhere"}:
            return True
        if expression_name in {"Subquery", "Exists"}:
            nested_query = getattr(expression, "query", None)
            if nested_query is None or id(nested_query) in seen_queries:
                return nested_query is None
            seen_queries.add(id(nested_query))
            return cls._project_query_depends_on_language(
                nested_query,
                seen_annotations=set(),
                seen_queries=seen_queries,
            )

        if expression_name == "F":
            reference = getattr(expression, "name", None)
            if reference in _PROJECT_LANGUAGE_FIELDS:
                return True
            annotation = query.annotations.get(reference)
            if annotation is not None and reference not in seen_annotations:
                seen_annotations.add(reference)
                return cls._project_expression_depends_on_language(
                    annotation,
                    query,
                    seen_annotations,
                    seen_queries,
                )

        target = getattr(expression, "target", None)
        target_name = getattr(target, "name", None)
        if target_name in _PROJECT_LANGUAGE_FIELDS:
            return True
        reference = getattr(expression, "name", None)
        if reference in _PROJECT_LANGUAGE_FIELDS:
            return True
        annotation = query.annotations.get(reference)
        if annotation is not None and reference not in seen_annotations:
            seen_annotations.add(reference)
            if cls._project_expression_depends_on_language(
                annotation,
                query,
                seen_annotations,
                seen_queries,
            ):
                return True

        get_source_expressions = getattr(expression, "get_source_expressions", None)
        if get_source_expressions is not None:
            for child in get_source_expressions() or ():
                if cls._project_expression_depends_on_language(
                    child,
                    query,
                    seen_annotations,
                    seen_queries,
                ):
                    return True
        return False

    @classmethod
    def _project_query_depends_on_language(
        cls,
        query: Any,
        *,
        seen_annotations: set[str] | None = None,
        seen_queries: set[int] | None = None,
    ) -> bool:
        where = query.where
        if where is None:
            return False
        seen_annotations = seen_annotations or set()
        seen_queries = seen_queries or set()

        for selected in getattr(query, "select", ()) or ():
            if cls._project_expression_depends_on_language(
                selected,
                query,
                seen_annotations,
                seen_queries,
            ):
                return True

        def visit(node: Any) -> bool:
            node_name = node.__class__.__name__
            if node_name in {"RawSQL", "ExtraWhere"}:
                return True
            if node_name == "WhereNode":
                if getattr(node, "connector", None) == "OR":
                    return True
                return any(visit(child) for child in getattr(node, "children", ()))
            if cls._project_expression_depends_on_language(
                node,
                query,
                seen_annotations,
                seen_queries,
            ):
                return True
            return any(
                visit(child)
                for child in getattr(node, "children", ())
                if child is not node
            )

        return visit(where)

    def _reject_unsafe_project_language_query_state(self) -> None:
        """Reject opaque/combined/language-dependent selection state before writes."""

        query = self.query
        if query.combinator or query.combined_queries:
            raise _project_language_error(
                "primary_language_tag",
                "Combined Project QuerySets cannot be used for language-guarded upserts.",
                code="project_primary_language_query_state_forbidden",
            )
        if self._project_query_depends_on_language(query):
            raise _project_language_error(
                "primary_language_tag",
                "Project QuerySet selection state is not safe for a language-guarded upsert.",
                code="project_primary_language_query_state_forbidden",
            )

    @staticmethod
    def _without_language_lookups(values: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in values.items()
            if key not in _PROJECT_LANGUAGE_FIELDS
        }

    @staticmethod
    def _prevalidate_project_language_request(
        *sources: dict[str, Any] | None,
    ) -> tuple[dict[str, str], tuple[dict[str, Any] | None, ...]]:
        from .services.language_tags import (
            LanguageTagValidationError,
            canonicalize_language_tag,
        )

        normalized_sources = tuple(
            dict(source) if source is not None else None for source in sources
        )
        for source in normalized_sources:
            if source is None:
                continue
            for key in source:
                if isinstance(key, str) and key.startswith(
                    _PROJECT_LANGUAGE_LOOKUP_PREFIXES
                ):
                    field = key.split("__", 1)[0]
                    raise _project_language_error(
                        field,
                        "Project language identity does not accept lookup expressions.",
                        code="project_primary_language_lookup_forbidden",
                    )

        requested: dict[str, str] = {}
        for source in normalized_sources:
            if source is None:
                continue
            for field in (
                "primary_language_tag",
                "primary_language_assignment",
            ):
                if field not in source:
                    continue
                value = source[field]
                if callable(value):
                    try:
                        value = value()
                    except Exception as exc:
                        raise _project_language_error(
                            field,
                            "Project language identity callable could not be resolved.",
                            code="project_primary_language_invalid",
                        ) from exc
                if field == "primary_language_tag":
                    try:
                        value = canonicalize_language_tag(value, allow_und=True)
                    except LanguageTagValidationError as exc:
                        raise _project_language_error(
                            field,
                            str(exc),
                            code="project_primary_language_invalid",
                        ) from exc
                elif not isinstance(value, str) or value not in (
                    ProjectPrimaryLanguageAssignment.EXPLICIT,
                    ProjectPrimaryLanguageAssignment.LEGACY_UNKNOWN,
                ):
                    raise _project_language_error(
                        field,
                        "Project language assignment must be EXPLICIT or LEGACY_UNKNOWN.",
                        code="project_primary_language_assignment_invalid",
                    )
                source[field] = value
                if field in requested and requested[field] != value:
                    raise _project_language_error(
                        field,
                        "Project language identity values are inconsistent.",
                        code="project_primary_language_conflict",
                    )
                requested[field] = value

        requested_tag = requested.get("primary_language_tag")
        requested_assignment = requested.get("primary_language_assignment")
        if requested_tag is not None and requested_assignment is not None:
            if (
                requested_assignment == ProjectPrimaryLanguageAssignment.EXPLICIT
                and requested_tag == "und"
            ):
                raise _project_language_error(
                    "primary_language_tag",
                    "EXPLICIT Project language cannot be 'und'.",
                    code="project_primary_language_und_forbidden",
                )
            if (
                requested_assignment
                == ProjectPrimaryLanguageAssignment.LEGACY_UNKNOWN
                and requested_tag != "und"
            ):
                raise _project_language_error(
                    "primary_language_assignment",
                    "LEGACY_UNKNOWN requires the exact 'und' language tag.",
                    code="project_primary_language_assignment_invalid",
                )
        return requested, normalized_sources

    @staticmethod
    def _assert_prevalidated_language_matches(
        project: "Project",
        requested: dict[str, str],
    ) -> None:
        requested_tag = requested.get("primary_language_tag")
        if (
            requested_tag is not None
            and requested_tag != project.primary_language_tag
        ):
            raise _project_language_error(
                "primary_language_tag",
                "The requested Project language conflicts with its immutable identity.",
                code="project_primary_language_conflict",
            )
        requested_assignment = requested.get("primary_language_assignment")
        if (
            requested_assignment is not None
            and requested_assignment != project.primary_language_assignment
        ):
            raise _project_language_error(
                "primary_language_assignment",
                "The requested Project language assignment conflicts with its immutable identity.",
                code="project_primary_language_conflict",
            )

    def _get_or_create_prevalidated(
        self,
        *,
        defaults: dict[str, Any] | None,
        lookup_values: dict[str, Any],
        requested_language: dict[str, str],
    ) -> tuple[Any, bool]:
        self._for_write = True
        identity_lookup = self._without_language_lookups(lookup_values)
        try:
            project = self.get(**identity_lookup)
        except self.model.DoesNotExist:
            params = self._extract_model_params(defaults, **lookup_values)
            try:
                with transaction.atomic(using=self.db):
                    params = dict(resolve_callables(params))
                    return self.create(**params), True
            except IntegrityError:
                try:
                    project = self.get(**identity_lookup)
                except self.model.DoesNotExist:
                    raise
                self._assert_prevalidated_language_matches(
                    project,
                    requested_language,
                )
                return project, False
        self._assert_prevalidated_language_matches(project, requested_language)
        return project, False

    def update(self, **kwargs: Any) -> int:
        if _PROJECT_LANGUAGE_FIELDS.intersection(kwargs):
            raise _project_language_error(
                "primary_language_tag",
                "A Project primary-language identity is immutable.",
                code="project_primary_language_immutable",
            )
        return super().update(**kwargs)

    def bulk_update(
        self,
        objs: Any,
        fields: Any,
        batch_size: int | None = None,
    ) -> int:
        objects = list(objs)
        field_list = list(fields)
        field_names = {
            field if isinstance(field, str) else field.name for field in field_list
        }
        if _PROJECT_LANGUAGE_FIELDS.intersection(field_names):
            raise _project_language_error(
                "primary_language_tag",
                "A Project primary-language identity is immutable.",
                code="project_primary_language_immutable",
            )
        for obj in objects:
            obj._validate_persisted_primary_language(using=self.db)
        return super().bulk_update(
            objects,
            field_list,
            batch_size=batch_size,
        )

    def bulk_create(
        self,
        objs: Any,
        batch_size: int | None = None,
        ignore_conflicts: bool = False,
        update_conflicts: bool = False,
        update_fields: Any = None,
        unique_fields: Any = None,
    ) -> Any:
        objects = list(objs)
        if ignore_conflicts or update_conflicts:
            raise _project_language_error(
                "primary_language_tag",
                "Project bulk inserts cannot ignore or rewrite identity conflicts.",
                code="project_primary_language_conflict_mode",
            )
        with transaction.atomic(using=self.db):
            for obj in objects:
                obj._prepare_ordinary_primary_language_insert()
                obj.full_clean()
            return super().bulk_create(
                objects,
                batch_size=batch_size,
                ignore_conflicts=False,
                update_conflicts=False,
                update_fields=update_fields,
                unique_fields=unique_fields,
            )

    def get_or_create(
        self,
        defaults: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[Any, bool]:
        self._reject_unsafe_project_language_query_state()
        requested_language, normalized_sources = (
            self._prevalidate_project_language_request(kwargs, defaults)
        )
        normalized_kwargs, normalized_defaults = normalized_sources
        assert normalized_kwargs is not None
        return self._get_or_create_prevalidated(
            defaults=normalized_defaults,
            lookup_values=normalized_kwargs,
            requested_language=requested_language,
        )

    def update_or_create(
        self,
        defaults: dict[str, Any] | None = None,
        create_defaults: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[Any, bool]:
        self._reject_unsafe_project_language_query_state()
        requested_language, normalized_sources = (
            self._prevalidate_project_language_request(
                kwargs,
                defaults,
                *(() if create_defaults is None else (create_defaults,)),
            )
        )
        normalized_kwargs, normalized_defaults, *normalized_create_defaults = (
            normalized_sources
        )
        assert normalized_kwargs is not None
        update_values = normalized_defaults or {}
        create_values = (
            normalized_create_defaults[0]
            if normalized_create_defaults
            else update_values
        )
        assert create_values is not None
        self._for_write = True
        with transaction.atomic(using=self.db):
            project, created = self.select_for_update()._get_or_create_prevalidated(
                defaults=create_values,
                lookup_values=normalized_kwargs,
                requested_language=requested_language,
            )
            if created:
                return project, True
            for name, value in resolve_callables(update_values):
                if name not in _PROJECT_LANGUAGE_FIELDS:
                    setattr(project, name, value)
            project.save(using=self.db)
            return project, False


class ProjectManager(models.Manager.from_queryset(ProjectQuerySet)):
    def restore_legacy_unknown_from_package(
        self,
        *,
        id: Any,
        code: str,
        version: str,
        name: str,
        description: str,
        metadata: dict[str, Any],
        primary_language_tag: str,
        primary_language_assignment: str,
        package_format: str,
        package_version: str,
        package_payload_sha256: str,
    ) -> "Project":
        """Insert one checksum-bound Project 1.1 legacy-unknown identity.

        This deliberately has no update branch.  Package parsing, JSON Schema
        validation, and checksum comparison happen before the sole caller hands
        the exact validated identity to this final persistence boundary.
        """

        from .services.language_tags import (
            LanguageTagValidationError,
            canonicalize_language_tag,
        )

        if package_format != "conflict-analysis-project" or package_version != "1.1.0":
            raise _project_language_error(
                "primary_language_assignment",
                "Legacy unknown restoration requires a validated project package 1.1.0.",
                code="project_primary_language_restore_package_invalid",
            )
        if re.fullmatch(r"[0-9a-f]{64}", package_payload_sha256) is None:
            raise _project_language_error(
                "primary_language_assignment",
                "Legacy unknown restoration requires an exact package payload checksum.",
                code="project_primary_language_restore_checksum_invalid",
            )
        try:
            canonical = canonicalize_language_tag(
                primary_language_tag,
                allow_und=True,
            )
        except LanguageTagValidationError as exc:
            raise _project_language_error(
                "primary_language_tag",
                str(exc),
                code="project_primary_language_invalid",
            ) from exc
        if (
            canonical != "und"
            or primary_language_tag != canonical
            or primary_language_assignment
            != ProjectPrimaryLanguageAssignment.LEGACY_UNKNOWN
        ):
            raise _project_language_error(
                "primary_language_assignment",
                "Package restoration accepts only exact und + LEGACY_UNKNOWN.",
                code="project_primary_language_restore_state_invalid",
            )

        project = self.model(
            id=id,
            code=code,
            version=version,
            name=name,
            description=description,
            metadata=metadata,
            primary_language_tag=canonical,
            primary_language_assignment=primary_language_assignment,
        )
        project.full_clean()
        try:
            with transaction.atomic(using=self.db):
                if self.filter(Q(pk=id) | Q(code=code)).exists():
                    raise _project_language_error(
                        "primary_language_tag",
                        "Legacy unknown restoration is insert-only.",
                        code="project_primary_language_restore_insert_only",
                    )
                models.Model.save(
                    project,
                    force_insert=True,
                    using=self.db,
                )
        except IntegrityError as exc:
            raise _project_language_error(
                "primary_language_tag",
                "Legacy unknown restoration conflicts with an existing Project identity.",
                code="project_primary_language_restore_insert_only",
            ) from exc
        return project


class Project(StableVersionedModel):
    objects = ProjectManager()

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    primary_language_tag = models.CharField(max_length=255)
    primary_language_assignment = models.CharField(
        max_length=16,
        choices=ProjectPrimaryLanguageAssignment.choices,
    )

    class Meta:
        ordering = ("code",)
        base_manager_name = "objects"
        constraints = [
            *_stable_constraints("domain_project"),
            models.UniqueConstraint(fields=("code",), name="domain_project_code_uniq"),
            models.CheckConstraint(
                condition=(
                    Q(
                        primary_language_assignment=(
                            ProjectPrimaryLanguageAssignment.EXPLICIT
                        )
                    )
                    & ~Q(primary_language_tag="und")
                    & ~Q(primary_language_tag="")
                    | Q(
                        primary_language_assignment=(
                            ProjectPrimaryLanguageAssignment.LEGACY_UNKNOWN
                        ),
                        primary_language_tag="und",
                    )
                ),
                name="domain_project_language_pair",
            ),
        ]

    def _canonicalize_primary_language(self, *, allow_und: bool) -> str:
        from .services.language_tags import (
            LanguageTagValidationError,
            canonicalize_language_tag,
        )

        if self.primary_language_tag in (None, ""):
            raise _project_language_error(
                "primary_language_tag",
                "A Project primary language is required.",
                code="project_primary_language_required",
            )
        try:
            canonical = canonicalize_language_tag(
                self.primary_language_tag,
                allow_und=allow_und,
            )
        except LanguageTagValidationError as exc:
            code = (
                "project_primary_language_und_forbidden"
                if exc.code == "und_forbidden"
                else "project_primary_language_invalid"
            )
            raise _project_language_error(
                "primary_language_tag",
                str(exc),
                code=code,
            ) from exc
        self.primary_language_tag = canonical
        return canonical

    def _prepare_ordinary_primary_language_insert(self) -> None:
        self._canonicalize_primary_language(allow_und=False)
        if self.primary_language_assignment in (None, ""):
            self.primary_language_assignment = (
                ProjectPrimaryLanguageAssignment.EXPLICIT
            )
        elif self.primary_language_assignment != ProjectPrimaryLanguageAssignment.EXPLICIT:
            raise _project_language_error(
                "primary_language_assignment",
                "Ordinary Project creation requires EXPLICIT language assignment.",
                code="project_primary_language_assignment_invalid",
            )

    def _normalize_primary_language_pair(self) -> None:
        canonical = self._canonicalize_primary_language(allow_und=True)
        assignment = self.primary_language_assignment
        if assignment == ProjectPrimaryLanguageAssignment.EXPLICIT:
            if canonical == "und":
                raise _project_language_error(
                    "primary_language_tag",
                    "EXPLICIT Project language cannot be 'und'.",
                    code="project_primary_language_und_forbidden",
                )
        elif assignment == ProjectPrimaryLanguageAssignment.LEGACY_UNKNOWN:
            if canonical != "und":
                raise _project_language_error(
                    "primary_language_assignment",
                    "LEGACY_UNKNOWN requires the exact 'und' language tag.",
                    code="project_primary_language_assignment_invalid",
                )
        else:
            raise _project_language_error(
                "primary_language_assignment",
                "Project language assignment must be EXPLICIT or LEGACY_UNKNOWN.",
                code="project_primary_language_assignment_invalid",
            )

    def _validate_persisted_primary_language(self, *, using: str | None = None) -> None:
        self._normalize_primary_language_pair()
        if self.pk is None:
            return
        database = using or self._state.db or "default"
        previous = (
            type(self).objects.using(database)
            .filter(pk=self.pk)
            .values("primary_language_tag", "primary_language_assignment")
            .first()
        )
        if previous is not None and (
            previous["primary_language_tag"] != self.primary_language_tag
            or previous["primary_language_assignment"]
            != self.primary_language_assignment
        ):
            raise _project_language_error(
                "primary_language_tag",
                "A Project primary-language identity is immutable.",
                code="project_primary_language_immutable",
            )

    def full_clean(self, *args: Any, **kwargs: Any) -> None:
        # Many established domain constructors explicitly validate before
        # saving. Prepare the server-owned assignment before Django records a
        # blank-field error; this is not a field default and still requires an
        # explicit, well-formed, non-und language on every ordinary insert.
        if self._state.adding and self.primary_language_assignment in (None, ""):
            self._prepare_ordinary_primary_language_insert()
        super().full_clean(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        self._normalize_primary_language_pair()
        self._validate_persisted_primary_language()

    def save(self, *args: Any, **kwargs: Any) -> None:
        database = kwargs.get("using") or self._state.db or "default"
        previous_exists = bool(
            self.pk
            and type(self).objects.using(database).filter(pk=self.pk).exists()
        )
        if previous_exists:
            self._validate_persisted_primary_language(using=database)
        else:
            self._prepare_ordinary_primary_language_insert()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.code}: {self.name}"


class WorkspaceQuerySet(models.QuerySet):
    def bulk_create(
        self,
        objs: Any,
        batch_size: int | None = None,
        ignore_conflicts: bool = False,
        update_conflicts: bool = False,
        update_fields: Any = None,
        unique_fields: Any = None,
    ) -> Any:
        objects = list(objs)
        if ignore_conflicts or update_conflicts:
            raise ValidationError(
                "Workspace bulk inserts cannot ignore or rewrite identity conflicts."
            )
        # full_clean() re-fetches the persisted definition, so a stale caller
        # object cannot hide a DRAFT, cross-project pin, or checksum drift.
        with transaction.atomic(using=self.db):
            for obj in objects:
                obj.full_clean()
            return super().bulk_create(
                objects,
                batch_size=batch_size,
                ignore_conflicts=False,
                update_conflicts=False,
                update_fields=update_fields,
                unique_fields=unique_fields,
            )

    def update(self, **kwargs: Any) -> int:
        protected = {
            "project",
            "project_id",
            "definition_version",
            "definition_version_id",
            "definition_manifest_hash",
        }
        if protected.intersection(kwargs):
            raise ValidationError("A workspace project/definition pin is immutable.")
        return super().update(**kwargs)

    def bulk_update(
        self,
        objs: Any,
        fields: Any,
        batch_size: int | None = None,
    ) -> int:
        if {
            "project",
            "project_id",
            "definition_version",
            "definition_version_id",
            "definition_manifest_hash",
        }.intersection(fields):
            raise ValidationError("A workspace project/definition pin is immutable.")
        return super().bulk_update(objs, fields, batch_size=batch_size)


class WorkspaceManager(models.Manager.from_queryset(WorkspaceQuerySet)):
    pass


class ProjectWorkspace(StableVersionedModel):
    """Strict data-isolation boundary within a project."""

    objects = WorkspaceManager()

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="workspaces",
    )
    definition_version = models.ForeignKey(
        "ProjectDefinitionVersion",
        on_delete=models.RESTRICT,
        related_name="pinned_workspaces",
    )
    definition_manifest_hash = models.CharField(
        max_length=64,
        validators=[SHA256_VALIDATOR],
    )
    name = models.CharField(max_length=255)
    is_default = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("project__code", "code")
        base_manager_name = "objects"
        constraints = [
            *_stable_constraints("domain_workspace"),
            models.UniqueConstraint(
                fields=("project", "code"),
                name="domain_workspace_project_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("project",),
                condition=Q(is_default=True),
                name="domain_workspace_one_default",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.project.code}/{self.code}"

    def clean(self) -> None:
        super().clean()
        if self.pk:
            previous = ProjectWorkspace.objects.filter(pk=self.pk).first()
            if previous is not None and (
                previous.definition_version_id != self.definition_version_id
                or previous.definition_manifest_hash != self.definition_manifest_hash
            ):
                raise ValidationError(
                    {"definition_version": "A workspace definition pin is immutable."}
                )
        definition = ProjectDefinitionVersion.objects.filter(
            pk=self.definition_version_id
        ).first()
        if definition is None:
            return
        errors: dict[str, str] = {}
        if definition.project_id != self.project_id:
            errors["definition_version"] = "The definition belongs to another project."
        if definition.publication_status != PublicationStatus.PUBLISHED:
            errors["definition_version"] = "A workspace must pin a published definition."
        if definition.manifest_hash != self.definition_manifest_hash:
            errors["definition_manifest_hash"] = (
                "Pinned definition checksum does not match the exact version."
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        if self.pk:
            previous = ProjectWorkspace.objects.filter(pk=self.pk).first()
            if previous is not None and (
                previous.definition_version_id != self.definition_version_id
                or previous.definition_manifest_hash != self.definition_manifest_hash
            ):
                raise ValidationError(
                    {"definition_version": "A workspace definition pin is immutable."}
                )
        super().save(*args, **kwargs)


class ProjectDefinitionQuerySet(models.QuerySet):
    """Force lifecycle mutations through the validation/publication services."""

    def bulk_create(
        self,
        objs: Any,
        batch_size: int | None = None,
        ignore_conflicts: bool = False,
        update_conflicts: bool = False,
        update_fields: Any = None,
        unique_fields: Any = None,
    ) -> Any:
        from .services.project_definitions import (
            identify_typed_project_definition_manifest,
        )

        objects = list(objs)
        if ignore_conflicts or update_conflicts:
            raise ValidationError(
                "Definition bulk inserts cannot ignore or rewrite identity conflicts."
            )
        with transaction.atomic(using=self.db):
            for obj in objects:
                if identify_typed_project_definition_manifest(obj.manifest):
                    raise ValidationError(
                        "Typed definition drafts require the canonical Studio draft service."
                    )
                if obj.publication_status != PublicationStatus.DRAFT:
                    raise ValidationError(
                        "Definition bulk inserts may create DRAFT records only."
                    )
                obj.full_clean()
            return super().bulk_create(
                objects,
                batch_size=batch_size,
                ignore_conflicts=False,
                update_conflicts=False,
                update_fields=update_fields,
                unique_fields=unique_fields,
            )

    def update(self, **kwargs: Any) -> int:
        if set(kwargs) <= {"is_current"} and kwargs.get("is_current") is False:
            from .services.project_definitions import (
                identify_typed_project_definition_manifest,
            )

            contains_typed_definition = any(
                identify_typed_project_definition_manifest(manifest)
                for manifest in self.values_list("manifest", flat=True)
            )
            if (
                contains_typed_definition
                and not _studio_write_is_authorized("definition")
            ):
                raise ValidationError(
                    "Typed definition lifecycle updates require the canonical Studio service."
                )
            return super().update(**kwargs)
        raise ValidationError("Definition lifecycle updates require the publication service.")

    def bulk_update(
        self,
        objs: Any,
        fields: Any,
        batch_size: int | None = None,
    ) -> int:
        raise ValidationError("Definition lifecycle updates require the publication service.")

    def delete(self) -> tuple[int, dict[str, int]]:
        if self.exclude(publication_status=PublicationStatus.DRAFT).exists():
            raise ValidationError("Validated definition snapshots are append-only.")
        return super().delete()


class ProjectDefinitionManager(models.Manager.from_queryset(ProjectDefinitionQuerySet)):
    pass


class ProjectDefinitionVersion(StableVersionedModel):
    """Publishable, versioned project definition; supersedes legacy schema rows."""

    objects = ProjectDefinitionManager()

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="definition_versions",
    )
    is_current = models.BooleanField(default=False)
    publication_status = models.CharField(
        max_length=16,
        choices=PublicationStatus.choices,
        default=PublicationStatus.DRAFT,
    )
    manifest = models.JSONField(default=dict, blank=True)
    manifest_hash = models.CharField(
        max_length=64,
        blank=True,
        validators=[SHA256_VALIDATOR],
    )
    published_at = models.DateTimeField(null=True, blank=True)
    schema_version = models.CharField(max_length=64, default="1.0.0")
    semantic_version = models.CharField(max_length=64, default="1.0.0")
    construct_version = models.CharField(max_length=64, default="1.0.0")
    validated_at = models.DateTimeField(null=True, blank=True)
    validated_by = models.CharField(max_length=255, blank=True)
    validation_result = models.JSONField(default=dict, blank=True)
    published_by = models.CharField(max_length=255, blank=True)
    supersedes = models.ForeignKey(
        "self",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="successors",
    )

    class Meta:
        ordering = ("project__code", "version")
        base_manager_name = "objects"
        permissions = (
            ("studio_read_definition", "Can read Studio project definitions"),
            ("studio_create_definition_draft", "Can create Studio definition drafts"),
            ("studio_clone_definition_draft", "Can clone Studio definition drafts"),
            ("studio_save_definition_draft", "Can save Studio definition drafts"),
            ("studio_validate_definition", "Can validate Studio project definitions"),
            ("studio_publish_definition", "Can publish Studio project definitions"),
        )
        constraints = [
            *_stable_constraints("domain_definition_version"),
            models.UniqueConstraint(
                fields=("project", "code"),
                name="domain_definition_project_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("project", "version"),
                name="domain_definition_project_version_uniq",
            ),
            models.UniqueConstraint(
                fields=("project",),
                condition=Q(is_current=True),
                name="domain_definition_one_current",
            ),
            models.CheckConstraint(
                condition=(
                    Q(publication_status=PublicationStatus.PUBLISHED, published_at__isnull=False)
                    | ~Q(publication_status=PublicationStatus.PUBLISHED)
                ),
                name="domain_definition_publish_time",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        publication_status=PublicationStatus.DRAFT,
                        validated_at__isnull=True,
                        validated_by="",
                        validation_result={},
                        published_at__isnull=True,
                        published_by="",
                    )
                    | Q(
                        publication_status=PublicationStatus.VALIDATED,
                        validated_at__isnull=False,
                        validation_result__valid=True,
                        published_at__isnull=True,
                        published_by="",
                    )
                    & ~Q(validated_by="")
                    | Q(
                        publication_status__in=(
                            PublicationStatus.PUBLISHED,
                            PublicationStatus.RETIRED,
                        ),
                        validated_at__isnull=False,
                        validation_result__valid=True,
                        published_at__isnull=False,
                    )
                    & ~Q(validated_by="")
                    & ~Q(published_by="")
                ),
                name="domain_definition_lifecycle_state",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        expected_manifest_hash = hashlib.sha256(
            json.dumps(
                self.manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if self.manifest_hash and self.manifest_hash != expected_manifest_hash:
            errors["manifest_hash"] = "Manifest checksum does not match exact draft bytes."
        if self.supersedes_id:
            previous = ProjectDefinitionVersion.objects.filter(
                pk=self.supersedes_id
            ).first()
            if previous is not None and previous.project_id != self.project_id:
                errors["supersedes"] = "A definition can supersede only in its project."
            if self.pk == self.supersedes_id:
                errors["supersedes"] = "A version cannot supersede itself."
        if self.publication_status in {
            PublicationStatus.VALIDATED,
            PublicationStatus.PUBLISHED,
            PublicationStatus.RETIRED,
        }:
            if not self.manifest_hash:
                errors["manifest_hash"] = "Validated definitions require an exact checksum."
            if self.validated_at is None:
                errors["validated_at"] = "Validated definitions require a timestamp."
            if not self.validated_by.strip():
                errors["validated_by"] = "Validated definitions require an actor."
            if self.validation_result.get("valid") is not True:
                errors["validation_result"] = (
                    "Validated definitions require a successful explicit validation result."
                )
        if self.publication_status == PublicationStatus.VALIDATED:
            if self.published_at is not None or self.published_by:
                errors["published_at"] = "A VALIDATED definition is not yet published."
        if self.publication_status in {
            PublicationStatus.PUBLISHED,
            PublicationStatus.RETIRED,
        }:
            if self.published_at is None:
                errors["published_at"] = "Published definitions require a timestamp."
            if not self.published_by.strip():
                errors["published_by"] = "Published definitions require an actor."
            if not self.manifest_hash:
                errors["manifest_hash"] = "Published definitions require a checksum."
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        from .services.project_definitions import (
            identify_typed_project_definition_manifest,
        )

        previous = None
        if self.pk:
            previous = ProjectDefinitionVersion.objects.filter(pk=self.pk).first()
        is_typed_runtime_write = identify_typed_project_definition_manifest(
            self.manifest
        ) or (
            previous is not None
            and identify_typed_project_definition_manifest(previous.manifest)
        )
        if is_typed_runtime_write and not _studio_write_is_authorized("definition"):
            raise ValidationError(
                "Typed definition writes require the canonical Studio service."
            )
        self.full_clean()
        if previous is not None:
            allowed_transitions = {
                PublicationStatus.DRAFT: {
                    PublicationStatus.DRAFT,
                    PublicationStatus.VALIDATED,
                },
                PublicationStatus.VALIDATED: {
                    PublicationStatus.VALIDATED,
                    PublicationStatus.PUBLISHED,
                },
                PublicationStatus.PUBLISHED: {PublicationStatus.PUBLISHED},
                PublicationStatus.RETIRED: {PublicationStatus.RETIRED},
            }
            if (
                previous is not None
                and self.publication_status
                not in allowed_transitions.get(previous.publication_status, set())
            ):
                raise ValidationError(
                    {
                        "publication_status": (
                            "Definition lifecycle is DRAFT -> VALIDATED -> PUBLISHED; "
                            "direct or reverse transitions are forbidden."
                        )
                    }
                )
            if previous.publication_status in {
                PublicationStatus.VALIDATED,
                PublicationStatus.PUBLISHED,
                PublicationStatus.RETIRED,
            }:
                allowed_changes = {"created_at", "updated_at"}
                if (
                    previous.publication_status == PublicationStatus.VALIDATED
                    and self.publication_status == PublicationStatus.PUBLISHED
                ):
                    allowed_changes.update(
                        {"publication_status", "published_at", "published_by", "is_current"}
                    )
                elif previous.publication_status == PublicationStatus.PUBLISHED:
                    allowed_changes.add("is_current")
                changed = [
                    field.name
                    for field in self._meta.concrete_fields
                    if field.name not in allowed_changes
                    and getattr(previous, field.attname) != getattr(self, field.attname)
                ]
                if changed:
                    raise ValidationError(
                        {
                            name: "Validated definition bytes are immutable; create a successor."
                            for name in changed
                        }
                    )
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        if self.publication_status != PublicationStatus.DRAFT:
            raise ValidationError("Validated definition snapshots are append-only.")
        return super().delete(*args, **kwargs)


class PublicationQuerySet(models.QuerySet):
    def bulk_create(
        self,
        objs: Any,
        batch_size: int | None = None,
        ignore_conflicts: bool = False,
        update_conflicts: bool = False,
        update_fields: Any = None,
        unique_fields: Any = None,
    ) -> Any:
        from .services.project_definitions import (
            identify_typed_project_definition_manifest,
        )

        objects = list(objs)
        if ignore_conflicts or update_conflicts:
            raise ValidationError(
                "Publication bulk inserts cannot ignore or rewrite identity conflicts."
            )
        with transaction.atomic(using=self.db):
            for obj in objects:
                persisted_manifest = ProjectDefinitionVersion.objects.filter(
                    pk=obj.definition_version_id
                ).values_list("manifest", flat=True).first()
                if identify_typed_project_definition_manifest(persisted_manifest):
                    raise ValidationError(
                        "Typed publications require the canonical Studio publication service."
                    )
                obj.full_clean()
            return super().bulk_create(
                objects,
                batch_size=batch_size,
                ignore_conflicts=False,
                update_conflicts=False,
                update_fields=update_fields,
                unique_fields=unique_fields,
            )

    def update(self, **kwargs: Any) -> int:
        raise ValidationError("Publication records are append-only.")

    def bulk_update(
        self,
        objs: Any,
        fields: Any,
        batch_size: int | None = None,
    ) -> int:
        raise ValidationError("Publication records are append-only.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Publication records are append-only.")


class PublicationManager(models.Manager.from_queryset(PublicationQuerySet)):
    pass


class ProjectPublication(StableVersionedModel):
    """Immutable publication pointer to one exact project-definition version."""

    objects = PublicationManager()

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="publications",
    )
    definition_version = models.ForeignKey(
        ProjectDefinitionVersion,
        on_delete=models.RESTRICT,
        related_name="publications",
    )
    initial_workspace = models.OneToOneField(
        ProjectWorkspace,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="initial_publication",
    )
    locale = models.CharField(max_length=16, validators=[LOCALE_VALIDATOR])
    actor_identifier = models.CharField(max_length=255, blank=True)
    validation_result = models.JSONField(default=dict, blank=True)
    published_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ("project__code", "-published_at")
        base_manager_name = "objects"
        constraints = [
            *_stable_constraints("domain_publication"),
            models.UniqueConstraint(
                fields=("project", "code"),
                name="domain_publication_project_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("project", "definition_version", "locale"),
                name="domain_publication_exact_uniq",
            ),
            models.CheckConstraint(
                condition=(~Q(actor_identifier="") & Q(validation_result__valid=True)),
                name="domain_publication_actor_validation",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        from .services.project_definitions import (
            identify_typed_project_definition_manifest,
        )

        definition = ProjectDefinitionVersion.objects.filter(
            pk=self.definition_version_id
        ).first()
        if definition is None:
            return
        errors: dict[str, str] = {}
        if definition.project_id != self.project_id:
            errors["definition_version"] = "Definition and publication projects differ."
        if definition.publication_status != PublicationStatus.PUBLISHED:
            errors["definition_version"] = "Only a published definition can be published."
        if not self.actor_identifier.strip():
            errors["actor_identifier"] = "Publication actor is required."
        if self.validation_result.get("valid") is not True:
            errors["validation_result"] = "Publication requires a successful validation result."
        if (
            identify_typed_project_definition_manifest(definition.manifest)
            and ProjectPublication.objects.filter(
                project_id=self.project_id,
                definition_version_id=self.definition_version_id,
            )
            .exclude(pk=self.pk)
            .exists()
        ):
            errors["definition_version"] = (
                "A typed definition has exactly one canonical publication receipt."
            )
        if self.initial_workspace_id:
            workspace = ProjectWorkspace.objects.filter(
                pk=self.initial_workspace_id
            ).first()
            if workspace is not None:
                if workspace.project_id != self.project_id:
                    errors["initial_workspace"] = (
                        "Initial workspace and publication projects differ."
                    )
                elif workspace.definition_version_id != self.definition_version_id:
                    errors["initial_workspace"] = (
                        "Initial workspace must pin the published definition."
                    )
                elif workspace.definition_manifest_hash != definition.manifest_hash:
                    errors["initial_workspace"] = (
                        "Initial workspace must pin the exact published manifest hash."
                    )
            if (
                ProjectPublication.objects.filter(
                    project_id=self.project_id,
                    initial_workspace_id__isnull=False,
                )
                .exclude(pk=self.pk)
                .exists()
            ):
                errors["initial_workspace"] = (
                    "A project has exactly one initial-workspace publication receipt."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        from .services.project_definitions import (
            identify_typed_project_definition_manifest,
        )

        persisted_manifest = ProjectDefinitionVersion.objects.filter(
            pk=self.definition_version_id
        ).values_list("manifest", flat=True).first()
        if (
            identify_typed_project_definition_manifest(persisted_manifest)
            and not _studio_write_is_authorized("publication")
        ):
            raise ValidationError(
                "Typed publication writes require the canonical Studio service."
            )
        self.full_clean()
        if self.pk and ProjectPublication.objects.filter(pk=self.pk).exists():
            previous = ProjectPublication.objects.get(pk=self.pk)
            changed = [
                field.name
                for field in self._meta.concrete_fields
                if field.name not in {"created_at", "updated_at"}
                and getattr(previous, field.attname) != getattr(self, field.attname)
            ]
            if changed:
                raise ValidationError(
                    {name: "Publication records are immutable." for name in changed}
                )
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError("Publication records are append-only.")


def _hydrate_legacy_default_workspace(
    instance: models.Model,
    *related_names: str,
) -> None:
    """Resolve the exact legacy default workspace before field validation.

    PR #21 constructors predate the workspace boundary.  They remain compatible
    only when every available related object agrees on one workspace, or when
    the instance's project has exactly one explicitly marked default workspace.
    Conflicting related workspaces are deliberately left unresolved so normal
    validation fails closed.
    """

    if getattr(instance, "workspace_id", None) is not None:
        return
    related_workspace_ids: set[uuid.UUID] = set()
    for related_name in related_names:
        try:
            related = getattr(instance, related_name)
        except (AttributeError, models.ObjectDoesNotExist):
            continue
        workspace_id = getattr(related, "workspace_id", None)
        if workspace_id is not None:
            related_workspace_ids.add(workspace_id)
    if len(related_workspace_ids) == 1:
        instance.workspace_id = related_workspace_ids.pop()
        return
    if related_workspace_ids:
        return
    project_id = getattr(instance, "project_id", None)
    if project_id is None:
        return
    instance.workspace_id = (
        ProjectWorkspace.objects.filter(project_id=project_id, is_default=True)
        .values_list("id", flat=True)
        .first()
    )


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


class TimeSliceQuerySet(models.QuerySet):
    """Preserve the exact cutoff/version provenance used by assessments."""

    def update(self, **kwargs: Any) -> int:
        raise ValidationError("TimeSlice records are immutable; create a new version.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("TimeSlice records are append-only while provenance may refer to them.")

class TimeSliceManager(models.Manager.from_queryset(TimeSliceQuerySet)):
    pass


class TimeSlice(ValidatedStableVersionedModel):
    objects = TimeSliceManager()
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="time_slices",
    )
    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.CASCADE,
        related_name="time_slices",
    )
    name = models.CharField(max_length=255, blank=True)
    cutoff_date = models.DateField()
    order = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("workspace__code", "order", "cutoff_date")
        constraints = [
            *_stable_constraints("domain_time_slice"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_slice_workspace_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("workspace", "cutoff_date"),
                name="domain_slice_workspace_date_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.project.code}/{self.code}"

    def full_clean(self, *args: Any, **kwargs: Any) -> None:
        _hydrate_legacy_default_workspace(self)
        super().full_clean(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        if self.workspace_id:
            workspace_project_id = ProjectWorkspace.objects.filter(
                pk=self.workspace_id
            ).values_list("project_id", flat=True).first()
            if workspace_project_id != self.project_id:
                raise ValidationError(
                    {"workspace": "The workspace belongs to a different project."}
                )

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        if self.pk and TimeSlice.objects.filter(pk=self.pk).exists():
            previous = TimeSlice.objects.get(pk=self.pk)
            changed = [
                field.name
                for field in self._meta.concrete_fields
                if field.name not in {"created_at", "updated_at"}
                and getattr(previous, field.attname) != getattr(self, field.attname)
            ]
            if changed:
                raise ValidationError(
                    {name: "TimeSlice provenance is immutable; create a new version." for name in changed}
                )
        models.Model.save(self, *args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError("TimeSlice records are append-only while provenance may refer to them.")


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


class Actor(RevisionedStableVersionedModel):
    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.CASCADE,
        related_name="actors",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="children",
    )
    actor_type = models.CharField(max_length=16, choices=ActorType.choices)
    label = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("workspace__code", "order", "code")
        constraints = [
            *_stable_constraints("domain_actor"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_actor_workspace_code_uniq",
            ),
            models.CheckConstraint(
                condition=~Q(id=models.F("parent")),
                name="domain_actor_not_own_parent",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if not self.parent_id:
            return
        parent = Actor.objects.filter(pk=self.parent_id).first()
        if parent is None:
            return
        errors: dict[str, str] = {}
        if parent.workspace_id != self.workspace_id:
            errors["parent"] = "An actor parent must be in the same workspace."
        seen = {self.pk}
        cursor = parent
        while cursor is not None:
            if cursor.pk in seen:
                errors["parent"] = "Actor hierarchy cannot contain a cycle."
                break
            seen.add(cursor.pk)
            cursor = (
                Actor.objects.filter(pk=cursor.parent_id).first()
                if cursor.parent_id
                else None
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.code}: {self.label}"


class AnalyticalElement(RevisionedStableVersionedModel):
    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.CASCADE,
        related_name="analytical_elements",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="children",
    )
    element_type = models.CharField(
        max_length=32,
        choices=AnalyticalElementType.choices,
    )
    label = models.CharField(max_length=500)
    reference_statement = models.TextField(blank=True)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("workspace__code", "order", "code")
        constraints = [
            *_stable_constraints("domain_element"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_element_workspace_code_uniq",
            ),
            models.CheckConstraint(
                condition=~Q(id=models.F("parent")),
                name="domain_element_not_own_parent",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if not self.parent_id:
            return
        parent = AnalyticalElement.objects.filter(pk=self.parent_id).first()
        if parent is None:
            return
        errors: dict[str, str] = {}
        if parent.workspace_id != self.workspace_id:
            errors["parent"] = "An element parent must be in the same workspace."
        seen = {self.pk}
        cursor = parent
        while cursor is not None:
            if cursor.pk in seen:
                errors["parent"] = "Element hierarchy cannot contain a cycle."
                break
            seen.add(cursor.pk)
            cursor = (
                AnalyticalElement.objects.filter(pk=cursor.parent_id).first()
                if cursor.parent_id
                else None
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.code}: {self.label}"


class ActorRelation(RevisionedStableVersionedModel):
    """Typed, directed relationship without inferred scoring or aggregation."""

    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.CASCADE,
        related_name="actor_relations",
    )
    source_actor = models.ForeignKey(
        Actor,
        on_delete=models.RESTRICT,
        related_name="outgoing_relations",
    )
    target_actor = models.ForeignKey(
        Actor,
        on_delete=models.RESTRICT,
        related_name="incoming_relations",
    )
    relation_type = models.CharField(max_length=64, validators=[CODE_VALIDATOR])
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("workspace__code", "source_actor__code", "target_actor__code")
        constraints = [
            *_stable_constraints("domain_actor_relation"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_actor_relation_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("workspace", "source_actor", "target_actor", "relation_type"),
                name="domain_actor_relation_exact_uniq",
            ),
            models.CheckConstraint(
                condition=~Q(source_actor=models.F("target_actor")),
                name="domain_actor_relation_distinct",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        for field_name, related_id in (
            ("source_actor", self.source_actor_id),
            ("target_actor", self.target_actor_id),
        ):
            _validate_related_workspace(
                workspace_id=self.workspace_id,
                related_model=Actor,
                related_id=related_id,
                field_name=field_name,
                errors=errors,
            )
        if self.source_actor_id == self.target_actor_id:
            errors["target_actor"] = "An actor relation requires two actors."
        if errors:
            raise ValidationError(errors)


class ActorElementRole(RevisionedStableVersionedModel):
    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.CASCADE,
        related_name="actor_element_roles",
    )
    actor = models.ForeignKey(
        Actor,
        on_delete=models.CASCADE,
        related_name="element_roles",
    )
    element = models.ForeignKey(
        AnalyticalElement,
        on_delete=models.CASCADE,
        related_name="actor_roles",
    )
    role = models.CharField(max_length=16, choices=ActorRoleType.choices)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ("workspace__code", "actor__code", "element__code", "role")
        constraints = [
            *_stable_constraints("domain_actor_element_role"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_actor_role_ws_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("workspace", "actor", "element", "role"),
                name="domain_actor_element_role_uniq",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        _validate_related_workspace(
            workspace_id=self.workspace_id,
            related_model=Actor,
            related_id=self.actor_id,
            field_name="actor",
            errors=errors,
        )
        _validate_related_workspace(
            workspace_id=self.workspace_id,
            related_model=AnalyticalElement,
            related_id=self.element_id,
            field_name="element",
            errors=errors,
        )
        if errors:
            raise ValidationError(errors)


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


def _validate_related_workspace(
    *,
    workspace_id: uuid.UUID | None,
    related_model: type[models.Model],
    related_id: uuid.UUID | None,
    field_name: str,
    errors: dict[str, str],
) -> None:
    """Fail closed when a canonical link crosses a workspace boundary."""

    if workspace_id is None or related_id is None:
        return
    related_workspace_id = (
        related_model._default_manager.filter(pk=related_id)
        .values_list("workspace_id", flat=True)
        .first()
    )
    if related_workspace_id != workspace_id:
        errors[field_name] = "The referenced object belongs to a different workspace."


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


class AssessmentSet(ValidatedStableVersionedModel):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="assessment_sets",
    )
    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.CASCADE,
        related_name="assessment_sets",
    )
    kind = models.CharField(max_length=16, choices=AssessmentKind.choices)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ("workspace__code", "kind", "code")
        constraints = [
            *_stable_constraints("domain_assessment_set"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_set_workspace_code_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.project.code}/{self.code} ({self.kind})"

    def full_clean(self, *args: Any, **kwargs: Any) -> None:
        _hydrate_legacy_default_workspace(self)
        super().full_clean(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        if self.workspace_id:
            workspace_project_id = ProjectWorkspace.objects.filter(
                pk=self.workspace_id
            ).values_list("project_id", flat=True).first()
            if workspace_project_id != self.project_id:
                raise ValidationError(
                    {"workspace": "The workspace belongs to a different project."}
                )


class ExpertProfile(ValidatedStableVersionedModel):
    """Stable HUMAN or AI coder identity; never a value store."""

    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.CASCADE,
        related_name="expert_profiles",
    )
    kind = models.CharField(max_length=16, choices=AssessmentKind.choices)
    display_name = models.CharField(max_length=255)
    identity_key = models.CharField(max_length=255)
    provider = models.CharField(max_length=128, blank=True)
    model_name = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("workspace__code", "kind", "code")
        constraints = [
            *_stable_constraints("domain_expert_profile"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_expert_ws_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("workspace", "identity_key"),
                name="domain_expert_identity_uniq",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.kind not in {AssessmentKind.HUMAN, AssessmentKind.AI}:
            raise ValidationError(
                {"kind": "An expert profile must use the HUMAN or AI lane."}
            )
        if self.kind == AssessmentKind.AI and not self.model_name.strip():
            raise ValidationError({"model_name": "AI profiles require a model name."})


class Experiment(ValidatedStableVersionedModel):
    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.CASCADE,
        related_name="experiments",
    )
    expert_profile = models.ForeignKey(
        ExpertProfile,
        on_delete=models.RESTRICT,
        related_name="experiments",
    )
    assessment_set = models.OneToOneField(
        AssessmentSet,
        on_delete=models.RESTRICT,
        related_name="experiment",
    )
    name = models.CharField(max_length=255)
    experiment_type = models.CharField(
        max_length=16,
        choices=ExperimentType.choices,
    )
    status = models.CharField(
        max_length=16,
        choices=ExperimentStatus.choices,
        default=ExperimentStatus.DRAFT,
    )
    color = models.CharField(max_length=32, blank=True)
    order = models.PositiveIntegerField(default=0)
    method_version = models.CharField(max_length=64, blank=True)
    frozen_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("workspace__code", "order", "code")
        constraints = [
            *_stable_constraints("domain_experiment"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_experiment_ws_code_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=ExperimentStatus.FROZEN, frozen_at__isnull=False)
                    | ~Q(status=ExperimentStatus.FROZEN)
                ),
                name="domain_experiment_frozen_time",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        _validate_related_workspace(
            workspace_id=self.workspace_id,
            related_model=ExpertProfile,
            related_id=self.expert_profile_id,
            field_name="expert_profile",
            errors=errors,
        )
        _validate_related_workspace(
            workspace_id=self.workspace_id,
            related_model=AssessmentSet,
            related_id=self.assessment_set_id,
            field_name="assessment_set",
            errors=errors,
        )
        profile = ExpertProfile.objects.filter(pk=self.expert_profile_id).first()
        assessment_set = AssessmentSet.objects.filter(pk=self.assessment_set_id).first()
        if (
            profile is not None
            and assessment_set is not None
            and self.experiment_type == ExperimentType.ASSESSMENT
            and profile.kind != assessment_set.kind
        ):
            errors["assessment_set"] = (
                "An assessment Experiment requires matching ExpertProfile and AssessmentSet lanes."
            )
        if self.experiment_type == ExperimentType.MODELING:
            if self.status != ExperimentStatus.DRAFT:
                errors["status"] = "MODELING is reserved and cannot be activated in I1."
        if self.status == ExperimentStatus.FROZEN and self.frozen_at is None:
            errors["frozen_at"] = "Frozen experiments require a timestamp."
        if errors:
            raise ValidationError(errors)


class ActorElementAssessment(RevisionedStableVersionedModel):
    """Non-numeric identity for Actor x Element x Time x Experiment."""

    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.CASCADE,
        related_name="actor_element_assessments",
    )
    actor = models.ForeignKey(
        Actor,
        on_delete=models.RESTRICT,
        related_name="assessments",
    )
    element = models.ForeignKey(
        AnalyticalElement,
        on_delete=models.RESTRICT,
        related_name="assessments",
    )
    time_slice = models.ForeignKey(
        TimeSlice,
        on_delete=models.RESTRICT,
        related_name="actor_element_assessments",
    )
    experiment = models.ForeignKey(
        Experiment,
        on_delete=models.RESTRICT,
        related_name="actor_element_assessments",
    )
    assessment_set = models.ForeignKey(
        AssessmentSet,
        on_delete=models.RESTRICT,
        related_name="actor_element_assessments",
    )
    supersedes = models.OneToOneField(
        "self",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="successor",
    )
    reference_statement = models.TextField(blank=True)
    reference_statement_incomplete = models.BooleanField(default=False)
    status = models.CharField(
        max_length=40,
        choices=AssessmentRecordStatus.choices,
        default=AssessmentRecordStatus.UNKNOWN,
    )
    confidence_level = models.CharField(
        max_length=16,
        choices=ConfidenceLevel.choices,
        default=ConfidenceLevel.UNKNOWN,
    )
    knowledge_cutoff = models.DateField()
    method_version = models.CharField(max_length=64, blank=True)
    provenance = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("workspace__code", "time_slice__cutoff_date", "code")
        constraints = [
            *_stable_constraints("domain_actor_assessment"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_actor_assessment_code_uniq",
            ),
            models.UniqueConstraint(
                fields=(
                    "workspace",
                    "actor",
                    "element",
                    "time_slice",
                    "assessment_set",
                    "version",
                ),
                name="domain_actor_assessment_context_version_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(reference_statement="")
                    | Q(reference_statement_incomplete=True)
                ),
                name="domain_actor_assessment_reference",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        for field_name, related_model, related_id in (
            ("actor", Actor, self.actor_id),
            ("element", AnalyticalElement, self.element_id),
            ("time_slice", TimeSlice, self.time_slice_id),
            ("experiment", Experiment, self.experiment_id),
            ("assessment_set", AssessmentSet, self.assessment_set_id),
        ):
            _validate_related_workspace(
                workspace_id=self.workspace_id,
                related_model=related_model,
                related_id=related_id,
                field_name=field_name,
                errors=errors,
            )
        experiment = Experiment.objects.filter(pk=self.experiment_id).first()
        if experiment is not None and experiment.assessment_set_id != self.assessment_set_id:
            errors["assessment_set"] = "AssessmentSet must match the experiment binding."
        time_slice = TimeSlice.objects.filter(pk=self.time_slice_id).first()
        if time_slice is not None and self.knowledge_cutoff > time_slice.cutoff_date:
            errors["knowledge_cutoff"] = (
                "Knowledge cutoff cannot be later than the TimeSlice cutoff."
            )
        if not self.reference_statement.strip() and not self.reference_statement_incomplete:
            errors["reference_statement"] = (
                "A coded assessment needs a reference statement or explicit incomplete flag."
            )
        if self.supersedes_id:
            previous = ActorElementAssessment.objects.filter(pk=self.supersedes_id).first()
            if previous is not None:
                context_fields = (
                    "workspace_id",
                    "actor_id",
                    "element_id",
                    "time_slice_id",
                    "assessment_set_id",
                )
                if any(
                    getattr(previous, field) != getattr(self, field)
                    for field in context_fields
                ):
                    errors["supersedes"] = "Assessment successor context must remain exact."
                if previous.version == self.version:
                    errors["version"] = "Assessment successor requires a new version."
        elif all(
            (
                self.workspace_id,
                self.actor_id,
                self.element_id,
                self.time_slice_id,
                self.assessment_set_id,
            )
        ) and ActorElementAssessment.objects.filter(
            workspace_id=self.workspace_id,
            actor_id=self.actor_id,
            element_id=self.element_id,
            time_slice_id=self.time_slice_id,
            assessment_set_id=self.assessment_set_id,
            supersedes__isnull=True,
        ).exclude(pk=self.pk).exists():
            errors["supersedes"] = "A later assessment must identify its exact predecessor."
        if errors:
            raise ValidationError(errors)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError("Assessment history is append-only.")


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
        if self.code.strip().upper() in {
            "TOTAL_POWER",
            "POW",
            "SCALAR_POWER",
            "AUTOMATIC_MEAN",
            "AUTOMATIC_WEIGHTS",
        }:
            errors["code"] = (
                "Scalar or automatically aggregated Power identities are forbidden; "
                "store only separate FA/ER/OC/CC/AL/IC/NI/EB components."
            )
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
        TargetType.ACTOR_ELEMENT_ASSESSMENT: ActorElementAssessment,
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
    if model is Project:
        target_project_id = target.pk
    elif hasattr(target, "project_id"):
        target_project_id = target.project_id
    else:
        target_project_id = ProjectWorkspace.objects.filter(
            pk=target.workspace_id
        ).values_list("project_id", flat=True).first()
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
    inherited_metadata_complete: bool = False,
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
    if confidence is None and not inherited_metadata_complete:
        errors["confidence"] = "A present assessment requires confidence."
    elif confidence is not None and (
        confidence < Decimal("0") or confidence > Decimal("100")
    ):
        errors["confidence"] = (
            "Coder confidence must be between 0 and 100; it is not a probability."
        )
    if not rationale.strip() and not inherited_metadata_complete:
        errors["rationale"] = "A present assessment requires a rationale."
    if (range_min is None) != (range_max is None):
        errors["range_min"] = "Range minimum and maximum must be provided together."
        return
    if range_min is None:
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


class ParameterValue(RevisionedStableVersionedModel):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="parameter_values",
    )
    workspace = models.ForeignKey(
        ProjectWorkspace,
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
    actor_element_assessment = models.ForeignKey(
        ActorElementAssessment,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="parameter_values",
    )
    supersedes = models.OneToOneField(
        "self",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="successor",
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
    temporal_status = models.CharField(
        max_length=40,
        choices=AssessmentTemporalStatus.choices,
        default=AssessmentTemporalStatus.UNKNOWN,
    )
    value = models.JSONField(null=True, blank=True, default=None)
    note = models.TextField(blank=True)
    confidence = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    range_min = models.JSONField(null=True, blank=True, default=None)
    range_max = models.JSONField(null=True, blank=True, default=None)
    rationale = models.TextField(blank=True)

    class Meta:
        ordering = ("workspace__code", "time_slice__order", "code")
        constraints = [
            *_stable_constraints("domain_parameter_value"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_value_workspace_code_uniq",
            ),
            models.UniqueConstraint(
                fields=(
                    "workspace",
                    "time_slice",
                    "assessment_set",
                    "parameter_definition",
                    "target_type",
                    "target_id",
                    "version",
                ),
                name="domain_value_context_target_version_uniq",
            ),
            _value_presence_constraint("domain_value"),
            _assessment_metadata_constraint(
                "domain_value",
                allow_assessment_header=True,
            ),
            models.CheckConstraint(
                condition=(
                    Q(confidence__isnull=True)
                    | Q(confidence__gte=0, confidence__lte=100)
                ),
                name="domain_value_confidence_0_100",
            ),
        ]

    @property
    def target_object(self) -> models.Model | None:
        model = _target_model(self.target_type)
        if model is None or self.target_id is None:
            return None
        return model._default_manager.filter(pk=self.target_id).first()

    def full_clean(self, *args: Any, **kwargs: Any) -> None:
        _hydrate_legacy_default_workspace(
            self,
            "time_slice",
            "assessment_set",
            "actor_element_assessment",
        )
        super().full_clean(*args, **kwargs)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Keep PR21 legacy lanes compatible; canonical V4 values are revision-only."""

        if (
            self.actor_element_assessment_id is None
            and self.target_type != TargetType.ACTOR_ELEMENT_ASSESSMENT
        ):
            self.full_clean()
            models.Model.save(self, *args, **kwargs)
            return
        super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        workspace_project_id = ProjectWorkspace.objects.filter(
            pk=self.workspace_id
        ).values_list("project_id", flat=True).first()
        if workspace_project_id != self.project_id:
            errors["workspace"] = "The workspace belongs to a different project."
        _validate_related_project(
            project_id=self.project_id,
            related_model=TimeSlice,
            related_id=self.time_slice_id,
            field_name="time_slice",
            errors=errors,
        )
        _validate_related_workspace(
            workspace_id=self.workspace_id,
            related_model=TimeSlice,
            related_id=self.time_slice_id,
            field_name="time_slice",
            errors=errors,
        )
        _validate_related_workspace(
            workspace_id=self.workspace_id,
            related_model=AssessmentSet,
            related_id=self.assessment_set_id,
            field_name="assessment_set",
            errors=errors,
        )
        if self.actor_element_assessment_id:
            _validate_related_workspace(
                workspace_id=self.workspace_id,
                related_model=ActorElementAssessment,
                related_id=self.actor_element_assessment_id,
                field_name="actor_element_assessment",
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
        assessment = None
        if self.actor_element_assessment_id:
            assessment = ActorElementAssessment.objects.filter(
                pk=self.actor_element_assessment_id
            ).first()
            if assessment is not None:
                if assessment.assessment_set_id != self.assessment_set_id:
                    errors["assessment_set"] = (
                        "ParameterValue and actor assessment must use the same set."
                    )
                if assessment.time_slice_id != self.time_slice_id:
                    errors["time_slice"] = (
                        "ParameterValue and actor assessment must use the same TimeSlice."
                    )
        if self.target_type == TargetType.ACTOR_ELEMENT_ASSESSMENT:
            if self.actor_element_assessment_id is None:
                errors["actor_element_assessment"] = (
                    "Canonical actor-element values require their assessment context."
                )
            elif self.target_id != self.actor_element_assessment_id:
                errors["target_id"] = "Target must be the actor-element assessment."
        _validate_typed_target(
            project_id=self.project_id,
            target_type=self.target_type,
            target_id=self.target_id,
            errors=errors,
        )
        _validate_status_and_value(status=self.status, value=self.value, errors=errors)
        if (
            self.temporal_status == AssessmentTemporalStatus.NO_DIRECT_POSITION
            and self.status != ValueStatus.UNKNOWN
        ):
            errors["temporal_status"] = (
                "NO_DIRECT_POSITION is compatible only with an explicit UNKNOWN value."
            )
        if definition is not None:
            _validate_parameter_value_type(
                definition=definition,
                value=self.value,
                errors=errors,
            )
            code = definition.code.upper()
            if self.value is not None and code in {"POS", "POSITION"}:
                try:
                    numeric = Decimal(str(self.value))
                except (InvalidOperation, ValueError):
                    numeric = None
                if numeric is not None and (
                    numeric < Decimal("-10") or numeric > Decimal("10")
                ):
                    errors["value"] = "POS must be between -10 and +10."
                if assessment is not None and not assessment.reference_statement.strip():
                    if not assessment.reference_statement_incomplete:
                        errors["actor_element_assessment"] = (
                            "POS requires a reference statement or explicit incomplete flag."
                        )
            if self.value is not None and code in {"SAL", "SALIENCE"}:
                try:
                    numeric = Decimal(str(self.value))
                except (InvalidOperation, ValueError):
                    numeric = None
                if numeric is not None and (
                    numeric < Decimal("0") or numeric > Decimal("10")
                ):
                    errors["value"] = "SAL must be between 0 and 10."
        _validate_assessment_metadata(
            definition=definition,
            status=self.status,
            value=self.value,
            confidence=self.confidence,
            range_min=self.range_min,
            range_max=self.range_max,
            rationale=self.rationale,
            inherited_metadata_complete=(
                assessment is not None
                and assessment.confidence_level != ConfidenceLevel.UNKNOWN
                and bool(assessment.reference_statement.strip())
            ),
            errors=errors,
        )
        if self.supersedes_id:
            previous = ParameterValue.objects.filter(pk=self.supersedes_id).first()
            if previous is not None:
                context_fields = (
                    "workspace_id",
                    "time_slice_id",
                    "assessment_set_id",
                    "actor_element_assessment_id",
                    "parameter_definition_id",
                    "target_type",
                    "target_id",
                )
                if any(
                    getattr(previous, field) != getattr(self, field)
                    for field in context_fields
                ):
                    errors["supersedes"] = "Value successor context must remain exact."
                if previous.version == self.version:
                    errors["version"] = "Value successor requires a new version."
        elif all(
            (
                self.workspace_id,
                self.time_slice_id,
                self.assessment_set_id,
                self.parameter_definition_id,
                self.target_id,
            )
        ) and ParameterValue.objects.filter(
            workspace_id=self.workspace_id,
            time_slice_id=self.time_slice_id,
            assessment_set_id=self.assessment_set_id,
            actor_element_assessment_id=self.actor_element_assessment_id,
            parameter_definition_id=self.parameter_definition_id,
            target_type=self.target_type,
            target_id=self.target_id,
            supersedes__isnull=True,
        ).exclude(pk=self.pk).exists():
            errors["supersedes"] = "A correction must identify its exact predecessor."
        if errors:
            raise ValidationError(errors)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        protected = (
            hasattr(self, "successor")
            or self.audit_events.exists()
            or self.evidence_links.exists()
            or self.fact_evidence_links.exists()
        )
        if protected:
            raise ValidationError("Attributed or evidenced values are append-only.")
        return super().delete(*args, **kwargs)

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


class ImmutableQuerySet(models.QuerySet):
    """Fail closed for ORM bulk mutation of append-only provenance rows."""

    def bulk_create(
        self,
        objs: Any,
        batch_size: int | None = None,
        ignore_conflicts: bool = False,
        update_conflicts: bool = False,
        update_fields: Any = None,
        unique_fields: Any = None,
    ) -> Any:
        objects = list(objs)
        if ignore_conflicts or update_conflicts:
            raise ValidationError(
                "Captured bulk inserts cannot ignore or rewrite identity conflicts."
            )
        with transaction.atomic(using=self.db):
            for obj in objects:
                obj.full_clean()
            return super().bulk_create(
                objects,
                batch_size=batch_size,
                ignore_conflicts=False,
                update_conflicts=False,
                update_fields=update_fields,
                unique_fields=unique_fields,
            )

    def update(self, **kwargs: Any) -> int:
        raise ValidationError("Captured records are append-only and cannot be bulk-updated.")

    def bulk_update(
        self,
        objs: Any,
        fields: Any,
        batch_size: int | None = None,
    ) -> int:
        raise ValidationError("Captured records are append-only and cannot be bulk-updated.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Captured records are append-only and cannot be bulk-deleted.")

    def _raw_delete(self, using: str) -> int:
        raise ValidationError("Captured records cannot be removed by a cascade fast-delete.")


class ImmutableManager(models.Manager.from_queryset(ImmutableQuerySet)):
    pass


class ImmutableCapturedModel(StableVersionedModel):
    """Reject in-place mutation and deletion of captured provenance objects."""

    immutable_excluded_fields = frozenset({"created_at", "updated_at"})
    objects = ImmutableManager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        if self.pk and type(self)._default_manager.filter(pk=self.pk).exists():
            previous = type(self)._default_manager.get(pk=self.pk)
            changed: list[str] = []
            for field in self._meta.concrete_fields:
                if field.name in self.immutable_excluded_fields:
                    continue
                if getattr(previous, field.attname) != getattr(self, field.attname):
                    changed.append(field.name)
            if changed:
                raise ValidationError(
                    {name: "Captured records are immutable; create a new version." for name in changed}
                )
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError("Captured records are append-only and cannot be deleted.")


class TerminologyEntry(ImmutableCapturedModel):
    """Versioned canonical display terminology, separate from stable identity."""

    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.RESTRICT,
        related_name="terminology_entries",
    )
    canonical_ru_name = models.CharField(max_length=500)
    canonical_ru_acronym = models.CharField(max_length=64, blank=True)
    exact_en_term = models.CharField(max_length=500)
    exact_en_acronym = models.CharField(max_length=64, blank=True)
    source_framework = models.CharField(max_length=500)
    source_citation = models.TextField()
    construct_version = models.CharField(max_length=64)
    locale = models.CharField(max_length=16, validators=[LOCALE_VALIDATOR])
    display_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("workspace__code", "code", "construct_version", "locale")
        constraints = [
            *_stable_constraints("domain_term_entry"),
            models.UniqueConstraint(
                fields=("workspace", "code", "construct_version", "locale"),
                name="domain_term_entry_identity_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(canonical_ru_name="")
                    & ~Q(exact_en_term="")
                    & ~Q(source_framework="")
                    & ~Q(source_citation="")
                    & ~Q(construct_version="")
                ),
                name="domain_term_entry_fields_present",
            ),
        ]


class LegacyTermMapping(ImmutableCapturedModel):
    """Hidden import/migration crosswalk; never current display terminology."""

    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.RESTRICT,
        related_name="legacy_term_mappings",
    )
    terminology_entry = models.ForeignKey(
        TerminologyEntry,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="legacy_mappings",
    )
    legacy_code = models.CharField(max_length=128, validators=[CODE_VALIDATOR])
    legacy_label = models.CharField(max_length=500, blank=True)
    source_version = models.CharField(max_length=64)
    mapping_status = models.CharField(
        max_length=32,
        choices=TerminologyMappingStatus.choices,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("workspace__code", "legacy_code", "source_version")
        constraints = [
            *_stable_constraints("domain_legacy_term"),
            models.UniqueConstraint(
                fields=("workspace", "legacy_code", "source_version"),
                name="domain_legacy_term_identity_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        mapping_status=TerminologyMappingStatus.RENAME_ONLY,
                        terminology_entry__isnull=False,
                    )
                    | Q(
                        mapping_status=TerminologyMappingStatus.TRANSFER_WITH_REVIEW,
                        terminology_entry__isnull=False,
                    )
                    | Q(
                        mapping_status__in=(
                            TerminologyMappingStatus.METHOD_BLOCKED,
                            TerminologyMappingStatus.RECODING_REQUIRED,
                        )
                    )
                ),
                name="domain_legacy_term_target_state",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.terminology_entry_id:
            _validate_related_workspace(
                workspace_id=self.workspace_id,
                related_model=TerminologyEntry,
                related_id=self.terminology_entry_id,
                field_name="terminology_entry",
                errors=errors,
            )
        if self.mapping_status in {
            TerminologyMappingStatus.RENAME_ONLY,
            TerminologyMappingStatus.TRANSFER_WITH_REVIEW,
        } and not self.terminology_entry_id:
            errors["terminology_entry"] = "This mapping status requires an exact target."
        if errors:
            raise ValidationError(errors)


class Source(ImmutableCapturedModel):
    """Publisher/source-group identity, deliberately independent of URL count."""

    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.CASCADE,
        related_name="sources",
    )
    name = models.CharField(max_length=500)
    publisher = models.CharField(max_length=500)
    independence_group = models.CharField(max_length=255)
    independence_status = models.CharField(
        max_length=16,
        choices=SourceIndependenceStatus.choices,
        default=SourceIndependenceStatus.UNVERIFIED,
    )
    homepage_url = models.URLField(max_length=2048, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("workspace__code", "independence_group", "code")
        constraints = [
            *_stable_constraints("domain_canonical_source"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_csource_ws_code_uniq",
            ),
            models.CheckConstraint(
                condition=~Q(independence_group=""),
                name="domain_csource_group_not_empty",
            ),
        ]

    @property
    def source_group(self) -> str:
        """Read-only compatibility spelling; canonical identity is independence_group."""

        return self.independence_group


class Document(ImmutableCapturedModel):
    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    source = models.ForeignKey(
        Source,
        on_delete=models.RESTRICT,
        related_name="documents",
    )
    title = models.CharField(max_length=500)
    canonical_url = models.URLField(max_length=2048, blank=True)
    publication_date = models.DateField(null=True, blank=True)
    accessed_on = models.DateField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("workspace__code", "source__code", "code")
        constraints = [
            *_stable_constraints("domain_document"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_document_ws_code_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    Q(publication_date__isnull=True)
                    | Q(accessed_on__isnull=True)
                    | Q(accessed_on__gte=models.F("publication_date"))
                ),
                name="domain_document_access_order",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        _validate_related_workspace(
            workspace_id=self.workspace_id,
            related_model=Source,
            related_id=self.source_id,
            field_name="source",
            errors=errors,
        )
        if (
            self.publication_date is not None
            and self.accessed_on is not None
            and self.accessed_on < self.publication_date
        ):
            errors["accessed_on"] = "Access date cannot precede publication date."
        if errors:
            raise ValidationError(errors)


class DocumentVersion(ImmutableCapturedModel):
    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.RESTRICT,
        related_name="document_versions",
    )
    document = models.ForeignKey(
        Document,
        on_delete=models.RESTRICT,
        related_name="versions",
    )
    supersedes = models.ForeignKey(
        "self",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="successors",
    )
    status = models.CharField(
        max_length=64,
        choices=DocumentVersionStatus.choices,
        default=DocumentVersionStatus.URL_ONLY,
    )
    capture_url = models.URLField(max_length=2048, blank=True)
    captured_at = models.DateTimeField(default=timezone.now, editable=False)
    content_sha256 = models.CharField(
        max_length=64,
        blank=True,
        validators=[SHA256_VALIDATOR],
    )
    media_type = models.CharField(max_length=128, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("workspace__code", "document__code", "version")
        constraints = [
            *_stable_constraints("domain_document_version"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_docversion_ws_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("document", "version"),
                name="domain_docversion_exact_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status__in=(
                            DocumentVersionStatus.URL_ONLY,
                            DocumentVersionStatus.URL_CAPTURED_FULL_CONTENT_HASH_PENDING_INGEST,
                        ),
                        content_sha256="",
                    )
                    | Q(
                        status__in=(
                            DocumentVersionStatus.CONTENT_CAPTURED,
                            DocumentVersionStatus.VERIFIED,
                        )
                    )
                    & ~Q(content_sha256="")
                ),
                name="domain_docversion_hash_status",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        _validate_related_workspace(
            workspace_id=self.workspace_id,
            related_model=Document,
            related_id=self.document_id,
            field_name="document",
            errors=errors,
        )
        if self.supersedes_id:
            previous = DocumentVersion.objects.filter(pk=self.supersedes_id).first()
            if previous is not None:
                if previous.workspace_id != self.workspace_id:
                    errors["supersedes"] = "Version lineage cannot cross workspaces."
                if previous.document_id != self.document_id:
                    errors["supersedes"] = "Version lineage cannot cross documents."
            if self.supersedes_id == self.pk:
                errors["supersedes"] = "A document version cannot supersede itself."
        pending = {
            DocumentVersionStatus.URL_ONLY,
            DocumentVersionStatus.URL_CAPTURED_FULL_CONTENT_HASH_PENDING_INGEST,
        }
        if self.status in pending and self.content_sha256:
            errors["content_sha256"] = "URL-only versions cannot claim a content checksum."
        if self.status not in pending and not self.content_sha256:
            errors["content_sha256"] = "Captured content requires its own checksum."
        if errors:
            raise ValidationError(errors)


class DocumentContent(ImmutableCapturedModel):
    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.RESTRICT,
        related_name="document_contents",
    )
    document_version = models.OneToOneField(
        DocumentVersion,
        on_delete=models.RESTRICT,
        related_name="content",
    )
    normalized_text = models.TextField(blank=True)
    original_bytes = models.BinaryField(null=True, blank=True)
    encoding = models.CharField(max_length=64, blank=True)
    normalization_version = models.CharField(max_length=64)
    content_sha256 = models.CharField(max_length=64, validators=[SHA256_VALIDATOR])

    class Meta:
        ordering = ("workspace__code", "document_version__code")
        constraints = [
            *_stable_constraints("domain_document_content"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_doccontent_ws_code_uniq",
            ),
            models.CheckConstraint(
                condition=(~Q(normalized_text="") | Q(original_bytes__isnull=False)),
                name="domain_doccontent_not_empty",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        _validate_related_workspace(
            workspace_id=self.workspace_id,
            related_model=DocumentVersion,
            related_id=self.document_version_id,
            field_name="document_version",
            errors=errors,
        )
        raw = bytes(self.original_bytes) if self.original_bytes is not None else None
        if raw is None and self.normalized_text:
            try:
                raw = self.normalized_text.encode(self.encoding or "utf-8")
            except LookupError:
                errors["encoding"] = "Unknown text encoding."
        if raw is None:
            errors["normalized_text"] = "Captured content cannot be empty."
        elif hashlib.sha256(raw).hexdigest() != self.content_sha256:
            errors["content_sha256"] = "Checksum does not match captured content."
        version = DocumentVersion.objects.filter(pk=self.document_version_id).first()
        if version is not None and version.content_sha256 != self.content_sha256:
            errors["content_sha256"] = "Checksum must match the exact DocumentVersion."
        if errors:
            raise ValidationError(errors)


class TextFragment(ImmutableCapturedModel):
    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.RESTRICT,
        related_name="text_fragments",
    )
    document_version = models.ForeignKey(
        DocumentVersion,
        on_delete=models.RESTRICT,
        related_name="fragments",
    )
    anchor_status = models.CharField(
        max_length=48,
        choices=AnchorStatus.choices,
        default=AnchorStatus.UNRESOLVED,
    )
    start_offset = models.PositiveIntegerField(null=True, blank=True)
    end_offset = models.PositiveIntegerField(null=True, blank=True)
    selector = models.JSONField(default=dict, blank=True)
    page = models.CharField(max_length=64, blank=True)
    section = models.CharField(max_length=255, blank=True)
    exact_text = models.TextField(blank=True)
    text_sha256 = models.CharField(
        max_length=64,
        blank=True,
        validators=[SHA256_VALIDATOR],
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("workspace__code", "document_version__code", "start_offset", "code")
        constraints = [
            *_stable_constraints("domain_text_fragment"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_fragment_ws_code_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        anchor_status=AnchorStatus.EXACT,
                        start_offset__isnull=False,
                        end_offset__isnull=False,
                    )
                    & ~Q(exact_text="")
                    & ~Q(text_sha256="")
                    | ~Q(anchor_status=AnchorStatus.EXACT)
                ),
                name="domain_fragment_exact_fields",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        _validate_related_workspace(
            workspace_id=self.workspace_id,
            related_model=DocumentVersion,
            related_id=self.document_version_id,
            field_name="document_version",
            errors=errors,
        )
        if self.anchor_status == AnchorStatus.EXACT:
            if self.start_offset is None or self.end_offset is None:
                errors["start_offset"] = "Exact anchors require both offsets."
            elif self.start_offset >= self.end_offset:
                errors["end_offset"] = "End offset must be greater than start offset."
            if not self.selector:
                errors["selector"] = "Exact anchors require a stable selector."
            if hashlib.sha256(self.exact_text.encode("utf-8")).hexdigest() != self.text_sha256:
                errors["text_sha256"] = "Fragment checksum does not match exact text."
            content = DocumentContent.objects.filter(
                document_version_id=self.document_version_id
            ).first()
            if content is None or not content.normalized_text:
                errors["document_version"] = (
                    "Exact fragments require captured normalized document content."
                )
            elif self.start_offset is not None and self.end_offset is not None:
                if content.normalized_text[self.start_offset : self.end_offset] != self.exact_text:
                    errors["exact_text"] = "ANCHOR_MISMATCH: exact text does not resolve."
        elif self.anchor_status == AnchorStatus.HASH_RECORDED_PENDING_INGEST:
            if not self.text_sha256:
                errors["text_sha256"] = "Pending-ingest fragments require the recorded hash."
            elif self.exact_text and (
                hashlib.sha256(self.exact_text.encode("utf-8")).hexdigest()
                != self.text_sha256
            ):
                errors["text_sha256"] = (
                    "Recorded fragment checksum does not match the captured fragment text."
                )
            if any(
                value not in (None, "", {})
                for value in (
                    self.start_offset,
                    self.end_offset,
                    self.selector,
                )
            ):
                errors["anchor_status"] = (
                    "A recorded fragment is not an exact document anchor; offsets and "
                    "selectors must stay empty until the full immutable content is ingested."
                )
        else:
            populated = any(
                value not in (None, "", {})
                for value in (
                    self.start_offset,
                    self.end_offset,
                    self.selector,
                    self.exact_text,
                    self.text_sha256,
                )
            )
            if populated:
                errors["anchor_status"] = (
                    "Unresolved and URL-only fragments cannot claim an exact anchor."
                )
        if errors:
            raise ValidationError(errors)


class Fact(ImmutableCapturedModel):
    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.RESTRICT,
        related_name="facts",
    )
    experiment = models.ForeignKey(
        Experiment,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="facts",
    )
    fact_type = models.CharField(max_length=32, choices=FactType.choices)
    statement = models.TextField()
    origin = models.CharField(max_length=32, choices=FactOrigin.choices)
    directness = models.CharField(
        max_length=24,
        choices=FactDirectness.choices,
        default=FactDirectness.UNKNOWN,
    )
    visibility = models.CharField(
        max_length=24,
        choices=Visibility.choices,
        default=Visibility.WORKSPACE_SHARED,
    )
    status = models.CharField(
        max_length=40,
        choices=AssessmentRecordStatus.choices,
        default=AssessmentRecordStatus.PROVISIONAL,
    )
    confidence = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    temporal_status = models.CharField(
        max_length=40,
        choices=EvidenceTemporalStatus.choices,
        default=EvidenceTemporalStatus.UNKNOWN,
    )
    coder_identifier = models.CharField(max_length=255, default="UNSPECIFIED")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("workspace__code", "code")
        constraints = [
            *_stable_constraints("domain_fact"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_fact_ws_code_uniq",
            ),
            models.CheckConstraint(
                condition=~Q(statement=""),
                name="domain_fact_statement_not_empty",
            ),
            models.CheckConstraint(
                condition=~Q(coder_identifier=""),
                name="domain_fact_coder_not_empty",
            ),
            models.CheckConstraint(
                condition=(
                    Q(confidence__isnull=True)
                    | Q(confidence__gte=0, confidence__lte=100)
                ),
                name="domain_fact_confidence_0_100",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.experiment_id:
            _validate_related_workspace(
                workspace_id=self.workspace_id,
                related_model=Experiment,
                related_id=self.experiment_id,
                field_name="experiment",
                errors=errors,
            )
        if self.visibility == Visibility.EXPERIMENT_PRIVATE and not self.experiment_id:
            errors["experiment"] = "Experiment-private facts require an experiment."
        if not self.coder_identifier.strip():
            errors["coder_identifier"] = "Fact coder/author identity is required."
        if self.confidence is not None and not Decimal("0") <= self.confidence <= Decimal("100"):
            errors["confidence"] = "Fact coder confidence must be in the 0..100 scale."
        if errors:
            raise ValidationError(errors)


class FactEvidence(ImmutableCapturedModel):
    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.RESTRICT,
        related_name="fact_evidence_links",
    )
    fact = models.ForeignKey(Fact, on_delete=models.RESTRICT, related_name="evidence_links")
    fragment = models.ForeignKey(
        TextFragment,
        on_delete=models.RESTRICT,
        related_name="fact_links",
    )
    relation = models.CharField(
        max_length=16,
        choices=FactEvidenceRelation.choices,
        default=FactEvidenceRelation.SUPPORTS,
    )
    temporal_status = models.CharField(
        max_length=40,
        choices=EvidenceTemporalStatus.choices,
        default=EvidenceTemporalStatus.UNKNOWN,
    )
    learned_on = models.DateField(null=True, blank=True)
    rationale = models.TextField(blank=True)

    class Meta:
        ordering = ("workspace__code", "fact__code", "code")
        constraints = [
            *_stable_constraints("domain_fact_evidence"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_fact_evidence_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("fact", "fragment", "relation"),
                name="domain_fact_fragment_relation_uniq",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        for field_name, related_model, related_id in (
            ("fact", Fact, self.fact_id),
            ("fragment", TextFragment, self.fragment_id),
        ):
            _validate_related_workspace(
                workspace_id=self.workspace_id,
                related_model=related_model,
                related_id=related_id,
                field_name=field_name,
                errors=errors,
            )
        if errors:
            raise ValidationError(errors)


def _validate_cutoff_provenance(
    *,
    fact_id: uuid.UUID | None,
    cutoff: Any,
    temporal_status: str,
    learned_on: Any,
    errors: dict[str, str],
) -> None:
    if cutoff is None:
        return
    retrospective = {
        EvidenceTemporalStatus.RETROSPECTIVE_KNOWLEDGE,
        EvidenceTemporalStatus.RETROSPECTIVE_CORROBORATION,
    }
    dates = list(
        Document.objects.filter(
            versions__fragments__fact_links__fact_id=fact_id,
            publication_date__isnull=False,
        ).values_list("publication_date", flat=True)
    )
    post_cutoff = (learned_on is not None and learned_on > cutoff) or any(
        date > cutoff for date in dates
    )
    if (
        temporal_status == EvidenceTemporalStatus.CONTEMPORANEOUS
        and learned_on is None
        and not dates
    ):
        errors["temporal_status"] = (
            "Contemporaneous status requires a known publication or learned-on date."
        )
    if post_cutoff and temporal_status not in retrospective:
        errors["temporal_status"] = (
            "Post-cutoff evidence must be explicitly retrospective."
        )


class AssessmentEvidence(ImmutableCapturedModel):
    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.RESTRICT,
        related_name="assessment_evidence_links",
    )
    assessment = models.ForeignKey(
        ActorElementAssessment,
        on_delete=models.RESTRICT,
        related_name="evidence_links",
    )
    fact = models.ForeignKey(Fact, on_delete=models.RESTRICT, related_name="assessment_links")
    role = models.CharField(max_length=40, choices=AssessmentEvidenceRole.choices)
    temporal_status = models.CharField(
        max_length=40,
        choices=EvidenceTemporalStatus.choices,
        default=EvidenceTemporalStatus.UNKNOWN,
    )
    learned_on = models.DateField(null=True, blank=True)
    rationale = models.TextField(blank=True)

    class Meta:
        ordering = ("workspace__code", "assessment__code", "code")
        constraints = [
            *_stable_constraints("domain_assessment_evidence"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_assessment_evidence_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("assessment", "fact", "role"),
                name="domain_assessment_fact_role_uniq",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        for field_name, related_model, related_id in (
            ("assessment", ActorElementAssessment, self.assessment_id),
            ("fact", Fact, self.fact_id),
        ):
            _validate_related_workspace(
                workspace_id=self.workspace_id,
                related_model=related_model,
                related_id=related_id,
                field_name=field_name,
                errors=errors,
            )
        assessment = ActorElementAssessment.objects.filter(pk=self.assessment_id).first()
        _validate_cutoff_provenance(
            fact_id=self.fact_id,
            cutoff=assessment.knowledge_cutoff if assessment else None,
            temporal_status=self.temporal_status,
            learned_on=self.learned_on,
            errors=errors,
        )
        if errors:
            raise ValidationError(errors)


class ParameterValueEvidence(ImmutableCapturedModel):
    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.RESTRICT,
        related_name="parameter_value_evidence_links",
    )
    parameter_value = models.ForeignKey(
        ParameterValue,
        on_delete=models.RESTRICT,
        related_name="fact_evidence_links",
    )
    fact = models.ForeignKey(Fact, on_delete=models.RESTRICT, related_name="value_links")
    role = models.CharField(max_length=40, choices=AssessmentEvidenceRole.choices)
    temporal_status = models.CharField(
        max_length=40,
        choices=EvidenceTemporalStatus.choices,
        default=EvidenceTemporalStatus.UNKNOWN,
    )
    learned_on = models.DateField(null=True, blank=True)
    rationale = models.TextField(blank=True)

    class Meta:
        ordering = ("workspace__code", "parameter_value__code", "code")
        constraints = [
            *_stable_constraints("domain_value_evidence"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_value_evidence_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("parameter_value", "fact", "role"),
                name="domain_value_fact_role_uniq",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        for field_name, related_model, related_id in (
            ("parameter_value", ParameterValue, self.parameter_value_id),
            ("fact", Fact, self.fact_id),
        ):
            _validate_related_workspace(
                workspace_id=self.workspace_id,
                related_model=related_model,
                related_id=related_id,
                field_name=field_name,
                errors=errors,
            )
        value = ParameterValue.objects.filter(pk=self.parameter_value_id).first()
        assessment = value.actor_element_assessment if value else None
        _validate_cutoff_provenance(
            fact_id=self.fact_id,
            cutoff=assessment.knowledge_cutoff if assessment else None,
            temporal_status=self.temporal_status,
            learned_on=self.learned_on,
            errors=errors,
        )
        if errors:
            raise ValidationError(errors)


class DataGap(ValidatedStableVersionedModel):
    """Persisted, round-trippable declaration of unresolved source-data gaps."""

    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.CASCADE,
        related_name="data_gaps",
    )
    gap_type = models.CharField(max_length=128, validators=[CODE_VALIDATOR])
    entity_type = models.CharField(max_length=128, validators=[CODE_VALIDATOR])
    entity_code = models.CharField(max_length=128, validators=[CODE_VALIDATOR])
    required_behavior = models.TextField()
    resolved = models.BooleanField(default=False)
    resolution = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("workspace__code", "resolved", "code")
        constraints = [
            *_stable_constraints("domain_data_gap"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_gap_ws_code_uniq",
            ),
            models.CheckConstraint(
                condition=(Q(resolved=False, resolution="") | Q(resolved=True) & ~Q(resolution="")),
                name="domain_gap_resolution_state",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.resolved != bool(self.resolution.strip()):
            raise ValidationError(
                {"resolution": "Resolved state and resolution text must change together."}
            )


_UNSAFE_HELP_HTML = re.compile(
    r"(?:<\s*(?:script|iframe|object|embed|style)\b|\bon[a-z]+\s*=|javascript\s*:|data\s*:\s*text/html)",
    flags=re.IGNORECASE,
)


class HelpTopic(ImmutableCapturedModel):
    """One exact locale/version of pre-sanitized help HTML."""

    stable_key = models.CharField(max_length=128, validators=[CODE_VALIDATOR])
    title = models.CharField(max_length=500)
    application_scope = models.CharField(
        max_length=16,
        choices=HelpApplicationScope.choices,
    )
    construct_version = models.CharField(max_length=64)
    term_version = models.CharField(max_length=64)
    locale = models.CharField(max_length=16, validators=[LOCALE_VALIDATOR])
    sanitized_html = models.TextField()
    content_sha256 = models.CharField(max_length=64, validators=[SHA256_VALIDATOR])
    publication_status = models.CharField(
        max_length=16,
        choices=PublicationStatus.choices,
        default=PublicationStatus.DRAFT,
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("stable_key", "locale", "version")
        constraints = [
            *_stable_constraints("domain_help_topic"),
            models.UniqueConstraint(
                fields=("application_scope", "stable_key", "locale", "version"),
                name="domain_help_exact_version_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    Q(publication_status=PublicationStatus.PUBLISHED, published_at__isnull=False)
                    | ~Q(publication_status=PublicationStatus.PUBLISHED)
                ),
                name="domain_help_publish_time",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        from .services.help_topics import sanitize_help_html

        if _UNSAFE_HELP_HTML.search(self.sanitized_html):
            errors["sanitized_html"] = "Unsafe executable HTML is forbidden."
        elif sanitize_help_html(self.sanitized_html) != self.sanitized_html:
            errors["sanitized_html"] = (
                "Help HTML must be persisted in canonical sanitized form."
            )
        actual_hash = hashlib.sha256(self.sanitized_html.encode("utf-8")).hexdigest()
        if actual_hash != self.content_sha256:
            errors["content_sha256"] = "Checksum does not match sanitized HTML."
        if self.publication_status == PublicationStatus.PUBLISHED and self.published_at is None:
            errors["published_at"] = "Published help requires a timestamp."
        if errors:
            raise ValidationError(errors)


class UIHelpBinding(ImmutableCapturedModel):
    """Stable UI/component key bound to one exact HelpTopic locale/version row."""

    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="help_bindings",
    )
    application_scope = models.CharField(
        max_length=16,
        choices=HelpApplicationScope.choices,
    )
    ui_key = models.CharField(max_length=255, validators=[CODE_VALIDATOR])
    locale = models.CharField(max_length=16, validators=[LOCALE_VALIDATOR])
    help_topic = models.ForeignKey(
        HelpTopic,
        on_delete=models.RESTRICT,
        related_name="ui_bindings",
    )

    class Meta:
        ordering = ("workspace__code", "ui_key", "locale", "version")
        base_manager_name = "objects"
        constraints = [
            *_stable_constraints("domain_ui_help_binding"),
            models.UniqueConstraint(
                fields=("workspace", "application_scope", "ui_key", "locale", "version"),
                condition=Q(workspace__isnull=False),
                name="domain_ui_help_ws_uniq",
            ),
            models.UniqueConstraint(
                fields=("application_scope", "ui_key", "locale", "version"),
                condition=Q(workspace__isnull=True),
                name="domain_ui_help_global_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    Q(workspace__isnull=False)
                    | Q(application_scope=HelpApplicationScope.STUDIO)
                ),
                name="domain_ui_help_global_studio",
            ),
        ]
        indexes = [
            models.Index(
                fields=("workspace", "application_scope", "ui_key", "locale", "version"),
                name="domain_ui_help_ws_idx",
            ),
            models.Index(
                fields=("application_scope", "ui_key", "locale", "version"),
                name="domain_ui_help_global_idx",
            ),
        ]

    def full_clean(self, *args: Any, **kwargs: Any) -> None:
        # Keep existing workspace-bound constructors source-compatible. New
        # pre-workspace bindings must always declare STUDIO explicitly.
        if self.workspace_id is not None and not self.application_scope:
            topic_scope = HelpTopic.objects.filter(pk=self.help_topic_id).values_list(
                "application_scope", flat=True
            ).first()
            if topic_scope:
                self.application_scope = topic_scope
        super().full_clean(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        topic = HelpTopic.objects.filter(pk=self.help_topic_id).first()
        if topic is None:
            return
        errors: dict[str, str] = {}
        if topic.locale != self.locale:
            errors["locale"] = "Binding locale must match the exact HelpTopic version."
        if topic.application_scope != self.application_scope:
            errors["application_scope"] = (
                "Binding application scope must match the exact HelpTopic version."
            )
        if topic.version != self.version:
            errors["version"] = "Binding version must match the exact HelpTopic version."
        if topic.publication_status != PublicationStatus.PUBLISHED:
            errors["help_topic"] = "Bindings require an exact published HelpTopic version."
        if errors:
            raise ValidationError(errors)


class PowerProfile(ValidatedStableVersionedModel):
    """Context header for an eight-dimensional vector; deliberately no scalar field."""

    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.CASCADE,
        related_name="power_profiles",
    )
    assessment = models.ForeignKey(
        ActorElementAssessment,
        on_delete=models.RESTRICT,
        related_name="power_profiles",
    )
    method_version = models.CharField(max_length=64, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ("workspace__code", "assessment__code", "code")
        constraints = [
            *_stable_constraints("domain_power_profile"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_power_profile_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("assessment", "version"),
                name="domain_power_profile_version_uniq",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        _validate_related_workspace(
            workspace_id=self.workspace_id,
            related_model=ActorElementAssessment,
            related_id=self.assessment_id,
            field_name="assessment",
            errors=errors,
        )
        if errors:
            raise ValidationError(errors)


class PowerComponent(ValidatedStableVersionedModel):
    """One independently statused/provenanced vector component."""

    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.CASCADE,
        related_name="power_components",
    )
    profile = models.ForeignKey(
        PowerProfile,
        on_delete=models.CASCADE,
        related_name="components",
    )
    dimension = models.CharField(max_length=2, choices=PowerDimension.choices)
    status = models.CharField(
        max_length=32,
        choices=ValueStatus.choices,
        default=ValueStatus.UNKNOWN,
    )
    value = models.JSONField(null=True, blank=True, default=None)
    confidence = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    rationale = models.TextField(blank=True)
    provenance = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("workspace__code", "profile__code", "dimension")
        constraints = [
            *_stable_constraints("domain_power_component"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_power_component_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("profile", "dimension"),
                name="domain_power_dimension_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status__in=tuple(ABSENT_VALUE_STATUSES), value__isnull=True)
                    | Q(status__in=tuple(PRESENT_VALUE_STATUSES), value__isnull=False)
                ),
                name="domain_power_status_value",
            ),
            models.CheckConstraint(
                condition=(
                    Q(confidence__isnull=True)
                    | Q(confidence__gte=0, confidence__lte=100)
                ),
                name="domain_power_confidence_0_100",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status__in=tuple(ABSENT_VALUE_STATUSES),
                        confidence__isnull=True,
                    )
                    | (
                        Q(
                            status__in=tuple(PRESENT_VALUE_STATUSES),
                            confidence__isnull=False,
                        )
                        & ~Q(rationale="")
                    )
                ),
                name="domain_power_metadata_state",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        _validate_related_workspace(
            workspace_id=self.workspace_id,
            related_model=PowerProfile,
            related_id=self.profile_id,
            field_name="profile",
            errors=errors,
        )
        _validate_status_and_value(status=self.status, value=self.value, errors=errors)
        if self.status in PRESENT_VALUE_STATUSES:
            if self.confidence is None:
                errors["confidence"] = "A present component requires coder confidence."
            if not self.rationale.strip():
                errors["rationale"] = "A present component requires rationale."
        elif self.confidence is not None:
            errors["confidence"] = "An unavailable component has null confidence."
        if errors:
            raise ValidationError(errors)


class PowerComponentEvidence(ImmutableCapturedModel):
    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.RESTRICT,
        related_name="power_evidence_links",
    )
    component = models.ForeignKey(
        PowerComponent,
        on_delete=models.RESTRICT,
        related_name="evidence_links",
    )
    fact = models.ForeignKey(Fact, on_delete=models.RESTRICT, related_name="power_links")
    role = models.CharField(max_length=40, choices=AssessmentEvidenceRole.choices)

    class Meta:
        ordering = ("workspace__code", "component__code", "code")
        constraints = [
            *_stable_constraints("domain_power_evidence"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_power_evidence_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("component", "fact", "role"),
                name="domain_power_fact_role_uniq",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        for field_name, related_model, related_id in (
            ("component", PowerComponent, self.component_id),
            ("fact", Fact, self.fact_id),
        ):
            _validate_related_workspace(
                workspace_id=self.workspace_id,
                related_model=related_model,
                related_id=related_id,
                field_name=field_name,
                errors=errors,
            )
        if errors:
            raise ValidationError(errors)


class ChatConversation(ValidatedStableVersionedModel):
    """Provider-neutral persisted conversation metadata; no live LLM execution."""

    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.CASCADE,
        related_name="chat_conversations",
    )
    channel_type = models.CharField(
        max_length=24,
        choices=ChatChannelType.choices,
        default=ChatChannelType.PERSONAL,
    )
    owner_identifier = models.CharField(max_length=255, default="UNSPECIFIED")
    participants = models.JSONField(default=list, blank=True)
    title = models.CharField(max_length=255, blank=True)
    provider = models.CharField(max_length=128, blank=True)
    model_name = models.CharField(max_length=255, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("workspace__code", "-created_at")
        constraints = [
            *_stable_constraints("domain_chat_conversation"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_chat_conversation_code_uniq",
            ),
            models.CheckConstraint(
                condition=~Q(owner_identifier=""),
                name="domain_chat_owner_not_empty",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if not self.owner_identifier.strip():
            errors["owner_identifier"] = "Chat owner identity is required."
        if not isinstance(self.participants, list) or any(
            not isinstance(item, str) or not item.strip()
            for item in self.participants
        ):
            errors["participants"] = "Chat participants must be non-empty identity strings."
        if errors:
            raise ValidationError(errors)


class ChatThread(ChatConversation):
    """Canonical naming alias for the provider-neutral conversation record."""

    class Meta:
        proxy = True


class ChatMessage(ImmutableCapturedModel):
    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.RESTRICT,
        related_name="chat_messages",
    )
    conversation = models.ForeignKey(
        ChatConversation,
        on_delete=models.RESTRICT,
        related_name="messages",
    )
    sequence = models.PositiveIntegerField()
    role = models.CharField(max_length=16, choices=ChatMessageRole.choices)
    content = models.TextField()
    provider = models.CharField(max_length=128, blank=True)
    model_name = models.CharField(max_length=255, blank=True)
    provider_request_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=16,
        choices=ChatMessageStatus.choices,
        default=ChatMessageStatus.COMPLETE,
    )
    error = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("conversation__code", "sequence")
        constraints = [
            *_stable_constraints("domain_chat_message"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_chat_message_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("conversation", "sequence"),
                name="domain_chat_message_sequence_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=ChatMessageStatus.ERROR) & ~Q(error="")
                    | Q(status=ChatMessageStatus.COMPLETE, error="")
                ),
                name="domain_chat_message_status_error",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        _validate_related_workspace(
            workspace_id=self.workspace_id,
            related_model=ChatConversation,
            related_id=self.conversation_id,
            field_name="conversation",
            errors=errors,
        )
        if self.status == ChatMessageStatus.ERROR and not self.error.strip():
            errors["error"] = "Failed chat messages require an explicit error."
        if self.status != ChatMessageStatus.ERROR and self.error:
            errors["error"] = "Completed chat messages cannot carry an error."
        if errors:
            raise ValidationError(errors)


class ChatCitation(ImmutableCapturedModel):
    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.RESTRICT,
        related_name="chat_citations",
    )
    message = models.ForeignKey(
        ChatMessage,
        on_delete=models.RESTRICT,
        related_name="citations",
    )
    fact = models.ForeignKey(
        Fact,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="chat_citations",
    )
    fragment = models.ForeignKey(
        TextFragment,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="chat_citations",
    )
    document_version = models.ForeignKey(
        DocumentVersion,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="chat_citations",
    )
    quote_start = models.PositiveIntegerField(null=True, blank=True)
    quote_end = models.PositiveIntegerField(null=True, blank=True)
    quote_text = models.TextField(blank=True)
    label = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("message__sequence", "code")
        constraints = [
            *_stable_constraints("domain_chat_citation"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_chat_citation_code_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        fact__isnull=False,
                        fragment__isnull=True,
                        document_version__isnull=True,
                        quote_start__isnull=True,
                        quote_end__isnull=True,
                        quote_text="",
                    )
                    | Q(
                        fragment__isnull=False,
                        document_version__isnull=False,
                        quote_start__isnull=False,
                        quote_end__isnull=False,
                    )
                    & ~Q(quote_text="")
                    & Q(quote_end__gt=models.F("quote_start"))
                ),
                name="domain_chat_citation_target_state",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        targets = (
            ("message", ChatMessage, self.message_id),
            ("fact", Fact, self.fact_id),
            ("fragment", TextFragment, self.fragment_id),
            ("document_version", DocumentVersion, self.document_version_id),
        )
        for field_name, related_model, related_id in targets:
            if related_id:
                _validate_related_workspace(
                    workspace_id=self.workspace_id,
                    related_model=related_model,
                    related_id=related_id,
                    field_name=field_name,
                    errors=errors,
                )
        fragment = TextFragment.objects.filter(pk=self.fragment_id).first()
        fact_only = self.fact_id is not None and self.fragment_id is None
        if fact_only:
            if any(
                value is not None
                for value in (
                    self.document_version_id,
                    self.quote_start,
                    self.quote_end,
                )
            ) or self.quote_text:
                errors["fragment"] = "Fact-only citations cannot carry a fragment quote span."
        else:
            if fragment is None or self.document_version_id is None:
                errors["fragment"] = (
                    "A fragment citation requires its exact TextFragment and DocumentVersion."
                )
            elif fragment.document_version_id != self.document_version_id:
                errors["document_version"] = "Citation and fragment versions must match exactly."
            if self.quote_start is None or self.quote_end is None:
                errors["quote_start"] = "A fragment citation requires an exact quote span."
            elif self.quote_start >= self.quote_end:
                errors["quote_end"] = "Quote end must be greater than quote start."
            elif fragment is not None:
                exact_text = fragment.exact_text
                if self.quote_end > len(exact_text):
                    errors["quote_end"] = "Quote span exceeds the exact fragment text."
                elif exact_text[self.quote_start : self.quote_end] != self.quote_text:
                    errors["quote_text"] = "Quote span does not match the exact fragment text."
        if self.fact_id and fragment is not None and not FactEvidence.objects.filter(
            fact_id=self.fact_id,
            fragment_id=fragment.pk,
        ).exists():
            errors["fact"] = "Fact citation must use an explicit FactEvidence link."
        if errors:
            raise ValidationError(errors)


class ImportRun(ImmutableCapturedModel):
    """Append-only receipt for preview/commit/reject; never an overwrite instruction."""

    project = models.ForeignKey(
        Project,
        on_delete=models.RESTRICT,
        related_name="import_runs",
    )
    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="import_runs",
    )
    definition_version = models.ForeignKey(
        ProjectDefinitionVersion,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="import_runs",
    )
    package_scope = models.CharField(
        max_length=24,
        choices=ImportPackageScope.choices,
        default=ImportPackageScope.WORKSPACE,
    )
    target_experiment = models.ForeignKey(
        Experiment,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="import_runs",
    )
    target_assessment_set = models.ForeignKey(
        AssessmentSet,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="import_runs",
    )
    package_format = models.CharField(max_length=64, validators=[CODE_VALIDATOR])
    package_id = models.CharField(max_length=128, validators=[CODE_VALIDATOR])
    package_version = models.CharField(max_length=64)
    schema_version = models.CharField(max_length=64)
    template_version = models.CharField(max_length=64)
    method_version = models.CharField(max_length=64)
    ontology_version = models.CharField(max_length=64)
    dataset_version = models.CharField(max_length=64)
    checksum = models.CharField(max_length=64, validators=[SHA256_VALIDATOR])
    adapter = models.CharField(max_length=255)
    selected_input = models.JSONField(default=dict, blank=True)
    selected_source_column = models.CharField(max_length=255, blank=True)
    source_identity_map = models.JSONField(default=dict, blank=True)
    correction_lineage = models.JSONField(default=list, blank=True)
    intended_changes = models.JSONField(default=dict, blank=True)
    row_counts = models.JSONField(default=dict, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    errors = models.JSONField(default=list, blank=True)
    allow_nonempty = models.BooleanField(default=False)
    status = models.CharField(max_length=16, choices=ImportRunStatus.choices)
    actor_identifier = models.CharField(max_length=255)
    committed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("project__code", "package_scope", "-created_at")
        base_manager_name = "objects"
        constraints = [
            *_stable_constraints("domain_import_run"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                condition=Q(package_scope=ImportPackageScope.WORKSPACE),
                name="domain_import_run_ws_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("project", "code"),
                condition=Q(package_scope=ImportPackageScope.PROJECT_DEFINITION),
                name="domain_import_run_def_code_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=ImportRunStatus.COMMITTED, committed_at__isnull=False)
                    | (~Q(status=ImportRunStatus.COMMITTED) & Q(committed_at__isnull=True))
                ),
                name="domain_import_commit_time",
            ),
            models.CheckConstraint(
                condition=(
                    Q(target_experiment__isnull=True, target_assessment_set__isnull=True)
                    | Q(
                        target_experiment__isnull=False,
                        target_assessment_set__isnull=False,
                    )
                ),
                name="domain_import_target_lane_pair",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        package_scope=ImportPackageScope.WORKSPACE,
                        workspace__isnull=False,
                        definition_version__isnull=False,
                    )
                    | Q(
                        package_scope=ImportPackageScope.PROJECT_DEFINITION,
                        workspace__isnull=True,
                        target_experiment__isnull=True,
                        target_assessment_set__isnull=True,
                    )
                    & (
                        ~Q(status=ImportRunStatus.COMMITTED)
                        | Q(definition_version__isnull=False)
                    )
                ),
                name="domain_import_scope_boundary",
            ),
        ]
        indexes = [
            models.Index(
                fields=("project", "package_scope", "created_at"),
                name="domain_import_scope_time_idx",
            ),
        ]

    def full_clean(self, *args: Any, **kwargs: Any) -> None:
        if self.workspace_id is not None:
            workspace_identity = ProjectWorkspace.objects.filter(
                pk=self.workspace_id
            ).values("project_id", "definition_version_id").first()
            if workspace_identity is not None:
                if self.project_id is None:
                    self.project_id = workspace_identity["project_id"]
                if self.definition_version_id is None:
                    self.definition_version_id = workspace_identity[
                        "definition_version_id"
                    ]
        super().full_clean(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if not isinstance(self.selected_input, dict):
            errors["selected_input"] = "Selected input must be a JSON object."
        if not isinstance(self.row_counts, dict):
            errors["row_counts"] = "Row counts must be a JSON object."
        if not isinstance(self.warnings, list):
            errors["warnings"] = "Warnings must be a JSON list."
        if not isinstance(self.errors, list):
            errors["errors"] = "Import errors must be a JSON list."
        if not isinstance(self.source_identity_map, dict):
            errors["source_identity_map"] = "Source identity map must be a JSON object."
        if not isinstance(self.correction_lineage, list):
            errors["correction_lineage"] = "Correction lineage must be a JSON list."
        if not isinstance(self.intended_changes, dict):
            errors["intended_changes"] = "Intended changes must be a JSON object."
        if (self.target_experiment_id is None) != (self.target_assessment_set_id is None):
            errors["target_experiment"] = "Target Experiment and AssessmentSet are one lane."
        workspace = None
        if self.workspace_id:
            workspace = ProjectWorkspace.objects.filter(pk=self.workspace_id).first()
        definition = None
        if self.definition_version_id:
            definition = ProjectDefinitionVersion.objects.filter(
                pk=self.definition_version_id
            ).first()
        if self.package_scope == ImportPackageScope.WORKSPACE:
            if workspace is None:
                errors["workspace"] = "Workspace package receipts require a workspace."
            else:
                if workspace.project_id != self.project_id:
                    errors["project"] = "Import receipt and workspace projects differ."
                if workspace.definition_version_id != self.definition_version_id:
                    errors["definition_version"] = (
                        "Workspace receipt must pin the workspace definition."
                    )
            if definition is None:
                errors["definition_version"] = (
                    "Workspace package receipts require an exact definition."
                )
        elif self.package_scope == ImportPackageScope.PROJECT_DEFINITION:
            if self.workspace_id is not None:
                errors["workspace"] = (
                    "Project-definition receipts are not workspace-scoped."
                )
            if self.target_experiment_id or self.target_assessment_set_id:
                errors["target_experiment"] = (
                    "Project-definition receipts cannot select a workspace target lane."
                )
            if self.status == ImportRunStatus.COMMITTED and definition is None:
                errors["definition_version"] = (
                    "Committed project-definition receipts require an exact definition."
                )
        if definition is not None and definition.project_id != self.project_id:
            errors["definition_version"] = (
                "Import receipt and definition projects differ."
            )
        if self.target_experiment_id and self.package_scope == ImportPackageScope.WORKSPACE:
            experiment = Experiment.objects.filter(pk=self.target_experiment_id).first()
            if experiment is not None:
                if experiment.workspace_id != self.workspace_id:
                    errors["target_experiment"] = "Import target lane cannot cross workspaces."
                if experiment.assessment_set_id != self.target_assessment_set_id:
                    errors["target_assessment_set"] = (
                        "Import target AssessmentSet must match the Experiment binding."
                    )
        if self.status == ImportRunStatus.COMMITTED and self.committed_at is None:
            errors["committed_at"] = "Committed runs require a timestamp."
        if self.status != ImportRunStatus.COMMITTED and self.committed_at is not None:
            errors["committed_at"] = "Only committed runs have a commit timestamp."
        if errors:
            raise ValidationError(errors)


class ImportReceipt(ImportRun):
    """Semantic alias: every ImportRun row is the append-only receipt."""

    class Meta:
        proxy = True


class LegacyCompatibilityReceipt(ImmutableCapturedModel):
    """Explicit fate of a legacy evidence object; never a second evidence chain."""

    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.RESTRICT,
        related_name="legacy_compatibility_receipts",
    )
    legacy_model = models.CharField(max_length=128, validators=[CODE_VALIDATOR])
    legacy_id = models.UUIDField()
    legacy_code = models.CharField(max_length=128, validators=[CODE_VALIDATOR])
    canonical_model = models.CharField(
        max_length=128,
        blank=True,
        validators=[CODE_VALIDATOR],
    )
    canonical_id = models.UUIDField(null=True, blank=True)
    canonical_code = models.CharField(
        max_length=128,
        blank=True,
        validators=[CODE_VALIDATOR],
    )
    status = models.CharField(max_length=16, choices=CompatibilityStatus.choices)
    reason = models.TextField(blank=True)
    migration_version = models.CharField(max_length=64)

    class Meta:
        ordering = ("workspace__code", "legacy_model", "legacy_code")
        constraints = [
            *_stable_constraints("domain_compat_receipt"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                name="domain_compat_receipt_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("workspace", "legacy_model", "legacy_id"),
                name="domain_compat_legacy_object_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status=CompatibilityStatus.MIGRATED,
                        canonical_id__isnull=False,
                    )
                    & ~Q(canonical_model="")
                    & ~Q(canonical_code="")
                    | Q(
                        status=CompatibilityStatus.UNRESOLVED,
                        canonical_id__isnull=True,
                        canonical_model="",
                        canonical_code="",
                    )
                    & ~Q(reason="")
                ),
                name="domain_compat_receipt_state",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.status == CompatibilityStatus.MIGRATED:
            if not self.canonical_id or not self.canonical_model or not self.canonical_code:
                raise ValidationError(
                    {"canonical_id": "Migrated receipts require an exact canonical target."}
                )
        elif self.status == CompatibilityStatus.UNRESOLVED:
            if self.canonical_id or self.canonical_model or self.canonical_code:
                raise ValidationError(
                    {"canonical_id": "Unresolved receipts cannot claim a canonical target."}
                )
            if not self.reason.strip():
                raise ValidationError({"reason": "Unresolved receipts require a reason."})


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
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
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


class AuditEvent(ImmutableCapturedModel):
    """Append-only attribution record for assessment and structure changes."""

    project = models.ForeignKey(
        Project,
        on_delete=models.RESTRICT,
        related_name="audit_events",
    )
    workspace = models.ForeignKey(
        ProjectWorkspace,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    definition_version = models.ForeignKey(
        ProjectDefinitionVersion,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    scope = models.CharField(
        max_length=16,
        choices=AuditScope.choices,
        default=AuditScope.WORKSPACE,
    )
    assessment_set = models.ForeignKey(
        AssessmentSet,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    parameter_value = models.ForeignKey(
        ParameterValue,
        on_delete=models.RESTRICT,
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
        base_manager_name = "objects"
        constraints = [
            *_stable_constraints("domain_audit_event"),
            models.UniqueConstraint(
                fields=("workspace", "code"),
                condition=Q(scope=AuditScope.WORKSPACE),
                name="domain_audit_ws_code_uniq",
            ),
            models.UniqueConstraint(
                fields=("definition_version", "code"),
                condition=Q(scope=AuditScope.DEFINITION),
                name="domain_audit_def_code_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        scope=AuditScope.WORKSPACE,
                        workspace__isnull=False,
                        definition_version__isnull=True,
                    )
                    | Q(
                        scope=AuditScope.DEFINITION,
                        workspace__isnull=True,
                        definition_version__isnull=False,
                        assessment_set__isnull=True,
                        parameter_value__isnull=True,
                    )
                ),
                name="domain_audit_scope_boundary",
            ),
        ]
        indexes = [
            models.Index(
                fields=("workspace", "entity_type", "entity_id"),
                name="domain_audit_entity_idx",
            ),
            models.Index(
                fields=("workspace", "occurred_at"),
                name="domain_audit_time_idx",
            ),
            models.Index(
                fields=("definition_version", "entity_type", "entity_id"),
                name="domain_audit_def_entity_idx",
            ),
            models.Index(
                fields=("definition_version", "occurred_at"),
                name="domain_audit_def_time_idx",
            ),
        ]

    def full_clean(self, *args: Any, **kwargs: Any) -> None:
        if self.scope == AuditScope.WORKSPACE and self.definition_version_id is None:
            _hydrate_legacy_default_workspace(
                self,
                "assessment_set",
                "parameter_value",
            )
        super().full_clean(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.scope == AuditScope.DEFINITION:
            definition_project_id = ProjectDefinitionVersion.objects.filter(
                pk=self.definition_version_id
            ).values_list("project_id", flat=True).first()
            if definition_project_id != self.project_id:
                errors["definition_version"] = (
                    "The definition belongs to a different project."
                )
            if self.workspace_id is not None:
                errors["workspace"] = "Definition audit events cannot borrow a workspace."
            if self.assessment_set_id is not None or self.parameter_value_id is not None:
                errors["assessment_set"] = (
                    "Definition audit events cannot reference workspace assessment data."
                )
        elif self.scope == AuditScope.WORKSPACE:
            workspace_project_id = ProjectWorkspace.objects.filter(
                pk=self.workspace_id
            ).values_list("project_id", flat=True).first()
            if workspace_project_id != self.project_id:
                errors["workspace"] = "The workspace belongs to a different project."
            if self.definition_version_id is not None:
                errors["definition_version"] = (
                    "Workspace audit events cannot use definition scope."
                )
        _validate_related_project(
            project_id=self.project_id,
            related_model=AssessmentSet,
            related_id=self.assessment_set_id,
            field_name="assessment_set",
            errors=errors,
        )
        if self.assessment_set_id and self.workspace_id:
            _validate_related_workspace(
                workspace_id=self.workspace_id,
                related_model=AssessmentSet,
                related_id=self.assessment_set_id,
                field_name="assessment_set",
                errors=errors,
            )
        if self.parameter_value_id and self.workspace_id:
            _validate_related_workspace(
                workspace_id=self.workspace_id,
                related_model=ParameterValue,
                related_id=self.parameter_value_id,
                field_name="parameter_value",
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
