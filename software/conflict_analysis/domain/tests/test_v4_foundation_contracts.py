from __future__ import annotations

import hashlib
import io
import inspect
import json
import tempfile
import zipfile
from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Callable
from unittest import mock
from uuid import UUID, uuid4
from xml.sax.saxutils import escape as xml_escape

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib import admin as django_admin
from django.db.models.deletion import RestrictedError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from domain.enums import (
    ActorRoleType,
    ActorType,
    AnalyticalElementType,
    AssessmentTemporalStatus,
    AssessmentKind,
    AuditAction,
    AssessmentRecordStatus,
    ConfidenceLevel,
    ChatChannelType,
    ChatMessageStatus,
    DocumentVersionStatus,
    EvidenceTemporalStatus,
    ExperimentStatus,
    ExperimentType,
    FactDirectness,
    FactOrigin,
    FactType,
    HelpApplicationScope,
    PowerDimension,
    SourceIndependenceStatus,
    AnchorStatus,
    AssessmentEvidenceRole,
    ParameterValueType,
    PublicationStatus,
    TargetType,
    TerminologyMappingStatus,
    ValueStatus,
    Visibility,
)
from domain.models import (
    Actor,
    ActorElementAssessment,
    ActorElementRole,
    AnalyticalElement,
    AssessmentSet,
    AssessmentEvidence,
    AuditEvent,
    ChatCitation,
    ChatConversation,
    ChatMessage,
    CalculationStrategyDefinition,
    DataGap,
    Document,
    DocumentContent,
    DocumentVersion,
    Experiment,
    ExpertProfile,
    Fact,
    FactEvidence,
    ParameterDefinition,
    ParameterValue,
    ParameterValueEvidence,
    PowerComponent,
    PowerComponentEvidence,
    PowerProfile,
    Project,
    ProjectDefinitionVersion,
    ProjectWorkspace,
    Scenario,
    ScenarioOverride,
    Source,
    TextFragment,
    TimeSlice,
    HelpTopic,
    ImportRun,
    LegacyCompatibilityReceipt,
    LegacyTermMapping,
    TerminologyEntry,
    UIHelpBinding,
)
from domain.services.foundation_packages import (
    ENTITY_SECTIONS,
    FOUNDATION_PACKAGE_FORMAT,
    FOUNDATION_PACKAGE_VERSION,
    FoundationPackageConflictError,
    FoundationPackageValidationError,
    attempt_foundation_import,
    canonical_json,
    commit_foundation_package,
    export_foundation_package,
    inspect_foundation_package,
    preview_foundation_package,
    register_foundation_adapter,
    seal_foundation_package,
    validate_foundation_package,
)
from domain.policies import (
    freeze_experiment,
    publish_project_definition,
    record_foundation_audit,
    validate_project_definition,
)


MATRIX_GROUPS = {
    "W": 5,
    "O": 5,
    "D": 5,
    "T": 5,
    "E": 6,
    "A": 5,
    "S": 7,
    "P": 4,
    "R": 5,
    "I": 8,
    "V": 4,
    "M": 5,
}
ALL_MATRIX_REQUIREMENTS = frozenset(
    f"FND-{group}{index:02d}"
    for group, count in MATRIX_GROUPS.items()
    for index in range(1, count + 1)
)
FIXTURE_FAMILIES = frozenset(
    {
        "ZHANAOZEN_V4_TRACE_FIXTURE_001",
        "V4_UNKNOWN_NOT_ZERO_FIXTURE_001",
        "V4_TEMPORAL_CUTOFF_FIXTURE_001",
        "V4_SOURCE_INDEPENDENCE_FIXTURE_001",
        "V4_DOCUMENTVERSION_ANCHOR_FIXTURE_001",
        "V4_STRENGTH_CONFIDENCE_FIXTURE_001",
        "V4_ATOMIC_IMPORT_NO_OVERWRITE_FIXTURE_001",
    }
)


def covers(*requirement_ids: str) -> Callable:
    """Attach executable acceptance-matrix traceability to a semantic test."""

    unknown = set(requirement_ids) - ALL_MATRIX_REQUIREMENTS
    if unknown:
        raise AssertionError(f"Unknown acceptance requirement IDs: {sorted(unknown)}")

    def decorator(function: Callable) -> Callable:
        function.acceptance_requirements = frozenset(requirement_ids)
        return function

    return decorator


def exercises_fixtures(*fixture_ids: str) -> Callable:
    unknown = set(fixture_ids) - FIXTURE_FAMILIES
    if unknown:
        raise AssertionError(f"Unknown fixture families: {sorted(unknown)}")

    def decorator(function: Callable) -> Callable:
        function.fixture_families = frozenset(fixture_ids)
        return function

    return decorator


def materializes_fixtures(*fixture_ids: str) -> Callable:
    """Mark tests that create accepted fixture rows/behaviors, not just trace IDs."""

    traced = exercises_fixtures(*fixture_ids)

    def decorator(function: Callable) -> Callable:
        function = traced(function)
        function.materialized_fixture_families = frozenset(fixture_ids)
        return function

    return decorator


def clean_save(instance):
    instance.full_clean()
    instance.save()
    return instance


def manifest_hash(manifest: dict) -> str:
    payload = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def minimal_foundation_package(
    workspace: ProjectWorkspace,
    *,
    compatibility_receipts: list[dict] | None = None,
) -> dict:
    package = {
        "format": FOUNDATION_PACKAGE_FORMAT,
        "format_version": FOUNDATION_PACKAGE_VERSION,
        "package_id": "IMPORT-FIX-001",
        "schema_version": "2.0.0",
        "template_version": "fixture-template-1",
        "method_version": "OPEN_METHOD",
        "ontology_version": "4.0.0",
        "dataset_version": "fixture-dataset-1",
        "workspace": {
            "id": str(workspace.id),
            "code": workspace.code,
            "version": workspace.version,
            "project_definition_version_id": str(workspace.definition_version_id),
            "project_definition_hash": workspace.definition_manifest_hash,
            "label": workspace.name,
            "metadata": {},
        },
        **{section: [] for section in ENTITY_SECTIONS},
        "compatibility_receipts": list(compatibility_receipts or []),
    }
    package["project_definition_versions"] = [
        {
            "id": str(workspace.definition_version_id),
            "code": workspace.definition_version.code,
            "version": workspace.definition_version.version,
            "metadata": {},
            "is_current": workspace.definition_version.is_current,
            "publication_status": workspace.definition_version.publication_status,
            "manifest": workspace.definition_version.manifest,
            "manifest_hash": workspace.definition_version.manifest_hash,
            "published_at": workspace.definition_version.published_at.isoformat().replace(
                "+00:00", "Z"
            ),
            "schema_version": workspace.definition_version.schema_version,
            "semantic_version": workspace.definition_version.semantic_version,
            "construct_version": workspace.definition_version.construct_version,
            "validated_at": (
                workspace.definition_version.validated_at.isoformat().replace(
                    "+00:00", "Z"
                )
                if workspace.definition_version.validated_at
                else None
            ),
            "validated_by": workspace.definition_version.validated_by,
            "validation_result": workspace.definition_version.validation_result,
            "published_by": workspace.definition_version.published_by,
            "supersedes_code": (
                workspace.definition_version.supersedes.code
                if workspace.definition_version.supersedes_id
                else None
            ),
        }
    ]
    return seal_foundation_package(package)


def assessment_import_package(workspace: ProjectWorkspace) -> dict:
    package = minimal_foundation_package(workspace)
    package["time_slices"] = [
        {
            "id": "34000000-0000-4000-8000-000000000001",
            "code": "TS-XLSX-001",
            "version": "1.0.0",
            "metadata": {},
            "name": "XLSX cutoff",
            "cutoff_date": "2022-01-02",
            "order": 0,
        }
    ]
    package["actors"] = [
        {
            "id": "34000000-0000-4000-8000-000000000002",
            "code": "ACTOR-XLSX-001",
            "version": "4.0.0",
            "metadata": {},
            "parent_code": None,
            "actor_type": ActorType.GROUP,
            "label": "XLSX actor",
            "description": "Imported through technical headers.",
            "order": 0,
        }
    ]
    package["analytical_elements"] = [
        {
            "id": "34000000-0000-4000-8000-000000000003",
            "code": "ELEMENT-XLSX-001",
            "version": "4.0.0",
            "metadata": {},
            "parent_code": None,
            "element_type": AnalyticalElementType.CONFLICT_ISSUE,
            "label": "XLSX issue",
            "reference_statement": "The actor supports the issue.",
            "description": "Canonical analytical element.",
            "order": 0,
        }
    ]
    package["assessment_sets"] = [
        {
            "id": "34000000-0000-4000-8000-000000000004",
            "code": "SET-XLSX-HUMAN",
            "version": "1.0.0",
            "metadata": {},
            "kind": AssessmentKind.HUMAN,
            "name": "XLSX human coding",
            "description": "Independent coder lane.",
            "independent": True,
        }
    ]
    package["expert_profiles"] = [
        {
            "id": "34000000-0000-4000-8000-000000000005",
            "code": "EXPERT-XLSX-001",
            "version": "1.0.0",
            "metadata": {},
            "kind": AssessmentKind.HUMAN,
            "display_name": "XLSX coder",
            "identity_key": "coder:xlsx:001",
            "provider": "",
            "model_name": "",
        }
    ]
    package["experiments"] = [
        {
            "id": "34000000-0000-4000-8000-000000000006",
            "code": "EXPERIMENT-XLSX-001",
            "version": "1.0.0",
            "metadata": {},
            "expert_profile_code": "EXPERT-XLSX-001",
            "assessment_set_code": "SET-XLSX-HUMAN",
            "experiment_type": ExperimentType.ASSESSMENT,
            "name": "XLSX experiment",
            "status": ExperimentStatus.DRAFT,
            "color": "#15803d",
            "order": 0,
            "method_version": "METHOD-1",
            "frozen_at": None,
        }
    ]
    package["actor_element_assessments"] = [
        {
            "id": "34000000-0000-4000-8000-000000000007",
            "code": "ASSESSMENT-XLSX-001",
            "version": "1.0.0",
            "metadata": {},
            "assessment_set_code": "SET-XLSX-HUMAN",
            "experiment_code": "EXPERIMENT-XLSX-001",
            "actor_code": "ACTOR-XLSX-001",
            "element_code": "ELEMENT-XLSX-001",
            "time_slice_code": "TS-XLSX-001",
            "supersedes_code": None,
            "reference_statement": "The actor supports the issue.",
            "reference_statement_incomplete": False,
            "status": AssessmentRecordStatus.PROVISIONAL,
            "confidence_level": ConfidenceLevel.MEDIUM,
            "knowledge_cutoff": "2022-01-02",
            "method_version": "METHOD-1",
            "provenance": {"transport": "xlsx"},
        }
    ]
    package["parameter_definitions"] = [
        {
            "id": "34000000-0000-4000-8000-000000000008",
            "code": "POS-XLSX",
            "version": "METHOD-1",
            "metadata": {},
            "name": "Position",
            "description": "Canonical position lane.",
            "target_type": TargetType.ACTOR_ELEMENT_ASSESSMENT,
            "value_type": ParameterValueType.INTEGER,
            "scale_min": -10,
            "scale_max": 10,
            "scale_metadata": {},
        },
        {
            "id": "34000000-0000-4000-8000-000000000010",
            "code": "SAL-XLSX",
            "version": "METHOD-1",
            "metadata": {},
            "name": "Salience",
            "description": "Independent salience lane.",
            "target_type": TargetType.ACTOR_ELEMENT_ASSESSMENT,
            "value_type": ParameterValueType.INTEGER,
            "scale_min": 0,
            "scale_max": 10,
            "scale_metadata": {},
        },
    ]
    package["parameter_values"] = [
        {
            "id": "34000000-0000-4000-8000-000000000009",
            "code": "VALUE-XLSX-UNKNOWN",
            "version": "1.0.0",
            "metadata": {},
            "assessment_code": "ASSESSMENT-XLSX-001",
            "assessment_set_code": "SET-XLSX-HUMAN",
            "parameter_definition_code": "POS-XLSX",
            "supersedes_code": None,
            "status": ValueStatus.UNKNOWN,
            "temporal_status": AssessmentTemporalStatus.NO_DIRECT_POSITION,
            "value": None,
            "note": "",
            "confidence": None,
            "range_min": None,
            "range_max": None,
            "rationale": "",
        },
        {
            "id": "34000000-0000-4000-8000-000000000011",
            "code": "VALUE-XLSX-SAL-8",
            "version": "1.0.0",
            "metadata": {},
            "assessment_code": "ASSESSMENT-XLSX-001",
            "assessment_set_code": "SET-XLSX-HUMAN",
            "parameter_definition_code": "SAL-XLSX",
            "supersedes_code": None,
            "status": ValueStatus.PROVISIONAL,
            "temporal_status": AssessmentTemporalStatus.CONTEMPORANEOUS,
            "value": 8,
            "note": "",
            "confidence": 50,
            "range_min": None,
            "range_max": None,
            "rationale": "SAL remains independent when POS is UNKNOWN.",
        },
    ]
    package["terminology_entries"] = [
        {
            "id": "34000000-0000-4000-8000-000000000012",
            "code": "TERM-POSITION-XLSX-001",
            "version": "4.0.0",
            "metadata": {},
            "canonical_ru_name": "Позиция актора",
            "canonical_ru_acronym": "ПОЗ",
            "exact_en_term": "Actor position",
            "exact_en_acronym": "POS",
            "source_framework": "Conflict Analysis Foundation",
            "source_citation": "OD-0016 terminology contract",
            "construct_version": "4.0.0",
            "locale": "ru-RU",
            "display_metadata": {"public": True},
        }
    ]
    package["legacy_term_mappings"] = [
        {
            "id": f"34000000-0000-4000-8000-00000000001{3 + index}",
            "code": f"LEGACY-POS-XLSX-0{index + 1}",
            "version": "4.0.0",
            "metadata": {},
            "terminology_entry_code": "TERM-POSITION-XLSX-001",
            "legacy_code": f"LEGACY-POS-XLSX-0{index + 1}",
            "legacy_label": alias,
            "source_version": "PR21",
            "mapping_status": TerminologyMappingStatus.RENAME_ONLY,
            "notes": "Hidden import/migration alias.",
        }
        for index, alias in enumerate(
            ("2026-ПТН-01-ГУ-08-УОС", "2026-ПТН-04-ГУ-08-УОС")
        )
    ]
    return seal_foundation_package(package)


def _fixture_uuid(index: int) -> str:
    return f"36000000-0000-4000-8000-{index:012d}"


def atomic_lane_package(workspace: ProjectWorkspace) -> dict:
    """Materialize comment 5389295741 without spreadsheet row-number identity."""

    package = minimal_foundation_package(workspace)
    package.update(
        package_id="IMPORT-FIX-001",
        template_version="V4-ATOMIC-IMPORT-NO-OVERWRITE-001",
        dataset_version="ATOMIC-FIXTURE-001",
        method_version="OPEN-METHOD",
    )
    package["workspace"]["metadata"] = {
        "fixture_workspace_id": "WS-FIX-ATOMIC-001"
    }
    package["time_slices"] = [
        {
            "id": "37000000-0000-4000-8000-000000000001",
            "code": "TS-FIX-2022-001",
            "version": "1.0.0",
            "metadata": {},
            "name": "Atomic fixture 2022",
            "cutoff_date": "2022-01-02",
            "order": 0,
        }
    ]
    package["actors"] = [
        {
            "id": "37000000-0000-4000-8000-000000000002",
            "code": "ACT-FIX-ATOMIC-001",
            "version": "4.0.0",
            "metadata": {},
            "parent_code": None,
            "actor_type": ActorType.GROUP,
            "label": "Atomic fixture actor",
            "description": "Shared subject for independent HUMAN and AI lanes.",
            "order": 0,
        }
    ]
    package["analytical_elements"] = [
        {
            "id": "37000000-0000-4000-8000-000000000003",
            "code": "CAE-FIX-ATOMIC-001",
            "version": "4.0.0",
            "metadata": {},
            "parent_code": None,
            "element_type": AnalyticalElementType.CONFLICT_ISSUE,
            "label": "Atomic fixture issue",
            "reference_statement": "The actor supports the fixture issue.",
            "description": "No calculation or consensus semantics.",
            "order": 0,
        }
    ]
    lane_specs = (
        (
            AssessmentKind.AI,
            "EXPERT-AI-FIX-001",
            "ASET-AI-FIX-001",
            "EXP-AI-FIX-001",
            "ASM-AI-FIX-001",
        ),
        (
            AssessmentKind.HUMAN,
            "EXPERT-HUMAN-FIX-001",
            "ASET-HUMAN-FIX-001",
            "EXP-HUMAN-FIX-001",
            "ASM-HUMAN-FIX-001",
        ),
    )
    for index, (kind, profile_code, set_code, experiment_code, assessment_code) in enumerate(lane_specs):
        package["assessment_sets"].append(
            {
                "id": f"37000000-0000-4000-8000-00000000001{index}",
                "code": set_code,
                "version": "1.0.0",
                "metadata": {},
                "kind": kind,
                "name": f"{kind} atomic fixture set",
                "description": "Independent source column lane.",
                "independent": True,
            }
        )
        package["expert_profiles"].append(
            {
                "id": f"37000000-0000-4000-8000-00000000002{index}",
                "code": profile_code,
                "version": "1.0.0",
                "metadata": {},
                "kind": kind,
                "display_name": f"{kind} atomic fixture expert",
                "identity_key": f"fixture:atomic:{kind.lower()}",
                "provider": "fixture-only" if kind == AssessmentKind.AI else "",
                "model_name": "captured-metadata-only" if kind == AssessmentKind.AI else "",
            }
        )
        package["experiments"].append(
            {
                "id": f"37000000-0000-4000-8000-00000000003{index}",
                "code": experiment_code,
                "version": "1.0.0",
                "metadata": {},
                "expert_profile_code": profile_code,
                "assessment_set_code": set_code,
                "experiment_type": ExperimentType.ASSESSMENT,
                "name": f"{kind} atomic fixture experiment",
                "status": ExperimentStatus.DRAFT,
                "color": "#4f46e5" if kind == AssessmentKind.AI else "#15803d",
                "order": index,
                "method_version": "OPEN-METHOD",
                "frozen_at": None,
            }
        )
        package["actor_element_assessments"].append(
            {
                "id": f"37000000-0000-4000-8000-00000000004{index}",
                "code": assessment_code,
                "version": "1.0.0",
                "metadata": {},
                "assessment_set_code": set_code,
                "experiment_code": experiment_code,
                "actor_code": "ACT-FIX-ATOMIC-001",
                "element_code": "CAE-FIX-ATOMIC-001",
                "time_slice_code": "TS-FIX-2022-001",
                "supersedes_code": None,
                "reference_statement": "The actor supports the fixture issue.",
                "reference_statement_incomplete": False,
                "status": AssessmentRecordStatus.PROVISIONAL,
                "confidence_level": ConfidenceLevel.MEDIUM,
                "knowledge_cutoff": "2022-01-02",
                "method_version": "OPEN-METHOD",
                "provenance": {
                    "selected_column": kind,
                    "fixture_id": "V4_ATOMIC_IMPORT_NO_OVERWRITE_FIXTURE_001",
                },
            }
        )
    package["parameter_definitions"] = [
        {
            "id": "37000000-0000-4000-8000-000000000050",
            "code": "PARAM-FIX-POS-001",
            "version": "OPEN-METHOD",
            "metadata": {},
            "name": "Position",
            "description": "Stable technical parameter identity.",
            "target_type": TargetType.ACTOR_ELEMENT_ASSESSMENT,
            "value_type": ParameterValueType.INTEGER,
            "scale_min": -10,
            "scale_max": 10,
            "scale_metadata": {},
        },
        {
            "id": "37000000-0000-4000-8000-000000000051",
            "code": "PARAM-FIX-SAL-001",
            "version": "OPEN-METHOD",
            "metadata": {},
            "name": "Salience",
            "description": "Stable technical parameter identity.",
            "target_type": TargetType.ACTOR_ELEMENT_ASSESSMENT,
            "value_type": ParameterValueType.INTEGER,
            "scale_min": 0,
            "scale_max": 10,
            "scale_metadata": {},
        },
    ]
    value_specs = (
        ("PV-AI-POS-FIX-001", "ASM-AI-FIX-001", "ASET-AI-FIX-001", "PARAM-FIX-POS-001", ValueStatus.PROVISIONAL, 7, AssessmentTemporalStatus.CONTEMPORANEOUS),
        ("PV-AI-SAL-FIX-001", "ASM-AI-FIX-001", "ASET-AI-FIX-001", "PARAM-FIX-SAL-001", ValueStatus.PROVISIONAL, 8, AssessmentTemporalStatus.CONTEMPORANEOUS),
        ("PV-HUMAN-POS-FIX-001", "ASM-HUMAN-FIX-001", "ASET-HUMAN-FIX-001", "PARAM-FIX-POS-001", ValueStatus.PROVISIONAL, 4, AssessmentTemporalStatus.CONTEMPORANEOUS),
        ("PV-HUMAN-SAL-FIX-001", "ASM-HUMAN-FIX-001", "ASET-HUMAN-FIX-001", "PARAM-FIX-SAL-001", ValueStatus.UNKNOWN, None, AssessmentTemporalStatus.UNKNOWN),
    )
    package["parameter_values"] = [
        {
            "id": f"37000000-0000-4000-8000-00000000006{index}",
            "code": code,
            "version": "1.0.0",
            "metadata": {},
            "assessment_code": assessment_code,
            "assessment_set_code": set_code,
            "parameter_definition_code": parameter_code,
            "supersedes_code": None,
            "status": status,
            "temporal_status": temporal_status,
            "value": value,
            "note": "",
            "confidence": None if value is None else 50,
            "range_min": None,
            "range_max": None,
            "rationale": "" if value is None else "Explicit source column value.",
        }
        for index, (
            code,
            assessment_code,
            set_code,
            parameter_code,
            status,
            value,
            temporal_status,
        ) in enumerate(value_specs)
    ]
    return seal_foundation_package(package)


def zhanaozen_trace_package(workspace: ProjectWorkspace) -> dict:
    """Materialize comment 5389217578 as canonical generic Foundation DTO rows."""

    package = minimal_foundation_package(workspace)
    package.update(
        package_id="ZHANAOZEN-V4-TRACE-FIXTURE-001",
        template_version="ZHANAOZEN-V4-TRACE-FIXTURE-001",
        method_version="OPEN-METHOD-PRE-FREEZE",
        dataset_version="ZHANAOZEN-2011-PILOT-001",
    )
    package["time_slices"] = [
        {
            "id": _fixture_uuid(1),
            "code": "TS-KZ-2011",
            "version": "1.0.0",
            "metadata": {},
            "name": "Zhanaozen 2011 cutoff",
            "cutoff_date": "2011-10-31",
            "order": 0,
        }
    ]
    package["actors"] = [
        {
            "id": _fixture_uuid(2),
            "code": "ACT-KZ-2011-OMG-STRIKERS",
            "version": "4.0.0",
            "metadata": {},
            "parent_code": None,
            "actor_type": ActorType.GROUP,
            "label": "striking OzenMunaiGaz workers / worker representatives",
            "description": "Historical actor identity from the accepted pilot fixture.",
            "order": 0,
        }
    ]
    package["analytical_elements"] = [
        {
            "id": _fixture_uuid(3),
            "code": "CAE-KZ-REMUNERATION-001",
            "version": "4.0.0",
            "metadata": {},
            "parent_code": None,
            "element_type": AnalyticalElementType.CONFLICT_ISSUE,
            "label": "remuneration / revision of collective agreement and pay scale",
            "reference_statement": "OzenMunaiGaz should revise the collective agreement/pay scale so that workers' remuneration increases.",
            "description": "Accepted pilot conflict issue.",
            "order": 0,
        }
    ]
    package["actor_element_roles"] = [
        {
            "id": _fixture_uuid(4),
            "code": "ROLE-KZ-2011-OMG-REMUNERATION-001",
            "version": "1.0.0",
            "metadata": {},
            "actor_code": "ACT-KZ-2011-OMG-STRIKERS",
            "element_code": "CAE-KZ-REMUNERATION-001",
            "role": ActorRoleType.PRIMARY,
            "note": "Historical assessment subject.",
        }
    ]
    package["assessment_sets"] = [
        {
            "id": _fixture_uuid(5),
            "code": "ASET-KZ-AI-PILOT-2011-001",
            "version": "1.0.0",
            "metadata": {},
            "kind": AssessmentKind.AI,
            "name": "Zhanaozen AI pilot 2011",
            "description": "Independent pre-method-freeze coding lane.",
            "independent": True,
        }
    ]
    package["expert_profiles"] = [
        {
            "id": _fixture_uuid(6),
            "code": "EXPERT-KZ-AI-PILOT-2011-001",
            "version": "1.0.0",
            "metadata": {},
            "kind": AssessmentKind.AI,
            "display_name": "Zhanaozen pilot AI coder",
            "identity_key": "fixture:zhanaozen:ai:2011",
            "provider": "fixture-only",
            "model_name": "captured-metadata-only",
        }
    ]
    package["experiments"] = [
        {
            "id": _fixture_uuid(7),
            "code": "EXP-KZ-AI-PILOT-2011-001",
            "version": "1.0.0",
            "metadata": {},
            "expert_profile_code": "EXPERT-KZ-AI-PILOT-2011-001",
            "assessment_set_code": "ASET-KZ-AI-PILOT-2011-001",
            "experiment_type": ExperimentType.ASSESSMENT,
            "name": "Zhanaozen pilot assessment experiment",
            "status": ExperimentStatus.DRAFT,
            "color": "#7c3aed",
            "order": 0,
            "method_version": "OPEN-METHOD-PRE-FREEZE",
            "frozen_at": None,
        }
    ]
    package["actor_element_assessments"] = [
        {
            "id": _fixture_uuid(8),
            "code": "ASM-KZ-2011-OMG-REMUNERATION-001",
            "version": "1.0.0",
            "metadata": {},
            "assessment_set_code": "ASET-KZ-AI-PILOT-2011-001",
            "experiment_code": "EXP-KZ-AI-PILOT-2011-001",
            "actor_code": "ACT-KZ-2011-OMG-STRIKERS",
            "element_code": "CAE-KZ-REMUNERATION-001",
            "time_slice_code": "TS-KZ-2011",
            "supersedes_code": None,
            "reference_statement": package["analytical_elements"][0]["reference_statement"],
            "reference_statement_incomplete": False,
            "status": AssessmentRecordStatus.PROVISIONAL_PRE_METHOD_FREEZE,
            "confidence_level": ConfidenceLevel.HIGH,
            "knowledge_cutoff": "2011-10-31",
            "method_version": "OPEN-METHOD-PRE-FREEZE",
            "provenance": {
                "fixture_id": "ZHANAOZEN_V4_TRACE_FIXTURE_001",
                "origin": "PILOT_CAPTURE",
            },
        }
    ]
    package["parameter_definitions"] = [
        {
            "id": _fixture_uuid(9),
            "code": "POS",
            "version": "OPEN-METHOD-PRE-FREEZE",
            "metadata": {},
            "name": "Position",
            "description": "Source value lane; no formula or aggregation.",
            "target_type": TargetType.ACTOR_ELEMENT_ASSESSMENT,
            "value_type": ParameterValueType.INTEGER,
            "scale_min": -10,
            "scale_max": 10,
            "scale_metadata": {},
        },
        {
            "id": _fixture_uuid(10),
            "code": "SAL",
            "version": "OPEN-METHOD-PRE-FREEZE",
            "metadata": {},
            "name": "Salience",
            "description": "Source value lane; no formula or aggregation.",
            "target_type": TargetType.ACTOR_ELEMENT_ASSESSMENT,
            "value_type": ParameterValueType.INTEGER,
            "scale_min": 0,
            "scale_max": 10,
            "scale_metadata": {},
        },
    ]
    package["parameter_values"] = [
        {
            "id": _fixture_uuid(11 + index),
            "code": code,
            "version": "1.0.0",
            "metadata": {},
            "assessment_code": "ASM-KZ-2011-OMG-REMUNERATION-001",
            "assessment_set_code": "ASET-KZ-AI-PILOT-2011-001",
            "parameter_definition_code": parameter,
            "supersedes_code": None,
            "status": ValueStatus.PROVISIONAL,
            "temporal_status": AssessmentTemporalStatus.CONTEMPORANEOUS,
            "value": value,
            "note": "",
            "confidence": None,
            "range_min": None,
            "range_max": None,
            "rationale": "Explicit pilot source value; no calculation invoked.",
        }
        for index, (code, parameter, value) in enumerate(
            (("PV-KZ-POS-001", "POS", 10), ("PV-KZ-SAL-001", "SAL", 9))
        )
    ]
    source_specs = (
        (
            "SRC-KZ-RFERL-001",
            "RFE/RL Kazakh Service",
            "DOC-KZ-RFERL-20110526",
            "DV-KZ-RFERL-20110526-WEB-001",
            "2011-05-26",
            "https://www.rferl.org/a/more_oil_workers_hunger_strike_kazakhstan/24206131.html",
            "FRG-KZ-RFERL-20110526-001",
            "431f482be21b10f98fa7ad02dea4ddeb27eef717624770518d1aad3f380d5066",
        ),
        (
            "SRC-KZ-OSW-001",
            "OSW Centre for Eastern Studies",
            "DOC-KZ-OSW-20110824",
            "DV-KZ-OSW-20110824-WEB-001",
            "2011-08-24",
            "https://www.osw.waw.pl/en/publikacje/analyses/2011-08-24/strikes-kazakhstan-are-growing",
            "FRG-KZ-OSW-20110824-001",
            "cc980df557ede5dfee85c4ffacbd17017fc06c9a08a1c8572998843d7fb7a7db",
        ),
        (
            "SRC-KZ-HRW-001",
            "Human Rights Watch",
            "DOC-KZ-HRW-20111031",
            "DV-KZ-HRW-20111031-WEB-001",
            "2011-10-31",
            "https://www.hrw.org/news/2011/10/31/kazakhstan-land-few-freedoms-i-discovered",
            "FRG-KZ-HRW-20111031-001",
            "7de226f2b906c150ee6b7b139536b37f54c32896ff6370c579ce467c6ae62ddc",
        ),
    )
    for index, (source_code, name, document_code, version_code, published_on, url, fragment_code, fragment_hash) in enumerate(source_specs):
        base = 20 + index * 5
        package["sources"].append(
            {
                "id": _fixture_uuid(base),
                "code": source_code,
                "version": "1.0.0",
                "metadata": {},
                "name": name,
                "publisher": name,
                "independence_group": source_code,
                "independence_status": SourceIndependenceStatus.INDEPENDENT,
                "homepage_url": url,
            }
        )
        package["documents"].append(
            {
                "id": _fixture_uuid(base + 1),
                "code": document_code,
                "version": "1.0.0",
                "metadata": {},
                "source_code": source_code,
                "title": f"{name} historical report",
                "canonical_url": url,
                "published_on": published_on,
                "accessed_on": "2026-08-24",
            }
        )
        package["document_versions"].append(
            {
                "id": _fixture_uuid(base + 2),
                "code": version_code,
                "version": "1.0.0",
                "metadata": {},
                "document_code": document_code,
                "supersedes_code": None,
                "status": DocumentVersionStatus.URL_CAPTURED_FULL_CONTENT_HASH_PENDING_INGEST,
                "capture_url": url,
                "captured_at": "2026-08-24T00:00:00Z",
                "checksum": None,
                "media_type": "text/html",
            }
        )
        package["text_fragments"].append(
            {
                "id": _fixture_uuid(base + 3),
                "code": fragment_code,
                "version": "1.0.0",
                "metadata": {},
                "document_version_code": version_code,
                "anchor_status": AnchorStatus.HASH_RECORDED_PENDING_INGEST,
                "start_offset": None,
                "end_offset": None,
                "selector": {},
                "page": "",
                "section": "",
                "exact_text": "",
                "exact_text_sha256": fragment_hash,
            }
        )
    package["gaps"] = [
        {
            "id": _fixture_uuid(39),
            "code": "GAP-DOCUMENTVERSION-BYTES-001",
            "version": "1.0.0",
            "metadata": {
                "affected_document_version_codes": [
                    item[3] for item in source_specs
                ]
            },
            "type": "FULL_DOCUMENT_BYTES_NOT_INGESTED",
            "document_version_code": None,
            "status": "OPEN",
            "required_behavior": "do not fabricate DocumentVersion checksum; preserve gap until immutable content is ingested",
            "resolution": "",
        }
    ]
    fact_specs = (
        (
            "FACT-KZ-2011-001",
            "On 26 May 2011 OzenMunaiGaz strikers explicitly demanded revision of the collective contract and pay scale.",
            "FRG-KZ-RFERL-20110526-001",
            "SUPPORTS_POSITION",
        ),
        (
            "FACT-KZ-2011-002",
            "Higher wages were identified as the basic demand that initially caused the strike; union-recognition demands coexisted with it.",
            "FRG-KZ-OSW-20110824-001",
            "SUPPORTS_POSITION_AND_SALIENCE",
        ),
        (
            "FACT-KZ-2011-003",
            "By the cutoff, hundreds of workers had sustained labor protest for months around higher wages, collective-agreement revision and union autonomy.",
            "FRG-KZ-HRW-20111031-001",
            "SUPPORTS_SALIENCE",
        ),
    )
    for index, (fact_code, statement, fragment_code, role) in enumerate(fact_specs):
        package["facts"].append(
            {
                "id": _fixture_uuid(50 + index),
                "code": fact_code,
                "version": "1.0.0",
                "metadata": {"fixture_id": "ZHANAOZEN_V4_TRACE_FIXTURE_001"},
                "experiment_code": "EXP-KZ-AI-PILOT-2011-001",
                "fact_type": FactType.ACTOR_CLAIM,
                "statement": statement,
                "origin": FactOrigin.DOCUMENT_DERIVED,
                "directness": FactDirectness.DIRECT,
                "visibility": Visibility.EXPERIMENT_PRIVATE,
                "status": AssessmentRecordStatus.PROVISIONAL_PRE_METHOD_FREEZE,
                "confidence": None,
                "temporal_status": EvidenceTemporalStatus.CONTEMPORANEOUS,
                "coder_identifier": "fixture:zhanaozen:ai:2011",
            }
        )
        package["fact_evidence_links"].append(
            {
                "id": _fixture_uuid(60 + index),
                "code": f"FEL-KZ-2011-00{index + 1}",
                "version": "1.0.0",
                "metadata": {},
                "fact_code": fact_code,
                "fragment_code": fragment_code,
                "relation": "SUPPORTS",
                "temporal_status": EvidenceTemporalStatus.CONTEMPORANEOUS,
                "learned_on": source_specs[index][4],
                "rationale": "Exact accepted pilot fixture link.",
            }
        )
        package["assessment_fact_links"].append(
            {
                "id": _fixture_uuid(70 + index),
                "code": f"AFL-KZ-2011-00{index + 1}",
                "version": "1.0.0",
                "metadata": {},
                "assessment_code": "ASM-KZ-2011-OMG-REMUNERATION-001",
                "fact_code": fact_code,
                "role": role,
                "temporal_status": EvidenceTemporalStatus.CONTEMPORANEOUS,
                "learned_on": source_specs[index][4],
                "rationale": "Accepted assessment evidence role.",
            }
        )
    for index, (value_code, fact_code, role) in enumerate(
        (
            ("PV-KZ-POS-001", "FACT-KZ-2011-001", "SUPPORTS_POSITION"),
            ("PV-KZ-POS-001", "FACT-KZ-2011-002", "SUPPORTS_POSITION"),
            ("PV-KZ-SAL-001", "FACT-KZ-2011-002", "SUPPORTS_SALIENCE"),
            ("PV-KZ-SAL-001", "FACT-KZ-2011-003", "SUPPORTS_SALIENCE"),
        )
    ):
        package["parameter_value_fact_links"].append(
            {
                "id": _fixture_uuid(80 + index),
                "code": f"PVFL-KZ-2011-00{index + 1}",
                "version": "1.0.0",
                "metadata": {},
                "parameter_value_code": value_code,
                "fact_code": fact_code,
                "role": role,
                "temporal_status": EvidenceTemporalStatus.CONTEMPORANEOUS,
                "learned_on": None,
                "rationale": "Direct trace from source value lane to accepted Fact.",
            }
        )
    return seal_foundation_package(package)


def project_package_to_selected_lane(
    package: dict,
    *,
    experiment_code: str,
    assessment_set_code: str,
    expert_profile_code: str,
) -> dict:
    """Project a canonical package to one explicit independent import lane."""

    projected = json.loads(json.dumps(package))
    projected["experiments"] = [
        item
        for item in projected["experiments"]
        if item["code"] == experiment_code
    ]
    projected["assessment_sets"] = [
        item
        for item in projected["assessment_sets"]
        if item["code"] == assessment_set_code
    ]
    projected["expert_profiles"] = [
        item
        for item in projected["expert_profiles"]
        if item["code"] == expert_profile_code
    ]
    projected["actor_element_assessments"] = [
        item
        for item in projected["actor_element_assessments"]
        if item["experiment_code"] == experiment_code
        and item["assessment_set_code"] == assessment_set_code
    ]
    assessment_codes = {
        item["code"] for item in projected["actor_element_assessments"]
    }
    projected["parameter_values"] = [
        item
        for item in projected["parameter_values"]
        if item["assessment_code"] in assessment_codes
        and item["assessment_set_code"] == assessment_set_code
    ]
    value_codes = {item["code"] for item in projected["parameter_values"]}
    projected["facts"] = [
        item
        for item in projected["facts"]
        if item["experiment_code"] in (None, experiment_code)
    ]
    fact_codes = {item["code"] for item in projected["facts"]}
    projected["fact_evidence_links"] = [
        item
        for item in projected["fact_evidence_links"]
        if item["fact_code"] in fact_codes
    ]
    projected["assessment_fact_links"] = [
        item
        for item in projected["assessment_fact_links"]
        if item["assessment_code"] in assessment_codes
        and item["fact_code"] in fact_codes
    ]
    projected["parameter_value_fact_links"] = [
        item
        for item in projected["parameter_value_fact_links"]
        if item["parameter_value_code"] in value_codes
        and item["fact_code"] in fact_codes
    ]
    projected["power_profiles"] = [
        item
        for item in projected["power_profiles"]
        if item["assessment_code"] in assessment_codes
    ]
    profile_codes = {item["code"] for item in projected["power_profiles"]}
    projected["power_components"] = [
        item
        for item in projected["power_components"]
        if item["profile_code"] in profile_codes
    ]
    component_codes = {item["code"] for item in projected["power_components"]}
    projected["power_component_fact_links"] = [
        item
        for item in projected["power_component_fact_links"]
        if item["component_code"] in component_codes
        and item["fact_code"] in fact_codes
    ]
    return projected


def _xlsx_column(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def _xlsx_cell_value(value) -> str:
    if isinstance(value, (dict, list)):
        return canonical_json(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else str(value)


def _xlsx_worksheet_xml(
    rows: list[list[object]],
    *,
    formula_reference: str | None = None,
) -> str:
    row_xml: list[str] = []
    for row_number, row in enumerate(rows, start=1):
        cells: list[str] = []
        for column_number, value in enumerate(row, start=1):
            if value is None:
                continue
            reference = f"{_xlsx_column(column_number)}{row_number}"
            if reference == formula_reference:
                cells.append(f'<c r="{reference}"><f>1+1</f><v>2</v></c>')
                continue
            escaped = xml_escape(_xlsx_cell_value(value))
            cells.append(
                f'<c r="{reference}" t="inlineStr"><is><t>{escaped}</t></is></c>'
            )
        row_xml.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(row_xml)}</sheetData></worksheet>'
    )


def foundation_xlsx_bytes(
    package: dict | None = None,
    *,
    technical_sheets: list[tuple[str, list[list[object]]]] | None = None,
    formula_sheet: str | None = None,
    formula_reference: str | None = None,
) -> bytes:
    if technical_sheets is None:
        if package is None:
            raise ValueError("A canonical package or explicit technical sheets are required.")
        meta_keys = (
            "format",
            "format_version",
            "package_id",
            "schema_version",
            "template_version",
            "method_version",
            "ontology_version",
            "dataset_version",
            "workspace",
        )
        sheets: list[tuple[str, list[list[object]]]] = [
            (
                "META",
                [["key", "value"], *[[key, package[key]] for key in meta_keys]],
            )
        ]
        for section in ENTITY_SECTIONS:
            items = package[section]
            if not items:
                continue
            headers = list(items[0])
            rows = [headers, *[[item.get(header) for header in headers] for item in items]]
            sheets.append((section.upper(), rows))
    else:
        sheets = technical_sheets

    workbook_sheets = "".join(
        f'<sheet name="{xml_escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, (name, _) in enumerate(sheets, start=1)
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{workbook_sheets}</sheets></workbook>"
    )
    relationships = "".join(
        '<Relationship '
        f'Id="rId{index}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, len(sheets) + 1)
    )
    workbook_relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{relationships}</Relationships>"
    )
    content_type_overrides = "".join(
        '<Override '
        f'PartName="/xl/worksheets/sheet{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, len(sheets) + 1)
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        f"{content_type_overrides}</Types>"
    )
    root_relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )

    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_relationships)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_relationships)
        for index, (name, rows) in enumerate(sheets, start=1):
            archive.writestr(
                f"xl/worksheets/sheet{index}.xml",
                _xlsx_worksheet_xml(
                    rows,
                    formula_reference=(
                        formula_reference if name == formula_sheet else None
                    ),
                ),
            )
    return output.getvalue()


PRE_FREEZE_META_FIELDS = (
    "package_id",
    "workbook_schema_version",
    "dataset_version",
    "case_id",
    "case_name",
    "coder_id",
    "coder_type",
    "assessment_set_id",
    "method_version",
    "ontology_version",
    "source_packet_hash",
    "cutoff_date",
    "created_at",
    "workbook_status",
)
PRE_FREEZE_ASSESSMENT_FIELDS = (
    "assessment_id",
    "assessment_set_id",
    "actor_id",
    "element_id",
    "time_slice_id",
    "assessment_status",
    "confidence",
    "reference_statement",
    "pos",
    "sal",
    "rationale",
)


def pre_freeze_workbook_bytes(
    *,
    meta: dict[str, object],
    assessment: dict[str, object] | None = None,
    assessments: list[dict[str, object]] | None = None,
    extra_sheets: list[tuple[str, list[list[object]]]] | None = None,
) -> bytes:
    """Build the accepted fixed META/ASSESSMENTS profile, never private DTO sheets."""

    rows = assessments if assessments is not None else [assessment or {}]
    return foundation_xlsx_bytes(
        technical_sheets=[
            (
                "META",
                [
                    ["key", "value"],
                    *[[field, meta[field]] for field in PRE_FREEZE_META_FIELDS],
                ],
            ),
            (
                "ASSESSMENTS",
                [
                    list(PRE_FREEZE_ASSESSMENT_FIELDS),
                    *[
                        [row.get(field) for field in PRE_FREEZE_ASSESSMENT_FIELDS]
                        for row in rows
                    ],
                ],
            ),
            *(extra_sheets or []),
        ]
    )


class FoundationFactoryMixin:
    project: Project
    definition: ProjectDefinitionVersion
    workspace: ProjectWorkspace

    def make_foundation(self, *, suffix: str = "A") -> ProjectWorkspace:
        self.project = clean_save(
            Project(code=f"PROJECT-{suffix}", version="1.0.0", name=f"Project {suffix}")
        )
        manifest = {"ontology_version": "4.0.0", "project": self.project.code}
        digest = manifest_hash(manifest)
        lifecycle_time = timezone.now()
        self.definition = clean_save(
            ProjectDefinitionVersion(
                project=self.project,
                code=f"DEF-{suffix}",
                version="4.0.0",
                publication_status=PublicationStatus.PUBLISHED,
                manifest=manifest,
                manifest_hash=digest,
                validated_at=lifecycle_time,
                validated_by="fixture:foundation-owner",
                validation_result={"valid": True, "fixture": True},
                published_at=lifecycle_time,
                published_by="fixture:foundation-owner",
                is_current=True,
            )
        )
        self.workspace = clean_save(
            ProjectWorkspace(
                project=self.project,
                definition_version=self.definition,
                definition_manifest_hash=digest,
                code=f"WORKSPACE-{suffix}",
                version="1.0.0",
                name=f"Workspace {suffix}",
                is_default=True,
            )
        )
        return self.workspace

    def make_workspace(self, *, code: str) -> ProjectWorkspace:
        return clean_save(
            ProjectWorkspace(
                project=self.project,
                definition_version=self.definition,
                definition_manifest_hash=self.definition.manifest_hash,
                code=code,
                version="1.0.0",
                name=code,
            )
        )


class WorkspaceAndOntologyContractTests(FoundationFactoryMixin, TestCase):
    def setUp(self):
        self.make_foundation()

    @covers("FND-W01", "FND-W02")
    def test_two_workspaces_pin_the_same_exact_immutable_definition(self):
        second = self.make_workspace(code="WORKSPACE-B")

        self.assertNotEqual(second.id, self.workspace.id)
        self.assertEqual(second.project_id, self.workspace.project_id)
        self.assertEqual(second.definition_version_id, self.definition.id)
        self.assertEqual(second.definition_manifest_hash, self.definition.manifest_hash)

        second.refresh_from_db()
        original_definition_id = second.definition_version_id
        next_manifest = {"ontology_version": "4.0.1", "project": self.project.code}
        lifecycle_time = timezone.now()
        successor = clean_save(
            ProjectDefinitionVersion(
                project=self.project,
                code="DEF-NEXT",
                version="4.0.1",
                publication_status=PublicationStatus.PUBLISHED,
                manifest=next_manifest,
                manifest_hash=manifest_hash(next_manifest),
                validated_at=lifecycle_time,
                validated_by="fixture:foundation-owner",
                validation_result={"valid": True, "fixture": True},
                published_at=lifecycle_time,
                published_by="fixture:foundation-owner",
                supersedes=self.definition,
            )
        )
        second.definition_version = successor
        second.definition_manifest_hash = successor.manifest_hash
        with self.assertRaises(ValidationError):
            second.full_clean()
        second.refresh_from_db()
        self.assertEqual(second.definition_version_id, original_definition_id)

    @covers("FND-W03", "FND-O05")
    def test_actor_and_element_hierarchies_reject_cycles_and_cross_workspace_links(self):
        other_workspace = self.make_workspace(code="WORKSPACE-B")
        parent = clean_save(
            Actor(
                workspace=self.workspace,
                code="ACTOR-PARENT",
                version="1.0.0",
                actor_type=ActorType.GROUP,
                label="Parent actor",
            )
        )
        child = clean_save(
            Actor(
                workspace=self.workspace,
                parent=parent,
                code="ACTOR-CHILD",
                version="1.0.0",
                actor_type=ActorType.GROUP,
                label="Child actor",
            )
        )
        parent.parent = child
        with self.assertRaises(ValidationError):
            parent.full_clean()

        foreign_element = clean_save(
            AnalyticalElement(
                workspace=other_workspace,
                code="ELEMENT-FOREIGN",
                version="1.0.0",
                element_type=AnalyticalElementType.CONFLICT_ISSUE,
                label="Foreign issue",
            )
        )
        invalid_role = ActorElementRole(
            workspace=self.workspace,
            actor=parent,
            element=foreign_element,
            role=ActorRoleType.PRIMARY,
            code="ROLE-CROSS-WORKSPACE",
            version="1.0.0",
        )
        with self.assertRaises(ValidationError):
            invalid_role.full_clean()

    @covers("FND-O01", "FND-O02", "FND-O05")
    def test_actor_identity_and_all_canonical_element_types_persist(self):
        actor_id = uuid4()
        actor = clean_save(
            Actor(
                id=actor_id,
                workspace=self.workspace,
                code="ACT-STABLE-001",
                version="4.0.0",
                actor_type=ActorType.ORGANIZATION,
                label="Stable actor",
            )
        )
        for order, element_type in enumerate(AnalyticalElementType.values):
            clean_save(
                AnalyticalElement(
                    workspace=self.workspace,
                    code=f"ELEMENT-{element_type}",
                    version="4.0.0",
                    element_type=element_type,
                    label=element_type.replace("_", " ").title(),
                    order=order,
                )
            )

        actor.refresh_from_db()
        self.assertEqual(actor.id, actor_id)
        self.assertIsInstance(actor.id, UUID)
        self.assertEqual(actor.code, "ACT-STABLE-001")
        self.assertEqual(
            set(
                AnalyticalElement.objects.filter(workspace=self.workspace).values_list(
                    "element_type", flat=True
                )
            ),
            set(AnalyticalElementType.values),
        )


class AssessmentAndStatusContractTests(FoundationFactoryMixin, TestCase):
    def setUp(self):
        self.make_foundation()
        self.time_slice = clean_save(
            TimeSlice(
                project=self.project,
                workspace=self.workspace,
                code="TS-2022",
                version="1.0.0",
                name="2022 cutoff",
                cutoff_date=date(2022, 1, 2),
            )
        )
        self.actor = clean_save(
            Actor(
                workspace=self.workspace,
                code="ACTOR-001",
                version="4.0.0",
                actor_type=ActorType.GROUP,
                label="Actor",
            )
        )
        self.element = clean_save(
            AnalyticalElement(
                workspace=self.workspace,
                code="ELEMENT-001",
                version="4.0.0",
                element_type=AnalyticalElementType.CONFLICT_ISSUE,
                label="Issue",
                reference_statement="The actor supports the issue.",
            )
        )
        self.pos_definition = clean_save(
            ParameterDefinition(
                project=self.project,
                code="POS",
                version="METHOD-1",
                name="Position",
                target_type=TargetType.ACTOR_ELEMENT_ASSESSMENT,
                value_type=ParameterValueType.INTEGER,
                scale_min=-10,
                scale_max=10,
            )
        )
        self.sal_definition = clean_save(
            ParameterDefinition(
                project=self.project,
                code="SAL",
                version="METHOD-1",
                name="Salience",
                target_type=TargetType.ACTOR_ELEMENT_ASSESSMENT,
                value_type=ParameterValueType.INTEGER,
                scale_min=0,
                scale_max=10,
            )
        )

    def make_lane(
        self,
        *,
        suffix: str,
        kind: str,
        assessment_status: str = AssessmentRecordStatus.PROVISIONAL,
        confidence_level: str = ConfidenceLevel.MEDIUM,
        reference_statement: str = "The actor supports the issue.",
        reference_statement_incomplete: bool = False,
    ) -> tuple[AssessmentSet, Experiment, ActorElementAssessment]:
        assessment_set = clean_save(
            AssessmentSet(
                project=self.project,
                workspace=self.workspace,
                code=f"SET-{suffix}",
                version="1.0.0",
                kind=kind,
                name=f"Set {suffix}",
            )
        )
        profile = clean_save(
            ExpertProfile(
                workspace=self.workspace,
                code=f"EXPERT-{suffix}",
                version="1.0.0",
                kind=kind,
                display_name=f"Expert {suffix}",
                identity_key=f"expert:{suffix}",
                model_name="test-model-v1" if kind == AssessmentKind.AI else "",
            )
        )
        experiment = clean_save(
            Experiment(
                workspace=self.workspace,
                expert_profile=profile,
                assessment_set=assessment_set,
                code=f"EXPERIMENT-{suffix}",
                version="1.0.0",
                name=f"Experiment {suffix}",
                experiment_type=ExperimentType.ASSESSMENT,
                status=ExperimentStatus.DRAFT,
                method_version="METHOD-1",
            )
        )
        assessment = clean_save(
            ActorElementAssessment(
                workspace=self.workspace,
                actor=self.actor,
                element=self.element,
                time_slice=self.time_slice,
                experiment=experiment,
                assessment_set=assessment_set,
                code=f"ASSESSMENT-{suffix}",
                version="1.0.0",
                reference_statement=reference_statement,
                reference_statement_incomplete=reference_statement_incomplete,
                status=assessment_status,
                confidence_level=confidence_level,
                knowledge_cutoff=self.time_slice.cutoff_date,
                method_version="METHOD-1",
            )
        )
        return assessment_set, experiment, assessment

    def make_value(
        self,
        *,
        suffix: str,
        assessment_set: AssessmentSet,
        assessment: ActorElementAssessment,
        definition: ParameterDefinition,
        status: str,
        value,
        confidence: Decimal | None,
        temporal_status: str = AssessmentTemporalStatus.UNKNOWN,
    ) -> ParameterValue:
        return clean_save(
            ParameterValue(
                project=self.project,
                workspace=self.workspace,
                time_slice=self.time_slice,
                assessment_set=assessment_set,
                actor_element_assessment=assessment,
                parameter_definition=definition,
                target_type=TargetType.ACTOR_ELEMENT_ASSESSMENT,
                target_id=assessment.id,
                code=f"VALUE-{suffix}",
                version="1.0.0",
                status=status,
                temporal_status=temporal_status,
                value=value,
                confidence=confidence,
                rationale="Explicit test coding." if value is not None else "",
            )
        )

    @covers("FND-A01", "FND-A02", "FND-A03", "FND-A04", "FND-A05", "FND-S05")
    @exercises_fixtures(
        "ZHANAOZEN_V4_TRACE_FIXTURE_001",
        "V4_UNKNOWN_NOT_ZERO_FIXTURE_001",
    )
    def test_human_ai_and_multiple_coders_remain_independent_without_consensus(self):
        human_set, _, human_assessment = self.make_lane(
            suffix="HUMAN-1",
            kind=AssessmentKind.HUMAN,
            assessment_status=AssessmentRecordStatus.DISPUTED,
        )
        ai_set, _, ai_assessment = self.make_lane(suffix="AI", kind=AssessmentKind.AI)
        second_human_set, _, second_human_assessment = self.make_lane(
            suffix="HUMAN-2",
            kind=AssessmentKind.HUMAN,
            assessment_status=AssessmentRecordStatus.DISPUTED,
        )
        unknown = self.make_value(
            suffix="HUMAN-UNKNOWN-POS",
            assessment_set=human_set,
            assessment=human_assessment,
            definition=self.pos_definition,
            status=ValueStatus.UNKNOWN,
            value=None,
            confidence=None,
            temporal_status=AssessmentTemporalStatus.NO_DIRECT_POSITION,
        )
        ai = self.make_value(
            suffix="AI-POS",
            assessment_set=ai_set,
            assessment=ai_assessment,
            definition=self.pos_definition,
            status=ValueStatus.PROVISIONAL,
            value=7,
            confidence=Decimal("25"),
        )
        second_human = self.make_value(
            suffix="HUMAN-2-POS",
            assessment_set=second_human_set,
            assessment=second_human_assessment,
            definition=self.pos_definition,
            status=ValueStatus.PROVISIONAL,
            value=-4,
            confidence=Decimal("50"),
        )

        unknown.refresh_from_db()
        self.assertIsNone(unknown.value)
        self.assertEqual(unknown.status, ValueStatus.UNKNOWN)
        self.assertEqual(
            unknown.temporal_status,
            AssessmentTemporalStatus.NO_DIRECT_POSITION,
        )
        self.assertEqual(ai.value, 7)
        self.assertEqual(second_human.value, -4)
        self.assertEqual(ParameterValue.objects.filter(workspace=self.workspace).count(), 3)
        self.assertFalse(
            AssessmentSet.objects.filter(
                workspace=self.workspace, kind=AssessmentKind.CONSENSUS
            ).exists()
        )

    @covers("FND-S01", "FND-S02", "FND-S03", "FND-S04")
    @exercises_fixtures("V4_UNKNOWN_NOT_ZERO_FIXTURE_001")
    def test_unknown_open_method_and_explicit_zero_have_distinct_semantics(self):
        assessment_set, _, assessment = self.make_lane(
            suffix="STATUS", kind=AssessmentKind.HUMAN
        )
        invalid_unknown = ParameterValue(
            project=self.project,
            workspace=self.workspace,
            time_slice=self.time_slice,
            assessment_set=assessment_set,
            actor_element_assessment=assessment,
            parameter_definition=self.pos_definition,
            target_type=TargetType.ACTOR_ELEMENT_ASSESSMENT,
            target_id=assessment.id,
            code="VALUE-INVALID-UNKNOWN",
            status=ValueStatus.UNKNOWN,
            temporal_status=AssessmentTemporalStatus.NO_DIRECT_POSITION,
            value=0,
        )
        with self.assertRaises(ValidationError):
            invalid_unknown.full_clean()

        invalid_direct_position = ParameterValue(
            project=self.project,
            workspace=self.workspace,
            time_slice=self.time_slice,
            assessment_set=assessment_set,
            actor_element_assessment=assessment,
            parameter_definition=self.pos_definition,
            target_type=TargetType.ACTOR_ELEMENT_ASSESSMENT,
            target_id=assessment.id,
            code="VALUE-INVALID-DIRECT-POSITION",
            status=ValueStatus.PROVISIONAL,
            temporal_status=AssessmentTemporalStatus.NO_DIRECT_POSITION,
            value=4,
            confidence=Decimal("50"),
            rationale="Numeric position cannot claim NO_DIRECT_POSITION.",
        )
        with self.assertRaises(ValidationError):
            invalid_direct_position.full_clean()

        neutral = self.make_value(
            suffix="EXPLICIT-NEUTRAL",
            assessment_set=assessment_set,
            assessment=assessment,
            definition=self.pos_definition,
            status=ValueStatus.CONFIRMED,
            value=0,
            confidence=Decimal("50"),
        )
        no_salience = self.make_value(
            suffix="EXPLICIT-NO-SALIENCE",
            assessment_set=assessment_set,
            assessment=assessment,
            definition=self.sal_definition,
            status=ValueStatus.CONFIRMED,
            value=0,
            confidence=Decimal("50"),
        )
        self.assertEqual(neutral.value, 0)
        self.assertEqual(no_salience.value, 0)

        open_method = ParameterValue(
            project=self.project,
            workspace=self.workspace,
            time_slice=self.time_slice,
            assessment_set=assessment_set,
            actor_element_assessment=assessment,
            parameter_definition=self.sal_definition,
            target_type=TargetType.ACTOR_ELEMENT_ASSESSMENT,
            target_id=assessment.id,
            code="VALUE-OPEN-METHOD",
            status=ValueStatus.OPEN_METHOD,
            value=1,
        )
        with self.assertRaises(ValidationError):
            open_method.full_clean()

    @covers("FND-S07", "FND-P01", "FND-P02", "FND-P03", "FND-P04")
    @materializes_fixtures("V4_STRENGTH_CONFIDENCE_FIXTURE_001")
    def test_pos_sal_method_reference_and_confidence_are_orthogonal(self):
        assessment_set, experiment, assessment = self.make_lane(
            suffix="STRENGTH",
            kind=AssessmentKind.HUMAN,
            confidence_level=ConfidenceLevel.LOW,
        )
        positive = self.make_value(
            suffix="POS-P10-LOW",
            assessment_set=assessment_set,
            assessment=assessment,
            definition=self.pos_definition,
            status=ValueStatus.PROVISIONAL,
            value=10,
            confidence=Decimal("25"),
        )
        salience = self.make_value(
            suffix="SAL-10-LOW",
            assessment_set=assessment_set,
            assessment=assessment,
            definition=self.sal_definition,
            status=ValueStatus.PROVISIONAL,
            value=10,
            confidence=Decimal("25"),
        )
        self.assertEqual(assessment.confidence_level, ConfidenceLevel.LOW)
        self.assertEqual(positive.confidence, Decimal("25"))
        self.assertEqual(salience.confidence, Decimal("25"))
        self.assertEqual(experiment.method_version, "METHOD-1")
        self.assertEqual(assessment.method_version, "METHOD-1")
        self.assertNotIn("probability", {field.name for field in ParameterValue._meta.fields})

        for value, definition in ((-11, self.pos_definition), (11, self.pos_definition), (-1, self.sal_definition), (11, self.sal_definition)):
            invalid = ParameterValue(
                project=self.project,
                workspace=self.workspace,
                time_slice=self.time_slice,
                assessment_set=assessment_set,
                actor_element_assessment=assessment,
                parameter_definition=definition,
                target_type=TargetType.ACTOR_ELEMENT_ASSESSMENT,
                target_id=assessment.id,
                code=f"INVALID-{definition.code}-{value}",
                status=ValueStatus.PROVISIONAL,
                value=value,
                confidence=Decimal("25"),
                rationale="Explicit invalid boundary probe.",
            )
            with self.assertRaises(ValidationError):
                invalid.full_clean()

        incomplete_set, _, incomplete_assessment = self.make_lane(
            suffix="INCOMPLETE",
            kind=AssessmentKind.HUMAN,
            reference_statement="",
            reference_statement_incomplete=True,
        )
        incomplete = self.make_value(
            suffix="INCOMPLETE-POS",
            assessment_set=incomplete_set,
            assessment=incomplete_assessment,
            definition=self.pos_definition,
            status=ValueStatus.PROVISIONAL,
            value=-10,
            confidence=Decimal("50"),
        )
        self.assertTrue(incomplete.actor_element_assessment.reference_statement_incomplete)

        warning_workspace = self.make_workspace(code="WORKSPACE-STRENGTH-PREVIEW")
        warning_package = assessment_import_package(warning_workspace)
        warning_value = next(
            row
            for row in warning_package["parameter_values"]
            if row["parameter_definition_code"] == "POS-XLSX"
        )
        warning_value.update(
            status=ValueStatus.PROVISIONAL,
            temporal_status=AssessmentTemporalStatus.CONTEMPORANEOUS,
            value=10,
            confidence=25,
            rationale="Explicit strong source value with no direct Fact link yet.",
        )
        warning_package = seal_foundation_package(warning_package)
        warning_preview = preview_foundation_package(
            warning_package,
            workspace=warning_workspace,
        )
        self.assertIn("STRONG_VALUE_LOW_EVIDENCE", warning_preview.warnings)
        preview_value = next(
            row
            for row in warning_preview.payload_copy()["parameter_values"]
            if row["code"] == "VALUE-XLSX-UNKNOWN"
        )
        self.assertEqual(
            (preview_value["value"], preview_value["confidence"]),
            (10, 25),
        )
        self.assertFalse(
            ParameterValue.objects.filter(
                workspace=warning_workspace,
                code="VALUE-XLSX-UNKNOWN",
            ).exists()
        )


class EvidenceChainContractTests(FoundationFactoryMixin, TestCase):
    def setUp(self):
        self.make_foundation()
        self.time_slice = clean_save(
            TimeSlice(
                project=self.project,
                workspace=self.workspace,
                code="TS-CUTOFF",
                version="1.0.0",
                name="Historical cutoff",
                cutoff_date=date(2022, 1, 2),
            )
        )
        self.actor = clean_save(
            Actor(
                workspace=self.workspace,
                code="ACT-EVIDENCE",
                version="4.0.0",
                actor_type=ActorType.GROUP,
                label="Evidence actor",
            )
        )
        self.element = clean_save(
            AnalyticalElement(
                workspace=self.workspace,
                code="ELEMENT-EVIDENCE",
                version="4.0.0",
                element_type=AnalyticalElementType.CONFLICT_ISSUE,
                label="Evidence issue",
                reference_statement="The actor supports the issue.",
            )
        )
        self.assessment_set = clean_save(
            AssessmentSet(
                project=self.project,
                workspace=self.workspace,
                code="SET-EVIDENCE",
                version="1.0.0",
                kind=AssessmentKind.HUMAN,
                name="Evidence set",
            )
        )
        profile = clean_save(
            ExpertProfile(
                workspace=self.workspace,
                code="EXPERT-EVIDENCE",
                version="1.0.0",
                kind=AssessmentKind.HUMAN,
                display_name="Evidence expert",
                identity_key="expert:evidence",
            )
        )
        self.experiment = clean_save(
            Experiment(
                workspace=self.workspace,
                expert_profile=profile,
                assessment_set=self.assessment_set,
                code="EXPERIMENT-EVIDENCE",
                version="1.0.0",
                name="Evidence experiment",
                experiment_type=ExperimentType.ASSESSMENT,
                method_version="METHOD-1",
            )
        )
        self.assessment = clean_save(
            ActorElementAssessment(
                workspace=self.workspace,
                actor=self.actor,
                element=self.element,
                time_slice=self.time_slice,
                experiment=self.experiment,
                assessment_set=self.assessment_set,
                code="ASSESSMENT-EVIDENCE",
                version="1.0.0",
                reference_statement="The actor supports the issue.",
                status=AssessmentRecordStatus.PROVISIONAL,
                confidence_level=ConfidenceLevel.LOW,
                knowledge_cutoff=self.time_slice.cutoff_date,
                method_version="METHOD-1",
            )
        )

    def make_source(
        self,
        *,
        suffix: str,
        source_group: str,
        independence_status: str = SourceIndependenceStatus.INDEPENDENT,
        workspace: ProjectWorkspace | None = None,
    ) -> Source:
        return clean_save(
            Source(
                workspace=workspace or self.workspace,
                code=f"SOURCE-{suffix}",
                version="1.0.0",
                name=f"Source {suffix}",
                publisher=f"Publisher {source_group}",
                independence_group=source_group,
                independence_status=independence_status,
                homepage_url=f"https://{suffix.lower()}.example.test",
            )
        )

    def make_document_chain(
        self,
        *,
        suffix: str,
        text: str,
        selected_text: str,
        publication_date: date | None,
        source: Source | None = None,
        workspace: ProjectWorkspace | None = None,
    ) -> tuple[Source, Document, DocumentVersion, DocumentContent, TextFragment]:
        target_workspace = workspace or self.workspace
        source = source or self.make_source(
            suffix=suffix,
            source_group=f"GROUP-{suffix}",
            workspace=target_workspace,
        )
        document = clean_save(
            Document(
                workspace=target_workspace,
                source=source,
                code=f"DOCUMENT-{suffix}",
                version="1.0.0",
                title=f"Document {suffix}",
                canonical_url=f"https://docs.example.test/{suffix.lower()}",
                publication_date=publication_date,
                accessed_on=date(2022, 1, 4),
            )
        )
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        version = clean_save(
            DocumentVersion(
                workspace=target_workspace,
                document=document,
                code=f"VERSION-{suffix}",
                version="1.0.0",
                status=DocumentVersionStatus.VERIFIED,
                capture_url=document.canonical_url,
                content_sha256=checksum,
                media_type="text/plain",
            )
        )
        content = clean_save(
            DocumentContent(
                workspace=target_workspace,
                document_version=version,
                code=f"CONTENT-{suffix}",
                version="1.0.0",
                normalized_text=text,
                encoding="utf-8",
                normalization_version="plain-text-v1",
                content_sha256=checksum,
            )
        )
        start = text.index(selected_text)
        end = start + len(selected_text)
        fragment = clean_save(
            TextFragment(
                workspace=target_workspace,
                document_version=version,
                code=f"FRAGMENT-{suffix}",
                version="1.0.0",
                anchor_status=AnchorStatus.EXACT,
                start_offset=start,
                end_offset=end,
                selector={"type": "TextPositionSelector", "start": start, "end": end},
                exact_text=selected_text,
                text_sha256=hashlib.sha256(selected_text.encode("utf-8")).hexdigest(),
            )
        )
        return source, document, version, content, fragment

    def make_fact(self, *, suffix: str, workspace: ProjectWorkspace | None = None) -> Fact:
        return clean_save(
            Fact(
                workspace=workspace or self.workspace,
                experiment=self.experiment if workspace in (None, self.workspace) else None,
                code=f"FACT-{suffix}",
                version="1.0.0",
                fact_type=FactType.OBSERVED_EVENT,
                statement=f"Atomic proposition {suffix}.",
                origin=FactOrigin.DOCUMENT_DERIVED,
                directness=FactDirectness.DIRECT,
                visibility=Visibility.WORKSPACE_SHARED,
                status=AssessmentRecordStatus.PROVISIONAL,
                confidence=Decimal("35"),
                temporal_status=EvidenceTemporalStatus.CONTEMPORANEOUS,
                coder_identifier="fixture:evidence-coder",
                metadata={"provenance_class": "DIRECT_DOCUMENT"},
            )
        )

    @covers(
        "FND-D01",
        "FND-E01",
        "FND-E02",
        "FND-E03",
        "FND-E04",
        "FND-V01",
    )
    @exercises_fixtures("ZHANAOZEN_V4_TRACE_FIXTURE_001")
    def test_full_assessment_fact_fragment_version_document_source_trace_is_exact(self):
        shared_source = self.make_source(suffix="SHARED", source_group="PUBLISHER-A")
        first = self.make_document_chain(
            suffix="TRACE-A",
            text="Prefix exact first fragment suffix.",
            selected_text="exact first fragment",
            publication_date=date(2022, 1, 1),
            source=shared_source,
        )
        second = self.make_document_chain(
            suffix="TRACE-B",
            text="Prefix exact second fragment suffix.",
            selected_text="exact second fragment",
            publication_date=date(2022, 1, 2),
            source=shared_source,
        )
        fact = self.make_fact(suffix="TRACE")
        clean_save(
            FactEvidence(
                workspace=self.workspace,
                fact=fact,
                fragment=first[-1],
                code="FACT-EVIDENCE-SUPPORT",
                version="1.0.0",
                relation="SUPPORTS",
                temporal_status=EvidenceTemporalStatus.CONTEMPORANEOUS,
            )
        )
        clean_save(
            FactEvidence(
                workspace=self.workspace,
                fact=fact,
                fragment=second[-1],
                code="FACT-EVIDENCE-REFUTE",
                version="1.0.0",
                relation="REFUTES",
                temporal_status=EvidenceTemporalStatus.CONTEMPORANEOUS,
            )
        )
        clean_save(
            AssessmentEvidence(
                workspace=self.workspace,
                assessment=self.assessment,
                fact=fact,
                code="ASSESSMENT-EVIDENCE-TRACE",
                version="1.0.0",
                role=AssessmentEvidenceRole.SUPPORTS_POSITION,
                temporal_status=EvidenceTemporalStatus.CONTEMPORANEOUS,
            )
        )

        self.assertEqual(shared_source.documents.count(), 2)
        paths = list(
            self.assessment.evidence_links.values_list(
                "fact__evidence_links__fragment__document_version__document__source__code",
                flat=True,
            )
        )
        self.assertEqual(paths, [shared_source.code, shared_source.code])
        identity = (
            str(self.workspace.id),
            str(self.workspace.definition_version_id),
            self.workspace.definition_manifest_hash,
            self.assessment.method_version,
            str(self.assessment.assessment_set_id),
            self.assessment.knowledge_cutoff.isoformat(),
            tuple(
                self.assessment.evidence_links.values_list(
                    "fact__evidence_links__fragment__document_version__content_sha256",
                    flat=True,
                )
            ),
        )
        self.assertEqual(identity[0], str(self.workspace.id))
        self.assertEqual(identity[2], self.definition.manifest_hash)
        self.assertEqual(len(identity[-1]), 2)
        self.assertEqual(fact.confidence, Decimal("35"))
        self.assertEqual(fact.temporal_status, EvidenceTemporalStatus.CONTEMPORANEOUS)
        self.assertEqual(fact.coder_identifier, "fixture:evidence-coder")

        for index, fact_type in enumerate(FactType.values):
            clean_save(
                Fact(
                    workspace=self.workspace,
                    code=f"FACT-TYPE-{index}",
                    version="1.0.0",
                    fact_type=fact_type,
                    statement=f"Typed proposition {index}.",
                    origin=FactOrigin.IMPORTED_COMMENT,
                    directness=FactDirectness.INDIRECT,
                    visibility=Visibility.WORKSPACE_SHARED,
                )
            )
        invalid_fact = Fact(
            workspace=self.workspace,
            code="FACT-UNTYPED",
            version="1.0.0",
            fact_type="FREE_TEXT",
            statement="Untyped proposition.",
            origin=FactOrigin.IMPORTED_COMMENT,
        )
        with self.assertRaises(ValidationError):
            invalid_fact.full_clean()

        for field, replacement in (("confidence", Decimal("101")), ("coder_identifier", "")):
            invalid_attribution = Fact(
                workspace=self.workspace,
                code=f"FACT-INVALID-{field.upper()}",
                version="1.0.0",
                fact_type=FactType.EXPERT_INTERPRETATION,
                statement="Explicitly attributed analytical inference.",
                origin=FactOrigin.HUMAN_EXPERT_ASSERTION,
                directness=FactDirectness.GROUP_INFERENCE,
                confidence=Decimal("30"),
                temporal_status=EvidenceTemporalStatus.RETROSPECTIVE_KNOWLEDGE,
                coder_identifier="analyst:fixture",
            )
            setattr(invalid_attribution, field, replacement)
            with self.assertRaises(ValidationError):
                invalid_attribution.full_clean()

    @covers("FND-D02", "FND-D03", "FND-D04", "FND-D05", "FND-V03")
    @materializes_fixtures("V4_DOCUMENTVERSION_ANCHOR_FIXTURE_001")
    def test_captured_version_is_immutable_and_changed_bytes_create_a_successor(self):
        source, document, original, _, _ = self.make_document_chain(
            suffix="IMMUTABLE",
            text="Original immutable bytes.",
            selected_text="immutable",
            publication_date=date(2022, 1, 1),
        )
        same_digest = hashlib.sha256(b"Original immutable bytes.").hexdigest()
        self.assertEqual(original.content_sha256, same_digest)
        original.metadata = {"hidden": "mutation"}
        with self.assertRaises(ValidationError):
            original.save()
        original.refresh_from_db()
        self.assertEqual(original.metadata, {})

        changed_text = "Changed immutable bytes."
        changed_digest = hashlib.sha256(changed_text.encode("utf-8")).hexdigest()
        successor = clean_save(
            DocumentVersion(
                workspace=self.workspace,
                document=document,
                code="VERSION-IMMUTABLE-NEXT",
                version="2.0.0",
                status=DocumentVersionStatus.VERIFIED,
                capture_url=document.canonical_url,
                content_sha256=changed_digest,
                media_type="text/plain",
                supersedes=original,
            )
        )
        clean_save(
            DocumentContent(
                workspace=self.workspace,
                document_version=successor,
                code="CONTENT-IMMUTABLE-NEXT",
                version="2.0.0",
                normalized_text=changed_text,
                encoding="utf-8",
                normalization_version="plain-text-v1",
                content_sha256=changed_digest,
            )
        )
        original.refresh_from_db()
        self.assertEqual(original.content_sha256, same_digest)
        self.assertNotEqual(successor.content_sha256, original.content_sha256)
        self.assertEqual(source.documents.count(), 1)
        self.assertEqual(document.versions.count(), 2)

    @covers("FND-T01", "FND-T02", "FND-T03", "FND-T04", "FND-T05")
    @exercises_fixtures("V4_DOCUMENTVERSION_ANCHOR_FIXTURE_001")
    def test_exact_anchor_passes_and_offset_hash_or_version_mutation_fails_closed(self):
        _, document, original, _, fragment = self.make_document_chain(
            suffix="ANCHOR",
            text="Alpha selected historical text omega.",
            selected_text="selected historical text",
            publication_date=date(2022, 1, 1),
        )
        self.assertEqual(fragment.anchor_status, AnchorStatus.EXACT)
        self.assertEqual(
            fragment.selector,
            {
                "type": "TextPositionSelector",
                "start": fragment.start_offset,
                "end": fragment.end_offset,
            },
        )

        bad_hash = TextFragment(
            workspace=self.workspace,
            document_version=original,
            code="FRAGMENT-BAD-HASH",
            version="1.0.0",
            anchor_status=AnchorStatus.EXACT,
            start_offset=fragment.start_offset,
            end_offset=fragment.end_offset,
            selector=fragment.selector,
            exact_text=fragment.exact_text,
            text_sha256="0" * 64,
        )
        with self.assertRaises(ValidationError):
            bad_hash.full_clean()

        changed_text = "Alpha selected hXstorical text omega."
        changed_digest = hashlib.sha256(changed_text.encode("utf-8")).hexdigest()
        changed_version = clean_save(
            DocumentVersion(
                workspace=self.workspace,
                document=document,
                code="VERSION-ANCHOR-CHANGED",
                version="2.0.0",
                status=DocumentVersionStatus.VERIFIED,
                content_sha256=changed_digest,
                media_type="text/plain",
                supersedes=original,
            )
        )
        clean_save(
            DocumentContent(
                workspace=self.workspace,
                document_version=changed_version,
                code="CONTENT-ANCHOR-CHANGED",
                version="2.0.0",
                normalized_text=changed_text,
                encoding="utf-8",
                normalization_version="plain-text-v1",
                content_sha256=changed_digest,
            )
        )
        wrong_version = TextFragment(
            workspace=self.workspace,
            document_version=changed_version,
            code="FRAGMENT-WRONG-VERSION",
            version="1.0.0",
            anchor_status=AnchorStatus.EXACT,
            start_offset=fragment.start_offset,
            end_offset=fragment.end_offset,
            selector={**fragment.selector, "page": 1, "section": "body"},
            exact_text=fragment.exact_text,
            text_sha256=fragment.text_sha256,
        )
        before = TextFragment.objects.count()
        with self.assertRaises(ValidationError):
            wrong_version.full_clean()
        self.assertEqual(TextFragment.objects.count(), before)

    @covers("FND-W03", "FND-E05")
    @exercises_fixtures(
        "ZHANAOZEN_V4_TRACE_FIXTURE_001",
        "V4_SOURCE_INDEPENDENCE_FIXTURE_001",
        "V4_DOCUMENTVERSION_ANCHOR_FIXTURE_001",
    )
    def test_cross_workspace_fact_fragment_and_assessment_links_are_rejected_atomically(self):
        other_workspace = self.make_workspace(code="WORKSPACE-B")
        _, _, _, _, foreign_fragment = self.make_document_chain(
            suffix="FOREIGN",
            text="Foreign exact fragment.",
            selected_text="exact fragment",
            publication_date=date(2022, 1, 1),
            workspace=other_workspace,
        )
        local_fact = self.make_fact(suffix="LOCAL")
        before = (FactEvidence.objects.count(), AssessmentEvidence.objects.count())
        invalid_fragment_link = FactEvidence(
            workspace=self.workspace,
            fact=local_fact,
            fragment=foreign_fragment,
            code="FACT-EVIDENCE-CROSS",
            version="1.0.0",
            relation="SUPPORTS",
        )
        with self.assertRaises(ValidationError):
            invalid_fragment_link.full_clean()

        foreign_fact = self.make_fact(suffix="FOREIGN", workspace=other_workspace)
        invalid_assessment_link = AssessmentEvidence(
            workspace=self.workspace,
            assessment=self.assessment,
            fact=foreign_fact,
            code="ASSESSMENT-EVIDENCE-CROSS",
            version="1.0.0",
            role=AssessmentEvidenceRole.SUPPORTS_POSITION,
        )
        with self.assertRaises(ValidationError):
            invalid_assessment_link.full_clean()
        self.assertEqual(
            (FactEvidence.objects.count(), AssessmentEvidence.objects.count()), before
        )

    @covers("FND-W03", "FND-E05", "FND-E06")
    def test_fact_evidence_bulk_create_validates_every_workspace_before_inserting_any_row(self):
        other_workspace = self.make_workspace(code="WORKSPACE-BULK-FOREIGN")
        *_, local_fragment = self.make_document_chain(
            suffix="BULK-LOCAL",
            text="Local exact bulk fragment.",
            selected_text="exact bulk fragment",
            publication_date=date(2022, 1, 1),
        )
        *_, foreign_fragment = self.make_document_chain(
            suffix="BULK-FOREIGN",
            text="Foreign exact bulk fragment.",
            selected_text="exact bulk fragment",
            publication_date=date(2022, 1, 1),
            workspace=other_workspace,
        )
        fact = self.make_fact(suffix="BULK-CREATE")
        valid = FactEvidence(
            workspace=self.workspace,
            fact=fact,
            fragment=local_fragment,
            code="FACT-EVIDENCE-BULK-VALID",
            version="1.0.0",
            relation="SUPPORTS",
            temporal_status=EvidenceTemporalStatus.CONTEMPORANEOUS,
        )
        invalid = FactEvidence(
            workspace=self.workspace,
            fact=fact,
            fragment=foreign_fragment,
            code="FACT-EVIDENCE-BULK-CROSS-WORKSPACE",
            version="1.0.0",
            relation="SUPPORTS",
            temporal_status=EvidenceTemporalStatus.CONTEMPORANEOUS,
        )
        with self.assertRaises(ValidationError):
            FactEvidence.objects.bulk_create([valid, invalid])
        self.assertFalse(FactEvidence.objects.exists())

        created = FactEvidence.objects.bulk_create([valid])
        self.assertEqual([item.pk for item in created], [valid.pk])
        self.assertEqual(
            FactEvidence.objects.values_list("code", flat=True).get(),
            "FACT-EVIDENCE-BULK-VALID",
        )

    @covers("FND-E06")
    def test_canonical_evidence_links_are_append_only(self):
        *_, fragment = self.make_document_chain(
            suffix="PROTECTED",
            text="Protected exact fragment.",
            selected_text="exact fragment",
            publication_date=date(2022, 1, 1),
        )
        fact = self.make_fact(suffix="PROTECTED")
        link = clean_save(
            FactEvidence(
                workspace=self.workspace,
                fact=fact,
                fragment=fragment,
                code="FACT-EVIDENCE-PROTECTED",
                version="1.0.0",
                relation="SUPPORTS",
                temporal_status=EvidenceTemporalStatus.CONTEMPORANEOUS,
            )
        )
        link.rationale = "Silent rewrite attempt"
        with self.assertRaises(ValidationError):
            link.save()
        with self.assertRaises(ValidationError):
            link.delete()

    @covers("FND-E06")
    @exercises_fixtures("V4_SOURCE_INDEPENDENCE_FIXTURE_001")
    def test_source_and_document_identity_cannot_be_relinked_or_reclassified(self):
        source, document, *_ = self.make_document_chain(
            suffix="SOURCE-IDENTITY",
            text="Captured source identity remains stable.",
            selected_text="source identity",
            publication_date=date(2022, 1, 1),
        )
        alternate = self.make_source(
            suffix="SOURCE-IDENTITY-ALTERNATE",
            source_group="INDEPENDENT-ALTERNATE-PUBLISHER",
        )

        document.source = alternate
        with self.assertRaises(ValidationError):
            document.save()
        document.refresh_from_db()
        self.assertEqual(document.source_id, source.id)

        source.publisher = "Silently rewritten publisher"
        source.independence_group = "SILENTLY-RECLASSIFIED-GROUP"
        with self.assertRaises(ValidationError):
            source.save()
        source.refresh_from_db()
        self.assertNotEqual(source.publisher, "Silently rewritten publisher")
        self.assertNotEqual(
            source.independence_group,
            "SILENTLY-RECLASSIFIED-GROUP",
        )

        with self.assertRaises(ValidationError):
            Source.objects.filter(pk=source.pk).update(
                independence_group="BULK-RECLASSIFICATION"
            )
        with self.assertRaises(ValidationError):
            Document.objects.filter(pk=document.pk).delete()
        with self.assertRaises(RestrictedError):
            self.workspace.delete()

    @covers("FND-S06", "FND-V03")
    @exercises_fixtures("V4_TEMPORAL_CUTOFF_FIXTURE_001")
    def test_time_slice_cutoff_version_and_metadata_are_append_only_provenance(self):
        original = (
            self.time_slice.cutoff_date,
            self.time_slice.version,
            dict(self.time_slice.metadata),
        )
        self.time_slice.cutoff_date = date(2022, 1, 3)
        self.time_slice.version = "2.0.0"
        self.time_slice.metadata = {"silent": "cutoff rewrite"}
        with self.assertRaises(ValidationError):
            self.time_slice.save()
        self.time_slice.refresh_from_db()
        self.assertEqual(
            (
                self.time_slice.cutoff_date,
                self.time_slice.version,
                self.time_slice.metadata,
            ),
            original,
        )
        with self.assertRaises(ValidationError):
            TimeSlice.objects.filter(pk=self.time_slice.pk).update(
                cutoff_date=date(2022, 1, 3)
            )
        with self.assertRaises(ValidationError):
            TimeSlice.objects.filter(pk=self.time_slice.pk).delete()

    @covers("FND-S06")
    @materializes_fixtures("V4_TEMPORAL_CUTOFF_FIXTURE_001")
    def test_post_cutoff_evidence_requires_explicit_retrospective_provenance(self):
        tengrinews = clean_save(
            Source(
                workspace=self.workspace,
                code="SRC-TCUT-TENGRINEWS-001",
                version="1.0.0",
                name="Tengrinews",
                publisher="Tengrinews",
                independence_group="PUBLISHER-TENGRINEWS",
                independence_status=SourceIndependenceStatus.INDEPENDENT,
                homepage_url="https://tengrinews.kz",
            )
        )
        contemporaneous_chains = (
            self.make_document_chain(
                suffix="TCUT-TENGRI-LPG-PROTEST",
                text="Zhanaozen protest over the LPG price increase.",
                selected_text="LPG price increase",
                publication_date=date(2022, 1, 2),
                source=tengrinews,
            ),
            self.make_document_chain(
                suffix="TCUT-TENGRI-AKIMAT-EXPLANATION",
                text="The akimat and energy ministry explained the LPG price increase.",
                selected_text="explained the LPG price increase",
                publication_date=date(2022, 1, 2),
                source=tengrinews,
            ),
        )
        for index, chain in enumerate(contemporaneous_chains, start=1):
            contemporary_fact = self.make_fact(suffix=f"TCUT-CONTEMP-{index}")
            clean_save(
                FactEvidence(
                    workspace=self.workspace,
                    fact=contemporary_fact,
                    fragment=chain[-1],
                    code=f"FACT-EVIDENCE-TCUT-CONTEMP-{index}",
                    version="1.0.0",
                    relation="SUPPORTS",
                    temporal_status=EvidenceTemporalStatus.CONTEMPORANEOUS,
                    learned_on=date(2022, 1, 2),
                )
            )

        rferl = clean_save(
            Source(
                workspace=self.workspace,
                code="SRC-TCUT-RFERL-20220103",
                version="1.0.0",
                name="RFE/RL",
                publisher="RFE/RL",
                independence_group="PUBLISHER-RFERL",
                independence_status=SourceIndependenceStatus.INDEPENDENT,
                homepage_url="https://www.rferl.org",
            )
        )
        *_, fragment = self.make_document_chain(
            suffix="TCUT-RFERL-20220103",
            text="Evidence published after cutoff.",
            selected_text="after cutoff",
            publication_date=date(2022, 1, 3),
            source=rferl,
        )
        unknown_publication = self.make_document_chain(
            suffix="TCUT-PUBLICATION-UNKNOWN",
            text="Publication date remains unverified.",
            selected_text="remains unverified",
            publication_date=None,
        )[1]
        self.assertIsNone(unknown_publication.publication_date)
        self.assertEqual(unknown_publication.accessed_on, date(2022, 1, 4))
        fact = self.make_fact(suffix="POST-CUTOFF")
        clean_save(
            FactEvidence(
                workspace=self.workspace,
                fact=fact,
                fragment=fragment,
                code="FACT-EVIDENCE-POST-CUTOFF",
                version="1.0.0",
                relation="SUPPORTS",
                temporal_status=EvidenceTemporalStatus.RETROSPECTIVE_CORROBORATION,
                learned_on=date(2022, 1, 3),
            )
        )
        invalid = AssessmentEvidence(
            workspace=self.workspace,
            assessment=self.assessment,
            fact=fact,
            code="ASSESSMENT-EVIDENCE-CONTEMPORANEOUS",
            version="1.0.0",
            role=AssessmentEvidenceRole.SUPPORTS_POSITION,
            temporal_status=EvidenceTemporalStatus.CONTEMPORANEOUS,
            learned_on=date(2022, 1, 3),
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()

        original_state = (
            self.assessment.status,
            self.assessment.confidence_level,
            self.assessment.reference_statement,
        )
        retrospective = clean_save(
            AssessmentEvidence(
                workspace=self.workspace,
                assessment=self.assessment,
                fact=fact,
                code="ASSESSMENT-EVIDENCE-RETROSPECTIVE",
                version="1.0.0",
                role=AssessmentEvidenceRole.SUPPORTS_POSITION,
                temporal_status=EvidenceTemporalStatus.RETROSPECTIVE_CORROBORATION,
                learned_on=date(2022, 1, 3),
            )
        )
        self.assessment.refresh_from_db()
        self.assertEqual(
            (
                self.assessment.status,
                self.assessment.confidence_level,
                self.assessment.reference_statement,
            ),
            original_state,
        )
        self.assertEqual(
            AssessmentEvidence.objects.filter(
                temporal_status=EvidenceTemporalStatus.RETROSPECTIVE_CORROBORATION
            ).count(),
            1,
        )
        self.assertEqual(
            FactEvidence.objects.filter(
                temporal_status=EvidenceTemporalStatus.CONTEMPORANEOUS
            ).count(),
            2,
        )
        self.assertEqual(
            retrospective.fact.evidence_links.first().fragment.document_version.document.publication_date,
            date(2022, 1, 3),
        )

    @materializes_fixtures("V4_SOURCE_INDEPENDENCE_FIXTURE_001")
    def test_source_independence_is_publisher_group_not_raw_url_count(self):
        first = self.make_source(suffix="MIRROR-A", source_group="ONE-PUBLISHER")
        second = self.make_source(suffix="MIRROR-B", source_group="ONE-PUBLISHER")
        third = self.make_source(suffix="INDEPENDENT", source_group="OTHER-PUBLISHER")
        unknown = self.make_source(
            suffix="UNVERIFIED",
            source_group="UNKNOWN-GROUP",
            independence_status=SourceIndependenceStatus.UNVERIFIED,
        )
        chains = {}
        for suffix, source in (("URL-A", first), ("URL-B", second), ("URL-C", third)):
            chains[suffix] = self.make_document_chain(
                suffix=suffix,
                text=f"Document from {suffix}.",
                selected_text=suffix,
                publication_date=date(2022, 1, 1),
                source=source,
            )
        self.assertEqual(Document.objects.filter(workspace=self.workspace).count(), 3)
        self.assertEqual(
            Source.objects.filter(code__in=[first.code, second.code])
            .values("independence_group")
            .distinct()
            .count(),
            1,
        )
        self.assertEqual(
            Source.objects.filter(code__in=[first.code, third.code])
            .values("independence_group")
            .distinct()
            .count(),
            2,
        )
        self.assertEqual(unknown.independence_status, SourceIndependenceStatus.UNVERIFIED)

        stable_fact = self.make_fact(suffix="SRCIND-STABLE")
        original_fact_id = stable_fact.id
        clean_save(
            FactEvidence(
                workspace=self.workspace,
                fact=stable_fact,
                fragment=chains["URL-A"][-1],
                code="FACT-EVIDENCE-SRCIND-OLD",
                version="1.0.0",
                relation="SUPPORTS",
                temporal_status=EvidenceTemporalStatus.CONTEMPORANEOUS,
            )
        )
        clean_save(
            FactEvidence(
                workspace=self.workspace,
                fact=stable_fact,
                fragment=chains["URL-C"][-1],
                code="FACT-EVIDENCE-SRCIND-INDEPENDENT",
                version="1.0.0",
                relation="SUPPORTS",
                temporal_status=EvidenceTemporalStatus.CONTEMPORANEOUS,
            )
        )
        audit = record_foundation_audit(
            workspace=self.workspace,
            action=AuditAction.UPDATE,
            actor_identifier="fixture:source-qa",
            entity_type="FACT_EVIDENCE_SET",
            entity_id=stable_fact.id,
            before={"source_group": first.independence_group},
            after={"source_group_added": third.independence_group},
        )
        stable_fact.refresh_from_db()
        self.assessment.refresh_from_db()
        self.assertEqual(stable_fact.id, original_fact_id)
        self.assertEqual(stable_fact.evidence_links.count(), 2)
        self.assertEqual(audit.before["source_group"], "ONE-PUBLISHER")
        self.assertEqual(self.assessment.status, AssessmentRecordStatus.PROVISIONAL)

    @exercises_fixtures(
        "ZHANAOZEN_V4_TRACE_FIXTURE_001",
        "V4_DOCUMENTVERSION_ANCHOR_FIXTURE_001",
    )
    def test_pending_document_bytes_are_an_explicit_gap_not_a_fabricated_checksum(self):
        source = self.make_source(suffix="URL-ONLY", source_group="URL-ONLY-GROUP")
        document = clean_save(
            Document(
                workspace=self.workspace,
                source=source,
                code="DOCUMENT-URL-ONLY",
                version="1.0.0",
                title="URL-only evidence",
                canonical_url="https://example.test/url-only",
            )
        )
        version = clean_save(
            DocumentVersion(
                workspace=self.workspace,
                document=document,
                code="VERSION-URL-ONLY",
                version="1.0.0",
                status=DocumentVersionStatus.URL_CAPTURED_FULL_CONTENT_HASH_PENDING_INGEST,
                capture_url=document.canonical_url,
                content_sha256="",
            )
        )
        gap = clean_save(
            DataGap(
                workspace=self.workspace,
                code="GAP-DOCUMENTVERSION-BYTES-001",
                version="1.0.0",
                gap_type="FULL_DOCUMENT_BYTES_NOT_INGESTED",
                entity_type="DOCUMENT_VERSION",
                entity_code=version.code,
                required_behavior="Do not fabricate a checksum before immutable content ingest.",
            )
        )
        self.assertEqual(version.content_sha256, "")
        self.assertFalse(gap.resolved)
        captured_text = "  Captured fragment text with preserved whitespace.\n"
        captured_hash = hashlib.sha256(captured_text.encode("utf-8")).hexdigest()
        pending_fragment = clean_save(
            TextFragment(
                workspace=self.workspace,
                document_version=version,
                code="FRAGMENT-PENDING-CAPTURED-TEXT",
                version="1.0.0",
                anchor_status=AnchorStatus.HASH_RECORDED_PENDING_INGEST,
                exact_text=captured_text,
                text_sha256=captured_hash,
            )
        )
        self.assertEqual(pending_fragment.exact_text, captured_text)
        self.assertEqual(pending_fragment.text_sha256, captured_hash)
        self.assertIsNone(pending_fragment.start_offset)
        self.assertIsNone(pending_fragment.end_offset)
        self.assertEqual(pending_fragment.selector, {})

        mismatched_fragment = TextFragment(
            workspace=self.workspace,
            document_version=version,
            code="FRAGMENT-PENDING-BAD-HASH",
            version="1.0.0",
            anchor_status=AnchorStatus.HASH_RECORDED_PENDING_INGEST,
            exact_text=captured_text,
            text_sha256="0" * 64,
        )
        with self.assertRaisesRegex(ValidationError, "checksum"):
            mismatched_fragment.full_clean()

        false_exact_anchor = TextFragment(
            workspace=self.workspace,
            document_version=version,
            code="FRAGMENT-PENDING-FALSE-OFFSETS",
            version="1.0.0",
            anchor_status=AnchorStatus.HASH_RECORDED_PENDING_INGEST,
            start_offset=0,
            end_offset=len(captured_text),
            selector={"type": "TextPositionSelector", "start": 0, "end": len(captured_text)},
            exact_text=captured_text,
            text_sha256=captured_hash,
        )
        with self.assertRaisesRegex(ValidationError, "not an exact document anchor"):
            false_exact_anchor.full_clean()

        invalid = DocumentVersion(
            workspace=self.workspace,
            document=document,
            code="VERSION-URL-FALSE-HASH",
            version="2.0.0",
            status=DocumentVersionStatus.URL_CAPTURED_FULL_CONTENT_HASH_PENDING_INGEST,
            capture_url=document.canonical_url,
            content_sha256=hashlib.sha256(b"fragment only").hexdigest(),
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()


class PowerVectorContractTests(FoundationFactoryMixin, TestCase):
    def setUp(self):
        self.make_foundation(suffix="POWER")
        time_slice = clean_save(
            TimeSlice(
                project=self.project,
                workspace=self.workspace,
                code="TS-POWER",
                version="1.0.0",
                cutoff_date=date(2022, 1, 2),
            )
        )
        actor = clean_save(
            Actor(
                workspace=self.workspace,
                code="ACTOR-POWER",
                version="4.0.0",
                actor_type=ActorType.ORGANIZATION,
                label="Power actor",
            )
        )
        element = clean_save(
            AnalyticalElement(
                workspace=self.workspace,
                code="ELEMENT-POWER",
                version="4.0.0",
                element_type=AnalyticalElementType.CONFLICT_ISSUE,
                label="Power issue",
            )
        )
        assessment_set = clean_save(
            AssessmentSet(
                project=self.project,
                workspace=self.workspace,
                code="SET-POWER",
                version="1.0.0",
                kind=AssessmentKind.HUMAN,
                name="Power set",
            )
        )
        profile = clean_save(
            ExpertProfile(
                workspace=self.workspace,
                code="EXPERT-POWER",
                version="1.0.0",
                kind=AssessmentKind.HUMAN,
                display_name="Power expert",
                identity_key="expert:power",
            )
        )
        experiment = clean_save(
            Experiment(
                workspace=self.workspace,
                expert_profile=profile,
                assessment_set=assessment_set,
                code="EXPERIMENT-POWER",
                version="1.0.0",
                name="Power experiment",
                experiment_type=ExperimentType.ASSESSMENT,
                method_version="METHOD-1",
            )
        )
        self.assessment = clean_save(
            ActorElementAssessment(
                workspace=self.workspace,
                actor=actor,
                element=element,
                time_slice=time_slice,
                experiment=experiment,
                assessment_set=assessment_set,
                code="ASSESSMENT-POWER",
                version="1.0.0",
                reference_statement="Explicit reference statement.",
                status=AssessmentRecordStatus.PROVISIONAL,
                confidence_level=ConfidenceLevel.LOW,
                knowledge_cutoff=time_slice.cutoff_date,
                method_version="METHOD-1",
            )
        )

    @covers("FND-R01", "FND-R02")
    def test_eight_power_components_round_trip_with_independent_status_and_provenance(self):
        profile = clean_save(
            PowerProfile(
                workspace=self.workspace,
                assessment=self.assessment,
                code="POWER-PROFILE",
                version="1.0.0",
                method_version="OPEN_METHOD",
            )
        )
        expected: dict[str, object | None] = {}
        for index, dimension in enumerate(PowerDimension.values):
            is_unknown = dimension == PowerDimension.EB
            component = clean_save(
                PowerComponent(
                    workspace=self.workspace,
                    profile=profile,
                    code=f"POWER-{dimension}",
                    version="1.0.0",
                    dimension=dimension,
                    status=ValueStatus.UNKNOWN if is_unknown else ValueStatus.PROVISIONAL,
                    value=None if is_unknown else index,
                    confidence=None if is_unknown else Decimal(str(10 + index)),
                    rationale="" if is_unknown else f"Independent rationale {dimension}.",
                    provenance={"fixture": dimension},
                )
            )
            expected[dimension] = component.value

        actual = dict(
            profile.components.order_by("dimension").values_list("dimension", "value")
        )
        self.assertEqual(set(actual), set(PowerDimension.values))
        self.assertEqual(actual, expected)
        unknown = profile.components.get(dimension=PowerDimension.EB)
        self.assertIsNone(unknown.value)
        self.assertIsNone(unknown.confidence)

        fact = clean_save(
            Fact(
                workspace=self.workspace,
                experiment=self.assessment.experiment,
                code="FACT-POWER",
                version="1.0.0",
                fact_type=FactType.EXPERT_INTERPRETATION,
                statement="Evidence for one vector component.",
                origin=FactOrigin.DOCUMENT_DERIVED,
                directness=FactDirectness.DIRECT,
                visibility=Visibility.WORKSPACE_SHARED,
            )
        )
        linked_component = profile.components.exclude(dimension=PowerDimension.EB).first()
        clean_save(
            PowerComponentEvidence(
                workspace=self.workspace,
                component=linked_component,
                fact=fact,
                code="POWER-EVIDENCE",
                version="1.0.0",
                role=AssessmentEvidenceRole.PRIMARY_SUPPORT,
            )
        )
        self.assertEqual(linked_component.evidence_links.get().fact_id, fact.id)

    @covers("FND-R03", "FND-R04", "FND-R05")
    @exercises_fixtures(
        "ZHANAOZEN_V4_TRACE_FIXTURE_001",
        "V4_STRENGTH_CONFIDENCE_FIXTURE_001",
    )
    def test_power_schema_has_no_scalar_mean_weight_or_salience_formula_path(self):
        field_names = {
            field.name
            for model in (PowerProfile, PowerComponent)
            for field in model._meta.get_fields()
        }
        forbidden = {
            "total_power",
            "pow",
            "scalar_power",
            "mean",
            "weight",
            "weights",
            "salience_weight",
        }
        self.assertTrue(field_names.isdisjoint(forbidden))
        public_methods = {
            name.lower()
            for model in (PowerProfile, PowerComponent)
            for name, member in inspect.getmembers(model)
            if callable(member) and not name.startswith("_")
        }
        self.assertFalse(
            any(
                token in method
                for method in public_methods
                for token in ("aggregate", "total_power", "weighted", "calculate_power")
            )
        )
        self.assertTrue(
            field_names.isdisjoint(
                {"constituency_size", "mobilization_capacity", "cs", "mc"}
            )
        )


class HelpAndChatContractTests(FoundationFactoryMixin, TestCase):
    def setUp(self):
        self.make_foundation(suffix="HELP")

    def test_help_topic_is_sanitized_versioned_and_bound_by_stable_locale_key(self):
        html = "<p>Exact safe help.</p>"
        topic = clean_save(
            HelpTopic(
                code="HELP-TOPIC-ROW",
                stable_key="foundation.actor.field",
                version="4.0.0",
                title="Actor field help",
                application_scope=HelpApplicationScope.SHARED,
                construct_version="4.0.0",
                term_version="4.0.0",
                locale="ru-RU",
                sanitized_html=html,
                content_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
                publication_status=PublicationStatus.PUBLISHED,
                published_at=timezone.now(),
            )
        )
        binding = clean_save(
            UIHelpBinding(
                workspace=self.workspace,
                code="HELP-BINDING-ROW",
                version="4.0.0",
                ui_key="player.actor.field",
                locale="ru-RU",
                help_topic=topic,
            )
        )
        resolved = UIHelpBinding.objects.get(
            workspace=self.workspace,
            ui_key="player.actor.field",
            locale="ru-RU",
            version="4.0.0",
        )
        self.assertEqual(resolved.help_topic_id, topic.id)
        self.assertEqual(binding.help_topic.version, "4.0.0")

        unsafe_html = '<p onclick="javascript:alert(1)">unsafe</p>'
        unsafe = HelpTopic(
            code="HELP-UNSAFE",
            stable_key="foundation.unsafe",
            version="1.0.0",
            title="Unsafe help",
            application_scope=HelpApplicationScope.SHARED,
            construct_version="4.0.0",
            term_version="4.0.0",
            locale="ru-RU",
            sanitized_html=unsafe_html,
            content_sha256=hashlib.sha256(unsafe_html.encode("utf-8")).hexdigest(),
        )
        with self.assertRaises(ValidationError):
            unsafe.full_clean()

        wrong_locale = UIHelpBinding(
            workspace=self.workspace,
            code="HELP-WRONG-LOCALE",
            version="4.0.0",
            ui_key="player.actor.other",
            locale="en",
            help_topic=topic,
        )
        with self.assertRaises(ValidationError):
            wrong_locale.full_clean()

    @covers("FND-O04")
    @exercises_fixtures("V4_UNKNOWN_NOT_ZERO_FIXTURE_001")
    def test_legacy_russian_aliases_are_hidden_crosswalks_not_import_identity(self):
        terminology = clean_save(
            TerminologyEntry(
                workspace=self.workspace,
                code="TERM-POSITION-001",
                version="4.0.0",
                canonical_ru_name="Позиция актора",
                canonical_ru_acronym="ПОЗ",
                exact_en_term="Actor position",
                exact_en_acronym="POS",
                source_framework="Conflict Analysis Foundation",
                source_citation="OD-0016 terminology contract",
                construct_version="4.0.0",
                locale="ru-RU",
                display_metadata={"public": True},
            )
        )
        aliases = (
            ("LEGACY-POS-ALIAS-01", "2026-ПТН-01-ГУ-08-УОС"),
            ("LEGACY-POS-ALIAS-04", "2026-ПТН-04-ГУ-08-УОС"),
        )
        for code, label in aliases:
            clean_save(
                LegacyTermMapping(
                    workspace=self.workspace,
                    terminology_entry=terminology,
                    code=code,
                    version="4.0.0",
                    legacy_code=code,
                    legacy_label=label,
                    source_version="PR21",
                    mapping_status=TerminologyMappingStatus.RENAME_ONLY,
                    notes="Hidden import/migration alias; never a current display label.",
                )
            )

        self.assertEqual(
            set(
                LegacyTermMapping.objects.filter(workspace=self.workspace).values_list(
                    "legacy_label", flat=True
                )
            ),
            {label for _, label in aliases},
        )
        self.assertFalse(
            TerminologyEntry.objects.filter(
                canonical_ru_name__in=[label for _, label in aliases]
            ).exists()
        )
        self.assertEqual(terminology.code, "TERM-POSITION-001")
        self.assertNotIn("2026-ПТН", terminology.display_metadata)

    def test_provider_neutral_chat_citations_are_exact_and_workspace_isolated(self):
        archived_at = timezone.now()
        conversation = clean_save(
            ChatConversation(
                workspace=self.workspace,
                code="CHAT-001",
                version="1.0.0",
                channel_type=ChatChannelType.PERSONAL,
                owner_identifier="analyst:owner",
                participants=["analyst:owner"],
                title="Stored conversation",
                provider="provider-neutral-metadata",
                model_name="model-version-only",
            )
        )
        shared_conversation = clean_save(
            ChatConversation(
                workspace=self.workspace,
                code="CHAT-PROJECT-SHARED-001",
                version="1.0.0",
                channel_type=ChatChannelType.PROJECT_SHARED,
                owner_identifier="analyst:owner",
                participants=["analyst:owner", "reviewer:second"],
                title="Archived project conversation",
                archived_at=archived_at,
            )
        )
        message = clean_save(
            ChatMessage(
                workspace=self.workspace,
                conversation=conversation,
                code="MESSAGE-001",
                version="1.0.0",
                sequence=1,
                role="ASSISTANT",
                content="Stored answer without a live call.",
                status=ChatMessageStatus.COMPLETE,
            )
        )
        failed_message = clean_save(
            ChatMessage(
                workspace=self.workspace,
                conversation=conversation,
                code="MESSAGE-ERROR-002",
                version="1.0.0",
                sequence=2,
                role="ASSISTANT",
                content="[provider error]",
                provider="provider-neutral-metadata",
                provider_request_id="request-failed-001",
                status=ChatMessageStatus.ERROR,
                error="Provider response was not persisted as a completed answer.",
            )
        )
        exact_text = "Stored cited proposition."
        document_text = f"Prefix {exact_text} Suffix"
        content_hash = hashlib.sha256(document_text.encode("utf-8")).hexdigest()
        source = clean_save(
            Source(
                workspace=self.workspace,
                code="SOURCE-CHAT-001",
                version="1.0.0",
                name="Chat citation publisher",
                publisher="Chat citation publisher",
                independence_group="CHAT-PUBLISHER-001",
                independence_status=SourceIndependenceStatus.INDEPENDENT,
                homepage_url="https://chat-source.example.test",
            )
        )
        document = clean_save(
            Document(
                workspace=self.workspace,
                source=source,
                code="DOCUMENT-CHAT-001",
                version="1.0.0",
                title="Captured chat citation",
                canonical_url="https://chat-source.example.test/document",
                publication_date=date(2022, 1, 1),
                accessed_on=date(2022, 1, 2),
            )
        )
        document_version = clean_save(
            DocumentVersion(
                workspace=self.workspace,
                document=document,
                code="DOCUMENT-VERSION-CHAT-001",
                version="1.0.0",
                status=DocumentVersionStatus.VERIFIED,
                capture_url=document.canonical_url,
                content_sha256=content_hash,
                media_type="text/plain",
            )
        )
        clean_save(
            DocumentContent(
                workspace=self.workspace,
                document_version=document_version,
                code="DOCUMENT-CONTENT-CHAT-001",
                version="1.0.0",
                normalized_text=document_text,
                encoding="utf-8",
                normalization_version="plain-text-v1",
                content_sha256=content_hash,
            )
        )
        fragment_start = document_text.index(exact_text)
        fragment = clean_save(
            TextFragment(
                workspace=self.workspace,
                document_version=document_version,
                code="FRAGMENT-CHAT-001",
                version="1.0.0",
                anchor_status=AnchorStatus.EXACT,
                start_offset=fragment_start,
                end_offset=fragment_start + len(exact_text),
                selector={
                    "type": "TextPositionSelector",
                    "start": fragment_start,
                    "end": fragment_start + len(exact_text),
                },
                exact_text=exact_text,
                text_sha256=hashlib.sha256(exact_text.encode("utf-8")).hexdigest(),
            )
        )
        fact = clean_save(
            Fact(
                workspace=self.workspace,
                code="FACT-CHAT",
                version="1.0.0",
                fact_type=FactType.OBSERVED_EVENT,
                statement="Stored cited proposition.",
                origin=FactOrigin.IMPORTED_COMMENT,
                directness=FactDirectness.DIRECT,
                visibility=Visibility.WORKSPACE_SHARED,
                confidence=Decimal("40"),
                temporal_status=EvidenceTemporalStatus.CONTEMPORANEOUS,
                coder_identifier="analyst:owner",
            )
        )
        clean_save(
            FactEvidence(
                workspace=self.workspace,
                fact=fact,
                fragment=fragment,
                code="FACT-EVIDENCE-CHAT-001",
                version="1.0.0",
                relation="SUPPORTS",
                temporal_status=EvidenceTemporalStatus.CONTEMPORANEOUS,
            )
        )
        fact_only_citation = clean_save(
            ChatCitation(
                workspace=self.workspace,
                message=message,
                fact=fact,
                code="CITATION-FACT-ONLY-001",
                version="1.0.0",
                label="Fact-only citation",
            )
        )
        fragment_only_citation = clean_save(
            ChatCitation(
                workspace=self.workspace,
                message=message,
                fragment=fragment,
                document_version=document_version,
                quote_start=0,
                quote_end=len(exact_text),
                quote_text=exact_text,
                code="CITATION-FRAGMENT-ONLY-001",
                version="1.0.0",
                label="Exact fragment citation",
            )
        )
        citation = clean_save(
            ChatCitation(
                workspace=self.workspace,
                message=message,
                fact=fact,
                fragment=fragment,
                document_version=document_version,
                quote_start=0,
                quote_end=len(exact_text),
                quote_text=exact_text,
                code="CITATION-001",
                version="1.0.0",
                label="Exact fact citation",
            )
        )
        self.assertEqual(citation.fact_id, fact.id)
        self.assertEqual(citation.fragment_id, fragment.id)
        self.assertEqual(citation.document_version_id, document_version.id)
        self.assertEqual(citation.quote_text, exact_text)
        self.assertEqual(citation.message.conversation_id, conversation.id)
        self.assertEqual(fact_only_citation.fact_id, fact.id)
        self.assertIsNone(fact_only_citation.fragment_id)
        self.assertEqual(fragment_only_citation.fragment_id, fragment.id)
        self.assertIsNone(fragment_only_citation.fact_id)
        self.assertEqual(conversation.channel_type, ChatChannelType.PERSONAL)
        self.assertEqual(shared_conversation.channel_type, ChatChannelType.PROJECT_SHARED)
        self.assertEqual(
            shared_conversation.participants,
            ["analyst:owner", "reviewer:second"],
        )
        self.assertEqual(shared_conversation.archived_at, archived_at)
        self.assertEqual((failed_message.status, bool(failed_message.error)), (ChatMessageStatus.ERROR, True))

        wrong_span = ChatCitation(
            workspace=self.workspace,
            message=message,
            fact=fact,
            fragment=fragment,
            document_version=document_version,
            quote_start=1,
            quote_end=len(exact_text),
            quote_text=exact_text,
            code="CITATION-WRONG-SPAN",
            version="1.0.0",
        )
        with self.assertRaises(ValidationError):
            wrong_span.full_clean()

        unlinked_fact = clean_save(
            Fact(
                workspace=self.workspace,
                code="FACT-CHAT-UNLINKED",
                version="1.0.0",
                fact_type=FactType.OBSERVED_EVENT,
                statement="A fact without an explicit link to the cited fragment.",
                origin=FactOrigin.IMPORTED_COMMENT,
                directness=FactDirectness.DIRECT,
                visibility=Visibility.WORKSPACE_SHARED,
            )
        )
        combined_without_evidence = ChatCitation(
            workspace=self.workspace,
            message=message,
            fact=unlinked_fact,
            fragment=fragment,
            document_version=document_version,
            quote_start=0,
            quote_end=len(exact_text),
            quote_text=exact_text,
            code="CITATION-COMBINED-WITHOUT-EVIDENCE",
            version="1.0.0",
        )
        with self.assertRaisesRegex(ValidationError, "FactEvidence"):
            combined_without_evidence.full_clean()

        other_workspace = self.make_workspace(code="WORKSPACE-CHAT-B")
        foreign_fact = clean_save(
            Fact(
                workspace=other_workspace,
                code="FACT-CHAT-FOREIGN",
                version="1.0.0",
                fact_type=FactType.OBSERVED_EVENT,
                statement="Foreign proposition.",
                origin=FactOrigin.IMPORTED_COMMENT,
                directness=FactDirectness.DIRECT,
                visibility=Visibility.WORKSPACE_SHARED,
            )
        )
        cross_workspace = ChatCitation(
            workspace=self.workspace,
            message=message,
            fact=foreign_fact,
            fragment=fragment,
            document_version=document_version,
            quote_start=0,
            quote_end=len(exact_text),
            quote_text=exact_text,
            code="CITATION-CROSS",
            version="1.0.0",
        )
        with self.assertRaises(ValidationError):
            cross_workspace.full_clean()


class ImportBoundaryContractTests(FoundationFactoryMixin, TestCase):
    def setUp(self):
        self.make_foundation(suffix="IMPORT")

    def make_pre_freeze_selected_lane(self, *, suffix: str) -> dict[str, object]:
        for code, minimum, maximum in (("POS", -10, 10), ("SAL", 0, 10)):
            clean_save(
                ParameterDefinition(
                    project=self.project,
                    code=code,
                    version="OPEN-METHOD-PRE-FREEZE",
                    name=code,
                    description="Exact PRE_FREEZE numeric lane.",
                    target_type=TargetType.ACTOR_ELEMENT_ASSESSMENT,
                    value_type=ParameterValueType.INTEGER,
                    scale_min=minimum,
                    scale_max=maximum,
                )
            )
        actor = clean_save(
            Actor(
                workspace=self.workspace,
                code=f"ACT-PRE-{suffix}",
                version="4.0.0",
                actor_type=ActorType.GROUP,
                label=f"PRE_FREEZE actor {suffix}",
            )
        )
        element = clean_save(
            AnalyticalElement(
                workspace=self.workspace,
                code=f"CAE-PRE-{suffix}",
                version="4.0.0",
                element_type=AnalyticalElementType.CONFLICT_ISSUE,
                label=f"PRE_FREEZE issue {suffix}",
                reference_statement=f"Exact PRE_FREEZE statement {suffix}.",
            )
        )
        time_slice = clean_save(
            TimeSlice(
                project=self.project,
                workspace=self.workspace,
                code=f"TS-PRE-{suffix}",
                version="1.0.0",
                name=f"PRE_FREEZE cutoff {suffix}",
                cutoff_date=date(2022, 1, 2),
            )
        )
        assessment_set = clean_save(
            AssessmentSet(
                project=self.project,
                workspace=self.workspace,
                code=f"ASET-PRE-{suffix}",
                version="1.0.0",
                kind=AssessmentKind.AI,
                name=f"PRE_FREEZE set {suffix}",
            )
        )
        profile = clean_save(
            ExpertProfile(
                workspace=self.workspace,
                code=f"EXPERT-PRE-{suffix}",
                version="1.0.0",
                kind=AssessmentKind.AI,
                display_name=f"PRE_FREEZE coder {suffix}",
                identity_key=f"fixture:pre-freeze:{suffix.lower()}",
                provider="fixture-only",
                model_name="captured-metadata-only",
            )
        )
        experiment = clean_save(
            Experiment(
                workspace=self.workspace,
                assessment_set=assessment_set,
                expert_profile=profile,
                code=f"EXP-PRE-{suffix}",
                version="1.0.0",
                experiment_type=ExperimentType.ASSESSMENT,
                name=f"PRE_FREEZE experiment {suffix}",
                method_version="OPEN-METHOD-PRE-FREEZE",
            )
        )
        return {
            "actor": actor,
            "element": element,
            "time_slice": time_slice,
            "assessment_set": assessment_set,
            "experiment": experiment,
        }

    @covers("FND-D01", "FND-E02", "FND-E04", "FND-I02", "FND-V04")
    @materializes_fixtures(
        "ZHANAOZEN_V4_TRACE_FIXTURE_001",
        "V4_DOCUMENTVERSION_ANCHOR_FIXTURE_001",
    )
    def test_materialized_zhanaozen_trace_fixture_imports_exact_graph_and_round_trips(self):
        package = zhanaozen_trace_package(self.workspace)
        altered = json.loads(json.dumps(package))
        altered["text_fragments"][0]["exact_text"] = "Unverified text claim."
        altered = seal_foundation_package(altered)

        with self.assertRaisesRegex(
            FoundationPackageValidationError,
            "does not match the captured fragment text",
        ):
            preview_foundation_package(altered, workspace=self.workspace)
        self.assertFalse(Actor.objects.exists())
        self.assertFalse(Fact.objects.exists())
        self.assertFalse(ImportRun.objects.exists())

        preview = preview_foundation_package(
            package,
            workspace=self.workspace,
            selected_input={
                "fixture_id": "ZHANAOZEN_V4_TRACE_FIXTURE_001",
                "assessment": "ASM-KZ-2011-OMG-REMUNERATION-001",
            },
        )
        self.assertEqual(preview.counts["assessment_sets"], 1)
        self.assertEqual(preview.counts["actor_element_assessments"], 1)
        self.assertEqual(preview.counts["sources"], 3)
        self.assertEqual(preview.counts["documents"], 3)
        self.assertEqual(preview.counts["document_versions"], 3)
        self.assertEqual(preview.counts["text_fragments"], 3)
        self.assertEqual(preview.counts["facts"], 3)
        self.assertEqual(preview.counts["assessment_fact_links"], 3)

        commit_foundation_package(
            preview,
            workspace=self.workspace,
            actor_identifier="fixture:zhanaozen:importer",
        )
        assessment = ActorElementAssessment.objects.get(
            code="ASM-KZ-2011-OMG-REMUNERATION-001"
        )
        actor = Actor.objects.get(code="ACT-KZ-2011-OMG-STRIKERS")
        self.assertEqual(str(actor.id), package["actors"][0]["id"])
        self.assertEqual(str(assessment.id), package["actor_element_assessments"][0]["id"])
        values = {
            value.parameter_definition.code: (value.status, value.value)
            for value in ParameterValue.objects.filter(
                actor_element_assessment=assessment
            ).select_related("parameter_definition")
        }
        self.assertEqual(values, {"POS": (ValueStatus.PROVISIONAL, 10), "SAL": (ValueStatus.PROVISIONAL, 9)})
        self.assertEqual(assessment.knowledge_cutoff, date(2011, 10, 31))
        self.assertEqual(assessment.confidence_level, ConfidenceLevel.HIGH)
        self.assertEqual(assessment.status, AssessmentRecordStatus.PROVISIONAL_PRE_METHOD_FREEZE)
        self.assertEqual(
            set(
                AssessmentEvidence.objects.filter(assessment=assessment).values_list(
                    "role", flat=True
                )
            ),
            {
                AssessmentEvidenceRole.SUPPORTS_POSITION,
                AssessmentEvidenceRole.SUPPORTS_POSITION_AND_SALIENCE,
                AssessmentEvidenceRole.SUPPORTS_SALIENCE,
            },
        )
        self.assertEqual(
            set(Source.objects.values_list("code", flat=True)),
            {"SRC-KZ-RFERL-001", "SRC-KZ-OSW-001", "SRC-KZ-HRW-001"},
        )
        self.assertEqual(
            set(DocumentVersion.objects.values_list("content_sha256", flat=True)),
            {""},
        )
        gap = DataGap.objects.get(code="GAP-DOCUMENTVERSION-BYTES-001")
        self.assertFalse(gap.resolved)
        self.assertEqual(
            gap.metadata["affected_document_version_codes"],
            [
                "DV-KZ-RFERL-20110526-WEB-001",
                "DV-KZ-OSW-20110824-WEB-001",
                "DV-KZ-HRW-20111031-WEB-001",
            ],
        )
        self.assertFalse(PowerProfile.objects.exists())

        pending_hash_overwrite = minimal_foundation_package(self.workspace)
        pending_hash_overwrite["sources"] = [
            {
                **package["sources"][0],
                "id": _fixture_uuid(90),
                "code": "SRC-PENDING-HASH-PROBE-001",
            }
        ]
        pending_hash_overwrite["documents"] = [
            {
                **package["documents"][0],
                "id": _fixture_uuid(91),
                "code": "DOC-PENDING-HASH-PROBE-001",
                "source_code": "SRC-PENDING-HASH-PROBE-001",
            }
        ]
        pending_hash_overwrite["document_versions"] = [
            {
                **package["document_versions"][0],
                "id": _fixture_uuid(92),
                "code": "DV-PENDING-HASH-PROBE-001",
                "document_code": "DOC-PENDING-HASH-PROBE-001",
            }
        ]
        pending_hash_overwrite["text_fragments"] = [
            {
                **package["text_fragments"][0],
                "document_version_code": "DV-PENDING-HASH-PROBE-001",
                "exact_text_sha256": "0" * 64,
            }
        ]
        pending_hash_overwrite["gaps"] = [
            {
                **package["gaps"][0],
                "id": _fixture_uuid(93),
                "code": "GAP-PENDING-HASH-PROBE-001",
                "metadata": {
                    "affected_document_version_codes": [
                        "DV-PENDING-HASH-PROBE-001"
                    ]
                },
            }
        ]
        pending_hash_overwrite = seal_foundation_package(pending_hash_overwrite)
        protected_counts = (
            Source.objects.count(),
            Document.objects.count(),
            DocumentVersion.objects.count(),
            TextFragment.objects.count(),
            ImportRun.objects.count(),
        )
        with self.assertRaisesRegex(
            FoundationPackageConflictError,
            "text_fragments stable UUID/code already exists; overwrite is forbidden",
        ):
            preview_foundation_package(
                pending_hash_overwrite,
                workspace=self.workspace,
                allow_nonempty=True,
            )
        self.assertEqual(
            (
                Source.objects.count(),
                Document.objects.count(),
                DocumentVersion.objects.count(),
                TextFragment.objects.count(),
                ImportRun.objects.count(),
            ),
            protected_counts,
        )

        exported = export_foundation_package(self.workspace)
        validate_foundation_package(exported)
        for section, identity_fields in {
            "sources": ("id", "code"),
            "documents": ("id", "code", "published_on"),
            "document_versions": ("id", "code", "checksum"),
            "text_fragments": ("id", "code", "exact_text_sha256"),
            "facts": ("id", "code", "statement"),
            "assessment_fact_links": ("id", "code", "role"),
            "parameter_values": ("id", "code", "status", "value"),
        }.items():
            expected_rows = sorted(
                tuple(row[field] for field in identity_fields)
                for row in package[section]
            )
            actual_rows = sorted(
                tuple(row[field] for field in identity_fields)
                for row in exported[section]
            )
            self.assertEqual(actual_rows, expected_rows, section)

        with self.assertRaises(FoundationPackageConflictError):
            preview_foundation_package(package, workspace=self.workspace)
        self.assertEqual(ActorElementAssessment.objects.count(), 1)
        self.assertEqual(Fact.objects.count(), 3)

    @covers("FND-D01", "FND-D03", "FND-T01", "FND-T02", "FND-T03")
    @materializes_fixtures("V4_DOCUMENTVERSION_ANCHOR_FIXTURE_001")
    def test_pending_ingest_fragment_preserves_exact_whitespace_and_hash_without_claiming_anchor(self):
        captured_text = "  Captured pending fragment — whitespace is evidence.\n"
        captured_hash = hashlib.sha256(captured_text.encode("utf-8")).hexdigest()
        package = minimal_foundation_package(self.workspace)
        package["sources"] = [
            {
                "id": "39000000-0000-4000-8000-000000000001",
                "code": "SOURCE-PENDING-TEXT-001",
                "version": "1.0.0",
                "metadata": {},
                "name": "Pending text source",
                "publisher": "Independent pending publisher",
                "independence_group": "PUBLISHER-PENDING-TEXT-001",
                "independence_status": SourceIndependenceStatus.INDEPENDENT,
                "homepage_url": "https://pending-text.example.test",
            }
        ]
        package["documents"] = [
            {
                "id": "39000000-0000-4000-8000-000000000002",
                "code": "DOCUMENT-PENDING-TEXT-001",
                "version": "1.0.0",
                "metadata": {},
                "source_code": "SOURCE-PENDING-TEXT-001",
                "title": "Pending immutable document bytes",
                "canonical_url": "https://pending-text.example.test/document",
                "published_on": "2022-01-01",
                "accessed_on": "2022-01-02",
            }
        ]
        package["document_versions"] = [
            {
                "id": "39000000-0000-4000-8000-000000000003",
                "code": "DOCUMENT-VERSION-PENDING-TEXT-001",
                "version": "1.0.0",
                "metadata": {},
                "document_code": "DOCUMENT-PENDING-TEXT-001",
                "supersedes_code": None,
                "status": DocumentVersionStatus.URL_CAPTURED_FULL_CONTENT_HASH_PENDING_INGEST,
                "capture_url": "https://pending-text.example.test/document",
                "captured_at": "2026-08-24T00:00:00Z",
                "checksum": None,
                "media_type": "text/html",
            }
        ]
        package["text_fragments"] = [
            {
                "id": "39000000-0000-4000-8000-000000000004",
                "code": "FRAGMENT-PENDING-TEXT-001",
                "version": "1.0.0",
                "metadata": {},
                "document_version_code": "DOCUMENT-VERSION-PENDING-TEXT-001",
                "anchor_status": AnchorStatus.HASH_RECORDED_PENDING_INGEST,
                "start_offset": None,
                "end_offset": None,
                "selector": {},
                "page": "",
                "section": "",
                "exact_text": captured_text,
                "exact_text_sha256": captured_hash,
            }
        ]
        package["gaps"] = [
            {
                "id": "39000000-0000-4000-8000-000000000005",
                "code": "GAP-PENDING-TEXT-001",
                "version": "1.0.0",
                "metadata": {
                    "affected_document_version_codes": [
                        "DOCUMENT-VERSION-PENDING-TEXT-001"
                    ]
                },
                "type": "FULL_DOCUMENT_BYTES_NOT_INGESTED",
                "document_version_code": "DOCUMENT-VERSION-PENDING-TEXT-001",
                "status": "OPEN",
                "required_behavior": "Preserve captured fragment text/hash without claiming an exact document anchor.",
                "resolution": "",
            }
        ]
        package = seal_foundation_package(package)

        mismatch = json.loads(json.dumps(package))
        mismatch["text_fragments"][0]["exact_text_sha256"] = "0" * 64
        mismatch = seal_foundation_package(mismatch)
        with self.assertRaisesRegex(
            FoundationPackageValidationError,
            "does not match the captured fragment text",
        ):
            preview_foundation_package(mismatch, workspace=self.workspace)
        self.assertFalse(TextFragment.objects.exists())

        false_anchor = json.loads(json.dumps(package))
        false_anchor["text_fragments"][0].update(
            start_offset=0,
            end_offset=len(captured_text),
            selector={
                "type": "TextPositionSelector",
                "start": 0,
                "end": len(captured_text),
            },
        )
        false_anchor = seal_foundation_package(false_anchor)
        with self.assertRaisesRegex(
            FoundationPackageValidationError,
            "cannot claim an exact anchor before ingest",
        ):
            preview_foundation_package(false_anchor, workspace=self.workspace)
        self.assertFalse(TextFragment.objects.exists())

        preview = preview_foundation_package(package, workspace=self.workspace)
        commit_foundation_package(
            preview,
            workspace=self.workspace,
            actor_identifier="fixture:pending-fragment-importer",
        )
        fragment = TextFragment.objects.get(code="FRAGMENT-PENDING-TEXT-001")
        self.assertEqual(fragment.anchor_status, AnchorStatus.HASH_RECORDED_PENDING_INGEST)
        self.assertEqual(fragment.exact_text, captured_text)
        self.assertEqual(fragment.text_sha256, captured_hash)
        self.assertIsNone(fragment.start_offset)
        self.assertIsNone(fragment.end_offset)
        self.assertEqual(fragment.selector, {})
        exported_fragment = export_foundation_package(self.workspace)["text_fragments"][0]
        self.assertEqual(exported_fragment["exact_text"], captured_text)
        self.assertEqual(exported_fragment["exact_text_sha256"], captured_hash)

    @covers("FND-E01", "FND-E02", "FND-E03", "FND-E04", "FND-I03")
    def test_confirmed_records_without_complete_exact_evidence_chain_fail_preview_atomically(self):
        assessment_package = assessment_import_package(self.workspace)
        assessment_package["actor_element_assessments"][0][
            "status"
        ] = AssessmentRecordStatus.CONFIRMED
        assessment_package = seal_foundation_package(assessment_package)
        with self.assertRaisesRegex(
            FoundationPackageValidationError,
            "CONFIRMED_EVIDENCE_CHAIN_INCOMPLETE:actor_element_assessments:ASSESSMENT-XLSX-001",
        ):
            preview_foundation_package(
                assessment_package,
                workspace=self.workspace,
            )

        value_package = assessment_import_package(self.workspace)
        salience = next(
            row
            for row in value_package["parameter_values"]
            if row["code"] == "VALUE-XLSX-SAL-8"
        )
        salience["status"] = ValueStatus.CONFIRMED
        value_package = seal_foundation_package(value_package)
        with self.assertRaisesRegex(
            FoundationPackageValidationError,
            "CONFIRMED_EVIDENCE_CHAIN_INCOMPLETE:parameter_values:VALUE-XLSX-SAL-8",
        ):
            preview_foundation_package(value_package, workspace=self.workspace)

        fact_package = assessment_import_package(self.workspace)
        fact_package["facts"] = [
            {
                "id": "39000000-0000-4000-8000-000000000006",
                "code": "FACT-CONFIRMED-WITHOUT-CHAIN-001",
                "version": "1.0.0",
                "metadata": {},
                "experiment_code": "EXPERIMENT-XLSX-001",
                "fact_type": FactType.EXPERT_INTERPRETATION,
                "statement": "A confirmed assertion cannot bypass the immutable evidence chain.",
                "origin": FactOrigin.HUMAN_EXPERT_ASSERTION,
                "directness": FactDirectness.GROUP_INFERENCE,
                "visibility": Visibility.EXPERIMENT_PRIVATE,
                "status": AssessmentRecordStatus.CONFIRMED,
                "confidence": 50,
                "temporal_status": EvidenceTemporalStatus.CONTEMPORANEOUS,
                "coder_identifier": "fixture:confirmed-chain-probe",
            }
        ]
        fact_package = seal_foundation_package(fact_package)
        with self.assertRaisesRegex(
            FoundationPackageValidationError,
            "CONFIRMED_EVIDENCE_CHAIN_INCOMPLETE:facts:FACT-CONFIRMED-WITHOUT-CHAIN-001",
        ):
            preview_foundation_package(fact_package, workspace=self.workspace)

        self.assertFalse(ActorElementAssessment.objects.exists())
        self.assertFalse(ParameterValue.objects.exists())
        self.assertFalse(Fact.objects.exists())
        self.assertFalse(ImportRun.objects.exists())

    @covers("FND-W04", "FND-I03", "FND-I08")
    def test_preview_is_immutable_non_mutating_workspace_scoped_and_adapter_neutral(self):
        package = minimal_foundation_package(self.workspace)
        original = json.loads(json.dumps(package))

        preview = preview_foundation_package(
            package,
            workspace=self.workspace,
            selected_input={"sheet": "Assessment"},
        )

        self.assertEqual(package, original)
        self.assertEqual(preview.payload_copy(), original)
        self.assertEqual(preview.selected_input["sheet"], "Assessment")
        self.assertFalse(ImportRun.objects.exists())
        with self.assertRaises(FrozenInstanceError):
            preview.checksum = "0" * 64
        with self.assertRaises(TypeError):
            preview.canonical_payload["dataset_version"] = "changed"

        adapter_name = f"xlsx-fixture-{uuid4().hex}"
        register_foundation_adapter(adapter_name, lambda raw: raw)
        xlsx_preview = preview_foundation_package(
            package,
            workspace=self.workspace,
            adapter=adapter_name,
            selected_input={"workbook": "fixture.xlsx", "sheet": "Assessment"},
        )
        self.assertEqual(xlsx_preview.checksum, preview.checksum)
        self.assertEqual(xlsx_preview.payload_copy(), preview.payload_copy())

        other_workspace = self.make_workspace(code="WORKSPACE-IMPORT-B")
        with self.assertRaises(FoundationPackageConflictError):
            preview_foundation_package(package, workspace=other_workspace)
        self.assertFalse(ImportRun.objects.exists())

    @covers("FND-I03", "FND-I04", "FND-I05", "FND-I06", "FND-I08")
    def test_structured_preview_reports_invalid_boundaries_and_valid_intended_changes_without_mutation(self):
        canonical = atomic_lane_package(self.workspace)
        invalid_cases: dict[str, tuple[dict, str, str]] = {}

        duplicate = json.loads(json.dumps(canonical))
        duplicate_definition = dict(duplicate["parameter_definitions"][0])
        duplicate_definition["id"] = "39000000-0000-4000-8000-000000000001"
        duplicate["parameter_definitions"].append(duplicate_definition)
        invalid_cases["duplicate"] = (
            seal_foundation_package(duplicate),
            "DUPLICATE_OR_CONFLICT",
            "duplicates",
        )

        stale_reference = json.loads(json.dumps(canonical))
        stale_reference["parameter_values"][0][
            "parameter_definition_code"
        ] = "PARAMETER-STALE-UUID-IDENTITY"
        invalid_cases["unknown_or_stale_reference"] = (
            seal_foundation_package(stale_reference),
            "UNKNOWN_REFERENCE",
            "unknown package-local stable code",
        )

        status_value = json.loads(json.dumps(canonical))
        status_value["parameter_values"][0]["status"] = ValueStatus.UNKNOWN
        status_value["parameter_values"][0]["value"] = 0
        status_value["parameter_values"][0]["confidence"] = None
        status_value["parameter_values"][0]["rationale"] = ""
        invalid_cases["unknown_is_not_zero"] = (
            seal_foundation_package(status_value),
            "STATUS_VALUE_INVALID",
            "must be null for status UNKNOWN",
        )

        cutoff = json.loads(json.dumps(zhanaozen_trace_package(self.workspace)))
        cutoff["documents"][0]["published_on"] = "2011-11-01"
        invalid_cases["post_cutoff_without_retrospective_provenance"] = (
            seal_foundation_package(cutoff),
            "FOUNDATION_IMPORT_INVALID",
            "post-cutoff evidence",
        )

        anchor = json.loads(json.dumps(zhanaozen_trace_package(self.workspace)))
        anchor["text_fragments"][0]["start_offset"] = 0
        invalid_cases["pending_fragment_claims_exact_anchor"] = (
            seal_foundation_package(anchor),
            "ANCHOR_VALIDATION_FAILED",
            "exact anchor before ingest",
        )

        cross_workspace = json.loads(json.dumps(canonical))
        cross_workspace["workspace"]["code"] = "WORKSPACE-FOREIGN-STALE"
        invalid_cases["cross_workspace"] = (
            seal_foundation_package(cross_workspace),
            "WORKSPACE_CONFLICT",
            "workspace code differs",
        )

        recoding = json.loads(json.dumps(canonical))
        recoding["parameter_values"][0][
            "parameter_definition_code"
        ] = "Позиция актора"
        invalid_cases["display_label_cannot_recode_import_identity"] = (
            seal_foundation_package(recoding),
            "UNKNOWN_REFERENCE",
            "parameter_definition_code",
        )

        before = {
            "actors": Actor.objects.count(),
            "assessments": ActorElementAssessment.objects.count(),
            "values": ParameterValue.objects.count(),
            "runs": ImportRun.objects.count(),
        }
        for name, (package, expected_code, message_fragment) in invalid_cases.items():
            with self.subTest(name=name):
                report = inspect_foundation_package(
                    package,
                    workspace=self.workspace,
                )
                self.assertFalse(report.valid)
                self.assertIsNone(report.preview)
                self.assertEqual(len(report.errors), 1)
                self.assertEqual(report.errors[0]["code"], expected_code)
                self.assertIn(message_fragment, report.errors[0]["message"])
                self.assertEqual(
                    {
                        "actors": Actor.objects.count(),
                        "assessments": ActorElementAssessment.objects.count(),
                        "values": ParameterValue.objects.count(),
                        "runs": ImportRun.objects.count(),
                    },
                    before,
                )

        stale_selection = inspect_foundation_package(
            minimal_foundation_package(self.workspace),
            workspace=self.workspace,
            selected_input={
                "target_experiment_id": "39000000-0000-4000-8000-000000000002",
                "target_assessment_set_id": "39000000-0000-4000-8000-000000000003",
            },
            allow_nonempty=True,
        )
        self.assertFalse(stale_selection.valid)
        self.assertIn("does not exist", stale_selection.errors[0]["message"])

        valid_report = inspect_foundation_package(
            canonical,
            workspace=self.workspace,
            selected_input={"transport_selection": "canonical-json-fixture"},
        )
        self.assertTrue(valid_report.valid)
        self.assertEqual(valid_report.errors, ())
        self.assertIsNotNone(valid_report.preview)
        self.assertEqual(
            valid_report.preview.selected_input["transport_selection"],
            "canonical-json-fixture",
        )
        self.assertIn(
            "ACT-FIX-ATOMIC-001",
            valid_report.preview.intended_changes["create"]["actors"],
        )
        self.assertEqual(
            {
                "actors": Actor.objects.count(),
                "assessments": ActorElementAssessment.objects.count(),
                "values": ParameterValue.objects.count(),
                "runs": ImportRun.objects.count(),
            },
            before,
        )

    @covers("FND-P01", "FND-P02", "FND-P03", "FND-P04", "FND-I02")
    def test_scalar_power_identifiers_are_rejected_as_numeric_lane_identity_at_preview(self):
        for forbidden_code in ("TOTAL_POWER", "POW", "SCALAR_POWER"):
            with self.subTest(code=forbidden_code):
                package = assessment_import_package(self.workspace)
                original_code = package["parameter_definitions"][0]["code"]
                package["parameter_definitions"][0]["code"] = forbidden_code
                for value in package["parameter_values"]:
                    if value["parameter_definition_code"] == original_code:
                        value["parameter_definition_code"] = forbidden_code
                package = seal_foundation_package(package)
                with self.assertRaisesRegex(
                    FoundationPackageValidationError,
                    "forbidden scalar/automatic Power numeric lane",
                ):
                    preview_foundation_package(package, workspace=self.workspace)
                self.assertFalse(ParameterDefinition.objects.exists())
                self.assertFalse(ParameterValue.objects.exists())
                self.assertFalse(ImportRun.objects.exists())

    @covers("FND-I01", "FND-I03", "FND-I08")
    @materializes_fixtures("V4_UNKNOWN_NOT_ZERO_FIXTURE_001")
    def test_real_xlsx_assessment_import_matches_json_dto_and_rejects_formula_cells(self):
        package = assessment_import_package(self.workspace)
        json_preview = preview_foundation_package(package, workspace=self.workspace)
        workbook_bytes = foundation_xlsx_bytes(package)
        formula_bytes = foundation_xlsx_bytes(
            package,
            formula_sheet="ACTORS",
            formula_reference="G2",
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            workbook_path = Path(temporary_directory) / "assessment-fixture.xlsx"
            formula_path = Path(temporary_directory) / "formula-fixture.xlsx"
            workbook_path.write_bytes(workbook_bytes)
            formula_path.write_bytes(formula_bytes)
            xlsx_preview = preview_foundation_package(
                workbook_path,
                workspace=self.workspace,
                adapter="xlsx",
                selected_input={"sheet": "ASSESSMENTS"},
            )
            with self.assertRaisesRegex(
                FoundationPackageValidationError,
                "Formula cells are forbidden",
            ):
                preview_foundation_package(
                    formula_path,
                    workspace=self.workspace,
                    adapter="xlsx",
                )

        self.assertEqual(xlsx_preview.checksum, json_preview.checksum)
        self.assertEqual(xlsx_preview.payload_copy(), json_preview.payload_copy())
        self.assertEqual(xlsx_preview.counts["actor_element_assessments"], 1)
        self.assertEqual(xlsx_preview.counts["parameter_values"], 2)
        self.assertEqual(xlsx_preview.selected_input["sheet"], "ASSESSMENTS")
        self.assertEqual(
            xlsx_preview.selected_input["input_sha256"],
            hashlib.sha256(workbook_bytes).hexdigest(),
        )
        self.assertFalse(ActorElementAssessment.objects.exists())
        self.assertFalse(ParameterValue.objects.exists())
        self.assertFalse(ImportRun.objects.exists())

        receipt = commit_foundation_package(
            xlsx_preview,
            workspace=self.workspace,
            actor_identifier="xlsx-coder",
        )
        assessment = ActorElementAssessment.objects.get(code="ASSESSMENT-XLSX-001")
        value = ParameterValue.objects.get(code="VALUE-XLSX-UNKNOWN")
        salience = ParameterValue.objects.get(code="VALUE-XLSX-SAL-8")
        run = ImportRun.objects.get(pk=receipt.id)
        self.assertEqual(
            assessment.experiment.experiment_type,
            ExperimentType.ASSESSMENT,
        )
        self.assertEqual(assessment.provenance, {"transport": "xlsx"})
        self.assertEqual(value.actor_element_assessment_id, assessment.id)
        self.assertEqual(
            (value.status, value.temporal_status, value.value),
            (
                ValueStatus.UNKNOWN,
                AssessmentTemporalStatus.NO_DIRECT_POSITION,
                None,
            ),
        )
        self.assertEqual(
            (salience.status, salience.value),
            (ValueStatus.PROVISIONAL, 8),
        )
        self.assertEqual(
            set(LegacyTermMapping.objects.values_list("legacy_label", flat=True)),
            {"2026-ПТН-01-ГУ-08-УОС", "2026-ПТН-04-ГУ-08-УОС"},
        )
        self.assertEqual(
            TerminologyEntry.objects.get().code,
            "TERM-POSITION-XLSX-001",
        )
        self.assertEqual(run.adapter, "xlsx")
        self.assertEqual(run.selected_input["input_name"], "assessment-fixture.xlsx")

    @covers("FND-I01", "FND-I02", "FND-I03", "FND-I04", "FND-I05", "FND-I06", "FND-I07")
    @materializes_fixtures("V4_ATOMIC_IMPORT_NO_OVERWRITE_FIXTURE_001")
    def test_pre_freeze_meta_assessments_profile_selects_exact_human_ai_lanes_atomically(self):
        master = atomic_lane_package(self.workspace)
        master["package_id"] = "PRE-FREEZE-MASTER-001"
        master["template_version"] = "V4-EXPERT-XLS-PRE-FREEZE-V1"
        master["actor_element_assessments"] = []
        master["parameter_values"] = []
        for definition, code in zip(master["parameter_definitions"], ("POS", "SAL")):
            definition["code"] = code
            definition["version"] = "OPEN-METHOD-PRE-FREEZE"
        master = seal_foundation_package(master)
        master_preview = preview_foundation_package(master, workspace=self.workspace)
        commit_foundation_package(
            master_preview,
            workspace=self.workspace,
            actor_identifier="fixture:pre-freeze-master",
        )

        actor = Actor.objects.get(code="ACT-FIX-ATOMIC-001")
        element = AnalyticalElement.objects.get(code="CAE-FIX-ATOMIC-001")
        time_slice = TimeSlice.objects.get(code="TS-FIX-2022-001")
        experiments = {
            experiment.assessment_set.kind: experiment
            for experiment in Experiment.objects.select_related("assessment_set")
        }
        source_packet_hash = hashlib.sha256(
            b"PRE_FREEZE_SOURCE_PACKET_BYTES_V1"
        ).hexdigest()
        reference_statements = {
            AssessmentKind.AI: "  AI coder preserves exact whitespace and UTF-8: Жанаозен.  ",
            AssessmentKind.HUMAN: "\tHuman coder preserves the exact source statement.\n",
        }
        lane_specs = {
            AssessmentKind.AI: {
                "assessment_id": "ASM-PRE-FREEZE-AI-001",
                "coder_id": "coder:ai:captured-001",
                "confidence": ConfidenceLevel.HIGH,
                "pos": 7,
                "sal": 8,
            },
            AssessmentKind.HUMAN: {
                "assessment_id": "ASM-PRE-FREEZE-HUMAN-001",
                "coder_id": "coder:human:captured-001",
                "confidence": ConfidenceLevel.MEDIUM,
                "pos": 4,
                "sal": 5,
            },
        }
        workbook_inputs: dict[str, tuple[Path, bytes]] = {}

        with tempfile.TemporaryDirectory() as temporary_directory:
            for lane, spec in lane_specs.items():
                experiment = experiments[lane]
                assessment_set = experiment.assessment_set
                meta = {
                    "package_id": f"PRE-FREEZE-{lane}-001",
                    "workbook_schema_version": "2.0.0",
                    "dataset_version": "PRE-FREEZE-FIXTURE-001",
                    "case_id": "CASE-PRE-FREEZE-001",
                    "case_name": "PRE_FREEZE Assessment import contract",
                    "coder_id": spec["coder_id"],
                    "coder_type": lane,
                    "assessment_set_id": str(assessment_set.id),
                    "method_version": "OPEN-METHOD-PRE-FREEZE",
                    "ontology_version": "4.0.0",
                    "source_packet_hash": source_packet_hash,
                    "cutoff_date": "2022-01-02",
                    "created_at": "2026-08-24T00:00:00Z",
                    "workbook_status": "DRAFT",
                }
                assessment = {
                    "assessment_id": spec["assessment_id"],
                    "assessment_set_id": str(assessment_set.id),
                    "actor_id": str(actor.id),
                    "element_id": str(element.id),
                    "time_slice_id": str(time_slice.id),
                    "assessment_status": "PROVISIONAL_PRE_METHOD_FREEZE",
                    "confidence": spec["confidence"],
                    "reference_statement": reference_statements[lane],
                    "pos": spec["pos"],
                    "sal": spec["sal"],
                    "rationale": f"Exact {lane} source workbook row; no fill-across.",
                }
                extra_sheets: list[tuple[str, list[list[object]]]] = []
                if lane == AssessmentKind.AI:
                    exact_fragment = "  Exact pending evidence fragment.  "
                    extra_sheets = [
                        (
                            "SOURCES",
                            [
                                [
                                    "source_id",
                                    "publisher_or_origin",
                                    "source_type",
                                    "jurisdiction",
                                    "language",
                                    "url_or_locator",
                                    "accessed_at",
                                    "independence_group",
                                    "source_notes",
                                ],
                                [
                                    "SRC-PRE-FREEZE-AI-001",
                                    "Independent fixture publisher",
                                    "NEWS",
                                    "KZ",
                                    "en",
                                    "https://example.test/pre-freeze/source",
                                    "2022-01-02",
                                    "PUBLISHER-PRE-FREEZE-AI-001",
                                    "Captured source row.",
                                ],
                            ],
                        ),
                        (
                            "DOCUMENTS",
                            [
                                [
                                    "document_id",
                                    "source_id",
                                    "title",
                                    "document_type",
                                    "document_version_id",
                                    "publication_date",
                                    "captured_at",
                                    "content_hash",
                                    "content_type",
                                    "language",
                                    "archive_or_local_locator",
                                    "is_after_cutoff",
                                ],
                                [
                                    "DOC-PRE-FREEZE-AI-001",
                                    "SRC-PRE-FREEZE-AI-001",
                                    "Exact PRE_FREEZE evidence document",
                                    "WEB_PAGE",
                                    "DV-PRE-FREEZE-AI-001",
                                    "2022-01-01",
                                    "2022-01-02T00:00:00Z",
                                    None,
                                    "text/html",
                                    "en",
                                    "https://example.test/pre-freeze/source",
                                    False,
                                ],
                            ],
                        ),
                        (
                            "FRAGMENTS",
                            [
                                [
                                    "fragment_id",
                                    "document_version_id",
                                    "exact_text",
                                    "fragment_hash",
                                    "start_offset",
                                    "end_offset",
                                    "page",
                                    "section",
                                    "translation_text",
                                    "translation_language",
                                ],
                                [
                                    "FRG-PRE-FREEZE-AI-001",
                                    "DV-PRE-FREEZE-AI-001",
                                    exact_fragment,
                                    hashlib.sha256(exact_fragment.encode("utf-8")).hexdigest(),
                                    None,
                                    None,
                                    None,
                                    "",
                                    "",
                                    "",
                                ],
                            ],
                        ),
                        (
                            "FACTS",
                            [
                                [
                                    "fact_id",
                                    "fact_statement",
                                    "fact_type",
                                    "fact_status",
                                    "time_start",
                                    "time_end",
                                    "geography",
                                    "fact_notes",
                                ],
                                [
                                    "FACT-PRE-FREEZE-AI-001",
                                    "The source records one atomic fixture proposition.",
                                    FactType.OBSERVED_EVENT,
                                    AssessmentRecordStatus.PROVISIONAL,
                                    "2022-01-01",
                                    "2022-01-01",
                                    "KZ",
                                    "No inferred assessment dimensions.",
                                ],
                            ],
                        ),
                        (
                            "FACT_EVIDENCE",
                            [
                                [
                                    "fact_fragment_link_id",
                                    "fact_id",
                                    "fragment_id",
                                    "evidence_relation",
                                ],
                                [
                                    "FEL-PRE-FREEZE-AI-001",
                                    "FACT-PRE-FREEZE-AI-001",
                                    "FRG-PRE-FREEZE-AI-001",
                                    "SUPPORTS",
                                ],
                            ],
                        ),
                        (
                            "ASSESSMENT_EVIDENCE",
                            [
                                [
                                    "assessment_fact_link_id",
                                    "assessment_id",
                                    "fact_id",
                                    "evidence_role",
                                ],
                                [
                                    "AEL-PRE-FREEZE-AI-001",
                                    spec["assessment_id"],
                                    "FACT-PRE-FREEZE-AI-001",
                                    AssessmentEvidenceRole.PRIMARY_SUPPORT,
                                ],
                            ],
                        ),
                    ]
                workbook_bytes = pre_freeze_workbook_bytes(
                    meta=meta,
                    assessment=assessment,
                    extra_sheets=extra_sheets,
                )
                workbook_path = Path(temporary_directory) / f"pre-freeze-{lane.lower()}.xlsx"
                workbook_path.write_bytes(workbook_bytes)
                workbook_inputs[lane] = (workbook_path, workbook_bytes)

            ai_experiment = experiments[AssessmentKind.AI]
            ai_path, ai_bytes = workbook_inputs[AssessmentKind.AI]
            wrong_selection = {
                "target_experiment_id": str(ai_experiment.id),
                "target_assessment_set_id": str(ai_experiment.assessment_set_id),
                "selected_source_column": "AI_POS",
            }
            with self.assertRaisesRegex(
                FoundationPackageValidationError,
                r"fixed to ASSESSMENTS\.pos\|sal",
            ):
                preview_foundation_package(
                    ai_path,
                    workspace=self.workspace,
                    adapter="xlsx",
                    selected_input=wrong_selection,
                    allow_nonempty=True,
                )
            self.assertFalse(ActorElementAssessment.objects.exists())
            self.assertFalse(ParameterValue.objects.exists())
            self.assertEqual(ImportRun.objects.count(), 1)

            receipts = {}
            for lane in (AssessmentKind.AI, AssessmentKind.HUMAN):
                experiment = experiments[lane]
                assessment_set = experiment.assessment_set
                workbook_path, workbook_bytes = workbook_inputs[lane]
                selected_input = {
                    "target_experiment_id": str(experiment.id),
                    "target_assessment_set_id": str(assessment_set.id),
                    "selected_source_column": "ASSESSMENTS.pos|sal",
                }
                before = (
                    ActorElementAssessment.objects.count(),
                    ParameterValue.objects.count(),
                    ImportRun.objects.count(),
                )
                preview = preview_foundation_package(
                    workbook_path,
                    workspace=self.workspace,
                    adapter="xlsx",
                    selected_input=selected_input,
                    allow_nonempty=True,
                )
                self.assertEqual(
                    (
                        ActorElementAssessment.objects.count(),
                        ParameterValue.objects.count(),
                        ImportRun.objects.count(),
                    ),
                    before,
                )
                self.assertEqual(preview.counts["actor_element_assessments"], 1)
                self.assertEqual(preview.counts["parameter_values"], 2)
                self.assertEqual(
                    preview.selected_input["adapter_profile"],
                    "V4_EXPERT_XLS_IMPORT_CONTRACT_PRE_FREEZE_V1",
                )
                self.assertEqual(
                    preview.selected_input["selected_source_column"],
                    "ASSESSMENTS.pos|sal",
                )
                self.assertEqual(
                    preview.selected_input["input_sha256"],
                    hashlib.sha256(workbook_bytes).hexdigest(),
                )
                canonical = preview.payload_copy()
                if lane == AssessmentKind.AI:
                    self.assertEqual(len(canonical["assessment_fact_links"]), 1)
                    self.assertEqual(canonical["parameter_value_fact_links"], [])
                assessment_row = canonical["actor_element_assessments"][0]
                self.assertEqual(assessment_row["code"], lane_specs[lane]["assessment_id"])
                self.assertEqual(
                    assessment_row["reference_statement"],
                    reference_statements[lane],
                )
                self.assertEqual(
                    assessment_row["provenance"],
                    {
                        "adapter_profile": "V4_EXPERT_XLS_IMPORT_CONTRACT_PRE_FREEZE_V1",
                        "coder_id": lane_specs[lane]["coder_id"],
                        "source_packet_hash": source_packet_hash,
                        "source_assessment_status": "PROVISIONAL_PRE_METHOD_FREEZE",
                    },
                )
                self.assertEqual(
                    {
                        row["parameter_definition_code"]: (row["status"], row["value"])
                        for row in canonical["parameter_values"]
                    },
                    {
                        "POS": (ValueStatus.PROVISIONAL, lane_specs[lane]["pos"]),
                        "SAL": (
                            ValueStatus.PROVISIONAL
                            if lane_specs[lane]["sal"] is not None
                            else ValueStatus.UNKNOWN,
                            lane_specs[lane]["sal"],
                        ),
                    },
                )
                receipt = commit_foundation_package(
                    preview,
                    workspace=self.workspace,
                    allow_nonempty=True,
                    actor_identifier=lane_specs[lane]["coder_id"],
                )
                receipts[lane] = receipt
                run = ImportRun.objects.get(pk=receipt.id)
                self.assertEqual(run.target_experiment_id, experiment.id)
                self.assertEqual(run.target_assessment_set_id, assessment_set.id)
                self.assertEqual(run.selected_source_column, "ASSESSMENTS.pos|sal")
                self.assertEqual(
                    run.row_counts["materialized"],
                    11 if lane == AssessmentKind.AI else 3,
                )
                self.assertEqual(run.selected_input["input_sha256"], hashlib.sha256(workbook_bytes).hexdigest())
                self.assertEqual(run.errors, [])

        imported = {
            assessment.assessment_set.kind: assessment
            for assessment in ActorElementAssessment.objects.select_related(
                "assessment_set", "experiment"
            )
        }
        self.assertEqual(set(imported), {AssessmentKind.AI, AssessmentKind.HUMAN})
        self.assertEqual(
            imported[AssessmentKind.AI].reference_statement,
            reference_statements[AssessmentKind.AI],
        )
        self.assertEqual(
            imported[AssessmentKind.HUMAN].reference_statement,
            reference_statements[AssessmentKind.HUMAN],
        )
        values = {
            (
                value.assessment_set.kind,
                value.parameter_definition.code,
            ): (value.status, value.value)
            for value in ParameterValue.objects.select_related(
                "assessment_set", "parameter_definition"
            )
        }
        self.assertEqual(
            values,
            {
                (AssessmentKind.AI, "POS"): (ValueStatus.PROVISIONAL, 7),
                (AssessmentKind.AI, "SAL"): (ValueStatus.PROVISIONAL, 8),
                (AssessmentKind.HUMAN, "POS"): (ValueStatus.PROVISIONAL, 4),
                (AssessmentKind.HUMAN, "SAL"): (ValueStatus.PROVISIONAL, 5),
            },
        )
        self.assertNotEqual(receipts[AssessmentKind.AI].id, receipts[AssessmentKind.HUMAN].id)
        self.assertEqual(AssessmentEvidence.objects.count(), 1)
        self.assertFalse(ParameterValueEvidence.objects.exists())

    @covers("FND-I01", "FND-I02", "FND-I03", "FND-I04", "FND-S03")
    @materializes_fixtures("V4_UNKNOWN_NOT_ZERO_FIXTURE_001")
    def test_pre_freeze_status_matrix_preserves_absence_and_rejects_blank_present_statuses(self):
        definitions = {}
        for code, minimum, maximum in (("POS", -10, 10), ("SAL", 0, 10)):
            definitions[code] = clean_save(
                ParameterDefinition(
                    project=self.project,
                    code=code,
                    version="OPEN-METHOD-PRE-FREEZE",
                    name=code,
                    description="Exact PRE_FREEZE numeric lane.",
                    target_type=TargetType.ACTOR_ELEMENT_ASSESSMENT,
                    value_type=ParameterValueType.INTEGER,
                    scale_min=minimum,
                    scale_max=maximum,
                )
            )

        def make_lane(suffix: str) -> tuple[ProjectWorkspace, Actor, AnalyticalElement, TimeSlice, Experiment]:
            workspace = (
                self.workspace
                if suffix == "NOT-APPLICABLE"
                else self.make_workspace(code=f"WORKSPACE-STATUS-{suffix}")
            )
            actor = clean_save(
                Actor(
                    workspace=workspace,
                    code=f"ACT-STATUS-{suffix}",
                    version="4.0.0",
                    actor_type=ActorType.GROUP,
                    label=f"Status actor {suffix}",
                )
            )
            element = clean_save(
                AnalyticalElement(
                    workspace=workspace,
                    code=f"CAE-STATUS-{suffix}",
                    version="4.0.0",
                    element_type=AnalyticalElementType.CONFLICT_ISSUE,
                    label=f"Status issue {suffix}",
                    reference_statement=f"Exact status statement {suffix}.",
                )
            )
            time_slice = clean_save(
                TimeSlice(
                    project=self.project,
                    workspace=workspace,
                    code=f"TS-STATUS-{suffix}",
                    version="1.0.0",
                    name=f"Status cutoff {suffix}",
                    cutoff_date=date(2022, 1, 2),
                )
            )
            assessment_set = clean_save(
                AssessmentSet(
                    project=self.project,
                    workspace=workspace,
                    code=f"ASET-STATUS-{suffix}",
                    version="1.0.0",
                    kind=AssessmentKind.AI,
                    name=f"Status set {suffix}",
                )
            )
            profile = clean_save(
                ExpertProfile(
                    workspace=workspace,
                    code=f"EXPERT-STATUS-{suffix}",
                    version="1.0.0",
                    kind=AssessmentKind.AI,
                    display_name=f"Status coder {suffix}",
                    identity_key=f"fixture:status:{suffix.lower()}",
                    provider="fixture-only",
                    model_name="captured-metadata-only",
                )
            )
            experiment = clean_save(
                Experiment(
                    workspace=workspace,
                    assessment_set=assessment_set,
                    expert_profile=profile,
                    code=f"EXP-STATUS-{suffix}",
                    version="1.0.0",
                    experiment_type=ExperimentType.ASSESSMENT,
                    name=f"Status experiment {suffix}",
                    method_version="OPEN-METHOD-PRE-FREEZE",
                )
            )
            return workspace, actor, element, time_slice, experiment

        def workbook_for(
            *,
            suffix: str,
            status: str,
            pos: int | None,
            sal: int | None,
            workspace: ProjectWorkspace,
            actor: Actor,
            element: AnalyticalElement,
            time_slice: TimeSlice,
            experiment: Experiment,
        ) -> bytes:
            rationale = f"Exact absent/present rationale for {status}."
            return pre_freeze_workbook_bytes(
                meta={
                    "package_id": f"PRE-FREEZE-STATUS-{suffix}",
                    "workbook_schema_version": "2.0.0",
                    "dataset_version": "PRE-FREEZE-STATUS-MATRIX-001",
                    "case_id": "CASE-PRE-FREEZE-STATUS-001",
                    "case_name": "PRE_FREEZE status matrix",
                    "coder_id": f"coder:status:{suffix.lower()}",
                    "coder_type": AssessmentKind.AI,
                    "assessment_set_id": str(experiment.assessment_set_id),
                    "method_version": "OPEN-METHOD-PRE-FREEZE",
                    "ontology_version": "4.0.0",
                    "source_packet_hash": hashlib.sha256(
                        f"status:{suffix}".encode("utf-8")
                    ).hexdigest(),
                    "cutoff_date": "2022-01-02",
                    "created_at": "2026-08-24T00:00:00Z",
                    "workbook_status": "DRAFT",
                },
                assessment={
                    "assessment_id": f"ASM-STATUS-{suffix}",
                    "assessment_set_id": str(experiment.assessment_set_id),
                    "actor_id": str(actor.id),
                    "element_id": str(element.id),
                    "time_slice_id": str(time_slice.id),
                    "assessment_status": status,
                    "confidence": ConfidenceLevel.LOW,
                    "reference_statement": f"Exact status statement {suffix}.",
                    "pos": pos,
                    "sal": sal,
                    "rationale": rationale,
                },
            )

        valid_specs = (
            ("NOT-APPLICABLE", ValueStatus.NOT_APPLICABLE, None, None),
            ("INSUFFICIENT-DATA", ValueStatus.INSUFFICIENT_DATA, None, None),
            ("OPEN-METHOD", ValueStatus.OPEN_METHOD, None, None),
            ("RETROSPECTIVE", ValueStatus.RETROSPECTIVE_KNOWLEDGE, 2, 3),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            for suffix, status, pos, sal in valid_specs:
                workspace, actor, element, time_slice, experiment = make_lane(suffix)
                workbook_bytes = workbook_for(
                    suffix=suffix,
                    status=status,
                    pos=pos,
                    sal=sal,
                    workspace=workspace,
                    actor=actor,
                    element=element,
                    time_slice=time_slice,
                    experiment=experiment,
                )
                path = Path(temporary_directory) / f"status-{suffix.lower()}.xlsx"
                path.write_bytes(workbook_bytes)
                preview = preview_foundation_package(
                    path,
                    workspace=workspace,
                    adapter="xlsx",
                    selected_input={
                        "target_experiment_id": str(experiment.id),
                        "target_assessment_set_id": str(experiment.assessment_set_id),
                        "selected_source_column": "ASSESSMENTS.pos|sal",
                    },
                    allow_nonempty=True,
                )
                rows = preview.payload_copy()["parameter_values"]
                self.assertEqual(
                    {
                        row["parameter_definition_code"]: (
                            row["status"],
                            row["value"],
                            row["rationale"],
                        )
                        for row in rows
                    },
                    {
                        "POS": (
                            status,
                            pos,
                            f"Exact absent/present rationale for {status}.",
                        ),
                        "SAL": (
                            status,
                            sal,
                            f"Exact absent/present rationale for {status}.",
                        ),
                    },
                )
                commit_foundation_package(
                    preview,
                    workspace=workspace,
                    allow_nonempty=True,
                    actor_identifier=f"coder:status:{suffix.lower()}",
                )

            for suffix, status in (
                ("PROVISIONAL-BLANK", ValueStatus.PROVISIONAL),
                ("CONFIRMED-BLANK", ValueStatus.CONFIRMED),
            ):
                workspace, actor, element, time_slice, experiment = make_lane(suffix)
                path = Path(temporary_directory) / f"status-{suffix.lower()}.xlsx"
                path.write_bytes(
                    workbook_for(
                        suffix=suffix,
                        status=status,
                        pos=None,
                        sal=None,
                        workspace=workspace,
                        actor=actor,
                        element=element,
                        time_slice=time_slice,
                        experiment=experiment,
                    )
                )
                before = ParameterValue.objects.filter(workspace=workspace).count()
                with self.assertRaisesRegex(
                    FoundationPackageValidationError,
                    r"blank POS/SAL.*no UNKNOWN fill-across",
                ):
                    preview_foundation_package(
                        path,
                        workspace=workspace,
                        adapter="xlsx",
                        selected_input={
                            "target_experiment_id": str(experiment.id),
                            "target_assessment_set_id": str(experiment.assessment_set_id),
                            "selected_source_column": "ASSESSMENTS.pos|sal",
                        },
                        allow_nonempty=True,
                    )
                self.assertEqual(
                    ParameterValue.objects.filter(workspace=workspace).count(),
                    before,
                )

    @covers("FND-D02", "FND-D03", "FND-I01", "FND-I02", "FND-I03")
    @exercises_fixtures("V4_DOCUMENTVERSION_ANCHOR_FIXTURE_001")
    def test_pre_freeze_repeated_document_id_materializes_distinct_stable_versions(self):
        lane = self.make_pre_freeze_selected_lane(suffix="DOCUMENT-VERSIONS")
        experiment = lane["experiment"]
        assessment_set = lane["assessment_set"]
        meta = {
            "package_id": "PRE-FREEZE-DOCUMENT-VERSIONS-001",
            "workbook_schema_version": "2.0.0",
            "dataset_version": "PRE-FREEZE-DOCUMENT-VERSIONS-001",
            "case_id": "CASE-DOCUMENT-VERSIONS-001",
            "case_name": "Repeated Document identity with captured versions",
            "coder_id": "coder:document-versions",
            "coder_type": AssessmentKind.AI,
            "assessment_set_id": str(assessment_set.id),
            "method_version": "OPEN-METHOD-PRE-FREEZE",
            "ontology_version": "4.0.0",
            "source_packet_hash": hashlib.sha256(
                b"PRE_FREEZE_DOCUMENT_VERSIONS_SOURCE_PACKET"
            ).hexdigest(),
            "cutoff_date": "2022-01-02",
            "created_at": "2026-08-24T00:00:00Z",
            "workbook_status": "DRAFT",
        }
        assessment = {
            "assessment_id": "ASM-PRE-DOCUMENT-VERSIONS-001",
            "assessment_set_id": str(assessment_set.id),
            "actor_id": str(lane["actor"].id),
            "element_id": str(lane["element"].id),
            "time_slice_id": str(lane["time_slice"].id),
            "assessment_status": "PROVISIONAL_PRE_METHOD_FREEZE",
            "confidence": ConfidenceLevel.MEDIUM,
            "reference_statement": "Exact repeated-document version statement.",
            "pos": 1,
            "sal": 2,
            "rationale": "Captured source values only.",
        }
        source_headers = [
            "source_id",
            "publisher_or_origin",
            "source_type",
            "jurisdiction",
            "language",
            "url_or_locator",
            "accessed_at",
            "independence_group",
            "source_notes",
        ]
        document_headers = [
            "document_id",
            "source_id",
            "title",
            "document_type",
            "document_version_id",
            "publication_date",
            "captured_at",
            "content_hash",
            "content_type",
            "language",
            "archive_or_local_locator",
            "is_after_cutoff",
        ]
        documents = [
            [
                "DOC-PRE-REPEATED-001",
                "SRC-PRE-REPEATED-001",
                "One immutable logical document",
                "WEB_PAGE",
                "DV-PRE-REPEATED-001-A",
                "2022-01-01",
                "2022-01-01T10:00:00Z",
                None,
                "text/html",
                "en",
                "https://example.test/repeated/version-a",
                False,
            ],
            [
                "DOC-PRE-REPEATED-001",
                "SRC-PRE-REPEATED-001",
                "One immutable logical document",
                "WEB_PAGE",
                "DV-PRE-REPEATED-001-B",
                "2022-01-01",
                "2022-01-02T10:00:00Z",
                None,
                "text/html",
                "en",
                "https://example.test/repeated/version-b",
                False,
            ],
        ]
        workbook = pre_freeze_workbook_bytes(
            meta=meta,
            assessment=assessment,
            extra_sheets=[
                (
                    "SOURCES",
                    [
                        source_headers,
                        [
                            "SRC-PRE-REPEATED-001",
                            "Repeated-version publisher",
                            "NEWS",
                            "KZ",
                            "en",
                            "https://example.test/repeated",
                            "2022-01-02",
                            "PUBLISHER-PRE-REPEATED-001",
                            "One source identity.",
                        ],
                    ],
                ),
                ("DOCUMENTS", [document_headers, *documents]),
            ],
        )
        selected_input = {
            "target_experiment_id": str(experiment.id),
            "target_assessment_set_id": str(assessment_set.id),
            "selected_source_column": "ASSESSMENTS.pos|sal",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "repeated-document-versions.xlsx"
            path.write_bytes(workbook)
            first = preview_foundation_package(
                path,
                workspace=self.workspace,
                adapter="xlsx",
                selected_input=selected_input,
                allow_nonempty=True,
            )
            second = preview_foundation_package(
                path,
                workspace=self.workspace,
                adapter="xlsx",
                selected_input=selected_input,
                allow_nonempty=True,
            )

        first_payload = first.payload_copy()
        second_payload = second.payload_copy()
        self.assertEqual(len(first_payload["documents"]), 1)
        self.assertEqual(first_payload["documents"][0]["code"], "DOC-PRE-REPEATED-001")
        versions = {
            row["code"]: (row["id"], row["version"])
            for row in first_payload["document_versions"]
        }
        self.assertEqual(set(versions), {"DV-PRE-REPEATED-001-A", "DV-PRE-REPEATED-001-B"})
        self.assertNotEqual(
            versions["DV-PRE-REPEATED-001-A"][1],
            versions["DV-PRE-REPEATED-001-B"][1],
        )
        self.assertTrue(all(len(version) <= 64 for _, version in versions.values()))
        self.assertEqual(
            versions,
            {
                row["code"]: (row["id"], row["version"])
                for row in second_payload["document_versions"]
            },
        )
        commit_foundation_package(
            first,
            workspace=self.workspace,
            allow_nonempty=True,
            actor_identifier="coder:document-versions",
        )
        self.assertEqual(Document.objects.filter(workspace=self.workspace).count(), 1)
        stored_versions = {
            row.code: row.version
            for row in DocumentVersion.objects.filter(workspace=self.workspace)
        }
        self.assertEqual(
            stored_versions,
            {code: version for code, (_, version) in versions.items()},
        )

    @covers("FND-I01", "FND-I02", "FND-P01", "FND-P02", "FND-P03")
    def test_pre_freeze_unknown_power_blank_provenance_is_object_and_non_objects_reject(self):
        lane = self.make_pre_freeze_selected_lane(suffix="POWER-PROVENANCE")
        experiment = lane["experiment"]
        assessment_set = lane["assessment_set"]
        meta = {
            "package_id": "PRE-FREEZE-POWER-PROVENANCE-001",
            "workbook_schema_version": "2.0.0",
            "dataset_version": "PRE-FREEZE-POWER-PROVENANCE-001",
            "case_id": "CASE-POWER-PROVENANCE-001",
            "case_name": "Blank UNKNOWN Power provenance",
            "coder_id": "coder:power-provenance",
            "coder_type": AssessmentKind.AI,
            "assessment_set_id": str(assessment_set.id),
            "method_version": "OPEN-METHOD-PRE-FREEZE",
            "ontology_version": "4.0.0",
            "source_packet_hash": hashlib.sha256(
                b"PRE_FREEZE_POWER_PROVENANCE_SOURCE_PACKET"
            ).hexdigest(),
            "cutoff_date": "2022-01-02",
            "created_at": "2026-08-24T00:00:00Z",
            "workbook_status": "DRAFT",
        }
        assessment_id = "ASM-PRE-POWER-PROVENANCE-001"
        assessment = {
            "assessment_id": assessment_id,
            "assessment_set_id": str(assessment_set.id),
            "actor_id": str(lane["actor"].id),
            "element_id": str(lane["element"].id),
            "time_slice_id": str(lane["time_slice"].id),
            "assessment_status": "PROVISIONAL_PRE_METHOD_FREEZE",
            "confidence": ConfidenceLevel.MEDIUM,
            "reference_statement": "Exact UNKNOWN Power provenance statement.",
            "pos": 1,
            "sal": 2,
            "rationale": "Power remains a separate source vector.",
        }
        power_headers = ["assessment_id"]
        for dimension in PowerDimension.values:
            power_headers.extend(
                f"{dimension.lower()}_{suffix}"
                for suffix in ("value", "status", "confidence", "rationale", "provenance")
            )

        def power_sheet(fa_provenance: object = None) -> tuple[str, list[list[object]]]:
            row: list[object] = [assessment_id]
            for dimension in PowerDimension.values:
                row.extend(
                    [
                        None,
                        ValueStatus.UNKNOWN,
                        None,
                        "",
                        fa_provenance if dimension == PowerDimension.FA else None,
                    ]
                )
            return "POWER_PROFILE", [power_headers, row]

        selected_input = {
            "target_experiment_id": str(experiment.id),
            "target_assessment_set_id": str(assessment_set.id),
            "selected_source_column": "ASSESSMENTS.pos|sal",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            valid_path = Path(temporary_directory) / "power-blank-provenance.xlsx"
            valid_path.write_bytes(
                pre_freeze_workbook_bytes(
                    meta=meta,
                    assessment=assessment,
                    extra_sheets=[power_sheet()],
                )
            )
            preview = preview_foundation_package(
                valid_path,
                workspace=self.workspace,
                adapter="xlsx",
                selected_input=selected_input,
                allow_nonempty=True,
            )
            components = preview.payload_copy()["power_components"]
            self.assertEqual(len(components), 8)
            self.assertEqual(
                {row["dimension"]: row["provenance"] for row in components},
                {dimension: {} for dimension in PowerDimension.values},
            )
            commit_foundation_package(
                preview,
                workspace=self.workspace,
                allow_nonempty=True,
                actor_identifier="coder:power-provenance",
            )
            self.assertEqual(PowerComponent.objects.count(), 8)
            self.assertEqual(
                set(canonical_json(value) for value in PowerComponent.objects.values_list("provenance", flat=True)),
                {"{}"},
            )

            for label, invalid_provenance in (("list", ["not", "an", "object"]), ("scalar", 7)):
                invalid_path = Path(temporary_directory) / f"power-{label}-provenance.xlsx"
                invalid_path.write_bytes(
                    pre_freeze_workbook_bytes(
                        meta={**meta, "package_id": f"PRE-FREEZE-POWER-{label.upper()}-001"},
                        assessment=assessment,
                        extra_sheets=[power_sheet(invalid_provenance)],
                    )
                )
                with self.assertRaisesRegex(
                    FoundationPackageValidationError,
                    "provenance must be a JSON object",
                ):
                    preview_foundation_package(
                        invalid_path,
                        workspace=self.workspace,
                        adapter="xlsx",
                        selected_input=selected_input,
                        allow_nonempty=True,
                    )
                self.assertEqual(PowerComponent.objects.count(), 8)

    @covers("FND-I02", "FND-I03", "FND-I04", "FND-I05", "FND-I06", "FND-I07")
    @materializes_fixtures("V4_ATOMIC_IMPORT_NO_OVERWRITE_FIXTURE_001")
    def test_materialized_atomic_human_ai_lanes_are_stable_order_independent_and_fail_closed(self):
        package = atomic_lane_package(self.workspace)
        selected_input = {
            "source_file_sha256": hashlib.sha256(
                canonical_json(package).encode("utf-8")
            ).hexdigest(),
            "selected_columns": {
                "AI": "ASET-AI-FIX-001",
                "HUMAN": "ASET-HUMAN-FIX-001",
            },
            "mapping_key": "parameter_definition_code",
        }

        invalid_sal = json.loads(json.dumps(package))
        next(
            item
            for item in invalid_sal["parameter_values"]
            if item["code"] == "PV-AI-SAL-FIX-001"
        )["value"] = 11
        invalid_sal = seal_foundation_package(invalid_sal)
        with self.assertRaises(FoundationPackageValidationError):
            preview_foundation_package(invalid_sal, workspace=self.workspace)
        self.assertFalse(ParameterValue.objects.exists())
        self.assertFalse(AssessmentSet.objects.exists())

        duplicate_parameter = json.loads(json.dumps(package))
        repeated = dict(duplicate_parameter["parameter_definitions"][0])
        repeated["id"] = "37000000-0000-4000-8000-000000000099"
        duplicate_parameter["parameter_definitions"].append(repeated)
        duplicate_parameter = seal_foundation_package(duplicate_parameter)
        with self.assertRaisesRegex(
            FoundationPackageValidationError,
            "code duplicates",
        ):
            preview_foundation_package(duplicate_parameter, workspace=self.workspace)

        unknown_parameter = json.loads(json.dumps(package))
        unknown_parameter["parameter_values"][0][
            "parameter_definition_code"
        ] = "PARAM-FIX-UNKNOWN-999"
        unknown_parameter = seal_foundation_package(unknown_parameter)
        with self.assertRaisesRegex(
            FoundationPackageValidationError,
            "PARAM-FIX-UNKNOWN-999",
        ):
            preview_foundation_package(unknown_parameter, workspace=self.workspace)

        reordered = json.loads(json.dumps(package))
        reordered["parameter_values"].reverse()
        reordered = seal_foundation_package(reordered)
        reordered_preview = preview_foundation_package(
            reordered,
            workspace=self.workspace,
            selected_input=selected_input,
        )
        preview = preview_foundation_package(
            package,
            workspace=self.workspace,
            selected_input=selected_input,
        )
        self.assertEqual(
            {
                row["code"]: (
                    row["assessment_set_code"],
                    row["parameter_definition_code"],
                    row["status"],
                    row["value"],
                )
                for row in reordered_preview.payload_copy()["parameter_values"]
            },
            {
                row["code"]: (
                    row["assessment_set_code"],
                    row["parameter_definition_code"],
                    row["status"],
                    row["value"],
                )
                for row in preview.payload_copy()["parameter_values"]
            },
        )

        with self.assertRaisesRegex(
            FoundationPackageValidationError,
            "Injected mid-import rollback",
        ):
            commit_foundation_package(
                preview,
                workspace=self.workspace,
                actor_identifier="fixture:atomic-importer",
                inject_failure_after=8,
            )
        self.assertFalse(ParameterValue.objects.exists())
        self.assertFalse(ImportRun.objects.exists())

        receipt = commit_foundation_package(
            preview,
            workspace=self.workspace,
            actor_identifier="fixture:atomic-importer",
        )
        values = {
            value.code: (
                value.assessment_set.code,
                value.parameter_definition.code,
                value.status,
                value.value,
            )
            for value in ParameterValue.objects.select_related(
                "assessment_set", "parameter_definition"
            )
        }
        self.assertEqual(
            values,
            {
                "PV-AI-POS-FIX-001": (
                    "ASET-AI-FIX-001",
                    "PARAM-FIX-POS-001",
                    ValueStatus.PROVISIONAL,
                    7,
                ),
                "PV-AI-SAL-FIX-001": (
                    "ASET-AI-FIX-001",
                    "PARAM-FIX-SAL-001",
                    ValueStatus.PROVISIONAL,
                    8,
                ),
                "PV-HUMAN-POS-FIX-001": (
                    "ASET-HUMAN-FIX-001",
                    "PARAM-FIX-POS-001",
                    ValueStatus.PROVISIONAL,
                    4,
                ),
                "PV-HUMAN-SAL-FIX-001": (
                    "ASET-HUMAN-FIX-001",
                    "PARAM-FIX-SAL-001",
                    ValueStatus.UNKNOWN,
                    None,
                ),
            },
        )
        self.assertEqual(
            Experiment.objects.filter(experiment_type=ExperimentType.ASSESSMENT).count(),
            2,
        )
        self.assertEqual(
            set(AssessmentSet.objects.values_list("kind", flat=True)),
            {AssessmentKind.HUMAN, AssessmentKind.AI},
        )
        run = ImportRun.objects.get(pk=receipt.id)
        self.assertEqual(
            {key: run.selected_input[key] for key in selected_input},
            selected_input,
        )
        self.assertEqual(run.selected_input["raw_input_kind"], "CANONICAL_MAPPING")
        self.assertEqual(run.selected_input["raw_input_sha256"], preview.raw_input_sha256)
        self.assertEqual(run.row_counts["parameter_values"], 4)
        self.assertEqual(run.checksum, preview.checksum)

        exported = export_foundation_package(self.workspace)
        self.assertEqual(
            {
                row["code"]: (row["id"], row["status"], row["value"])
                for row in exported["parameter_values"]
            },
            {
                row["code"]: (row["id"], row["status"], row["value"])
                for row in package["parameter_values"]
            },
        )
        changed = json.loads(json.dumps(package))
        next(
            row
            for row in changed["parameter_values"]
            if row["code"] == "PV-AI-POS-FIX-001"
        )["value"] = 6
        changed = seal_foundation_package(changed)
        with self.assertRaises(FoundationPackageConflictError):
            preview_foundation_package(changed, workspace=self.workspace)
        self.assertEqual(
            ParameterValue.objects.get(code="PV-AI-POS-FIX-001").value,
            7,
        )

    @covers("FND-I03", "FND-I04", "FND-I05", "FND-I06", "FND-I07")
    @materializes_fixtures("V4_ATOMIC_IMPORT_NO_OVERWRITE_FIXTURE_001")
    def test_selected_lane_receipt_correction_lineage_and_frozen_child_guard_are_exact(self):
        initial_package = atomic_lane_package(self.workspace)
        initial_preview = preview_foundation_package(
            initial_package,
            workspace=self.workspace,
        )
        commit_foundation_package(
            initial_preview,
            workspace=self.workspace,
            actor_identifier="fixture:selected-lane-seed",
        )
        human_experiment = Experiment.objects.get(code="EXP-HUMAN-FIX-001")
        human_set = AssessmentSet.objects.get(code="ASET-HUMAN-FIX-001")

        append_package = project_package_to_selected_lane(
            export_foundation_package(self.workspace),
            experiment_code=human_experiment.code,
            assessment_set_code=human_set.code,
            expert_profile_code=human_experiment.expert_profile.code,
        )
        self.assertEqual(
            {item["code"] for item in append_package["experiments"]},
            {human_experiment.code},
        )
        self.assertEqual(
            {item["assessment_set_code"] for item in append_package["parameter_values"]},
            {human_set.code},
        )
        predecessor = next(
            row
            for row in append_package["actor_element_assessments"]
            if row["code"] == "ASM-HUMAN-FIX-001"
        )
        successor = {
            **predecessor,
            "id": "38000000-0000-4000-8000-000000000001",
            "code": "ASM-HUMAN-FIX-002",
            "version": "2.0.0",
            "supersedes_code": predecessor["code"],
            "provenance": {"fixture": "selected-existing-human-column"},
        }
        append_package["actor_element_assessments"].append(successor)
        append_package["facts"].append(
            {
                "id": "38000000-0000-4000-8000-000000000002",
                "code": "FACT-HUMAN-FIX-001",
                "version": "1.0.0",
                "metadata": {"fixture": "selected-existing-human-column"},
                "experiment_code": human_experiment.code,
                "fact_type": FactType.EXPERT_INTERPRETATION,
                "statement": "The selected HUMAN lane records an attributed source assertion.",
                "origin": FactOrigin.HUMAN_EXPERT_ASSERTION,
                "directness": FactDirectness.GROUP_INFERENCE,
                "visibility": Visibility.EXPERIMENT_PRIVATE,
                "status": AssessmentRecordStatus.PROVISIONAL,
                "confidence": 40,
                "temporal_status": EvidenceTemporalStatus.CONTEMPORANEOUS,
                "coder_identifier": "fixture:selected-human-coder",
            }
        )
        append_package["assessment_fact_links"].append(
            {
                "id": "38000000-0000-4000-8000-000000000003",
                "code": "AFL-HUMAN-FIX-001",
                "version": "1.0.0",
                "metadata": {},
                "assessment_code": successor["code"],
                "fact_code": "FACT-HUMAN-FIX-001",
                "role": AssessmentEvidenceRole.SUPPORTS_POSITION,
                "temporal_status": EvidenceTemporalStatus.CONTEMPORANEOUS,
                "learned_on": "2022-01-01",
                "rationale": "Explicit selected-column evidence link.",
            }
        )
        append_package = seal_foundation_package(append_package)
        selected_input = {
            "target_experiment_id": str(human_experiment.id),
            "target_assessment_set_id": str(human_set.id),
            "selected_source_column": "HUMAN_POS",
        }
        append_preview = preview_foundation_package(
            append_package,
            workspace=self.workspace,
            selected_input=selected_input,
            allow_nonempty=True,
        )
        self.assertEqual(
            append_preview.source_identity_map["actor_element_assessments"][
                successor["code"]
            ],
            successor["id"],
        )
        self.assertIn(
            successor["code"],
            append_preview.intended_changes["create"][
                "actor_element_assessments"
            ],
        )
        self.assertIn(
            human_experiment.code,
            append_preview.intended_changes["reuse"]["experiments"],
        )
        self.assertEqual(
            dict(append_preview.correction_lineage[0]),
            {
                "section": "actor_element_assessments",
                "code": successor["code"],
                "id": successor["id"],
                "supersedes_code": predecessor["code"],
                "supersedes_id": predecessor["id"],
            },
        )

        receipt = commit_foundation_package(
            append_preview,
            workspace=self.workspace,
            allow_nonempty=True,
            actor_identifier="fixture:selected-human-coder",
        )
        run = ImportRun.objects.get(pk=receipt.id)
        self.assertEqual(run.target_experiment_id, human_experiment.id)
        self.assertEqual(run.target_assessment_set_id, human_set.id)
        self.assertEqual(run.selected_source_column, "HUMAN_POS")
        self.assertEqual(run.source_identity_map, dict(append_preview.source_identity_map))
        self.assertEqual(run.correction_lineage, [dict(append_preview.correction_lineage[0])])
        preview_changes = {
            action: {
                section: list(codes)
                for section, codes in append_preview.intended_changes[action].items()
            }
            for action in ("create", "reuse")
        }
        self.assertEqual(run.intended_changes, preview_changes)
        self.assertEqual(run.errors, [])
        self.assertEqual(run.warnings, list(append_preview.warnings))
        self.assertTrue(run.allow_nonempty)
        self.assertEqual(run.row_counts["materialized"], 3)
        self.assertEqual(
            run.selected_input["target_experiment_code"],
            human_experiment.code,
        )

        freeze_experiment(
            human_experiment,
            actor_identifier="fixture:selected-human-coder",
        )
        human_experiment.refresh_from_db()
        self.assertEqual(human_experiment.status, ExperimentStatus.FROZEN)
        frozen_append = project_package_to_selected_lane(
            export_foundation_package(self.workspace),
            experiment_code=human_experiment.code,
            assessment_set_code=human_set.code,
            expert_profile_code=human_experiment.expert_profile.code,
        )
        frozen_predecessor = next(
            row
            for row in frozen_append["actor_element_assessments"]
            if row["code"] == successor["code"]
        )
        frozen_successor = {
            **frozen_predecessor,
            "id": "38000000-0000-4000-8000-000000000004",
            "code": "ASM-HUMAN-FIX-003",
            "version": "3.0.0",
            "supersedes_code": frozen_predecessor["code"],
        }
        frozen_append["actor_element_assessments"].append(frozen_successor)
        frozen_append["facts"].append(
            {
                "id": "38000000-0000-4000-8000-000000000005",
                "code": "FACT-HUMAN-FIX-002",
                "version": "1.0.0",
                "metadata": {"fixture": "frozen-child-rejection"},
                "experiment_code": human_experiment.code,
                "fact_type": FactType.EXPERT_INTERPRETATION,
                "statement": "This fact must never enter a frozen selected lane.",
                "origin": FactOrigin.HUMAN_EXPERT_ASSERTION,
                "directness": FactDirectness.GROUP_INFERENCE,
                "visibility": Visibility.EXPERIMENT_PRIVATE,
                "status": AssessmentRecordStatus.PROVISIONAL,
                "confidence": 40,
                "temporal_status": EvidenceTemporalStatus.CONTEMPORANEOUS,
                "coder_identifier": "fixture:selected-human-coder",
            }
        )
        frozen_append["assessment_fact_links"].append(
            {
                "id": "38000000-0000-4000-8000-000000000006",
                "code": "AFL-HUMAN-FIX-002",
                "version": "1.0.0",
                "metadata": {},
                "assessment_code": frozen_successor["code"],
                "fact_code": "FACT-HUMAN-FIX-002",
                "role": AssessmentEvidenceRole.SUPPORTS_POSITION,
                "temporal_status": EvidenceTemporalStatus.CONTEMPORANEOUS,
                "learned_on": "2022-01-02",
                "rationale": "Must roll back with every frozen child row.",
            }
        )
        frozen_append = seal_foundation_package(frozen_append)
        protected_counts = (
            ActorElementAssessment.objects.count(),
            Fact.objects.count(),
            AssessmentEvidence.objects.count(),
            ImportRun.objects.count(),
        )
        with self.assertRaisesRegex(
            FoundationPackageConflictError,
            "Selected Experiment is FROZEN",
        ):
            preview_foundation_package(
                frozen_append,
                workspace=self.workspace,
                selected_input=selected_input,
                allow_nonempty=True,
            )
        self.assertEqual(
            (
                ActorElementAssessment.objects.count(),
                Fact.objects.count(),
                AssessmentEvidence.objects.count(),
                ImportRun.objects.count(),
            ),
            protected_counts,
        )

    @covers("FND-I04", "FND-I05", "FND-I06", "FND-I07")
    @exercises_fixtures("V4_ATOMIC_IMPORT_NO_OVERWRITE_FIXTURE_001")
    def test_atomic_commit_rolls_back_then_records_complete_append_only_receipt_without_overwrite(self):
        actor_id = "31000000-0000-4000-8000-000000000001"
        compatibility_id = "31000000-0000-4000-8000-000000000002"
        legacy_id = "31000000-0000-4000-8000-000000000003"
        package = minimal_foundation_package(
            self.workspace,
            compatibility_receipts=[
                {
                    "id": compatibility_id,
                    "code": "LEGACY-EVIDENCE-UNRESOLVED-001",
                    "version": "2.0.0",
                    "legacy_model": "EvidenceSource",
                    "legacy_id": legacy_id,
                    "legacy_code": "LEGACY-SOURCE-001",
                    "canonical_model": "",
                    "canonical_id": None,
                    "canonical_code": "",
                    "status": "UNRESOLVED",
                    "reason": "No immutable document version is available.",
                    "migration_version": "0002_foundation",
                }
            ],
        )
        package["actors"] = [
            {
                "id": actor_id,
                "code": "ACTOR-IMPORTED-001",
                "version": "4.0.0",
                "metadata": {"fixture": "atomic-import"},
                "parent_code": None,
                "actor_type": ActorType.GROUP,
                "label": "Imported actor",
                "description": "Must be inserted once and never overwritten.",
                "order": 0,
            }
        ]
        package = seal_foundation_package(package)
        preview = preview_foundation_package(
            package,
            workspace=self.workspace,
            selected_input={"sheet": "Assessment", "rows": [2]},
        )
        self.assertIn(
            "LEGACY_MAPPING_UNRESOLVED:EvidenceSource:LEGACY-SOURCE-001",
            preview.warnings,
        )

        with self.assertRaisesRegex(
            FoundationPackageValidationError,
            "Injected mid-import rollback",
        ):
            commit_foundation_package(
                preview,
                workspace=self.workspace,
                actor_identifier="fixture-coder",
                inject_failure_after=1,
            )
        self.assertFalse(Actor.objects.filter(pk=actor_id).exists())
        self.assertFalse(ImportRun.objects.exists())
        self.assertFalse(LegacyCompatibilityReceipt.objects.exists())

        receipt = commit_foundation_package(
            preview,
            workspace=self.workspace,
            actor_identifier="fixture-coder",
        )
        imported = Actor.objects.get(pk=actor_id)
        run = ImportRun.objects.get(pk=receipt.id)
        compatibility = LegacyCompatibilityReceipt.objects.get(pk=compatibility_id)
        self.assertEqual(imported.code, "ACTOR-IMPORTED-001")
        self.assertEqual(imported.metadata, {"fixture": "atomic-import"})
        self.assertEqual(run.checksum, preview.checksum)
        self.assertEqual(run.package_id, "IMPORT-FIX-001")
        self.assertEqual(run.package_version, FOUNDATION_PACKAGE_VERSION)
        self.assertEqual(run.schema_version, "2.0.0")
        self.assertEqual(run.template_version, "fixture-template-1")
        self.assertEqual(run.method_version, "OPEN_METHOD")
        self.assertEqual(run.ontology_version, "4.0.0")
        self.assertEqual(run.dataset_version, "fixture-dataset-1")
        self.assertEqual(run.adapter, "json")
        self.assertEqual(run.selected_input["sheet"], "Assessment")
        self.assertEqual(run.selected_input["rows"], [2])
        self.assertEqual(run.selected_input["raw_input_kind"], "CANONICAL_MAPPING")
        self.assertEqual(run.selected_input["raw_input_sha256"], preview.raw_input_sha256)
        self.assertEqual(run.actor_identifier, "fixture-coder")
        self.assertEqual(run.row_counts["actors"], 1)
        self.assertEqual(run.row_counts["compatibility_receipts"], 1)
        self.assertEqual(compatibility.status, "UNRESOLVED")
        self.assertEqual(compatibility.reason, "No immutable document version is available.")

        run.warnings = []
        with self.assertRaises(ValidationError):
            run.save()

        with self.assertRaisesRegex(
            FoundationPackageConflictError,
            "exact package checksum",
        ):
            commit_foundation_package(
                preview,
                workspace=self.workspace,
                actor_identifier="fixture-coder",
            )
        imported.refresh_from_db()
        self.assertEqual(imported.label, "Imported actor")
        self.assertEqual(ImportRun.objects.count(), 1)

        changed = preview.payload_copy()
        changed["actors"][0]["label"] = "Forbidden overwrite"
        changed = seal_foundation_package(changed)
        with self.assertRaises(FoundationPackageConflictError):
            preview_foundation_package(changed, workspace=self.workspace)
        imported.refresh_from_db()
        self.assertEqual(imported.label, "Imported actor")

    @covers("FND-I03", "FND-I04", "FND-I05", "FND-I06", "FND-I07", "FND-M04")
    @materializes_fixtures("V4_ATOMIC_IMPORT_NO_OVERWRITE_FIXTURE_001")
    def test_import_attempt_orchestrator_records_rejection_after_rollback_and_allows_exact_retry(self):
        oversized_unicode = "🔥Ж" * 200
        malformed = {
            "package_id": f"INVALID / {oversized_unicode}",
            "schema_version": oversized_unicode,
            "template_version": oversized_unicode,
            "method_version": oversized_unicode,
            "ontology_version": oversized_unicode,
            "dataset_version": oversized_unicode,
            "manifest": {"not": "a canonical package"},
        }
        rejected = attempt_foundation_import(
            malformed,
            workspace=self.workspace,
            actor_identifier="fixture:rejected-import",
        )
        self.assertEqual(rejected.status, "REJECTED")
        self.assertFalse(rejected.report.valid)
        self.assertIsNotNone(rejected.receipt)
        rejected_run = ImportRun.objects.get(pk=rejected.receipt.id)
        self.assertEqual(rejected_run.status, "REJECTED")
        self.assertTrue(rejected_run.package_id.startswith("INVALID-"))
        for field in (
            "schema_version",
            "template_version",
            "method_version",
            "ontology_version",
            "dataset_version",
        ):
            self.assertLessEqual(len(getattr(rejected_run, field)), 64)
        rejected_audit = AuditEvent.objects.get(entity_id=rejected_run.id)
        self.assertEqual(rejected_audit.action, AuditAction.IMPORT)
        self.assertEqual(rejected_audit.after["status"], "REJECTED")
        self.assertFalse(Actor.objects.exists())
        self.assertFalse(ActorElementAssessment.objects.exists())
        self.assertFalse(ParameterValue.objects.exists())

        with tempfile.TemporaryDirectory() as temporary_directory:
            invalid_path = Path(temporary_directory) / "malformed-unicode-package.json"
            invalid_path.write_text(
                json.dumps(malformed, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(CommandError, "REJECTED receipt="):
                call_command(
                    "import_foundation_package",
                    str(invalid_path),
                    workspace=str(self.workspace.id),
                    adapter="json",
                    commit=True,
                    actor="fixture:command-rejected-import",
                    stdout=io.StringIO(),
                )
        self.assertEqual(
            ImportRun.objects.filter(status="REJECTED").count(),
            2,
        )
        self.assertFalse(Actor.objects.exists())

        package = assessment_import_package(self.workspace)
        failed_attempt = attempt_foundation_import(
            package,
            workspace=self.workspace,
            actor_identifier="fixture:injected-rollback",
            inject_failure_after=5,
        )
        self.assertIn(failed_attempt.status, {"REJECTED", "FAILED"})
        self.assertFalse(failed_attempt.report.valid)
        self.assertIsNotNone(failed_attempt.report.preview)
        self.assertIsNotNone(failed_attempt.receipt)
        failed_run = ImportRun.objects.get(pk=failed_attempt.receipt.id)
        self.assertEqual(failed_run.status, failed_attempt.status)
        self.assertEqual(failed_run.checksum, failed_attempt.report.preview.checksum)
        self.assertTrue(failed_run.errors)
        self.assertFalse(Actor.objects.exists())
        self.assertFalse(ActorElementAssessment.objects.exists())
        self.assertFalse(ParameterValue.objects.exists())

        committed = attempt_foundation_import(
            package,
            workspace=self.workspace,
            actor_identifier="fixture:exact-retry",
        )
        self.assertEqual(committed.status, "COMMITTED")
        self.assertTrue(committed.report.valid)
        self.assertIsNotNone(committed.receipt)
        committed_run = ImportRun.objects.get(pk=committed.receipt.id)
        self.assertEqual(committed_run.status, "COMMITTED")
        self.assertEqual(committed_run.checksum, failed_run.checksum)
        self.assertEqual(
            set(
                ImportRun.objects.filter(checksum=failed_run.checksum).values_list(
                    "status", flat=True
                )
            ),
            {failed_attempt.status, "COMMITTED"},
        )
        self.assertEqual(ActorElementAssessment.objects.count(), 1)
        self.assertEqual(ParameterValue.objects.count(), 2)

    @covers("FND-V04")
    @exercises_fixtures(
        "ZHANAOZEN_V4_TRACE_FIXTURE_001",
        "V4_DOCUMENTVERSION_ANCHOR_FIXTURE_001",
    )
    def test_import_export_import_round_trip_preserves_exact_document_version_identity(self):
        content = "Alpha document captured."
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        exact_text = "document"
        exact_text_hash = hashlib.sha256(exact_text.encode("utf-8")).hexdigest()
        version_id = "32000000-0000-4000-8000-000000000003"
        package = minimal_foundation_package(self.workspace)
        package["sources"] = [
            {
                "id": "32000000-0000-4000-8000-000000000001",
                "code": "SOURCE-ROUNDTRIP-001",
                "version": "1.0.0",
                "metadata": {},
                "name": "Round-trip source",
                "publisher": "Independent publisher",
                "independence_group": "PUBLISHER-ROUNDTRIP-001",
                "independence_status": SourceIndependenceStatus.INDEPENDENT,
                "homepage_url": "https://example.test/source",
            }
        ]
        package["documents"] = [
            {
                "id": "32000000-0000-4000-8000-000000000002",
                "code": "DOCUMENT-ROUNDTRIP-001",
                "version": "1.0.0",
                "metadata": {},
                "source_code": "SOURCE-ROUNDTRIP-001",
                "title": "Exact round-trip document",
                "canonical_url": "https://example.test/source/document",
                "published_on": "2022-01-01",
                "accessed_on": "2022-01-02",
            }
        ]
        package["document_versions"] = [
            {
                "id": version_id,
                "code": "DOCUMENT-VERSION-ROUNDTRIP-001",
                "version": "1.0.0",
                "metadata": {},
                "document_code": "DOCUMENT-ROUNDTRIP-001",
                "supersedes_code": None,
                "status": DocumentVersionStatus.CONTENT_CAPTURED,
                "capture_url": "https://example.test/source/document",
                "captured_at": "2022-01-02T10:00:00Z",
                "checksum": checksum,
                "media_type": "text/plain",
            }
        ]
        package["document_contents"] = [
            {
                "id": "32000000-0000-4000-8000-000000000004",
                "code": "DOCUMENT-CONTENT-ROUNDTRIP-001",
                "version": "1.0.0",
                "metadata": {},
                "document_version_code": "DOCUMENT-VERSION-ROUNDTRIP-001",
                "encoding": "UTF8",
                "normalization_version": "plain-text-v1",
                "content": content,
                "checksum": checksum,
            }
        ]
        package["text_fragments"] = [
            {
                "id": "32000000-0000-4000-8000-000000000005",
                "code": "TEXT-FRAGMENT-ROUNDTRIP-001",
                "version": "1.0.0",
                "metadata": {},
                "document_version_code": "DOCUMENT-VERSION-ROUNDTRIP-001",
                "anchor_status": AnchorStatus.EXACT,
                "start_offset": 6,
                "end_offset": 14,
                "selector": {"type": "TextPositionSelector", "start": 6, "end": 14},
                "page": "",
                "section": "",
                "exact_text": exact_text,
                "exact_text_sha256": exact_text_hash,
            }
        ]
        package = seal_foundation_package(package)
        first_preview = preview_foundation_package(package, workspace=self.workspace)
        commit_foundation_package(
            first_preview,
            workspace=self.workspace,
            actor_identifier="roundtrip-coder",
        )

        exported = export_foundation_package(self.workspace)
        validate_foundation_package(exported)
        exported_version = exported["document_versions"][0]
        self.assertEqual(exported_version["id"], version_id)
        self.assertEqual(exported_version["checksum"], checksum)
        self.assertEqual(exported["text_fragments"][0]["document_version_code"], exported_version["code"])

        with self.assertRaises(RestrictedError):
            self.workspace.delete()
        with self.assertRaises(ValidationError):
            Document.objects.get(code="DOCUMENT-ROUNDTRIP-001").delete()
        with self.assertRaises(ValidationError):
            Source.objects.get(code="SOURCE-ROUNDTRIP-001").delete()
        captured_again = DocumentVersion.objects.get(pk=version_id)
        self.assertEqual(captured_again.content_sha256, checksum)
        self.assertEqual(captured_again.content.document_version_id, captured_again.id)
        with self.assertRaises(FoundationPackageConflictError):
            preview_foundation_package(exported, workspace=self.workspace)
        self.assertEqual(
            canonical_json(export_foundation_package(self.workspace)),
            canonical_json(exported),
        )
        self.assertEqual(ImportRun.objects.count(), 1)


class FoundationAuditContractTests(FoundationFactoryMixin, TestCase):
    def setUp(self):
        self.make_foundation(suffix="AUDIT")

    @covers("FND-V02")
    def test_create_publish_freeze_and_import_are_attributed_append_only_audit_events(self):
        actor_identifier = "foundation-owner"
        created = record_foundation_audit(
            workspace=self.workspace,
            action=AuditAction.CREATE,
            actor_identifier=actor_identifier,
            entity_type="PROJECT_WORKSPACE",
            entity_id=self.workspace.id,
            after={"code": self.workspace.code},
        )

        successor_manifest = {
            "ontology_version": "4.0.1",
            "project": self.project.code,
        }
        successor = clean_save(
            ProjectDefinitionVersion(
                project=self.project,
                code="DEF-AUDIT-NEXT",
                version="4.0.1",
                schema_version="2.0.0",
                semantic_version="4.0.1",
                construct_version="4.0.1",
                manifest=successor_manifest,
                manifest_hash=manifest_hash(successor_manifest),
                supersedes=self.definition,
            )
        )
        validate_project_definition(
            successor,
            audit_workspace=self.workspace,
            actor_identifier=actor_identifier,
            validation_result={"valid": True, "checks": ["schema", "semantics"]},
        )
        successor.refresh_from_db()
        self.assertEqual(successor.publication_status, PublicationStatus.VALIDATED)
        self.assertEqual(successor.validated_by, actor_identifier)
        self.assertIsNotNone(successor.validated_at)
        validated_manifest = successor.manifest
        successor.manifest = {"forbidden": "validated byte mutation"}
        successor.schema_version = "forbidden-validated-mutation"
        with self.assertRaises(ValidationError):
            successor.save()
        successor.refresh_from_db()
        self.assertEqual(successor.manifest, validated_manifest)
        self.assertEqual(successor.schema_version, "2.0.0")
        publish_project_definition(
            successor,
            audit_workspace=self.workspace,
            actor_identifier=actor_identifier,
        )
        successor.refresh_from_db()
        self.assertEqual(successor.publication_status, PublicationStatus.PUBLISHED)
        self.assertEqual(successor.published_by, actor_identifier)
        successor.manifest = {"forbidden": "published mutation"}
        with self.assertRaises(ValidationError):
            successor.save()
        successor.refresh_from_db()
        self.assertEqual(successor.manifest, successor_manifest)

        self.workspace.refresh_from_db()
        package = minimal_foundation_package(self.workspace)
        import_preview = preview_foundation_package(package, workspace=self.workspace)
        commit_foundation_package(
            import_preview,
            workspace=self.workspace,
            actor_identifier=actor_identifier,
        )

        assessment_set = clean_save(
            AssessmentSet(
                project=self.project,
                workspace=self.workspace,
                code="SET-AUDIT",
                version="1.0.0",
                kind=AssessmentKind.HUMAN,
                name="Audit set",
            )
        )
        expert = clean_save(
            ExpertProfile(
                workspace=self.workspace,
                code="EXPERT-AUDIT",
                version="1.0.0",
                kind=AssessmentKind.HUMAN,
                display_name="Audit expert",
                identity_key="expert:audit",
            )
        )
        experiment = clean_save(
            Experiment(
                workspace=self.workspace,
                expert_profile=expert,
                assessment_set=assessment_set,
                code="EXPERIMENT-AUDIT",
                version="1.0.0",
                name="Audit experiment",
                experiment_type=ExperimentType.ASSESSMENT,
                status=ExperimentStatus.DRAFT,
                method_version="METHOD-1",
            )
        )
        freeze_experiment(experiment, actor_identifier=actor_identifier)

        events = AuditEvent.objects.filter(workspace=self.workspace)
        self.assertEqual(
            set(events.values_list("action", flat=True)),
            {
                AuditAction.CREATE,
                AuditAction.VALIDATE,
                AuditAction.PUBLISH,
                AuditAction.FREEZE,
                AuditAction.IMPORT,
            },
        )
        self.assertEqual(
            set(events.values_list("actor_identifier", flat=True)),
            {actor_identifier},
        )
        self.assertEqual(
            events.get(action=AuditAction.CREATE).entity_id,
            self.workspace.id,
        )
        self.assertEqual(
            events.get(action=AuditAction.PUBLISH).entity_id,
            successor.id,
        )
        self.assertEqual(
            events.get(action=AuditAction.FREEZE).entity_id,
            experiment.id,
        )
        import_event = events.get(action=AuditAction.IMPORT)
        self.assertEqual(import_event.entity_id, ImportRun.objects.get().id)

        created.after = {"code": "mutated"}
        with self.assertRaises(ValidationError):
            created.save()
        with self.assertRaises(ValidationError):
            created.delete()


class PublicContractStaticTests(SimpleTestCase):
    @property
    def schema(self) -> dict:
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "services"
            / "schemas"
            / "foundation-package-2.0.0.schema.json"
        )
        return json.loads(schema_path.read_text(encoding="utf-8"))

    @covers("FND-O03", "FND-O04", "FND-I01", "FND-I08")
    @exercises_fixtures("V4_UNKNOWN_NOT_ZERO_FIXTURE_001")
    def test_v4_public_schema_is_adapter_neutral_and_legacy_terms_are_not_public_entities(self):
        properties = set(self.schema["properties"])
        self.assertTrue(
            {
                "actors",
                "analytical_elements",
                "actor_element_assessments",
                "sources",
                "documents",
                "document_versions",
                "text_fragments",
                "facts",
            }.issubset(properties)
        )
        legacy_sections = {
            "project_schema_versions",
            "tension_points",
            "participant_groups",
            "group_tension_relations",
            "evidence_sources",
            "evidence_links",
            "calculation_strategies",
            "scenarios",
            "scenario_overrides",
        }
        self.assertTrue(legacy_sections.isdisjoint(properties))
        self.assertTrue(
            legacy_sections.isdisjoint(self.schema.get("required", []))
        )
        v1_compatibility_schema = (
            Path(__file__).resolve().parents[1]
            / "services"
            / "schemas"
            / "project-package-1.0.0.schema.json"
        )
        self.assertTrue(v1_compatibility_schema.is_file())

        from domain.admin import HiddenLegacyCompatibilityAdmin

        for legacy_model in (
            CalculationStrategyDefinition,
            Scenario,
            ScenarioOverride,
        ):
            registered_admin = django_admin.site._registry[legacy_model]
            self.assertIsInstance(
                registered_admin,
                HiddenLegacyCompatibilityAdmin,
            )
            self.assertFalse(registered_admin.has_module_permission(None))
        model_field_names = {
            field.name
            for model in (Actor, AnalyticalElement, ProjectWorkspace)
            for field in model._meta.get_fields()
        }
        self.assertFalse(
            any(
                name.startswith(("xls_", "sheet_", "column_", "row_"))
                for name in model_field_names
            )
        )

    @covers("FND-I02")
    def test_canonical_schema_requires_version_and_stable_identity(self):
        required = set(self.schema["required"])
        self.assertTrue(
            {
                "format_version",
                "schema_version",
                "template_version",
                "method_version",
                "ontology_version",
                "dataset_version",
            }.issubset(required)
        )
        entity_required = set(self.schema["$defs"]["entity_base"]["required"])
        self.assertTrue({"id", "code", "version"}.issubset(entity_required))

    @covers("FND-M01", "FND-M02")
    def test_ci_pins_exact_base_and_runs_the_complete_pr21_regression_suite(self):
        repository_root = Path(__file__).resolve().parents[4]
        workflow_path = repository_root / ".github" / "workflows" / "conflict-analysis.yml"
        workflow = workflow_path.read_text(encoding="utf-8")
        self.assertIn("f940a91a92658285063802ee1a43bf84360fc013", workflow)
        self.assertIn("1125b01a90da3ea324e661d729a845c58febb8e2", workflow)
        self.assertIn("git merge-base --is-ancestor", workflow)
        self.assertIn("python -m pytest domain/tests", workflow)
        self.assertIn('USE_SQLITE: "true"', workflow)
        self.assertTrue((Path(__file__).parent / "test_data_foundation.py").is_file())
        self.assertTrue(
            (Path(__file__).parent / "test_postgresql_migrations.py").is_file()
        )

    def test_foundation_gate_disables_live_network_and_model_access_during_tests(self):
        repository_root = Path(__file__).resolve().parents[4]
        workflow = (
            repository_root / ".github" / "workflows" / "conflict-analysis.yml"
        ).read_text(encoding="utf-8")
        for marker in (
            'HTTP_PROXY: "http://127.0.0.1:9"',
            'HTTPS_PROXY: "http://127.0.0.1:9"',
            'OPENAI_API_KEY: ""',
            'HF_HUB_OFFLINE: "1"',
            'TRANSFORMERS_OFFLINE: "1"',
        ):
            self.assertIn(marker, workflow)

        service_source = (
            Path(__file__).resolve().parents[1]
            / "services"
            / "foundation_packages.py"
        ).read_text(encoding="utf-8")
        self.assertFalse(
            any(
                forbidden in service_source
                for forbidden in (
                    "import openai",
                    "from openai",
                    "import requests",
                    "from requests",
                    "import httpx",
                    "from httpx",
                )
            )
        )

    def test_public_foundation_contract_contains_no_forbidden_scope(self):
        canonical_models = (
            ProjectWorkspace,
            ProjectDefinitionVersion,
            Actor,
            AnalyticalElement,
            ActorElementAssessment,
            ParameterValue,
            Source,
            Document,
            DocumentVersion,
            TextFragment,
            Fact,
            PowerProfile,
            PowerComponent,
        )
        public_field_names = {
            field.name.lower()
            for model in canonical_models
            for field in model._meta.get_fields()
            if getattr(field, "concrete", False)
        }
        self.assertTrue(
            public_field_names.isdisjoint(
                {
                    "total_power",
                    "scalar_power",
                    "pow",
                    "calculated_risk",
                    "conflict_danger_score",
                    "violence_probability",
                    "early_warning_score",
                    "dangerous_actor",
                    "recommendation",
                    "ranking",
                    "response_engine",
                }
            )
        )

        def schema_keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield key.lower()
                    yield from schema_keys(child)
            elif isinstance(value, list):
                for child in value:
                    yield from schema_keys(child)

        self.assertTrue(
            set(schema_keys(self.schema)).isdisjoint(
                {
                    "total_power",
                    "scalar_power",
                    "pow",
                    "calculated_risk",
                    "conflict_danger_score",
                    "violence_probability",
                    "early_warning_score",
                    "recommendations",
                    "rankings",
                    "scenarios",
                }
            )
        )

        import domain.services.foundation_packages as foundation_service

        public_callables = {
            name.lower()
            for name, member in inspect.getmembers(foundation_service)
            if callable(member) and not name.startswith("_")
        }
        self.assertFalse(
            any(
                token in name
                for name in public_callables
                for token in (
                    "predict",
                    "early_warning",
                    "violence_probability",
                    "calculate_risk",
                    "recommend",
                    "rank",
                    "response_engine",
                    "scenario_model",
                )
            )
        )


class AcceptanceTraceabilityTests(SimpleTestCase):
    def test_every_matrix_row_and_fixture_family_has_a_semantic_test(self):
        requirement_ids: set[str] = set()
        fixture_ids: set[str] = set()
        materialized_fixture_ids: set[str] = set()
        module = inspect.getmodule(self)
        assert module is not None
        from domain.tests import test_postgresql_migrations

        for test_module in (module, test_postgresql_migrations):
            for _, candidate in inspect.getmembers(test_module, inspect.isclass):
                if not issubclass(candidate, (SimpleTestCase, TestCase)):
                    continue
                for _, method in inspect.getmembers(candidate, inspect.isfunction):
                    requirement_ids.update(
                        getattr(method, "acceptance_requirements", frozenset())
                    )
                    fixture_ids.update(
                        getattr(method, "fixture_families", frozenset())
                    )
                    materialized_fixture_ids.update(
                        getattr(
                            method,
                            "materialized_fixture_families",
                            frozenset(),
                        )
                    )

        self.assertEqual(requirement_ids, ALL_MATRIX_REQUIREMENTS)
        self.assertEqual(fixture_ids, FIXTURE_FAMILIES)
        self.assertEqual(materialized_fixture_ids, FIXTURE_FAMILIES)
