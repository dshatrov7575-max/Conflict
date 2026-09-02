#!/usr/bin/env python3
"""Verify the exact Production Studio and Foundation slice boundaries."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile


PINNED_BASE_HEAD = "5f73ebf2fd29a161a34ea047c7eead4fb0c582d4"
PINNED_BASE_TREE = "ea5ff9ab510cb76f0c2b1bfda1c02c1278812aae"
PINNED_DOMAIN_TREE = "8e737658c80fe5f489b8d810f82fd8828c33fb13"

PINNED_R0_BASE_HEAD = "ca16f7a99ff044f7fbccb83354d5a9112c99027a"
PINNED_R0_BASE_TREE = "c25848dbbb19aabd5a2d4d642b69c66254879059"
PINNED_R0_DOMAIN_TREE = "51279fb4d656ed42e5da3b18d7922380dce3800d"
PINNED_R0_MIGRATIONS_TREE = "b0cc214cd63086172c9d3801338a5a2302a7ce0f"
PINNED_R0_PRODUCTION_STUDIO_TREE = "87d8e93ec09a18b87ae016977f0fb5fbf67d4104"
PINNED_R0_MODELS_BLOB = "c6c5c2419989e7b0cf40bd1242ab65d37cc2e162"
PINNED_R0_ENUMS_BLOB = "a701c3c83511b7d1706519d40fab4580d0a0d63e"
PINNED_R0_CLAIM_CONTRACTS_TREE = "737ff552664913fd87496bc2dfb0499389cea3c4"
PINNED_C1_START_HEAD = "bd6e88c2a5f6552e057ea5b49fc63a1eb77ef4c6"
PINNED_C1_START_TREE = "e1124839da8571408c258517c8afdf24622f1655"
PINNED_FD02_BASE_HEAD = "bbe852d2f30f1be042e9cd8c35a52fd120d65ae4"
PINNED_FD02_BASE_TREE = "838364d0f10a9517160a6bb0a81b547f121e2447"
PINNED_FD02_DOMAIN_TREE = "51279fb4d656ed42e5da3b18d7922380dce3800d"
PINNED_FD03_BASE_HEAD = "6b7d8977f9798fa21b9ccc3d12f9410a5165d6b5"
PINNED_FD03_BASE_TREE = "09f9a2f93b0e63f7d90863131ffbe799b17475bf"
PINNED_FD03_BASE_DOMAIN_TREE = "e47f058218efb79e04b52d4434f9e72f9f91a901"
PINNED_FD03_RC2_START_HEAD = "bee7335d441c0b5d6d3501481fb14fb62a5de7a8"
PINNED_FD03_RC2_START_TREE = "a94e9c08bdc67d3f6b2e04952de44ac3f8339f99"
PINNED_FD06_BASE_HEAD = "feefd3899b5a168e650ddb3094881f48830acb96"
PINNED_FD06_BASE_TREE = "0dad3448608b3bbab28c7f1bfc7399c30382a343"
PINNED_FD06_BASE_DOMAIN_TREE = "8fd38b8d56177527473ac652978594593773c973"
PINNED_FD06_PRODUCTION_STUDIO_TREE = "31ba7273cfe4a6ae3c57054518de2e2ba98113ff"
PINNED_FD06_RC4_INTERMEDIATE_HEAD = "0dd4ae788c765a0a0c24ac4d61582870d73e29e2"
PINNED_FD06_RC4_INTERMEDIATE_TREE = "b59baccfa73ba6b9cce6e89419cb540005564b64"
FD06_BASE_BRANCH = "codex/ca-suite-i1-foundation-fd03-lifecycle-read-result"
FD06_TARGET_BRANCH = (
    "codex/ca-suite-i1-foundation-fd06-publication-reconciliation"
)
FD06_EXACT_PATH_COUNT = 10
FD06_POSTGRESQL_TOTAL = 227
FD06_POSTGRESQL_SKIPPED = 0
FD06_SQLITE_PASSED = 212
FD06_SQLITE_SKIPPED = 15
PINNED_FD07_BASE_HEAD = "b161ed387b3aec90bb8e4010e665fbe35d4b9ea6"
PINNED_FD07_BASE_TREE = "42dab05a7cbf99e8e71f127ad196139da8b46734"
PINNED_FD07_BASE_DOMAIN_TREE = "813315e1f2850fe8ebc5971eb3194721d636cc6f"
FD07_BASE_BRANCH = FD06_TARGET_BRANCH
FD07_TARGET_BRANCH = "codex/ca-suite-i1-foundation-fd07-publication-readiness"
FD07_EXACT_PATH_COUNT = 8
FD07_POSTGRESQL_TOTAL = 236
FD07_POSTGRESQL_SKIPPED = 0
FD07_SQLITE_PASSED = 221
FD07_SQLITE_SKIPPED = 15
PINNED_F0L_BASE_HEAD = "710b88f0db9ec2f0e2fae65c7e0c77025115771a"
PINNED_F0L_BASE_TREE = "0a15bd4d6993f87199329d0907be372aec9e69ca"
F0L_BASE_BRANCH = FD07_TARGET_BRANCH
F0L_TARGET_BRANCH = "codex/ca-suite-i1-project-language-bootstrap-f0l"
F0L_RATIFIED_EXISTING_COMMITS = (
    "545e24231673b2c113bde064f835aa24c7d7b10d",
    "79b03a653a1c9c675fba49d09ac61933ec07f114",
    "0f67adabf697f1be67daa5a07b68bc0731954bb0",
    "a6363f8206ed0276ee40fd3c652bf572c872e2b8",
)
PINNED_F0L_CORRECTION_4_HEAD = F0L_RATIFIED_EXISTING_COMMITS[-1]
PINNED_F0L_CORRECTION_4_TREE = "f3869f7e66d3fe9601b937df196f03b1de51aee0"
F0L_CORRECTION_4_PATHS = frozenset(
    {
        "software/conflict_analysis/domain/models.py",
        "software/conflict_analysis/domain/tests/test_data_foundation.py",
        "software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py",
    }
)
F0L_CORRECTION_5_PATHS = frozenset(
    {
        ".github/workflows/conflict-analysis.yml",
        "software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py",
    }
)
F1_TARGET_BRANCH = "codex/ca-suite-i1-evidence-multilingual-f1"
C2A_TARGET_BRANCH = (
    "codex/ca-suite-i1-production-studio-c2a-lifecycle-publication"
)
F0L_EXACT_PATH_COUNT = 26
F0L_NEW_PATH_COUNT = 4
F0L_PORTABLE_TEST_COUNT = 16
F0L_POSTGRESQL_MIGRATION_TEST_COUNT = 2
F0L_FOUNDATION_POSTGRESQL_PASSED = 254
F0L_FOUNDATION_SQLITE_PASSED = 237
F0L_FOUNDATION_SQLITE_SKIPPED = 17
F0L_LANGUAGE_LOOKUP_PREFIXES = (
    "primary_language_tag__",
    "primary_language_assignment__",
)
F0L_ASYNC_ORM_ENTRYPOINTS = (
    "acreate",
    "aget_or_create",
    "aupdate_or_create",
    "aupdate",
    "abulk_create",
    "abulk_update",
)
F1_PORTABLE_TEST_CLASS = "MultilingualEvidenceLineageTests"
F1_PORTABLE_TEST_METHODS = (
    "test_fact_category_is_project_scoped_versioned_and_path_is_deterministic",
    "test_category_self_cycle_cross_project_reparent_and_delete_fail_closed",
    "test_fact_classification_status_is_assignment_state_and_fact_type_remains_separate",
    "test_legacy_facts_remain_unclassified_without_identity_or_evidence_drift",
    "test_monolingual_content_is_synchronized_without_fabricated_translation_provenance",
    "test_complete_one_to_one_one_to_many_and_many_to_one_alignment_is_checksum_bound",
    "test_partial_positional_contradictory_or_many_to_many_alignment_is_never_synchronized",
    "test_translation_provenance_preserves_exact_known_fields_and_explicit_unknowns",
    "test_any_primary_translation_edit_creates_unsynchronized_derivative_and_preserves_history",
    "test_explicit_complete_realign_creates_new_synchronized_derivative_without_mutation",
    "test_memory_origin_fact_returns_typed_no_document_evidence",
    "test_multiple_document_evidence_is_deterministic_without_truth_or_independence_inference",
    "test_synchronized_drilldown_resolves_exact_primary_and_original_fragments",
    "test_unsynchronized_drilldown_returns_alignment_not_guaranteed_without_guessed_original",
    "test_drilldown_authorizes_before_disclosure_and_performs_zero_writes",
    "test_noncanonical_in_place_or_bypass_mutations_fail_closed",
)
F1_MIGRATION_TEST_CLASS = "MultilingualEvidenceLineageMigrationTests"
F1_MIGRATION_TEST_METHODS = (
    "test_0016_to_0017_preserves_project_language_and_all_legacy_evidence_identities",
    "test_0017_reverse_reapply_and_empty_database_are_deterministic",
)
F1_NEW_PATHS = frozenset(
    {
        "software/conflict_analysis/domain/migrations/0017_multilingual_evidence_lineage.py",
        "software/conflict_analysis/domain/services/document_lineage.py",
        "software/conflict_analysis/domain/services/evidence_drilldown.py",
        "software/conflict_analysis/domain/api/evidence.py",
        "software/conflict_analysis/domain/tests/test_multilingual_evidence_lineage.py",
        "software/conflict_analysis/docs/adr/0012-multilingual-evidence-document-lineage.md",
    }
)
F1_FROZEN_PATHS = (
    ".github/workflows/conflict-analysis.yml",
    "software/conflict_analysis/pyproject.toml",
    "software/conflict_analysis/production_studio",
    "software/conflict_analysis/domain/migrations/0016_project_primary_language.py",
    "software/conflict_analysis/domain/services/language_tags.py",
    "software/conflict_analysis/domain/services/project_definitions.py",
    "software/conflict_analysis/domain/api/studio_definitions.py",
    "software/conflict_analysis/domain/services/seed.py",
    "software/conflict_analysis/domain/services/project_packages.py",
    "software/conflict_analysis/domain/services/schemas/project-package-1.1.0.schema.json",
    "software/conflict_analysis/docs/adr/0011-project-primary-language-bootstrap.md",
)
F1_FOCUSED_POSTGRESQL_TOTAL = 18
F1_FOCUSED_SQLITE_PASSED = 16
F1_FOCUSED_SQLITE_SKIPPED = 2
F1_FOUNDATION_POSTGRESQL_TOTAL = 272
F1_FOUNDATION_SQLITE_PASSED = 253
F1_FOUNDATION_SQLITE_SKIPPED = 19

C2A_PORTABLE_TEST_CLASS = "ProductionStudioLifecyclePublicationTests"
C2A_PORTABLE_TEST_METHODS = (
    "test_route_auth_and_checksum_bound_claim_contract_are_exact",
    "test_initial_draft_uses_optional_preview_then_atomic_publication_without_prior_validate",
    "test_validation_unknown_outcome_allows_only_explicit_same_request_reconciliation",
    "test_fd07_never_labels_standalone_or_validated_initial_as_publishable_and_is_refetched_before_attempt",
    "test_successor_draft_validates_then_fd07_allows_only_exact_successor_publication",
    "test_publication_unknown_outcome_disables_post_and_uses_only_operation_recovery_get",
    "test_operation_identity_and_receipts_never_enter_browser_persistent_storage",
    "test_current_noncurrent_retired_and_unknown_lifecycle_states_render_truthfully",
    "test_typed_auth_scope_capability_csrf_stale_reuse_and_state_conflicts_are_bounded",
    "test_package_science_chat_document_prediction_and_recommendation_controls_remain_unavailable",
    "test_dirty_busy_unresolved_navigation_and_unload_are_guarded_without_automatic_mutation",
    "test_publication_requires_human_retained_recovery_ticket_and_busy_unload_is_guarded",
    "test_recovery_ticket_and_post_share_one_frozen_attempt_and_edits_require_new_operation",
)
C2A_CHROMIUM_TEST_METHODS = (
    "test_chromium_draft_preview_atomic_initial_publish_recover_and_reload",
    "test_chromium_successor_validate_publish_lost_response_recovery_and_predecessor_noncurrent",
)
C2A_NEW_PATHS = frozenset(
    {
        "software/conflict_analysis/docs/adr/0009-production-studio-c-lifecycle-publication.md",
        "software/conflict_analysis/production_studio/lifecycle_claim_boundaries.py",
        "software/conflict_analysis/production_studio/contracts/lifecycle_publication_claim_boundaries_v1.ru.json",
        "software/conflict_analysis/production_studio/contracts/lifecycle_publication_claim_boundaries_v1.ru.json.sha256",
        "software/conflict_analysis/production_studio/static/production_studio/lifecycle_publication.css",
        "software/conflict_analysis/production_studio/static/production_studio/lifecycle_publication.js",
        "software/conflict_analysis/production_studio/templates/production_studio/lifecycle_publication_definition.html",
        "software/conflict_analysis/production_studio/tests/test_lifecycle_publication.py",
        "software/conflict_analysis/production_studio/browser_tests/lifecycle_publication.mjs",
    }
)
C2A_FROZEN_PATHS = (
    "software/conflict_analysis/pyproject.toml",
    "software/conflict_analysis/production_studio/templates/production_studio/audited_draft_entry.html",
    "software/conflict_analysis/production_studio/tests/test_audited_authoring.py",
    "software/conflict_analysis/production_studio/browser_tests/audited_authoring.mjs",
    "software/conflict_analysis/domain/models.py",
    "software/conflict_analysis/domain/migrations/0016_project_primary_language.py",
    "software/conflict_analysis/domain/services/language_tags.py",
    "software/conflict_analysis/domain/services/project_definitions.py",
    "software/conflict_analysis/domain/api/studio_definitions.py",
    "software/conflict_analysis/domain/services/seed.py",
    "software/conflict_analysis/domain/services/project_packages.py",
    "software/conflict_analysis/domain/services/schemas/project-package-1.1.0.schema.json",
    "software/conflict_analysis/docs/adr/0011-project-primary-language-bootstrap.md",
)
C2A_PORTABLE_TOTAL = 13
C2A_CHROMIUM_TOTAL = 2
C2A_FOUNDATION_POSTGRESQL_TOTAL = 254
C2A_FOUNDATION_SQLITE_PASSED = 237
C2A_FOUNDATION_SQLITE_SKIPPED = 17
SUCCESSOR_C0_TOTAL = 19
SUCCESSOR_C1_PORTABLE_TOTAL = 8
SUCCESSOR_C1_CHROMIUM_TOTAL = 1

SUCCESSOR_WHEEL_NAME = "conflict_analysis-0.1.0-py3-none-any.whl"
SUCCESSOR_EVIDENCE_SCHEMA = "POST_F0L_SUCCESSOR_CI_EVIDENCE_V1"
SUCCESSOR_MIGRATION_EVIDENCE_SCHEMA = "POST_F0L_MIGRATION_EVIDENCE_V1"
SUCCESSOR_WHEEL_EVIDENCE_SCHEMA = "POST_F0L_WHEEL_INSTALL_EVIDENCE_V1"
C2A_SYNTHETIC_EVIDENCE_SCHEMA = "C2A_SYNTHETIC_TREE_EVIDENCE_V1"
SUCCESSOR_JUNIT_FILES = {
    "F1": (
        "f1-focused-postgresql.xml",
        "f1-focused-sqlite.xml",
        "f1-foundation-postgresql.xml",
        "f1-foundation-sqlite.xml",
        "f1-c0-postgresql.xml",
        "f1-c0-sqlite.xml",
        "f1-c1-postgresql.xml",
        "f1-c1-sqlite.xml",
        "f1-c1-chromium-postgresql.xml",
    ),
    "C2A": (
        "c2a-portable-postgresql.xml",
        "c2a-portable-sqlite.xml",
        "c2a-foundation-postgresql.xml",
        "c2a-foundation-sqlite.xml",
        "c2a-c0-postgresql.xml",
        "c2a-c0-sqlite.xml",
        "c2a-c1-postgresql.xml",
        "c2a-c1-sqlite.xml",
        "c2a-c1-chromium-postgresql.xml",
        "c2a-chromium-postgresql.xml",
    ),
}
SUCCESSOR_MIGRATION_GATES = {
    "F1": (
        "compileall",
        "django_check",
        "makemigrations_check",
        "postgresql_clean_migrate_0017",
        "postgresql_0016_to_0017",
        "postgresql_0017_reverse_reapply",
        "postgresql_immutable_identity",
        "sqlite_clean_migrate_0017",
    ),
    "C2A": (
        "compileall",
        "django_check",
        "makemigrations_check",
        "postgresql_clean_migrate_0016",
        "sqlite_clean_migrate_0016",
        "migration_filenames_unchanged",
    ),
}
SUCCESSOR_WHEEL_CHECKS = {
    "F1": (
        "wheel_built_exactly_once",
        "isolated_install",
        "migration_0017_discovered",
        "document_lineage_imported",
        "evidence_drilldown_imported",
        "domain_api_evidence_imported",
        "adr_repository_only",
    ),
    "C2A": (
        "wheel_built_exactly_once",
        "isolated_install",
        "production_studio_imported",
        "lifecycle_claim_boundaries_imported",
        "contract_payload_present",
        "template_payload_present",
        "static_payload_present",
        "docs_repository_only",
    ),
}
SUCCESSOR_WHEEL_REQUIRED_MEMBERS = {
    "F1": frozenset(
        {
            "domain/__init__.py",
            "domain/migrations/__init__.py",
            "domain/migrations/0017_multilingual_evidence_lineage.py",
            "domain/services/__init__.py",
            "domain/services/document_lineage.py",
            "domain/services/evidence_drilldown.py",
            "domain/api/__init__.py",
            "domain/api/evidence.py",
        }
    ),
    "C2A": frozenset(
        {
            "production_studio/__init__.py",
            "production_studio/apps.py",
            "production_studio/lifecycle_claim_boundaries.py",
            "production_studio/urls.py",
            "production_studio/views.py",
            "production_studio/contracts/lifecycle_publication_claim_boundaries_v1.ru.json",
            "production_studio/contracts/lifecycle_publication_claim_boundaries_v1.ru.json.sha256",
            "production_studio/templates/production_studio/lifecycle_publication_definition.html",
            "production_studio/static/production_studio/lifecycle_publication.css",
            "production_studio/static/production_studio/lifecycle_publication.js",
        }
    ),
}
SUCCESSOR_REPOSITORY_ONLY_WHEEL_PATHS = {
    "F1": frozenset(
        {"docs/adr/0012-multilingual-evidence-document-lineage.md"}
    ),
    "C2A": frozenset(
        {
            "README.md",
            "docs/adr/0009-production-studio-c-lifecycle-publication.md",
            "docs/production-studio-c-read-only-runtime.md",
        }
    ),
}
_LOWER_HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
_LOWER_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")

ACTIVE_C0_ALLOWLIST = frozenset(
    {
        ".github/workflows/conflict-analysis.yml",
        "software/conflict_analysis/README.md",
        "software/conflict_analysis/conflict_analysis/settings.py",
        "software/conflict_analysis/conflict_analysis/urls.py",
        "software/conflict_analysis/docs/adr/0007-production-studio-c-read-only-first.md",
        "software/conflict_analysis/docs/production-studio-c-read-only-runtime.md",
        "software/conflict_analysis/production_studio/__init__.py",
        "software/conflict_analysis/production_studio/apps.py",
        "software/conflict_analysis/production_studio/browser_tests/cdp_client.mjs",
        "software/conflict_analysis/production_studio/browser_tests/read_only_smoke.mjs",
        "software/conflict_analysis/production_studio/claim_boundaries.py",
        "software/conflict_analysis/production_studio/contracts/read_only_claim_boundaries_v1.ru.json",
        "software/conflict_analysis/production_studio/contracts/read_only_claim_boundaries_v1.ru.json.sha256",
        "software/conflict_analysis/production_studio/static/production_studio/studio.css",
        "software/conflict_analysis/production_studio/static/production_studio/studio.js",
        "software/conflict_analysis/production_studio/templates/production_studio/definition.html",
        "software/conflict_analysis/production_studio/templates/production_studio/entry.html",
        "software/conflict_analysis/production_studio/tests/__init__.py",
        "software/conflict_analysis/production_studio/tests/test_browser_contract.py",
        "software/conflict_analysis/production_studio/tests/test_claim_boundaries.py",
        "software/conflict_analysis/production_studio/tests/test_read_only_http.py",
        "software/conflict_analysis/production_studio/tests/test_read_only_static_contracts.py",
        "software/conflict_analysis/production_studio/urls.py",
        "software/conflict_analysis/production_studio/views.py",
        "software/conflict_analysis/pyproject.toml",
        "software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py",
    }
)

ACTIVE_R0_ALLOWLIST = frozenset(
    {
        ".github/workflows/conflict-analysis.yml",
        "software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py",
    }
)

# Sealed exact 16-path delta against the accepted R0 authorization point;
# additions are not accepted through directory-prefix matching.
ACTIVE_C1_ALLOWLIST = frozenset(
    {
        ".github/workflows/conflict-analysis.yml",
        "software/conflict_analysis/README.md",
        "software/conflict_analysis/docs/adr/0008-production-studio-c-audited-draft.md",
        "software/conflict_analysis/docs/production-studio-c-read-only-runtime.md",
        "software/conflict_analysis/production_studio/authoring_claim_boundaries.py",
        "software/conflict_analysis/production_studio/browser_tests/audited_authoring.mjs",
        "software/conflict_analysis/production_studio/contracts/audited_draft_claim_boundaries_v1.ru.json",
        "software/conflict_analysis/production_studio/contracts/audited_draft_claim_boundaries_v1.ru.json.sha256",
        "software/conflict_analysis/production_studio/static/production_studio/audited_draft.css",
        "software/conflict_analysis/production_studio/static/production_studio/audited_draft.js",
        "software/conflict_analysis/production_studio/templates/production_studio/audited_draft_definition.html",
        "software/conflict_analysis/production_studio/templates/production_studio/audited_draft_entry.html",
        "software/conflict_analysis/production_studio/tests/test_audited_authoring.py",
        "software/conflict_analysis/production_studio/urls.py",
        "software/conflict_analysis/production_studio/views.py",
        "software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py",
    }
)

C1_FROZEN_PATHS = (
    "software/conflict_analysis/domain",
    "software/conflict_analysis/domain/migrations",
    "software/conflict_analysis/domain/models.py",
    "software/conflict_analysis/domain/enums.py",
    "software/conflict_analysis/domain/policies.py",
    "software/conflict_analysis/domain/services/foundation_packages.py",
    "software/conflict_analysis/domain/services/project_definitions.py",
    "software/conflict_analysis/domain/services/schemas",
    "software/conflict_analysis/production_studio/__init__.py",
    "software/conflict_analysis/production_studio/apps.py",
    "software/conflict_analysis/production_studio/browser_tests/cdp_client.mjs",
    "software/conflict_analysis/production_studio/claim_boundaries.py",
    "software/conflict_analysis/production_studio/contracts/read_only_claim_boundaries_v1.ru.json",
    "software/conflict_analysis/production_studio/contracts/read_only_claim_boundaries_v1.ru.json.sha256",
    "software/conflict_analysis/production_studio/static/production_studio/studio.css",
    "software/conflict_analysis/production_studio/static/production_studio/studio.js",
    "software/conflict_analysis/production_studio/templates/production_studio/definition.html",
    "software/conflict_analysis/production_studio/templates/production_studio/entry.html",
    "software/conflict_analysis/production_studio/browser_tests/read_only_smoke.mjs",
    "software/conflict_analysis/production_studio/tests/__init__.py",
    "software/conflict_analysis/production_studio/tests/test_browser_contract.py",
    "software/conflict_analysis/production_studio/tests/test_claim_boundaries.py",
    "software/conflict_analysis/production_studio/tests/test_read_only_http.py",
    "software/conflict_analysis/production_studio/tests/test_read_only_static_contracts.py",
)

ACTIVE_FD02_ALLOWLIST = frozenset(
    {
        ".github/workflows/conflict-analysis.yml",
        "software/conflict_analysis/docs/adr/0006-foundation-studio-application-gateways.md",
        "software/conflict_analysis/domain/content/studio_help_ru_v1.json",
        "software/conflict_analysis/domain/management/commands/provision_studio_help.py",
        "software/conflict_analysis/domain/services/studio_help_catalog.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_help_provisioning.py",
        "software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py",
    }
)

ACTIVE_FD03_ALLOWLIST = frozenset(
    {
        ".github/workflows/conflict-analysis.yml",
        "software/conflict_analysis/domain/urls.py",
        "software/conflict_analysis/domain/api/studio_definitions.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_http.py",
        "software/conflict_analysis/docs/adr/0006-foundation-studio-application-gateways.md",
        "software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py",
        "software/conflict_analysis/production_studio/tests/test_read_only_http.py",
    }
)

ACTIVE_FD06_ALLOWLIST = frozenset(
    {
        ".github/workflows/conflict-analysis.yml",
        "software/conflict_analysis/docs/adr/0006-foundation-studio-application-gateways.md",
        "software/conflict_analysis/domain/api/studio_definitions.py",
        "software/conflict_analysis/domain/policies.py",
        "software/conflict_analysis/domain/services/project_definitions.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_bootstrap.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_http.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_publication_reconciliation.py",
        "software/conflict_analysis/domain/urls.py",
        "software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py",
    }
)

ACTIVE_FD07_ALLOWLIST = frozenset(
    {
        ".github/workflows/conflict-analysis.yml",
        "software/conflict_analysis/docs/adr/0006-foundation-studio-application-gateways.md",
        "software/conflict_analysis/domain/api/studio_definitions.py",
        "software/conflict_analysis/domain/services/project_definitions.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_http.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_publication_readiness.py",
        "software/conflict_analysis/domain/urls.py",
        "software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py",
    }
)

ACTIVE_F0L_ALLOWLIST = frozenset(
    {
        ".github/workflows/conflict-analysis.yml",
        "software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py",
        "software/conflict_analysis/domain/models.py",
        "software/conflict_analysis/domain/migrations/0016_project_primary_language.py",
        "software/conflict_analysis/domain/services/language_tags.py",
        "software/conflict_analysis/domain/services/project_definitions.py",
        "software/conflict_analysis/domain/api/studio_definitions.py",
        "software/conflict_analysis/domain/services/seed.py",
        "software/conflict_analysis/domain/services/project_packages.py",
        "software/conflict_analysis/domain/services/schemas/project-package-1.1.0.schema.json",
        "software/conflict_analysis/domain/tests/test_data_foundation.py",
        "software/conflict_analysis/domain/tests/test_v4_foundation_contracts.py",
        "software/conflict_analysis/domain/tests/test_postgresql_migrations.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_bootstrap.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_package.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_http.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_write_reconciliation.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_publication_readiness.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_publication_reconciliation.py",
        "software/conflict_analysis/production_studio/static/production_studio/audited_draft.js",
        "software/conflict_analysis/production_studio/templates/production_studio/audited_draft_entry.html",
        "software/conflict_analysis/production_studio/tests/test_audited_authoring.py",
        "software/conflict_analysis/production_studio/tests/test_browser_contract.py",
        "software/conflict_analysis/production_studio/tests/test_read_only_http.py",
        "software/conflict_analysis/production_studio/browser_tests/audited_authoring.mjs",
        "software/conflict_analysis/docs/adr/0011-project-primary-language-bootstrap.md",
    }
)

F0L_NEW_PATHS = frozenset(
    {
        "software/conflict_analysis/domain/migrations/0016_project_primary_language.py",
        "software/conflict_analysis/domain/services/language_tags.py",
        "software/conflict_analysis/domain/services/schemas/project-package-1.1.0.schema.json",
        "software/conflict_analysis/docs/adr/0011-project-primary-language-bootstrap.md",
    }
)

F1_POST_F0L_ALLOWLIST = frozenset(
    {
        "software/conflict_analysis/domain/enums.py",
        "software/conflict_analysis/domain/models.py",
        "software/conflict_analysis/domain/migrations/0017_multilingual_evidence_lineage.py",
        "software/conflict_analysis/domain/services/document_lineage.py",
        "software/conflict_analysis/domain/services/evidence_drilldown.py",
        "software/conflict_analysis/domain/api/evidence.py",
        "software/conflict_analysis/domain/urls.py",
        "software/conflict_analysis/domain/tests/test_multilingual_evidence_lineage.py",
        "software/conflict_analysis/docs/adr/0012-multilingual-evidence-document-lineage.md",
    }
)

C2A_POST_F0L_ALLOWLIST = frozenset(
    {
        ".github/workflows/conflict-analysis.yml",
        "software/conflict_analysis/README.md",
        "software/conflict_analysis/docs/adr/0009-production-studio-c-lifecycle-publication.md",
        "software/conflict_analysis/docs/production-studio-c-read-only-runtime.md",
        "software/conflict_analysis/production_studio/lifecycle_claim_boundaries.py",
        "software/conflict_analysis/production_studio/contracts/lifecycle_publication_claim_boundaries_v1.ru.json",
        "software/conflict_analysis/production_studio/contracts/lifecycle_publication_claim_boundaries_v1.ru.json.sha256",
        "software/conflict_analysis/production_studio/static/production_studio/lifecycle_publication.css",
        "software/conflict_analysis/production_studio/static/production_studio/lifecycle_publication.js",
        "software/conflict_analysis/production_studio/templates/production_studio/lifecycle_publication_definition.html",
        "software/conflict_analysis/production_studio/tests/test_lifecycle_publication.py",
        "software/conflict_analysis/production_studio/browser_tests/lifecycle_publication.mjs",
        "software/conflict_analysis/production_studio/templates/production_studio/audited_draft_definition.html",
        "software/conflict_analysis/production_studio/static/production_studio/audited_draft.js",
        "software/conflict_analysis/production_studio/urls.py",
        "software/conflict_analysis/production_studio/views.py",
        "software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py",
    }
)

F0L_EXISTING_BASE_BLOBS = {
    ".github/workflows/conflict-analysis.yml": "d8187433716431bc2e6c93468f826cd21d08792d",
    "software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py": "d5fac3155f887cd4253b64db1cba89f7a94181d9",
    "software/conflict_analysis/domain/models.py": "c6c5c2419989e7b0cf40bd1242ab65d37cc2e162",
    "software/conflict_analysis/domain/services/project_definitions.py": "1b0fa567b138e13752924f47aecede2cf093cec0",
    "software/conflict_analysis/domain/api/studio_definitions.py": "8d62faa9e47d4d8a7a1da429052a25bb060a41e4",
    "software/conflict_analysis/domain/services/seed.py": "87453c8580519c056fe9289ce177d4609867c4cd",
    "software/conflict_analysis/domain/services/project_packages.py": "e02778b1fb94da0c5ba99336fb073a7ea43e4760",
    "software/conflict_analysis/domain/tests/test_data_foundation.py": "c2e3ac258c761426fb01075e6ebdebf9b74c57df",
    "software/conflict_analysis/domain/tests/test_v4_foundation_contracts.py": "8a831df39c7316b53f0d6547fbb934d548d075f2",
    "software/conflict_analysis/domain/tests/test_postgresql_migrations.py": "a73aa341c83255049be40ddd642944bf84c864d2",
    "software/conflict_analysis/domain/tests/test_foundation_studio_bootstrap.py": "1f582969390cb98f71a3dca18b663c7667e4a6ec",
    "software/conflict_analysis/domain/tests/test_foundation_studio_package.py": "a3aa4b979401640c7267fffd5ee09973def6a6e5",
    "software/conflict_analysis/domain/tests/test_foundation_studio_http.py": "792c0029693aec99aa9fa95213d87983d9c784fa",
    "software/conflict_analysis/domain/tests/test_foundation_studio_write_reconciliation.py": "5a495e843ce5c91acfced662174a83a1ec67bf3f",
    "software/conflict_analysis/domain/tests/test_foundation_studio_publication_readiness.py": "6b788a33a3d5ea7e71e79a293565a186d318cfb8",
    "software/conflict_analysis/domain/tests/test_foundation_studio_publication_reconciliation.py": "36e646eb5d50226b29442450b7e7bb196403275c",
    "software/conflict_analysis/production_studio/static/production_studio/audited_draft.js": "ff62a55dceb11a136c0e4d7bf55a0db2f00ac35c",
    "software/conflict_analysis/production_studio/templates/production_studio/audited_draft_entry.html": "3e566b505b0b2120b33c54a9bb0bfa34647830e2",
    "software/conflict_analysis/production_studio/tests/test_audited_authoring.py": "c4667ddd0c034d80db23e9dca668413ee6a762a0",
    "software/conflict_analysis/production_studio/tests/test_browser_contract.py": "ae55f52c3951c12ad2fecc872f94e1574761c631",
    "software/conflict_analysis/production_studio/tests/test_read_only_http.py": "6397eb79e9a7f192ea65cebd518e2365635c0c3d",
    "software/conflict_analysis/production_studio/browser_tests/audited_authoring.mjs": "e7ae2b0d98a312322eec0b0db521f8934dc56e62",
}

F0L_FIXTURE_DELTAS = {
    "software/conflict_analysis/domain/tests/test_foundation_studio_publication_reconciliation.py": {
        "call_line": 493,
        "call_source": "        project = Project.objects.create(",
        "insert_after_line": 499,
        "insert_after_source": '            metadata={"oracle": "FD06"},',
    },
    "software/conflict_analysis/production_studio/tests/test_browser_contract.py": {
        "call_line": 52,
        "call_source": "        cls.project = Project.objects.create(",
        "insert_after_line": 56,
        "insert_after_source": '            name=identity["name"],',
    },
    "software/conflict_analysis/production_studio/tests/test_read_only_http.py": {
        "call_line": 41,
        "call_source": "        cls.project = Project.objects.create(",
        "insert_after_line": 45,
        "insert_after_source": '            name=identity["name"],',
    },
}
F0L_FIXTURE_INSERTION = (
    '            primary_language_tag="en",',
    '            primary_language_assignment="EXPLICIT",',
)

F0L_FROZEN_OBJECTS = {
    "software/conflict_analysis/pyproject.toml": "3a4705d5b016aaabbfc66899db852a77eed30b9e",
    "software/conflict_analysis/domain/enums.py": "a701c3c83511b7d1706519d40fab4580d0a0d63e",
    "software/conflict_analysis/domain/policies.py": "4b5eba67ab9d6ee4f70497a71d2b0af420ab9afb",
    "software/conflict_analysis/domain/services/foundation_packages.py": "41c5a6ba2dddd39bdf01ccd398f8ab8213133986",
    "software/conflict_analysis/domain/services/schemas/project-package-1.0.0.schema.json": "2827994fe19d7c8b93f3bc6ee43452459252e98c",
    "software/conflict_analysis/domain/services/schemas/foundation-package-2.0.0.schema.json": "f6d980c1ba298aabd7373b9579b2333ec18a52be",
    "software/conflict_analysis/domain/services/schemas/foundation-package-2.1.0.schema.json": "6aaf283725c8b929b1996b4e0200abf7f1804130",
    "software/conflict_analysis/domain/services/schemas/project-definition-manifest-1.0.0.schema.json": "4861d951fc2d2baf747fd302dff727f1c60fad83",
    "software/conflict_analysis/domain/urls.py": "28f1c046799fc7013e0eb45f0f732a39421bce22",
    "software/conflict_analysis/domain/demo_data.py": "a9f969a816eeedca58db4732dec0909d33287c9c",
    "software/conflict_analysis/production_studio/views.py": "954cbc5bc543dc3ae9da65872e15fdc714542338",
    "software/conflict_analysis/production_studio/urls.py": "ae436ed997c0b9a446449986abc49481ed0cee8e",
}

PROJECT_LANGUAGE_TEST_CLASS = "ProjectPrimaryLanguageContractTests"
PROJECT_LANGUAGE_TEST_METHODS = (
    "test_language_tag_well_formedness_and_canonicalization_vectors_are_exact",
    "test_project_create_and_base_manager_require_explicit_non_und_language",
    "test_instance_save_rejects_relanguage_and_other_fields_remain_mutable",
    "test_queryset_update_and_bulk_update_reject_relanguage",
    "test_get_or_create_requires_language_for_create_and_preserves_existing_identity",
    "test_update_or_create_same_language_is_idempotent_and_different_language_conflicts",
    "test_bulk_create_validates_the_full_batch_and_rejects_conflict_modes",
    "test_seed_creates_ru_replays_and_rejects_existing_non_ru_identity",
    "test_project_package_1_1_round_trip_preserves_explicit_and_legacy_unknown_language",
    "test_project_package_1_0_is_frozen_and_only_exact_kz_upgrade_is_admitted",
)
PROJECT_LANGUAGE_WRITE_TEST_CLASS = "FoundationStudioProjectLanguageWriteTests"
PROJECT_LANGUAGE_WRITE_TEST_METHODS = (
    "test_bootstrap_missing_invalid_and_und_language_reject_before_any_write",
    "test_bootstrap_case_equivalent_language_replays_by_canonical_semantic_identity",
    "test_bootstrap_different_language_is_typed_operation_key_reuse",
    "test_bootstrap_language_persists_in_project_receipt_response_and_fault_rollback",
)
PROJECT_LANGUAGE_HTTP_TEST_CLASS = "FoundationStudioProjectLanguageHttpTests"
PROJECT_LANGUAGE_HTTP_TEST_METHODS = (
    "test_http_bootstrap_requires_exact_project_primary_language_envelope",
    "test_http_language_admission_preserves_auth_csrf_scope_and_zero_write_order",
)
PROJECT_LANGUAGE_MIGRATION_TEST_CLASS = "ProjectPrimaryLanguageMigrationGateTests"
PROJECT_LANGUAGE_MIGRATION_TEST_METHODS = (
    "test_0015_to_0016_maps_exact_kz_to_ru_and_other_projects_to_und_without_drift",
    "test_0016_reverse_reapply_and_clean_database_seed_are_exact",
)

F1_FOCUSED_TEST_NODES = (
    *((F1_PORTABLE_TEST_CLASS, method) for method in F1_PORTABLE_TEST_METHODS),
    *((F1_MIGRATION_TEST_CLASS, method) for method in F1_MIGRATION_TEST_METHODS),
)
C2A_PORTABLE_TEST_NODES = tuple(
    (C2A_PORTABLE_TEST_CLASS, method) for method in C2A_PORTABLE_TEST_METHODS
)
SUCCESSOR_C1_CHROMIUM_TEST_NODE = (
    "ProductionStudioAuditedAuthoringBrowserTests",
    "test_authenticated_edit_save_reload_is_bounded_foundation_only_and_receipted",
)
F0L_SQLITE_SKIPPED_TEST_NODES = (
    (
        "domain.tests.test_foundation_studio_bootstrap.FoundationStudioBootstrapConcurrencyTests",
        "test_postgresql_concurrent_bootstrap_has_one_winner_and_one_explicit_conflict",
    ),
    (
        "domain.tests.test_foundation_studio_bootstrap.FoundationStudioSuccessorConcurrencyTests",
        "test_postgresql_competing_successors_have_one_winner_and_preserve_old_pin",
    ),
    (
        "domain.tests.test_foundation_studio_bootstrap.FoundationStudioApplicationSuccessorConcurrencyTests",
        "test_postgresql_application_wrapper_has_one_success_and_one_typed_conflict",
    ),
    (
        "domain.tests.test_foundation_studio_bootstrap.FoundationStudioFirstProjectApplicationConcurrencyTests",
        "test_postgresql_application_bootstrap_has_one_complete_winner_and_no_orphans",
    ),
    (
        "domain.tests.test_foundation_studio_package.FoundationStudioCrossPathLockOrderTests",
        "test_postgresql_import_initial_and_successor_paths_share_one_lock_order",
    ),
    (
        "domain.tests.test_foundation_studio_publication_reconciliation.FoundationStudioPublicationReconciliationConcurrencyTests",
        "test_concurrent_initial_different_keys_has_one_commit_and_one_typed_loser",
    ),
    (
        "domain.tests.test_foundation_studio_publication_reconciliation.FoundationStudioPublicationReconciliationConcurrencyTests",
        "test_concurrent_initial_same_key_has_one_fresh_and_one_replay",
    ),
    (
        "domain.tests.test_foundation_studio_publication_reconciliation.FoundationStudioPublicationReconciliationConcurrencyTests",
        "test_concurrent_successor_different_keys_has_one_current_winner_and_one_typed_loser",
    ),
    (
        "domain.tests.test_foundation_studio_publication_reconciliation.FoundationStudioPublicationReconciliationConcurrencyTests",
        "test_concurrent_successor_same_key_has_one_fresh_and_one_replay",
    ),
    (
        "domain.tests.test_foundation_studio_write_reconciliation.FoundationStudioWriteReconciliationConcurrencyTests",
        "test_postgresql_concurrent_bootstrap_same_key_has_one_graph_one_audit_one_reconcile",
    ),
    (
        "domain.tests.test_foundation_studio_write_reconciliation.FoundationStudioWriteReconciliationConcurrencyTests",
        "test_postgresql_concurrent_create_same_key_has_one_commit_one_reconcile",
    ),
    (
        "domain.tests.test_foundation_studio_write_reconciliation.FoundationStudioWriteReconciliationConcurrencyTests",
        "test_postgresql_concurrent_stale_saves_have_one_commit_one_draft_stale",
    ),
    (
        "domain.tests.test_foundation_studio_write_reconciliation.FoundationStudioWriteReconciliationConcurrencyTests",
        "test_postgresql_different_keys_same_create_or_clone_identity_have_one_typed_loser",
    ),
    (
        "domain.tests.test_foundation_studio_write_reconciliation.FoundationStudioWriteReconciliationConcurrencyTests",
        "test_postgresql_save_validate_race_obeys_project_first_lock_order",
    ),
    (
        "domain.tests.test_postgresql_migrations.PostgreSQLMigrationGateTests",
        "test_clean_test_database_is_at_every_migration_leaf",
    ),
    (
        "domain.tests.test_postgresql_migrations.ProjectPrimaryLanguageMigrationGateTests",
        "test_0015_to_0016_maps_exact_kz_to_ru_and_other_projects_to_und_without_drift",
    ),
    (
        "domain.tests.test_postgresql_migrations.ProjectPrimaryLanguageMigrationGateTests",
        "test_0016_reverse_reapply_and_clean_database_seed_are_exact",
    ),
)

FD07_TEST_CLASS = "FoundationStudioPublicationReadinessTests"
FD07_TEST_METHODS = (
    "test_route_method_auth_scope_query_headers_and_zero_write_are_exact",
    "test_first_project_draft_is_initial_candidate_snapshot_only",
    "test_standalone_draft_in_published_project_is_never_initial_candidate",
    "test_exact_successor_draft_requires_validate_and_validated_requires_publish",
    "test_wrong_predecessor_missing_current_and_initial_receipt_integrity_fail_closed",
    "test_published_retired_and_validated_initial_states_have_no_publication_action",
    "test_response_is_canonical_hash_bound_no_store_and_deterministic",
    "test_old_hash_basic_absent_and_cross_scope_are_password_cookie_write_free",
    "test_readiness_is_advisory_and_fd06_rechecks_after_persisted_state_changes",
)

FD07_EXACT_FROZEN_OBJECTS = {
    "software/conflict_analysis/domain/models.py": (
        "c6c5c2419989e7b0cf40bd1242ab65d37cc2e162"
    ),
    "software/conflict_analysis/domain/enums.py": (
        "a701c3c83511b7d1706519d40fab4580d0a0d63e"
    ),
    "software/conflict_analysis/domain/migrations": (
        "b0cc214cd63086172c9d3801338a5a2302a7ce0f"
    ),
    "software/conflict_analysis/domain/policies.py": (
        "4b5eba67ab9d6ee4f70497a71d2b0af420ab9afb"
    ),
    "software/conflict_analysis/production_studio": (
        "31ba7273cfe4a6ae3c57054518de2e2ba98113ff"
    ),
    "software/conflict_analysis/domain/services/foundation_packages.py": (
        "41c5a6ba2dddd39bdf01ccd398f8ab8213133986"
    ),
}

FD07_REOPENED_BASE_BLOBS = {
    ".github/workflows/conflict-analysis.yml": (
        "ea6dc0c12897eb683ffa108b8e247639f6e34da1"
    ),
    "software/conflict_analysis/docs/adr/0006-foundation-studio-application-gateways.md": (
        "6544eedc45d0e77c2f89dbfbb4e52874337b7e63"
    ),
    "software/conflict_analysis/domain/api/studio_definitions.py": (
        "ff2680683af265b0c35258df21d15eb575ec1f47"
    ),
    "software/conflict_analysis/domain/services/project_definitions.py": (
        "c4cbb6b426fdfe0359dfe30eff58e712baf1fd19"
    ),
    "software/conflict_analysis/domain/tests/test_foundation_studio_http.py": (
        "376122c7511df26477b2d1ec839d4fd2af00b1e5"
    ),
    "software/conflict_analysis/domain/urls.py": (
        "e4ffdc3efc608fb9a1933c52298e10db0523aaa7"
    ),
    "software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py": (
        "188abd70b4b89bd423c148da98240150a7a4d56f"
    ),
}

FD06_PORTABLE_CLASS = "FoundationStudioPublicationReconciliationTests"
FD06_PORTABLE_METHODS = (
    "test_initial_and_successor_require_exact_key_if_match_envelope_and_prebody_method_gate",
    "test_initial_fresh_result_persists_hash_bound_project_operation_and_exact_receipt",
    "test_successor_fresh_result_preserves_predecessor_and_exact_receipt",
    "test_same_key_same_request_replays_before_lifecycle_rejection_and_after_workspace_or_lifecycle_change",
    "test_same_uuid_key_is_independent_across_projects_and_foreign_operation_is_hidden",
    "test_same_key_different_request_actor_or_target_is_typed_conflict",
    "test_response_loss_recovers_immutable_receipt_and_fd03_current_state_remains_separate",
    "test_already_published_stale_noncurrent_and_cross_scope_failures_are_typed",
    "test_every_initial_failure_stage_rolls_back_definition_workspace_help_publication_and_audits",
    "test_every_successor_failure_stage_rolls_back_currentness_publication_and_audits",
    "test_auth_csrf_basic_cookie_and_nonpost_paths_are_bounded_and_write_free_before_admission",
)
FD06_CONCURRENCY_CLASS = "FoundationStudioPublicationReconciliationConcurrencyTests"
FD06_CONCURRENCY_METHODS = (
    "test_concurrent_initial_same_key_has_one_fresh_and_one_replay",
    "test_concurrent_initial_different_keys_has_one_commit_and_one_typed_loser",
    "test_concurrent_successor_same_key_has_one_fresh_and_one_replay",
    "test_concurrent_successor_different_keys_has_one_current_winner_and_one_typed_loser",
)

FD06_EXACT_FROZEN_OBJECTS = {
    "software/conflict_analysis/domain/models.py": (
        "c6c5c2419989e7b0cf40bd1242ab65d37cc2e162"
    ),
    "software/conflict_analysis/domain/enums.py": (
        "a701c3c83511b7d1706519d40fab4580d0a0d63e"
    ),
    "software/conflict_analysis/domain/migrations": (
        "b0cc214cd63086172c9d3801338a5a2302a7ce0f"
    ),
    "software/conflict_analysis/production_studio": (
        PINNED_FD06_PRODUCTION_STUDIO_TREE
    ),
}
FD06_REOPENED_BASE_BLOBS = {
    "software/conflict_analysis/domain/api/studio_definitions.py": (
        "bf6cdf29c49878025c73e2a984f61a1e326b0c8e"
    ),
    "software/conflict_analysis/domain/policies.py": (
        "697c72a91fe6fbe00ae54ec249ea89583d47ca93"
    ),
    "software/conflict_analysis/domain/services/project_definitions.py": (
        "9bb454a25a9621507662d5aa12e35ccd8a91dd1d"
    ),
    "software/conflict_analysis/domain/urls.py": (
        "127bde69d539844d59b53b74f81aa3483f865e66"
    ),
}
FD06_HTTP_BOUNDED_CLASS = "FoundationStudioApplicationGatewayHttpTests"
FD06_HTTP_BOUNDED_METHOD = (
    "test_successor_http_201_etag_pin_preservation_and_stable_retry_409"
)
FD06_BOOTSTRAP_BOUNDED_CLASS = "FoundationStudioHttpAuthorizationTests"
FD06_BOOTSTRAP_BOUNDED_METHOD = (
    "test_editor_viewer_publisher_matrix_and_exact_routes"
)

FD03_AGGREGATE_ALLOWLIST = ACTIVE_FD02_ALLOWLIST | ACTIVE_FD03_ALLOWLIST

FD03_TEST_CLASS = "FoundationStudioLifecycleReadResultHttpTests"
FD03_TEST_METHODS = (
    "test_fd03_open_definition_returns_exact_persisted_lifecycle_values",
    "test_fd03_open_definition_distinguishes_current_successor_and_published_predecessor",
    "test_fd03_initial_publication_result_recovers_exact_workspace_pin",
    "test_fd03_successor_publication_result_has_exact_null_workspace_fields",
    "test_fd03_publication_result_scope_identity_and_get_only_boundary_are_indistinguishable",
    "test_fd03_reads_are_repeat_stable_and_non_mutating",
)

FD03_C0_CLASS = "ProductionStudioReadOnlyHttpTests"
FD03_C0_METHOD = (
    "test_open_all_literal_lifecycle_states_has_exact_hash_etag_and_zero_writes"
)

FD02_FROZEN_PATHS = (
    "software/conflict_analysis/conflict_analysis",
    "software/conflict_analysis/domain/api/studio_definitions.py",
    "software/conflict_analysis/domain/enums.py",
    "software/conflict_analysis/domain/migrations",
    "software/conflict_analysis/domain/models.py",
    "software/conflict_analysis/domain/policies.py",
    "software/conflict_analysis/domain/services/foundation_packages.py",
    "software/conflict_analysis/domain/services/help_topics.py",
    "software/conflict_analysis/domain/services/project_definitions.py",
    "software/conflict_analysis/domain/services/schemas",
    "software/conflict_analysis/domain/urls.py",
    "software/conflict_analysis/production_studio",
    "software/conflict_analysis/pyproject.toml",
)

FD03_FROZEN_PATHS = (
    "software/conflict_analysis/conflict_analysis",
    "software/conflict_analysis/domain/content/studio_help_ru_v1.json",
    "software/conflict_analysis/domain/management/commands/provision_studio_help.py",
    "software/conflict_analysis/domain/models.py",
    "software/conflict_analysis/domain/enums.py",
    "software/conflict_analysis/domain/migrations",
    "software/conflict_analysis/domain/policies.py",
    "software/conflict_analysis/domain/services",
    "software/conflict_analysis/domain/tests/test_foundation_studio_help_provisioning.py",
    "software/conflict_analysis/production_studio/browser_tests",
    "software/conflict_analysis/production_studio/contracts",
    "software/conflict_analysis/production_studio/static",
    "software/conflict_analysis/production_studio/templates",
    "software/conflict_analysis/production_studio/urls.py",
    "software/conflict_analysis/production_studio/views.py",
    "software/conflict_analysis/pyproject.toml",
)

PINNED_MIGRATIONS = (
    "software/conflict_analysis/domain/migrations/0001_initial.py",
    "software/conflict_analysis/domain/migrations/0002_foundation_v4_schema.py",
    "software/conflict_analysis/domain/migrations/0003_foundation_v4_workspace_required.py",
    "software/conflict_analysis/domain/migrations/0004_power_metadata_state.py",
    "software/conflict_analysis/domain/migrations/0005_foundation_contract_completion.py",
    "software/conflict_analysis/domain/migrations/0006_definition_lifecycle_enforcement.py",
    "software/conflict_analysis/domain/migrations/0007_assessment_header_confidence.py",
    "software/conflict_analysis/domain/migrations/0008_evidence_relation_contract.py",
    "software/conflict_analysis/domain/migrations/0009_append_only_provenance_restrict.py",
    "software/conflict_analysis/domain/migrations/0010_import_receipt_contract.py",
    "software/conflict_analysis/domain/migrations/0011_chat_citation_target_modes.py",
    "software/conflict_analysis/domain/migrations/0012_xlsx_metadata_contract.py",
    "software/conflict_analysis/domain/migrations/0013_foundation_studio_contract_fields.py",
    "software/conflict_analysis/domain/migrations/0014_foundation_studio_contract_backfill.py",
    "software/conflict_analysis/domain/migrations/0015_foundation_studio_contract_constraints.py",
    "software/conflict_analysis/domain/migrations/__init__.py",
)

F0L_MIGRATIONS = (
    *PINNED_MIGRATIONS[:-1],
    "software/conflict_analysis/domain/migrations/0016_project_primary_language.py",
    PINNED_MIGRATIONS[-1],
)
F1_MIGRATIONS = (
    *F0L_MIGRATIONS[:-1],
    "software/conflict_analysis/domain/migrations/0017_multilingual_evidence_lineage.py",
    F0L_MIGRATIONS[-1],
)


class VerificationError(RuntimeError):
    """A deterministic Production Studio slice-boundary verification failure."""


def _git(repo: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    if check and completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise VerificationError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()


def _git_bytes(repo: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise VerificationError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout


def _repo_root(start: Path) -> Path:
    top = _git(start, "rev-parse", "--show-toplevel")
    return Path(top).resolve()


def _normalize(path: str) -> str:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    if normalized.startswith("../") or normalized == "..":
        raise VerificationError(f"changed path escapes repository: {path!r}")
    return normalized


def _changed_paths(repo: Path, base_head: str) -> set[str]:
    committed = {
        _normalize(path)
        for path in _git(repo, "diff", "--name-only", f"{base_head}...HEAD", "--").splitlines()
        if path
    }
    worktree = {
        _normalize(path)
        for path in _git(repo, "diff", "--name-only", "HEAD", "--").splitlines()
        if path
    }
    staged = {
        _normalize(path)
        for path in _git(repo, "diff", "--cached", "--name-only", "HEAD", "--").splitlines()
        if path
    }
    untracked = {
        _normalize(path)
        for path in _git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
        if path
    }
    return committed | worktree | staged | untracked


def _commit_changed_paths(repo: Path, commit: str) -> set[str]:
    commit = _require_exact_object_id("F0L correction commit", commit)
    return {
        _normalize(path)
        for path in _git(
            repo,
            "diff",
            "--name-only",
            "--no-renames",
            f"{commit}^",
            commit,
            "--",
        ).splitlines()
        if path
    }


def _require_exact_object_id(label: str, value: str | None) -> str:
    if value is None or _LOWER_HEX_40.fullmatch(value) is None:
        raise VerificationError(f"{label} must be an exact lowercase 40-hex object id")
    return value


def _resolve_slice_contract(
    *,
    active_slice: str,
    base_head: str,
    base_tree: str,
    fd05_accepted_head: str | None,
    fd05_accepted_tree: str | None,
) -> dict[str, object]:
    base_head = _require_exact_object_id("base HEAD", base_head)
    base_tree = _require_exact_object_id("base TREE", base_tree)
    if active_slice == "C0":
        if fd05_accepted_head is not None or fd05_accepted_tree is not None:
            raise VerificationError("C0 does not accept FD05 external pin arguments")
        if base_head != PINNED_BASE_HEAD or base_tree != PINNED_BASE_TREE:
            raise VerificationError("C0 accepts only the pinned authorization HEAD/TREE")
        return {
            "active_slice": active_slice,
            "allowlist": ACTIVE_C0_ALLOWLIST,
            "exact_changed_paths": False,
            "domain_tree": PINNED_DOMAIN_TREE,
            "fd05_base_pin": "NOT_APPLICABLE_CURRENT_C0",
            "fd05_accepted_head": None,
            "fd05_accepted_tree": None,
            "r0_start_pin": "NOT_APPLICABLE_CURRENT_C0",
            "c1_base_pin": "NOT_APPLICABLE_CURRENT_C0",
            "fd02_base_pin": "NOT_APPLICABLE_CURRENT_C0",
        }
    if active_slice == "FD02":
        if fd05_accepted_head is not None or fd05_accepted_tree is not None:
            raise VerificationError("FD02 does not accept FD05 external pin arguments")
        if base_head != PINNED_FD02_BASE_HEAD or base_tree != PINNED_FD02_BASE_TREE:
            raise VerificationError("FD02 accepts only the exact accepted C1 HEAD/TREE")
        return {
            "active_slice": active_slice,
            "allowlist": ACTIVE_FD02_ALLOWLIST,
            "exact_changed_paths": True,
            "domain_tree": PINNED_FD02_DOMAIN_TREE,
            "fd05_base_pin": "NOT_APPLICABLE_CURRENT_FD02",
            "fd05_accepted_head": None,
            "fd05_accepted_tree": None,
            "r0_start_pin": "NOT_APPLICABLE_CURRENT_FD02",
            "c1_base_pin": "PIN_VERIFIED_AUTHORIZATION",
            "fd02_base_pin": "NOT_APPLICABLE_CURRENT_FD02",
        }
    if active_slice == "FD03":
        if fd05_accepted_head is not None or fd05_accepted_tree is not None:
            raise VerificationError("FD03 does not accept FD05 external pin arguments")
        if base_head != PINNED_FD03_BASE_HEAD or base_tree != PINNED_FD03_BASE_TREE:
            raise VerificationError("FD03 accepts only the exact accepted FD02 HEAD/TREE")
        return {
            "active_slice": active_slice,
            "allowlist": ACTIVE_FD03_ALLOWLIST,
            "exact_changed_paths": True,
            "domain_tree": PINNED_FD03_BASE_DOMAIN_TREE,
            "fd05_base_pin": "NOT_APPLICABLE_CURRENT_FD03",
            "fd05_accepted_head": None,
            "fd05_accepted_tree": None,
            "r0_start_pin": "NOT_APPLICABLE_CURRENT_FD03",
            "c1_base_pin": "NOT_APPLICABLE_CURRENT_FD03",
            "fd02_base_pin": "PIN_VERIFIED_AUTHORIZATION",
        }
    if active_slice == "FD06":
        if fd05_accepted_head is not None or fd05_accepted_tree is not None:
            raise VerificationError("FD06 does not accept external pin arguments")
        if base_head != PINNED_FD06_BASE_HEAD or base_tree != PINNED_FD06_BASE_TREE:
            raise VerificationError("FD06 accepts only the exact accepted FD03 HEAD/TREE")
        return {
            "active_slice": active_slice,
            "allowlist": ACTIVE_FD06_ALLOWLIST,
            "exact_changed_paths": True,
            "domain_tree": PINNED_FD06_BASE_DOMAIN_TREE,
            "fd05_base_pin": "NOT_APPLICABLE_CURRENT_FD06",
            "fd05_accepted_head": None,
            "fd05_accepted_tree": None,
            "r0_start_pin": "NOT_APPLICABLE_CURRENT_FD06",
            "c1_base_pin": "NOT_APPLICABLE_CURRENT_FD06",
            "fd02_base_pin": "NOT_APPLICABLE_CURRENT_FD06",
        }
    if active_slice == "FD07":
        if fd05_accepted_head is not None or fd05_accepted_tree is not None:
            raise VerificationError("FD07 does not accept external pin arguments")
        if base_head != PINNED_FD07_BASE_HEAD or base_tree != PINNED_FD07_BASE_TREE:
            raise VerificationError("FD07 accepts only the exact accepted FD06 HEAD/TREE")
        return {
            "active_slice": active_slice,
            "allowlist": ACTIVE_FD07_ALLOWLIST,
            "exact_changed_paths": True,
            "domain_tree": PINNED_FD07_BASE_DOMAIN_TREE,
            "fd05_base_pin": "NOT_APPLICABLE_CURRENT_FD07",
            "fd05_accepted_head": None,
            "fd05_accepted_tree": None,
            "r0_start_pin": "NOT_APPLICABLE_CURRENT_FD07",
            "c1_base_pin": "NOT_APPLICABLE_CURRENT_FD07",
            "fd02_base_pin": "NOT_APPLICABLE_CURRENT_FD07",
            "fd06_base_pin": "PIN_VERIFIED_AUTHORIZATION",
        }
    if active_slice not in {"R0", "C1"}:
        raise VerificationError(f"unsupported Production Studio verifier slice: {active_slice!r}")

    accepted_head = _require_exact_object_id(
        "FD05_ACCEPTED_HEAD",
        fd05_accepted_head,
    )
    accepted_tree = _require_exact_object_id(
        "FD05_ACCEPTED_TREE",
        fd05_accepted_tree,
    )
    if accepted_head != PINNED_R0_BASE_HEAD or accepted_tree != PINNED_R0_BASE_TREE:
        raise VerificationError("external FD05 pin does not match authorized H2/T2")
    if active_slice == "R0":
        if base_head != accepted_head or base_tree != accepted_tree:
            raise VerificationError("R0 base HEAD/TREE does not match the external FD05 pin")
        return {
            "active_slice": active_slice,
            "allowlist": ACTIVE_R0_ALLOWLIST,
            "exact_changed_paths": True,
            "domain_tree": PINNED_R0_DOMAIN_TREE,
            "fd05_base_pin": "PIN_VERIFIED_EXTERNAL",
            "fd05_accepted_head": accepted_head,
            "fd05_accepted_tree": accepted_tree,
            "r0_start_pin": "NOT_APPLICABLE_CURRENT_R0",
            "c1_base_pin": "NOT_APPLICABLE_CURRENT_R0",
            "fd02_base_pin": "NOT_APPLICABLE_CURRENT_R0",
        }

    if base_head != PINNED_C1_START_HEAD or base_tree != PINNED_C1_START_TREE:
        raise VerificationError("C1 accepts only the exact authorized R0 START HEAD/TREE")
    return {
        "active_slice": active_slice,
        "allowlist": ACTIVE_C1_ALLOWLIST,
        "exact_changed_paths": True,
        "domain_tree": PINNED_R0_DOMAIN_TREE,
        "fd05_base_pin": "PIN_VERIFIED_EXTERNAL",
        "fd05_accepted_head": accepted_head,
        "fd05_accepted_tree": accepted_tree,
        "r0_start_pin": "PIN_VERIFIED_AUTHORIZATION",
        "c1_base_pin": "NOT_APPLICABLE_CURRENT_C1",
        "fd02_base_pin": "NOT_APPLICABLE_CURRENT_C1",
    }


def _require_changed_path_contract(
    *,
    active_slice: str,
    changed: frozenset[str] | set[str],
    allowlist: frozenset[str],
    exact_changed_paths: bool,
) -> None:
    outside = sorted(changed - allowlist)
    if outside:
        raise VerificationError(
            f"changed path(s) outside ACTIVE {active_slice} EXACT ALLOWLIST: "
            + ", ".join(outside)
        )
    if exact_changed_paths and changed != allowlist:
        missing = sorted(allowlist - changed)
        raise VerificationError(
            f"{active_slice} changed paths must equal the exact delivered allowlist; "
            "missing: "
            + ", ".join(missing)
        )


def _require_f0l_clean_status(status: str) -> None:
    if status:
        raise VerificationError(
            "F0L verification requires a clean committed worktree; dirty paths: "
            + status.replace("\n", "; ")
        )


def _require_exact_fixture_delta_source(
    *,
    path: str,
    base_source: str,
    head_source: str,
    specification: dict[str, int | str],
) -> None:
    base_lines = base_source.splitlines(keepends=True)
    call_line = int(specification["call_line"])
    insert_after_line = int(specification["insert_after_line"])
    if not (1 <= call_line <= insert_after_line <= len(base_lines)):
        raise VerificationError(f"F0L fixture line bounds drifted at {path}")

    def without_line_ending(value: str) -> str:
        return value.removesuffix("\n").removesuffix("\r")

    if without_line_ending(base_lines[call_line - 1]) != specification["call_source"]:
        raise VerificationError(f"F0L fixture Project create call drifted at {path}")
    anchor = base_lines[insert_after_line - 1]
    if without_line_ending(anchor) != specification["insert_after_source"]:
        raise VerificationError(f"F0L fixture insertion anchor drifted at {path}")
    if anchor.endswith("\r\n"):
        newline = "\r\n"
    elif anchor.endswith("\n"):
        newline = "\n"
    else:
        newline = ""
    if not newline:
        raise VerificationError(f"F0L fixture insertion anchor has no newline at {path}")

    expected_lines = [
        *base_lines[:insert_after_line],
        *(f"{line}{newline}" for line in F0L_FIXTURE_INSERTION),
        *base_lines[insert_after_line:],
    ]
    if head_source != "".join(expected_lines):
        raise VerificationError(
            f"F0L fixture delta at {path} must contain only the exact bounded "
            "primary-language insertion"
        )


def _require_regular_blob_tree_entry(
    *,
    path: str,
    revision: str,
    entry: str,
    expected_blob: str | None = None,
) -> str:
    fields = entry.split(maxsplit=3)
    if (
        len(fields) != 4
        or fields[0] != "100644"
        or fields[1] != "blob"
        or fields[3] != path
        or not _LOWER_HEX_40.fullmatch(fields[2])
    ):
        raise VerificationError(
            f"F0L fixture must be an exact 100644 blob at {revision}:{path}"
        )
    blob = fields[2]
    if expected_blob is not None and blob != expected_blob:
        raise VerificationError(
            f"F0L fixture base blob drift at {path}: expected "
            f"{expected_blob}, got {blob}"
        )
    return blob


def _require_f0l_fixture_deltas(repo: Path) -> None:
    for path, specification in F0L_FIXTURE_DELTAS.items():
        base_blob = F0L_EXISTING_BASE_BLOBS[path]
        try:
            base_object = _require_regular_blob_tree_entry(
                path=path,
                revision=PINNED_F0L_BASE_HEAD,
                entry=_git(
                    repo,
                    "ls-tree",
                    PINNED_F0L_BASE_HEAD,
                    "--",
                    path,
                ),
                expected_blob=base_blob,
            )
            head_object = _require_regular_blob_tree_entry(
                path=path,
                revision="HEAD",
                entry=_git(repo, "ls-tree", "HEAD", "--", path),
            )
            base_source = _git_bytes(repo, "cat-file", "blob", base_object).decode(
                "utf-8"
            )
            head_source = _git_bytes(repo, "cat-file", "blob", head_object).decode(
                "utf-8"
            )
        except (OSError, UnicodeDecodeError) as exc:
            raise VerificationError(
                f"F0L fixture source cannot be read as exact UTF-8 at {path}: {exc}"
            ) from exc
        _require_exact_fixture_delta_source(
            path=path,
            base_source=base_source,
            head_source=head_source,
            specification=specification,
        )


def _require_merge_free(active_slice: str, merge_commits: tuple[str, ...]) -> None:
    if merge_commits:
        raise VerificationError(
            f"merge commits are forbidden after the exact {active_slice} base: "
            + ", ".join(merge_commits)
        )


def _require_single_fast_forward_commit(
    *,
    active_slice: str,
    commit_count: int,
    delivery_parent: str,
    base_head: str,
) -> None:
    if commit_count != 1 or delivery_parent != base_head:
        raise VerificationError(
            f"{active_slice} delivery must be exactly one fast-forward commit "
            f"whose sole parent is the exact base; count={commit_count}, "
            f"parent={delivery_parent}, base={base_head}"
        )


def _require_f0l_bounded_fast_forward_commits(
    *,
    commit_count: int,
    oldest_parent: str,
    base_head: str,
    ordered_commits: tuple[str, ...],
    delivery_parent: str,
) -> None:
    ratified_prefix = F0L_RATIFIED_EXISTING_COMMITS[
        : min(commit_count, len(F0L_RATIFIED_EXISTING_COMMITS))
    ]
    expected_delivery_parent = (
        base_head
        if commit_count == 1
        else ordered_commits[-2]
        if len(ordered_commits) >= 2
        else None
    )
    if (
        commit_count not in {1, 2, 3, 4, 5}
        or oldest_parent != base_head
        or len(ordered_commits) != commit_count
        or ordered_commits[: len(ratified_prefix)] != ratified_prefix
        or delivery_parent != expected_delivery_parent
    ):
        raise VerificationError(
            "F0L delivery must preserve the exact ratified ordinary commit prefix "
            "and contain at most one authorized fifth correction commit; "
            f"count={commit_count}, oldest_parent={oldest_parent}, "
            f"delivery_parent={delivery_parent}, base={base_head}, "
            f"commits={ordered_commits}"
        )


def _require_f0l_correction_4_paths(
    *,
    commit_count: int,
    changed_paths: set[str] | None,
) -> None:
    if commit_count < 4:
        if changed_paths is not None:
            raise VerificationError(
                "F0L correction-4 paths must be absent before the fourth commit"
            )
        return
    if changed_paths != F0L_CORRECTION_4_PATHS:
        raise VerificationError(
            "F0L fourth commit must change exactly the three authorized correction "
            "paths: "
            + json.dumps(
                {
                    "expected": sorted(F0L_CORRECTION_4_PATHS),
                    "actual": sorted(changed_paths or set()),
                }
            )
        )


def _require_f0l_correction_5_paths(
    *,
    commit_count: int,
    changed_paths: set[str] | None,
) -> None:
    if commit_count < 5:
        if changed_paths is not None:
            raise VerificationError(
                "F0L correction-5 paths must be absent before the fifth commit"
            )
        return
    if changed_paths != F0L_CORRECTION_5_PATHS:
        raise VerificationError(
            "F0L fifth commit must change exactly the workflow and verifier paths: "
            + json.dumps(
                {
                    "expected": sorted(F0L_CORRECTION_5_PATHS),
                    "actual": sorted(changed_paths or set()),
                }
            )
        )


def _require_fd06_rc5_public_history(
    *,
    commit_count: int,
    delivery_head: str,
    delivery_parent: str,
    intermediate_parent: str,
    intermediate_tree: str,
    ordered_commits: tuple[str, ...],
) -> None:
    delivery_head = _require_exact_object_id("FD06 RC5 delivery HEAD", delivery_head)
    delivery_parent = _require_exact_object_id(
        "FD06 RC5 delivery parent", delivery_parent
    )
    intermediate_parent = _require_exact_object_id(
        "FD06 RC4 intermediate parent", intermediate_parent
    )
    intermediate_tree = _require_exact_object_id(
        "FD06 RC4 intermediate TREE", intermediate_tree
    )
    expected_order = (PINNED_FD06_RC4_INTERMEDIATE_HEAD, delivery_head)
    if (
        commit_count != 2
        or delivery_head == PINNED_FD06_RC4_INTERMEDIATE_HEAD
        or delivery_parent != PINNED_FD06_RC4_INTERMEDIATE_HEAD
        or intermediate_parent != PINNED_FD06_BASE_HEAD
        or intermediate_tree != PINNED_FD06_RC4_INTERMEDIATE_TREE
        or ordered_commits != expected_order
    ):
        raise VerificationError(
            "FD06 RC5 public history must preserve the exact RC4 intermediate "
            "and add exactly one child commit; "
            f"count={commit_count}, delivery={delivery_head}, "
            f"delivery_parent={delivery_parent}, "
            f"intermediate_parent={intermediate_parent}, "
            f"intermediate_tree={intermediate_tree}, "
            f"ordered_commits={ordered_commits}"
        )


def _require_fd03_rc2_fast_forward(
    *,
    commit_count: int,
    delivery_parent: str,
) -> None:
    if commit_count != 2 or delivery_parent != PINNED_FD03_RC2_START_HEAD:
        raise VerificationError(
            "FD03 RC2 delivery must be exactly two fast-forward commits from "
            "the accepted FD02 base, with the final commit whose sole parent "
            "is the exact RC2 start; "
            f"count={commit_count}, parent={delivery_parent}, "
            f"rc2_start={PINNED_FD03_RC2_START_HEAD}"
        )


def _resolve_fd06_route(
    *,
    event_name: str,
    event_ref: str = "",
    head_ref: str = "",
    base_ref: str = "",
) -> str:
    if event_name == "push" and event_ref == f"refs/heads/{FD06_TARGET_BRANCH}":
        return "PINNED_FD03"
    if (
        event_name == "pull_request"
        and head_ref == FD06_TARGET_BRANCH
        and base_ref == FD06_BASE_BRANCH
    ):
        return "EVENT_FD03"
    raise VerificationError(
        "FD06 routing accepts only its exact push ref or its exact stacked "
        "pull-request ref pair"
    )


def _require_fd06_static_contract(
    *,
    exact_path_count: int,
    portable_count: int,
    concurrency_count: int,
    postgresql_total: int,
    postgresql_skipped: int,
    sqlite_passed: int,
    sqlite_skipped: int,
) -> None:
    actual = (
        exact_path_count,
        portable_count,
        concurrency_count,
        postgresql_total,
        postgresql_skipped,
        sqlite_passed,
        sqlite_skipped,
    )
    expected = (
        FD06_EXACT_PATH_COUNT,
        11,
        4,
        FD06_POSTGRESQL_TOTAL,
        FD06_POSTGRESQL_SKIPPED,
        FD06_SQLITE_PASSED,
        FD06_SQLITE_SKIPPED,
    )
    if actual != expected:
        raise VerificationError(
            "FD06 static path/test total contract drifted: "
            + json.dumps({"expected": expected, "actual": actual})
        )


def _require_fd06_frozen_contract(
    *,
    exact_frozen_objects: dict[str, str],
    reopened_base_blobs: dict[str, str],
) -> None:
    if exact_frozen_objects != FD06_EXACT_FROZEN_OBJECTS:
        raise VerificationError("FD06 exact frozen-object contract drifted")
    if reopened_base_blobs != FD06_REOPENED_BASE_BLOBS:
        raise VerificationError("FD06 reopened base-blob contract drifted")


def _resolve_fd07_route(
    *,
    event_name: str,
    event_ref: str = "",
    head_ref: str = "",
    base_ref: str = "",
) -> str:
    if event_name == "push" and event_ref == f"refs/heads/{FD07_TARGET_BRANCH}":
        return "PINNED_FD06"
    if (
        event_name == "pull_request"
        and head_ref == FD07_TARGET_BRANCH
        and base_ref == FD07_BASE_BRANCH
    ):
        return "EVENT_FD06"
    raise VerificationError(
        "FD07 routing accepts only its exact push ref or its exact stacked "
        "pull-request ref pair"
    )


def _require_fd07_static_contract(
    *,
    exact_path_count: int,
    test_node_count: int,
    postgresql_total: int,
    postgresql_skipped: int,
    sqlite_passed: int,
    sqlite_skipped: int,
) -> None:
    actual = (
        exact_path_count,
        test_node_count,
        postgresql_total,
        postgresql_skipped,
        sqlite_passed,
        sqlite_skipped,
    )
    expected = (
        FD07_EXACT_PATH_COUNT,
        9,
        FD07_POSTGRESQL_TOTAL,
        FD07_POSTGRESQL_SKIPPED,
        FD07_SQLITE_PASSED,
        FD07_SQLITE_SKIPPED,
    )
    if actual != expected:
        raise VerificationError(
            "FD07 static path/test total contract drifted: "
            + json.dumps({"expected": expected, "actual": actual})
        )


def _require_fd07_frozen_contract(
    *,
    exact_frozen_objects: dict[str, str],
    reopened_base_blobs: dict[str, str],
) -> None:
    if exact_frozen_objects != FD07_EXACT_FROZEN_OBJECTS:
        raise VerificationError("FD07 exact frozen-object contract drifted")
    if reopened_base_blobs != FD07_REOPENED_BASE_BLOBS:
        raise VerificationError("FD07 reopened base-blob contract drifted")


def _resolve_f0l_route(
    *,
    event_name: str,
    event_ref: str = "",
    head_ref: str = "",
    base_ref: str = "",
) -> str:
    if event_name == "push" and event_ref == f"refs/heads/{F0L_TARGET_BRANCH}":
        return "PINNED_FD07"
    if (
        event_name == "pull_request"
        and head_ref == F0L_TARGET_BRANCH
        and base_ref == F0L_BASE_BRANCH
    ):
        return "EVENT_FD07"
    raise VerificationError(
        "F0L routing accepts only its exact push ref or exact FD07-targeted "
        "pull-request ref pair"
    )


def _resolve_post_f0l_route(
    *,
    active_slice: str,
    event_name: str,
    event_ref: str = "",
    head_ref: str = "",
    base_ref: str = "",
) -> str:
    target = {"F1": F1_TARGET_BRANCH, "C2A": C2A_TARGET_BRANCH}.get(active_slice)
    if target is None:
        raise VerificationError("post-F0L routing supports only F1 or C2A")
    if event_name == "push" and event_ref == f"refs/heads/{target}":
        return "PINNED_ACCEPTED_F0L"
    if (
        event_name == "pull_request"
        and head_ref == target
        and base_ref == F0L_TARGET_BRANCH
    ):
        return "EVENT_ACCEPTED_F0L"
    raise VerificationError(
        f"{active_slice} routing accepts only its exact push ref or exact "
        "F0L-targeted pull-request ref pair"
    )


def _require_f0l_static_contract() -> None:
    actual = (
        len(ACTIVE_F0L_ALLOWLIST),
        len(F0L_NEW_PATHS),
        len(F0L_EXISTING_BASE_BLOBS),
        len(PROJECT_LANGUAGE_TEST_METHODS)
        + len(PROJECT_LANGUAGE_WRITE_TEST_METHODS)
        + len(PROJECT_LANGUAGE_HTTP_TEST_METHODS),
        len(PROJECT_LANGUAGE_MIGRATION_TEST_METHODS),
        F0L_FOUNDATION_POSTGRESQL_PASSED,
        F0L_FOUNDATION_SQLITE_PASSED,
        F0L_FOUNDATION_SQLITE_SKIPPED,
        len(F1_POST_F0L_ALLOWLIST),
        len(C2A_POST_F0L_ALLOWLIST),
        len(F1_POST_F0L_ALLOWLIST & C2A_POST_F0L_ALLOWLIST),
        tuple(sorted(F0L_FIXTURE_DELTAS)),
        all(path in ACTIVE_F0L_ALLOWLIST for path in F0L_FIXTURE_DELTAS),
        all(path in F0L_EXISTING_BASE_BLOBS for path in F0L_FIXTURE_DELTAS),
        F0L_LANGUAGE_LOOKUP_PREFIXES,
        F0L_ASYNC_ORM_ENTRYPOINTS,
        F0L_RATIFIED_EXISTING_COMMITS,
        PINNED_F0L_CORRECTION_4_TREE,
        tuple(sorted(F0L_CORRECTION_4_PATHS)),
        tuple(sorted(F0L_CORRECTION_5_PATHS)),
    )
    expected = (
        F0L_EXACT_PATH_COUNT,
        F0L_NEW_PATH_COUNT,
        F0L_EXACT_PATH_COUNT - F0L_NEW_PATH_COUNT,
        F0L_PORTABLE_TEST_COUNT,
        F0L_POSTGRESQL_MIGRATION_TEST_COUNT,
        254,
        237,
        17,
        9,
        17,
        0,
        (
            "software/conflict_analysis/domain/tests/test_foundation_studio_publication_reconciliation.py",
            "software/conflict_analysis/production_studio/tests/test_browser_contract.py",
            "software/conflict_analysis/production_studio/tests/test_read_only_http.py",
        ),
        True,
        True,
        (
            "primary_language_tag__",
            "primary_language_assignment__",
        ),
        (
            "acreate",
            "aget_or_create",
            "aupdate_or_create",
            "aupdate",
            "abulk_create",
            "abulk_update",
        ),
        (
            "545e24231673b2c113bde064f835aa24c7d7b10d",
            "79b03a653a1c9c675fba49d09ac61933ec07f114",
            "0f67adabf697f1be67daa5a07b68bc0731954bb0",
            "a6363f8206ed0276ee40fd3c652bf572c872e2b8",
        ),
        "f3869f7e66d3fe9601b937df196f03b1de51aee0",
        (
            "software/conflict_analysis/domain/models.py",
            "software/conflict_analysis/domain/tests/test_data_foundation.py",
            "software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py",
        ),
        (
            ".github/workflows/conflict-analysis.yml",
            "software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py",
        ),
    )
    if actual != expected:
        raise VerificationError(
            "F0L static path/test/downstream contract drifted: "
            + json.dumps({"expected": expected, "actual": actual})
        )


def _require_f0l_accepted_pin(
    *, accepted_head: str | None, accepted_tree: str | None, base_head: str, base_tree: str
) -> None:
    accepted_head = _require_exact_object_id("F0L_ACCEPTED_HEAD", accepted_head)
    accepted_tree = _require_exact_object_id("F0L_ACCEPTED_TREE", accepted_tree)
    if base_head != accepted_head or base_tree != accepted_tree:
        raise VerificationError(
            "post-F0L base HEAD/TREE does not match external accepted-F0L pins"
        )


def _successor_static_contract_payload() -> dict[str, object]:
    return {
        "f0l_correction_4_head": PINNED_F0L_CORRECTION_4_HEAD,
        "f0l_correction_4_tree": PINNED_F0L_CORRECTION_4_TREE,
        "f0l_ratified_commits": F0L_RATIFIED_EXISTING_COMMITS,
        "f0l_correction_4_paths": sorted(F0L_CORRECTION_4_PATHS),
        "f0l_correction_5_paths": sorted(F0L_CORRECTION_5_PATHS),
        "f1_allowlist": sorted(F1_POST_F0L_ALLOWLIST),
        "f1_new_paths": sorted(F1_NEW_PATHS),
        "f1_frozen_paths": F1_FROZEN_PATHS,
        "f1_portable_class": F1_PORTABLE_TEST_CLASS,
        "f1_portable_methods": F1_PORTABLE_TEST_METHODS,
        "f1_migration_class": F1_MIGRATION_TEST_CLASS,
        "f1_migration_methods": F1_MIGRATION_TEST_METHODS,
        "f1_migrations": F1_MIGRATIONS,
        "f1_totals": (
            F1_FOCUSED_POSTGRESQL_TOTAL,
            F1_FOCUSED_SQLITE_PASSED,
            F1_FOCUSED_SQLITE_SKIPPED,
            F1_FOUNDATION_POSTGRESQL_TOTAL,
            F1_FOUNDATION_SQLITE_PASSED,
            F1_FOUNDATION_SQLITE_SKIPPED,
        ),
        "c2a_allowlist": sorted(C2A_POST_F0L_ALLOWLIST),
        "c2a_new_paths": sorted(C2A_NEW_PATHS),
        "c2a_frozen_paths": C2A_FROZEN_PATHS,
        "c2a_portable_class": C2A_PORTABLE_TEST_CLASS,
        "c2a_portable_methods": C2A_PORTABLE_TEST_METHODS,
        "c2a_chromium_methods": C2A_CHROMIUM_TEST_METHODS,
        "c2a_totals": (
            C2A_PORTABLE_TOTAL,
            C2A_CHROMIUM_TOTAL,
            C2A_FOUNDATION_POSTGRESQL_TOTAL,
            C2A_FOUNDATION_SQLITE_PASSED,
            C2A_FOUNDATION_SQLITE_SKIPPED,
            SUCCESSOR_C0_TOTAL,
            SUCCESSOR_C1_PORTABLE_TOTAL,
            SUCCESSOR_C1_CHROMIUM_TOTAL,
        ),
        "f0l_sqlite_skipped_nodes": F0L_SQLITE_SKIPPED_TEST_NODES,
        "successor_junit_files": SUCCESSOR_JUNIT_FILES,
        "successor_migration_gates": SUCCESSOR_MIGRATION_GATES,
        "successor_wheel_checks": SUCCESSOR_WHEEL_CHECKS,
        "successor_wheel_required_members": {
            key: sorted(value)
            for key, value in SUCCESSOR_WHEEL_REQUIRED_MEMBERS.items()
        },
        "successor_repository_only_wheel_paths": {
            key: sorted(value)
            for key, value in SUCCESSOR_REPOSITORY_ONLY_WHEEL_PATHS.items()
        },
    }


def _require_successor_static_contract() -> None:
    encoded = json.dumps(
        _successor_static_contract_payload(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    expected = "0c23032ee8a7da3548834d89912c03805aa9fa5ac1450927898e7483e446deca"
    if digest != expected:
        raise VerificationError(
            "post-F0L successor static contract drifted: "
            + json.dumps({"expected": expected, "actual": digest})
        )


def _successor_workflow_required_tokens() -> tuple[str, ...]:
    terminal_cli = '--successor-evidence-dir "$RUNNER_TEMP/successor-evidence"'
    return (
        "name: Require complete F1/C2A functional evidence",
        "if: env.ACTIVE_SLICE == 'F1' || env.ACTIVE_SLICE == 'C2A'",
        terminal_cli,
        "POST_F0L_F1_C2A_EXECUTABLE_CI=PASS",
        "-k",
        *C2A_CHROMIUM_TEST_METHODS,
        SUCCESSOR_EVIDENCE_SCHEMA,
        SUCCESSOR_MIGRATION_EVIDENCE_SCHEMA,
        SUCCESSOR_WHEEL_EVIDENCE_SCHEMA,
        C2A_SYNTHETIC_EVIDENCE_SCHEMA,
        "manifest.json",
        "migration.json",
        "wheel-install.json",
        "synthetic-tree.json",
        SUCCESSOR_WHEEL_NAME,
        *SUCCESSOR_JUNIT_FILES["F1"],
        *SUCCESSOR_JUNIT_FILES["C2A"],
    )


def _require_successor_workflow_contract(source: str) -> None:
    terminal_cli = '--successor-evidence-dir "$RUNNER_TEMP/successor-evidence"'
    required_tokens = _successor_workflow_required_tokens()
    missing = [token for token in required_tokens if token not in source]
    if missing or source.count(terminal_cli) != 1:
        raise VerificationError(
            "successor workflow terminal evidence gate drifted: "
            + json.dumps(
                {
                    "missing": missing,
                    "terminal_invocation_count": source.count(terminal_cli),
                }
            )
        )


def _require_successor_repository_contract(
    repo: Path,
    *,
    active_slice: str,
    base_head: str,
) -> dict[str, object]:
    allowlist = (
        F1_POST_F0L_ALLOWLIST if active_slice == "F1" else C2A_POST_F0L_ALLOWLIST
    )
    new_paths = F1_NEW_PATHS if active_slice == "F1" else C2A_NEW_PATHS
    frozen_paths = F1_FROZEN_PATHS if active_slice == "F1" else C2A_FROZEN_PATHS
    base_blobs: dict[str, str] = {}
    for path in sorted(allowlist):
        base_entry = _git(repo, "ls-tree", base_head, "--", path)
        head_entry = _git(repo, "ls-tree", "HEAD", "--", path)
        if path in new_paths:
            if base_entry:
                raise VerificationError(
                    f"{active_slice} required-new path already exists at accepted F0L: {path}"
                )
            _require_regular_blob_tree_entry(
                path=path,
                revision="HEAD",
                entry=head_entry,
            )
            continue
        base_blobs[path] = _require_regular_blob_tree_entry(
            path=path,
            revision=base_head,
            entry=base_entry,
        )
        _require_regular_blob_tree_entry(
            path=path,
            revision="HEAD",
            entry=head_entry,
        )

    frozen_objects: dict[str, str] = {}
    for path in frozen_paths:
        base_object = _git(repo, "rev-parse", f"{base_head}:{path}")
        head_object = _git(repo, "rev-parse", f"HEAD:{path}")
        if base_object != head_object:
            raise VerificationError(
                f"{active_slice} accepted-F0L frozen input drifted at {path}"
            )
        frozen_objects[path] = base_object

    migrations = tuple(
        line
        for line in _git(
            repo,
            "ls-files",
            "software/conflict_analysis/domain/migrations",
        ).splitlines()
        if line
    )
    expected_migrations = F1_MIGRATIONS if active_slice == "F1" else F0L_MIGRATIONS
    if migrations != expected_migrations:
        raise VerificationError(
            f"{active_slice} migration filename set drifted: "
            + json.dumps(
                {"expected": expected_migrations, "actual": migrations}
            )
        )
    if active_slice == "F1":
        migration_source = (
            repo
            / "software/conflict_analysis/domain/migrations/0017_multilingual_evidence_lineage.py"
        ).read_text(encoding="utf-8")
        if not re.search(
            r"dependencies\s*=\s*\[\s*\(\s*[\"']domain[\"']\s*,\s*"
            r"[\"']0016_project_primary_language[\"']\s*\)\s*,?\s*\]",
            migration_source,
            re.DOTALL,
        ):
            raise VerificationError(
                "F1 migration must depend only on domain.0016_project_primary_language"
            )
    return {
        "new_paths": sorted(new_paths),
        "existing_base_blobs": dict(sorted(base_blobs.items())),
        "frozen_objects": dict(sorted(frozen_objects.items())),
        "migration_filenames": list(migrations),
    }


def _find_exact_test_class_source(repo: Path, class_name: str) -> str:
    matches: list[str] = []
    for path in sorted(
        (repo / "software/conflict_analysis/domain/tests").glob("test_*.py")
    ):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        if any(
            isinstance(node, ast.ClassDef) and node.name == class_name
            for node in tree.body
        ):
            matches.append(source)
    if len(matches) != 1:
        raise VerificationError(
            f"expected exactly one {class_name} class across domain tests, "
            f"found {len(matches)}"
        )
    return matches[0]


def _require_package_restore_caller_registry(repo: Path) -> None:
    production_calls: list[str] = []
    domain_root = repo / "software/conflict_analysis/domain"
    for path in sorted(domain_root.rglob("*.py")):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "restore_legacy_unknown_from_package"
            ):
                production_calls.append(path.relative_to(repo).as_posix())
    expected = [
        "software/conflict_analysis/domain/services/project_packages.py"
    ]
    if production_calls != expected:
        raise VerificationError(
            "legacy-unknown package restore production caller registry drifted: "
            + json.dumps({"expected": expected, "actual": production_calls})
        )


def _require_synthetic_merge_contract(
    *,
    expected_base_head: str,
    expected_delivery_head: str,
    actual_parents: tuple[str, ...],
    delivery_tree: str,
    synthetic_tree: str,
    independent_tree: str,
) -> None:
    expected_base_head = _require_exact_object_id(
        "synthetic expected base HEAD", expected_base_head
    )
    expected_delivery_head = _require_exact_object_id(
        "synthetic expected delivery HEAD", expected_delivery_head
    )
    delivery_tree = _require_exact_object_id("delivery TREE", delivery_tree)
    synthetic_tree = _require_exact_object_id("synthetic merge TREE", synthetic_tree)
    independent_tree = _require_exact_object_id(
        "independent merge-tree TREE", independent_tree
    )
    if actual_parents != (expected_base_head, expected_delivery_head):
        raise VerificationError(
            "synthetic merge parents must be [exact base HEAD, exact delivery HEAD]"
        )
    if synthetic_tree != delivery_tree or independent_tree != delivery_tree:
        raise VerificationError(
            "synthetic merge, delivery and independent merge-tree trees must be equal"
        )


def _require_exact_test_topology(
    *,
    source: str,
    class_name: str,
    expected_methods: tuple[str, ...],
) -> None:
    tree = ast.parse(source)
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    ]
    if len(classes) != 1:
        raise VerificationError(
            f"expected exactly one {class_name} class, found {len(classes)}"
        )
    actual = tuple(
        node.name
        for node in classes[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    )
    if actual != expected_methods:
        raise VerificationError(
            f"{class_name} test topology mismatch: "
            + json.dumps({"expected": expected_methods, "actual": actual})
        )


def _require_successor_test_source_topology(
    source: str, *, active_slice: str
) -> None:
    tree = ast.parse(source)
    module_level_tests = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]
    if module_level_tests:
        raise VerificationError(
            f"{active_slice} successor test file has unauthorized module-level tests: "
            + json.dumps(module_level_tests)
        )
    if active_slice == "F1":
        contracts = (
            (F1_PORTABLE_TEST_CLASS, F1_PORTABLE_TEST_METHODS),
            (F1_MIGRATION_TEST_CLASS, F1_MIGRATION_TEST_METHODS),
        )
    else:
        contracts = ((C2A_PORTABLE_TEST_CLASS, C2A_PORTABLE_TEST_METHODS),)
    for class_name, methods in contracts:
        _require_exact_test_topology(
            source=source,
            class_name=class_name,
            expected_methods=methods,
        )
    actual_test_nodes = [
        (class_node.name, method.name)
        for class_node in tree.body
        if isinstance(class_node, ast.ClassDef)
        for method in class_node.body
        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
        and method.name.startswith("test_")
    ]
    expected_test_nodes = [
        (class_name, method)
        for class_name, methods in contracts
        for method in methods
    ]
    if active_slice == "C2A":
        portable_nodes = set(C2A_PORTABLE_TEST_NODES)
        chromium_nodes = [
            node for node in actual_test_nodes if node not in portable_nodes
        ]
        chromium_methods = tuple(method for _class_name, method in chromium_nodes)
        expected_registry_matches = (
            len(actual_test_nodes)
            == len(C2A_PORTABLE_TEST_METHODS) + len(C2A_CHROMIUM_TEST_METHODS)
            and set(chromium_methods) == set(C2A_CHROMIUM_TEST_METHODS)
            and len(chromium_methods) == len(set(chromium_methods))
        )
        expected_for_report: object = {
            "portable_nodes": expected_test_nodes,
            "chromium_methods": C2A_CHROMIUM_TEST_METHODS,
            "chromium_class": "authority-does-not-pin",
        }
    else:
        expected_registry_matches = actual_test_nodes == expected_test_nodes
        expected_for_report = expected_test_nodes
    if not expected_registry_matches:
        raise VerificationError(
            f"{active_slice} successor test-file registry drifted: "
            + json.dumps(
                {"expected": expected_for_report, "actual": actual_test_nodes}
            )
        )


def _require_successor_test_topology(repo: Path, *, active_slice: str) -> None:
    for class_name, methods in (
        (PROJECT_LANGUAGE_TEST_CLASS, PROJECT_LANGUAGE_TEST_METHODS),
        (PROJECT_LANGUAGE_WRITE_TEST_CLASS, PROJECT_LANGUAGE_WRITE_TEST_METHODS),
        (PROJECT_LANGUAGE_HTTP_TEST_CLASS, PROJECT_LANGUAGE_HTTP_TEST_METHODS),
        (PROJECT_LANGUAGE_MIGRATION_TEST_CLASS, PROJECT_LANGUAGE_MIGRATION_TEST_METHODS),
    ):
        _require_exact_test_topology(
            source=_find_exact_test_class_source(repo, class_name),
            class_name=class_name,
            expected_methods=methods,
        )
    models_source = (
        repo / "software/conflict_analysis/domain/models.py"
    ).read_text(encoding="utf-8")
    _require_f0l_correction_4_evidence(
        models_source=models_source,
        tests_source=_find_exact_test_class_source(repo, PROJECT_LANGUAGE_TEST_CLASS),
    )
    _require_package_restore_caller_registry(repo)
    test_path = (
        "software/conflict_analysis/domain/tests/test_multilingual_evidence_lineage.py"
        if active_slice == "F1"
        else "software/conflict_analysis/production_studio/tests/test_lifecycle_publication.py"
    )
    _require_successor_test_source_topology(
        (repo / test_path).read_text(encoding="utf-8"),
        active_slice=active_slice,
    )


def _require_f0l_correction_4_evidence(
    *,
    models_source: str,
    tests_source: str,
) -> None:
    models_tree = ast.parse(models_source)
    prefix_assignments = [
        node
        for node in models_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "_PROJECT_LANGUAGE_LOOKUP_PREFIXES"
            for target in node.targets
        )
    ]
    try:
        declared_prefixes = (
            ast.literal_eval(prefix_assignments[0].value)
            if len(prefix_assignments) == 1
            else None
        )
    except (ValueError, SyntaxError):
        declared_prefixes = None
    if declared_prefixes != F0L_LANGUAGE_LOOKUP_PREFIXES:
        raise VerificationError("F0L language lookup-expression prefixes drifted")

    queryset_classes = [
        node
        for node in models_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ProjectQuerySet"
    ]
    if len(queryset_classes) != 1:
        raise VerificationError("expected exactly one ProjectQuerySet class")
    queryset_methods = {
        node.name: node
        for node in queryset_classes[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    prevalidate = queryset_methods.get("_prevalidate_project_language_request")
    core = queryset_methods.get("_get_or_create_prevalidated")
    if prevalidate is None or core is None:
        raise VerificationError("F0L prevalidated Project upsert boundary is absent")

    def has_positive_lookup_prefix_guard(
        expression: ast.AST,
        *,
        negated: bool = False,
    ) -> bool:
        if isinstance(expression, ast.UnaryOp) and isinstance(expression.op, ast.Not):
            return has_positive_lookup_prefix_guard(
                expression.operand,
                negated=not negated,
            )
        if (
            isinstance(expression, ast.Call)
            and isinstance(expression.func, ast.Attribute)
            and expression.func.attr == "startswith"
            and any(
                isinstance(argument, ast.Name)
                and argument.id == "_PROJECT_LANGUAGE_LOOKUP_PREFIXES"
                for argument in expression.args
            )
        ):
            return not negated
        return any(
            has_positive_lookup_prefix_guard(child, negated=negated)
            for child in ast.iter_child_nodes(expression)
        )

    prefix_guard = any(
        has_positive_lookup_prefix_guard(node.test)
        and any(
            isinstance(body_node, ast.Raise)
            for statement in node.body
            for body_node in ast.walk(statement)
        )
        for node in ast.walk(prevalidate)
        if isinstance(node, ast.If)
    )
    helper_names = {
        node.id for node in ast.walk(prevalidate) if isinstance(node, ast.Name)
    }
    helper_attributes = {
        node.attr for node in ast.walk(prevalidate) if isinstance(node, ast.Attribute)
    }
    helper_literals = {
        node.value
        for node in ast.walk(prevalidate)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    if (
        not prefix_guard
        or not {"callable", "canonicalize_language_tag"} <= helper_names
        or not {"EXPLICIT", "LEGACY_UNKNOWN"} <= helper_attributes
        or not {
            "project_primary_language_lookup_forbidden",
            "Project language identity values are inconsistent.",
        }
        <= helper_literals
    ):
        raise VerificationError(
            "F0L lookup rejection, scalar validation or duplicate guard drifted"
        )

    for method_name in ("get_or_create", "update_or_create"):
        method = queryset_methods.get(method_name)
        if method is None or not method.body:
            raise VerificationError(f"ProjectQuerySet.{method_name} is absent")
        first_statement_calls = [
            node for node in ast.walk(method.body[0]) if isinstance(node, ast.Call)
        ]
        if len(first_statement_calls) != 1 or not any(
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "_prevalidate_project_language_request"
            for call in first_statement_calls
        ):
            raise VerificationError(
                f"ProjectQuerySet.{method_name} must prevalidate before lookup/lock"
            )

    if not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_assert_prevalidated_language_matches"
        for node in ast.walk(core)
    ):
        raise VerificationError("F0L persisted language comparison guard drifted")

    tests_tree = ast.parse(tests_source)
    test_classes = [
        node
        for node in tests_tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == PROJECT_LANGUAGE_TEST_CLASS
    ]
    if len(test_classes) != 1:
        raise VerificationError(
            f"expected exactly one {PROJECT_LANGUAGE_TEST_CLASS} class"
        )
    async_locations: dict[str, set[str]] = {
        entrypoint: set() for entrypoint in F0L_ASYNC_ORM_ENTRYPOINTS
    }
    uninvoked_coroutines: dict[str, list[str]] = {}
    for method in test_classes[0].body:
        if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        invoked_coroutines = {
            call.func.args[0].id
            for statement in method.body
            if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))
            for call in ast.walk(statement)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Call)
            and isinstance(call.func.func, ast.Name)
            and call.func.func.id == "async_to_sync"
            and len(call.func.args) == 1
            and isinstance(call.func.args[0], ast.Name)
        }
        for coroutine in (
            node for node in method.body if isinstance(node, ast.AsyncFunctionDef)
        ):
            coroutine_entrypoints = {
                call.func.attr
                for awaited in ast.walk(coroutine)
                if isinstance(awaited, ast.Await)
                for call in ast.walk(awaited.value)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr in async_locations
            }
            if not coroutine_entrypoints:
                continue
            if coroutine.name not in invoked_coroutines:
                uninvoked_coroutines[
                    f"{method.name}.{coroutine.name}"
                ] = sorted(coroutine_entrypoints)
                continue
            for entrypoint in coroutine_entrypoints:
                async_locations[entrypoint].add(method.name)
    missing = sorted(
        entrypoint
        for entrypoint, locations in async_locations.items()
        if not locations
    )
    outside_registered_tests = {
        entrypoint: sorted(locations - set(PROJECT_LANGUAGE_TEST_METHODS))
        for entrypoint, locations in async_locations.items()
        if locations - set(PROJECT_LANGUAGE_TEST_METHODS)
    }
    if missing or outside_registered_tests or uninvoked_coroutines:
        raise VerificationError(
            "F0L async ORM runtime evidence drifted: "
            + json.dumps(
                {
                    "missing": missing,
                    "outside_registered_tests": outside_registered_tests,
                    "uninvoked_coroutines": uninvoked_coroutines,
                }
            )
        )


def _normalized_test_node(class_name: str, method_name: str) -> tuple[str, str]:
    return class_name.rsplit(".", 1)[-1], method_name


def _f0l_focused_test_nodes() -> tuple[tuple[str, str], ...]:
    return tuple(
        (class_name, method)
        for class_name, methods in (
            (PROJECT_LANGUAGE_TEST_CLASS, PROJECT_LANGUAGE_TEST_METHODS),
            (PROJECT_LANGUAGE_WRITE_TEST_CLASS, PROJECT_LANGUAGE_WRITE_TEST_METHODS),
            (PROJECT_LANGUAGE_HTTP_TEST_CLASS, PROJECT_LANGUAGE_HTTP_TEST_METHODS),
            (
                PROJECT_LANGUAGE_MIGRATION_TEST_CLASS,
                PROJECT_LANGUAGE_MIGRATION_TEST_METHODS,
            ),
        )
        for method in methods
    )


def _require_junit_contract(
    *,
    label: str,
    source: str,
    expected_total: int,
    expected_skipped: int,
    exact_nodes: tuple[tuple[str, str], ...] | None = None,
    exact_method_names: tuple[str, ...] | None = None,
    required_nodes: tuple[tuple[str, str], ...] = (),
    exact_skipped_nodes: tuple[tuple[str, str], ...] | None = None,
) -> dict[str, object]:
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        raise VerificationError(f"{label} JUnit XML is malformed: {exc}") from exc
    cases = root.findall(".//testcase")
    identities: list[tuple[str, str]] = []
    skipped: list[tuple[str, str]] = []
    failures: list[tuple[str, str]] = []
    for case in cases:
        class_name = case.attrib.get("classname")
        method_name = case.attrib.get("name")
        if not class_name or not method_name:
            raise VerificationError(f"{label} JUnit testcase identity is incomplete")
        identity = _normalized_test_node(class_name, method_name)
        identities.append(identity)
        if case.find("skipped") is not None:
            skipped.append(identity)
        if case.find("failure") is not None or case.find("error") is not None:
            failures.append(identity)
    if len(set(identities)) != len(identities):
        raise VerificationError(f"{label} JUnit contains duplicate testcase identities")
    expected_exact = (
        {_normalized_test_node(*item) for item in exact_nodes}
        if exact_nodes is not None
        else None
    )
    required = {_normalized_test_node(*item) for item in required_nodes}
    expected_skips = (
        {_normalized_test_node(*item) for item in exact_skipped_nodes}
        if exact_skipped_nodes is not None
        else None
    )
    actual = set(identities)
    actual_methods = {method for _class_name, method in identities}
    expected_methods = set(exact_method_names or ())
    actual_skips = set(skipped)
    if (
        len(cases) != expected_total
        or len(skipped) != expected_skipped
        or failures
        or (expected_exact is not None and actual != expected_exact)
        or (
            exact_method_names is not None
            and (
                actual_methods != expected_methods
                or len(identities) != len(expected_methods)
            )
        )
        or not required <= actual
        or (expected_skips is not None and actual_skips != expected_skips)
    ):
        raise VerificationError(
            f"{label} JUnit evidence drifted: "
            + json.dumps(
                {
                    "expected_total": expected_total,
                    "actual_total": len(cases),
                    "expected_skipped": expected_skipped,
                    "actual_skipped": len(skipped),
                    "failures": failures,
                    "missing_required": sorted(required - actual),
                    "exact_node_match": (
                        None if expected_exact is None else actual == expected_exact
                    ),
                    "exact_method_match": (
                        None
                        if exact_method_names is None
                        else actual_methods == expected_methods
                    ),
                    "exact_skip_match": (
                        None if expected_skips is None else actual_skips == expected_skips
                    ),
                }
            )
        )
    return {
        "total": len(cases),
        "passed": len(cases) - len(skipped),
        "skipped": len(skipped),
    }


def _successor_junit_contracts(
    active_slice: str,
) -> dict[str, dict[str, object]]:
    f0l_nodes = _f0l_focused_test_nodes()
    if active_slice == "F1":
        f1_skips = tuple(
            (F1_MIGRATION_TEST_CLASS, method)
            for method in F1_MIGRATION_TEST_METHODS
        )
        return {
            "f1-focused-postgresql.xml": {
                "expected_total": 18,
                "expected_skipped": 0,
                "exact_nodes": F1_FOCUSED_TEST_NODES,
            },
            "f1-focused-sqlite.xml": {
                "expected_total": 18,
                "expected_skipped": 2,
                "exact_nodes": F1_FOCUSED_TEST_NODES,
                "exact_skipped_nodes": f1_skips,
            },
            "f1-foundation-postgresql.xml": {
                "expected_total": F1_FOUNDATION_POSTGRESQL_TOTAL,
                "expected_skipped": 0,
                "required_nodes": (*f0l_nodes, *F1_FOCUSED_TEST_NODES),
            },
            "f1-foundation-sqlite.xml": {
                "expected_total": F1_FOUNDATION_POSTGRESQL_TOTAL,
                "expected_skipped": F1_FOUNDATION_SQLITE_SKIPPED,
                "required_nodes": (*f0l_nodes, *F1_FOCUSED_TEST_NODES),
                "exact_skipped_nodes": (*F0L_SQLITE_SKIPPED_TEST_NODES, *f1_skips),
            },
            "f1-c0-postgresql.xml": {
                "expected_total": SUCCESSOR_C0_TOTAL,
                "expected_skipped": 0,
            },
            "f1-c0-sqlite.xml": {
                "expected_total": SUCCESSOR_C0_TOTAL,
                "expected_skipped": 0,
            },
            "f1-c1-postgresql.xml": {
                "expected_total": SUCCESSOR_C1_PORTABLE_TOTAL,
                "expected_skipped": 0,
            },
            "f1-c1-sqlite.xml": {
                "expected_total": SUCCESSOR_C1_PORTABLE_TOTAL,
                "expected_skipped": 0,
            },
            "f1-c1-chromium-postgresql.xml": {
                "expected_total": SUCCESSOR_C1_CHROMIUM_TOTAL,
                "expected_skipped": 0,
                "exact_nodes": (SUCCESSOR_C1_CHROMIUM_TEST_NODE,),
            },
        }
    return {
        "c2a-portable-postgresql.xml": {
            "expected_total": C2A_PORTABLE_TOTAL,
            "expected_skipped": 0,
            "exact_nodes": C2A_PORTABLE_TEST_NODES,
        },
        "c2a-portable-sqlite.xml": {
            "expected_total": C2A_PORTABLE_TOTAL,
            "expected_skipped": 0,
            "exact_nodes": C2A_PORTABLE_TEST_NODES,
        },
        "c2a-foundation-postgresql.xml": {
            "expected_total": C2A_FOUNDATION_POSTGRESQL_TOTAL,
            "expected_skipped": 0,
            "required_nodes": f0l_nodes,
        },
        "c2a-foundation-sqlite.xml": {
            "expected_total": C2A_FOUNDATION_POSTGRESQL_TOTAL,
            "expected_skipped": C2A_FOUNDATION_SQLITE_SKIPPED,
            "required_nodes": f0l_nodes,
            "exact_skipped_nodes": F0L_SQLITE_SKIPPED_TEST_NODES,
        },
        "c2a-c0-postgresql.xml": {
            "expected_total": SUCCESSOR_C0_TOTAL,
            "expected_skipped": 0,
        },
        "c2a-c0-sqlite.xml": {
            "expected_total": SUCCESSOR_C0_TOTAL,
            "expected_skipped": 0,
        },
        "c2a-c1-postgresql.xml": {
            "expected_total": SUCCESSOR_C1_PORTABLE_TOTAL,
            "expected_skipped": 0,
        },
        "c2a-c1-sqlite.xml": {
            "expected_total": SUCCESSOR_C1_PORTABLE_TOTAL,
            "expected_skipped": 0,
        },
        "c2a-c1-chromium-postgresql.xml": {
            "expected_total": SUCCESSOR_C1_CHROMIUM_TOTAL,
            "expected_skipped": 0,
            "exact_nodes": (SUCCESSOR_C1_CHROMIUM_TEST_NODE,),
        },
        "c2a-chromium-postgresql.xml": {
            "expected_total": C2A_CHROMIUM_TOTAL,
            "expected_skipped": 0,
            "exact_method_names": C2A_CHROMIUM_TEST_METHODS,
        },
    }


def _load_exact_json(path: Path, *, keys: frozenset[str]) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"successor evidence JSON is unreadable at {path.name}: {exc}") from exc
    if not isinstance(value, dict) or set(value) != keys:
        raise VerificationError(
            f"successor evidence JSON shape drifted at {path.name}: "
            + json.dumps({"expected": sorted(keys), "actual": sorted(value) if isinstance(value, dict) else None})
        )
    return value


def _require_evidence_identity(
    evidence: dict[str, object],
    *,
    schema: str,
    active_slice: str,
    base_head: str,
    base_tree: str,
    delivery_head: str,
    delivery_tree: str,
) -> None:
    expected = {
        "schema": schema,
        "active_slice": active_slice,
        "base_head": base_head,
        "base_tree": base_tree,
        "delivery_head": delivery_head,
        "delivery_tree": delivery_tree,
    }
    actual = {key: evidence.get(key) for key in expected}
    if actual != expected:
        raise VerificationError(
            "successor evidence identity is stale or mismatched: "
            + json.dumps({"expected": expected, "actual": actual})
        )


def _require_successor_ci_evidence(
    evidence_dir: Path | None,
    *,
    repo: Path,
    active_slice: str,
    base_head: str,
    base_tree: str,
    delivery_head: str,
    delivery_tree: str,
) -> dict[str, object]:
    if evidence_dir is None:
        raise VerificationError(
            f"{active_slice} routed verification requires --successor-evidence-dir"
        )
    try:
        if evidence_dir.is_symlink() or not evidence_dir.is_dir():
            raise VerificationError("successor evidence directory is absent or a symlink")
        directory = evidence_dir.resolve(strict=True)
        junit_names = SUCCESSOR_JUNIT_FILES[active_slice]
        synthetic_name = "synthetic-tree.json" if active_slice == "C2A" else None
        expected_names = {
            "manifest.json",
            "migration.json",
            "wheel-install.json",
            SUCCESSOR_WHEEL_NAME,
            *junit_names,
        }
        if synthetic_name is not None:
            expected_names.add(synthetic_name)
        entries = list(directory.iterdir())
        actual_names = {entry.name for entry in entries}
        if actual_names != expected_names:
            raise VerificationError(
                "successor evidence filename set drifted: "
                + json.dumps(
                    {"expected": sorted(expected_names), "actual": sorted(actual_names)}
                )
            )
        for entry in entries:
            if entry.is_symlink() or not entry.is_file():
                raise VerificationError(
                    f"successor evidence entry must be a regular file: {entry.name}"
                )

        manifest = _load_exact_json(
            directory / "manifest.json",
            keys=frozenset(
                {
                    "schema",
                    "active_slice",
                    "base_head",
                    "base_tree",
                    "delivery_head",
                    "delivery_tree",
                    "junit_files",
                    "migration_evidence",
                    "wheel_file",
                    "wheel_install_evidence",
                    "synthetic_tree_evidence",
                }
            ),
        )
        _require_evidence_identity(
            manifest,
            schema=SUCCESSOR_EVIDENCE_SCHEMA,
            active_slice=active_slice,
            base_head=base_head,
            base_tree=base_tree,
            delivery_head=delivery_head,
            delivery_tree=delivery_tree,
        )
        expected_manifest_files = {
            "junit_files": list(junit_names),
            "migration_evidence": "migration.json",
            "wheel_file": SUCCESSOR_WHEEL_NAME,
            "wheel_install_evidence": "wheel-install.json",
            "synthetic_tree_evidence": synthetic_name,
        }
        actual_manifest_files = {
            key: manifest.get(key) for key in expected_manifest_files
        }
        if actual_manifest_files != expected_manifest_files:
            raise VerificationError(
                "successor evidence manifest file registry drifted: "
                + json.dumps(
                    {
                        "expected": expected_manifest_files,
                        "actual": actual_manifest_files,
                    }
                )
            )

        junit_reports: dict[str, object] = {}
        for name, contract in _successor_junit_contracts(active_slice).items():
            junit_reports[name] = _require_junit_contract(
                label=name,
                source=(directory / name).read_text(encoding="utf-8"),
                **contract,
            )

        identity_keys = {
            "schema",
            "active_slice",
            "base_head",
            "base_tree",
            "delivery_head",
            "delivery_tree",
        }
        migration = _load_exact_json(
            directory / "migration.json",
            keys=frozenset({*identity_keys, "gates"}),
        )
        _require_evidence_identity(
            migration,
            schema=SUCCESSOR_MIGRATION_EVIDENCE_SCHEMA,
            active_slice=active_slice,
            base_head=base_head,
            base_tree=base_tree,
            delivery_head=delivery_head,
            delivery_tree=delivery_tree,
        )
        if migration.get("gates") != list(SUCCESSOR_MIGRATION_GATES[active_slice]):
            raise VerificationError("successor migration evidence gate registry drifted")

        wheel_evidence = _load_exact_json(
            directory / "wheel-install.json",
            keys=frozenset(
                {*identity_keys, "wheel_sha256", "source_tree_fallback", "checks"}
            ),
        )
        _require_evidence_identity(
            wheel_evidence,
            schema=SUCCESSOR_WHEEL_EVIDENCE_SCHEMA,
            active_slice=active_slice,
            base_head=base_head,
            base_tree=base_tree,
            delivery_head=delivery_head,
            delivery_tree=delivery_tree,
        )
        wheel_digest = wheel_evidence.get("wheel_sha256")
        if (
            not isinstance(wheel_digest, str)
            or _LOWER_HEX_64.fullmatch(wheel_digest) is None
            or wheel_evidence.get("source_tree_fallback") is not False
            or wheel_evidence.get("checks")
            != list(SUCCESSOR_WHEEL_CHECKS[active_slice])
        ):
            raise VerificationError("successor wheel/install evidence drifted")
        wheel_path = directory / SUCCESSOR_WHEEL_NAME
        actual_wheel_digest = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
        if actual_wheel_digest != wheel_digest:
            raise VerificationError("successor wheel SHA-256 does not match its evidence")
        with ZipFile(wheel_path) as archive:
            members = archive.namelist()
            if archive.testzip() is not None or len(members) != len(set(members)):
                raise VerificationError("successor wheel is corrupt or has duplicate members")
            member_set = set(members)
        missing_members = SUCCESSOR_WHEEL_REQUIRED_MEMBERS[active_slice] - member_set
        repository_only_paths = SUCCESSOR_REPOSITORY_ONLY_WHEEL_PATHS[active_slice]
        forbidden_members = {
            member
            for member in member_set
            if any(
                member == path or member.endswith(f"/{path}")
                for path in repository_only_paths
            )
        }
        if missing_members or forbidden_members:
            raise VerificationError(
                "successor wheel payload contract drifted: "
                + json.dumps(
                    {
                        "missing": sorted(missing_members),
                        "repository_only_in_wheel": sorted(forbidden_members),
                    }
                )
            )

        synthetic_report: dict[str, object] | None = None
        if active_slice == "C2A":
            synthetic = _load_exact_json(
                directory / "synthetic-tree.json",
                keys=frozenset(
                    {
                        "schema",
                        "base_head",
                        "delivery_head",
                        "parents",
                        "delivery_tree",
                        "synthetic_tree",
                        "independent_tree",
                    }
                ),
            )
            if synthetic.get("schema") != C2A_SYNTHETIC_EVIDENCE_SCHEMA:
                raise VerificationError("C2A synthetic-tree evidence schema drifted")
            parents = synthetic.get("parents")
            if not isinstance(parents, list) or not all(
                isinstance(parent, str) for parent in parents
            ):
                raise VerificationError("C2A synthetic-tree parents are malformed")
            recomputed_independent_tree = _git(
                repo,
                "merge-tree",
                "--write-tree",
                base_head,
                delivery_head,
            )
            _require_synthetic_merge_contract(
                expected_base_head=base_head,
                expected_delivery_head=delivery_head,
                actual_parents=tuple(parents),
                delivery_tree=delivery_tree,
                synthetic_tree=str(synthetic.get("synthetic_tree", "")),
                independent_tree=recomputed_independent_tree,
            )
            if (
                synthetic.get("base_head") != base_head
                or synthetic.get("delivery_head") != delivery_head
                or synthetic.get("delivery_tree") != delivery_tree
                or synthetic.get("independent_tree")
                != recomputed_independent_tree
            ):
                raise VerificationError("C2A synthetic-tree evidence identity drifted")
            synthetic_report = {
                "parents": parents,
                "synthetic_tree": synthetic["synthetic_tree"],
                "independent_tree": recomputed_independent_tree,
            }
    except (OSError, UnicodeDecodeError, BadZipFile) as exc:
        raise VerificationError(f"successor CI evidence is unreadable: {exc}") from exc
    return {
        "schema": SUCCESSOR_EVIDENCE_SCHEMA,
        "directory": str(directory),
        "junit": junit_reports,
        "migration_gates": list(SUCCESSOR_MIGRATION_GATES[active_slice]),
        "wheel_sha256": actual_wheel_digest,
        "wheel_required_members": sorted(
            SUCCESSOR_WHEEL_REQUIRED_MEMBERS[active_slice]
        ),
        "repository_only_wheel_paths": sorted(
            SUCCESSOR_REPOSITORY_ONLY_WHEEL_PATHS[active_slice]
        ),
        "synthetic_tree": synthetic_report,
    }


def _normalized_authorized_method_body(
    source: str,
    *,
    class_name: str,
    method_name: str,
) -> str:
    tree = ast.parse(source)
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    ]
    if len(classes) != 1:
        raise VerificationError(
            f"expected exactly one frozen {class_name} class, found {len(classes)}"
        )
    methods = [
        node
        for node in classes[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == method_name
    ]
    if len(methods) != 1 or not methods[0].body:
        raise VerificationError(
            f"expected exactly one non-empty frozen {class_name}.{method_name}"
        )
    method = methods[0]
    lines = source.splitlines(keepends=True)
    start = method.body[0].lineno - 1
    end = method.end_lineno
    indent = " " * (method.col_offset + 4)
    lines[start:end] = [f"{indent}<AUTHORIZED_FD03_RC2_ASSERTION_BODY>\n"]
    return "".join(lines).rstrip("\n")


def self_check() -> dict[str, object]:
    """Exercise only deterministic slice/pin parsing; make no repository claims."""

    c0 = _resolve_slice_contract(
        active_slice="C0",
        base_head=PINNED_BASE_HEAD,
        base_tree=PINNED_BASE_TREE,
        fd05_accepted_head=None,
        fd05_accepted_tree=None,
    )
    r0 = _resolve_slice_contract(
        active_slice="R0",
        base_head=PINNED_R0_BASE_HEAD,
        base_tree=PINNED_R0_BASE_TREE,
        fd05_accepted_head=PINNED_R0_BASE_HEAD,
        fd05_accepted_tree=PINNED_R0_BASE_TREE,
    )
    c1 = _resolve_slice_contract(
        active_slice="C1",
        base_head=PINNED_C1_START_HEAD,
        base_tree=PINNED_C1_START_TREE,
        fd05_accepted_head=PINNED_R0_BASE_HEAD,
        fd05_accepted_tree=PINNED_R0_BASE_TREE,
    )
    fd02 = _resolve_slice_contract(
        active_slice="FD02",
        base_head=PINNED_FD02_BASE_HEAD,
        base_tree=PINNED_FD02_BASE_TREE,
        fd05_accepted_head=None,
        fd05_accepted_tree=None,
    )
    fd03 = _resolve_slice_contract(
        active_slice="FD03",
        base_head=PINNED_FD03_BASE_HEAD,
        base_tree=PINNED_FD03_BASE_TREE,
        fd05_accepted_head=None,
        fd05_accepted_tree=None,
    )
    other_head = "b" * 40
    other_tree = "d" * 40
    valid_r0 = {
        "active_slice": "R0",
        "base_head": PINNED_R0_BASE_HEAD,
        "base_tree": PINNED_R0_BASE_TREE,
        "fd05_accepted_head": PINNED_R0_BASE_HEAD,
        "fd05_accepted_tree": PINNED_R0_BASE_TREE,
    }
    invalid_contracts = (
        ("unsupported slice", {"active_slice": "UNKNOWN"}, "unsupported"),
        (
            "missing pins",
            {"fd05_accepted_head": None, "fd05_accepted_tree": None},
            "FD05_ACCEPTED_HEAD",
        ),
        ("missing tree pin", {"fd05_accepted_tree": None}, "FD05_ACCEPTED_TREE"),
        ("missing head pin", {"fd05_accepted_head": None}, "FD05_ACCEPTED_HEAD"),
        (
            "uppercase head pin",
            {"fd05_accepted_head": PINNED_R0_BASE_HEAD.upper()},
            "FD05_ACCEPTED_HEAD",
        ),
        (
            "uppercase tree pin",
            {"fd05_accepted_tree": PINNED_R0_BASE_TREE.upper()},
            "FD05_ACCEPTED_TREE",
        ),
        (
            "malformed head pin",
            {"fd05_accepted_head": "not-an-object-id"},
            "FD05_ACCEPTED_HEAD",
        ),
        (
            "malformed tree pin",
            {"fd05_accepted_tree": "not-an-object-id"},
            "FD05_ACCEPTED_TREE",
        ),
        (
            "mismatched head pin",
            {"fd05_accepted_head": other_head},
            "does not match authorized H2/T2",
        ),
        (
            "mismatched tree pin",
            {"fd05_accepted_tree": other_tree},
            "does not match authorized H2/T2",
        ),
        (
            "mismatched base head",
            {"base_head": other_head},
            "does not match the external FD05 pin",
        ),
        (
            "mismatched base tree",
            {"base_tree": other_tree},
            "does not match the external FD05 pin",
        ),
        (
            "malformed base head",
            {"base_head": "not-an-object-id"},
            "base HEAD",
        ),
        (
            "malformed base tree",
            {"base_tree": "not-an-object-id"},
            "base TREE",
        ),
    )
    for label, overrides, expected_error in invalid_contracts:
        candidate = {**valid_r0, **overrides}
        try:
            _resolve_slice_contract(**candidate)  # type: ignore[arg-type]
        except VerificationError as exc:
            if expected_error not in str(exc):
                raise VerificationError(
                    f"offline self-check {label!r} failed for the wrong reason: {exc}"
                ) from exc
        else:
            raise VerificationError(
                f"offline self-check unexpectedly accepted {label!r}"
            )

    valid_c1 = {
        "active_slice": "C1",
        "base_head": PINNED_C1_START_HEAD,
        "base_tree": PINNED_C1_START_TREE,
        "fd05_accepted_head": PINNED_R0_BASE_HEAD,
        "fd05_accepted_tree": PINNED_R0_BASE_TREE,
    }
    invalid_c1_contracts = (
        (
            "C1 H2 substituted for R0 start",
            {"base_head": PINNED_R0_BASE_HEAD, "base_tree": PINNED_R0_BASE_TREE},
            "exact authorized R0 START HEAD/TREE",
        ),
        (
            "C1 mismatched R0 start head",
            {"base_head": other_head},
            "exact authorized R0 START HEAD/TREE",
        ),
        (
            "C1 mismatched R0 start tree",
            {"base_tree": other_tree},
            "exact authorized R0 START HEAD/TREE",
        ),
        (
            "C1 missing H2 head pin",
            {"fd05_accepted_head": None},
            "FD05_ACCEPTED_HEAD",
        ),
        (
            "C1 mismatched H2 tree pin",
            {"fd05_accepted_tree": other_tree},
            "authorized H2/T2",
        ),
    )
    for label, overrides, expected_error in invalid_c1_contracts:
        candidate = {**valid_c1, **overrides}
        try:
            _resolve_slice_contract(**candidate)  # type: ignore[arg-type]
        except VerificationError as exc:
            if expected_error not in str(exc):
                raise VerificationError(
                    f"offline self-check {label!r} failed for the wrong reason: {exc}"
                ) from exc
        else:
            raise VerificationError(
                f"offline self-check unexpectedly accepted {label!r}"
            )

    _require_changed_path_contract(
        active_slice="C1",
        changed=ACTIVE_C1_ALLOWLIST,
        allowlist=ACTIVE_C1_ALLOWLIST,
        exact_changed_paths=True,
    )
    _require_merge_free("C1", ())
    path_negative_cases = 0
    for label, changed, expected_error in (
        (
            "C1 path outside allowlist",
            ACTIVE_C1_ALLOWLIST | {"software/conflict_analysis/domain/models.py"},
            "outside ACTIVE C1 EXACT ALLOWLIST",
        ),
        (
            "C1 missing delivered path",
            ACTIVE_C1_ALLOWLIST
            - {"software/conflict_analysis/production_studio/views.py"},
            "C1 changed paths must equal",
        ),
    ):
        path_negative_cases += 1
        try:
            _require_changed_path_contract(
                active_slice="C1",
                changed=frozenset(changed),
                allowlist=ACTIVE_C1_ALLOWLIST,
                exact_changed_paths=True,
            )
        except VerificationError as exc:
            if expected_error not in str(exc):
                raise VerificationError(
                    f"offline self-check {label!r} failed for the wrong reason: {exc}"
                ) from exc
        else:
            raise VerificationError(
                f"offline self-check unexpectedly accepted {label!r}"
            )
    try:
        _require_merge_free("C1", ("synthetic-merge-object",))
    except VerificationError as exc:
        if "merge commits are forbidden after the exact C1 base" not in str(exc):
            raise VerificationError(
                "offline C1 merge-topology self-check failed for the wrong reason"
            ) from exc
    else:
        raise VerificationError(
            "offline self-check unexpectedly accepted a C1 merge commit"
        )

    valid_fd02 = {
        "active_slice": "FD02",
        "base_head": PINNED_FD02_BASE_HEAD,
        "base_tree": PINNED_FD02_BASE_TREE,
        "fd05_accepted_head": None,
        "fd05_accepted_tree": None,
    }
    invalid_fd02_contracts = (
        (
            "FD02 mismatched accepted C1 head",
            {"base_head": other_head},
            "exact accepted C1 HEAD/TREE",
        ),
        (
            "FD02 mismatched accepted C1 tree",
            {"base_tree": other_tree},
            "exact accepted C1 HEAD/TREE",
        ),
        (
            "FD02 uppercase accepted C1 head",
            {"base_head": PINNED_FD02_BASE_HEAD.upper()},
            "base HEAD",
        ),
        (
            "FD02 unexpected external pin",
            {"fd05_accepted_head": PINNED_R0_BASE_HEAD},
            "does not accept FD05 external pin arguments",
        ),
    )
    for label, overrides, expected_error in invalid_fd02_contracts:
        candidate = {**valid_fd02, **overrides}
        try:
            _resolve_slice_contract(**candidate)  # type: ignore[arg-type]
        except VerificationError as exc:
            if expected_error not in str(exc):
                raise VerificationError(
                    f"offline self-check {label!r} failed for the wrong reason: {exc}"
                ) from exc
        else:
            raise VerificationError(
                f"offline self-check unexpectedly accepted {label!r}"
            )

    _require_changed_path_contract(
        active_slice="FD02",
        changed=ACTIVE_FD02_ALLOWLIST,
        allowlist=ACTIVE_FD02_ALLOWLIST,
        exact_changed_paths=True,
    )
    fd02_path_negative_cases = 0
    for label, changed, expected_error in (
        (
            "FD02 path outside allowlist",
            ACTIVE_FD02_ALLOWLIST | {"software/conflict_analysis/pyproject.toml"},
            "outside ACTIVE FD02 EXACT ALLOWLIST",
        ),
        (
            "FD02 missing delivered path",
            ACTIVE_FD02_ALLOWLIST
            - {"software/conflict_analysis/domain/content/studio_help_ru_v1.json"},
            "FD02 changed paths must equal",
        ),
    ):
        fd02_path_negative_cases += 1
        try:
            _require_changed_path_contract(
                active_slice="FD02",
                changed=frozenset(changed),
                allowlist=ACTIVE_FD02_ALLOWLIST,
                exact_changed_paths=True,
            )
        except VerificationError as exc:
            if expected_error not in str(exc):
                raise VerificationError(
                    f"offline self-check {label!r} failed for the wrong reason: {exc}"
                ) from exc
        else:
            raise VerificationError(
                f"offline self-check unexpectedly accepted {label!r}"
            )
    _require_merge_free("FD02", ())
    _require_single_fast_forward_commit(
        active_slice="FD02",
        commit_count=1,
        delivery_parent=PINNED_FD02_BASE_HEAD,
        base_head=PINNED_FD02_BASE_HEAD,
    )
    try:
        _require_merge_free("FD02", ("synthetic-merge-object",))
    except VerificationError as exc:
        if "merge commits are forbidden after the exact FD02 base" not in str(exc):
            raise VerificationError(
                "offline FD02 merge-topology self-check failed for the wrong reason"
            ) from exc
    else:
        raise VerificationError(
            "offline self-check unexpectedly accepted an FD02 merge commit"
        )
    for label, commit_count, parent in (
        ("FD02 extra commit", 2, PINNED_FD02_BASE_HEAD),
        ("FD02 wrong parent", 1, other_head),
    ):
        try:
            _require_single_fast_forward_commit(
                active_slice="FD02",
                commit_count=commit_count,
                delivery_parent=parent,
                base_head=PINNED_FD02_BASE_HEAD,
            )
        except VerificationError as exc:
            if "exactly one fast-forward commit" not in str(exc):
                raise VerificationError(
                    f"offline self-check {label!r} failed for the wrong reason"
                ) from exc
        else:
            raise VerificationError(
                f"offline self-check unexpectedly accepted {label!r}"
            )

    valid_fd03 = {
        "active_slice": "FD03",
        "base_head": PINNED_FD03_BASE_HEAD,
        "base_tree": PINNED_FD03_BASE_TREE,
        "fd05_accepted_head": None,
        "fd05_accepted_tree": None,
    }
    invalid_fd03_contracts = (
        (
            "FD03 mismatched accepted FD02 head",
            {"base_head": other_head},
            "exact accepted FD02 HEAD/TREE",
        ),
        (
            "FD03 mismatched accepted FD02 tree",
            {"base_tree": other_tree},
            "exact accepted FD02 HEAD/TREE",
        ),
        (
            "FD03 uppercase accepted FD02 head",
            {"base_head": PINNED_FD03_BASE_HEAD.upper()},
            "base HEAD",
        ),
        (
            "FD03 unexpected external pin",
            {"fd05_accepted_head": PINNED_R0_BASE_HEAD},
            "does not accept FD05 external pin arguments",
        ),
    )
    for label, overrides, expected_error in invalid_fd03_contracts:
        candidate = {**valid_fd03, **overrides}
        try:
            _resolve_slice_contract(**candidate)  # type: ignore[arg-type]
        except VerificationError as exc:
            if expected_error not in str(exc):
                raise VerificationError(
                    f"offline self-check {label!r} failed for the wrong reason: {exc}"
                ) from exc
        else:
            raise VerificationError(
                f"offline self-check unexpectedly accepted {label!r}"
            )

    _require_changed_path_contract(
        active_slice="FD03",
        changed=ACTIVE_FD03_ALLOWLIST,
        allowlist=ACTIVE_FD03_ALLOWLIST,
        exact_changed_paths=True,
    )
    _require_changed_path_contract(
        active_slice="FD03_AGGREGATE",
        changed=FD03_AGGREGATE_ALLOWLIST,
        allowlist=FD03_AGGREGATE_ALLOWLIST,
        exact_changed_paths=True,
    )
    fd03_path_negative_cases = 0
    for label, changed, allowlist, expected_error in (
        (
            "FD03 eighth path",
            ACTIVE_FD03_ALLOWLIST | {"software/conflict_analysis/domain/models.py"},
            ACTIVE_FD03_ALLOWLIST,
            "outside ACTIVE FD03 EXACT ALLOWLIST",
        ),
        (
            "FD03 missing bounded C0 node path",
            ACTIVE_FD03_ALLOWLIST
            - {"software/conflict_analysis/production_studio/tests/test_read_only_http.py"},
            ACTIVE_FD03_ALLOWLIST,
            "FD03 changed paths must equal",
        ),
        (
            "FD03 twelfth aggregate path",
            FD03_AGGREGATE_ALLOWLIST | {"software/conflict_analysis/domain/models.py"},
            FD03_AGGREGATE_ALLOWLIST,
            "outside ACTIVE FD03_AGGREGATE EXACT ALLOWLIST",
        ),
        (
            "FD03 missing aggregate FD02 catalog",
            FD03_AGGREGATE_ALLOWLIST
            - {"software/conflict_analysis/domain/content/studio_help_ru_v1.json"},
            FD03_AGGREGATE_ALLOWLIST,
            "FD03_AGGREGATE changed paths must equal",
        ),
    ):
        fd03_path_negative_cases += 1
        try:
            _require_changed_path_contract(
                active_slice=(
                    "FD03_AGGREGATE"
                    if allowlist is FD03_AGGREGATE_ALLOWLIST
                    else "FD03"
                ),
                changed=frozenset(changed),
                allowlist=allowlist,
                exact_changed_paths=True,
            )
        except VerificationError as exc:
            if expected_error not in str(exc):
                raise VerificationError(
                    f"offline self-check {label!r} failed for the wrong reason: {exc}"
                ) from exc
        else:
            raise VerificationError(
                f"offline self-check unexpectedly accepted {label!r}"
            )
    _require_merge_free("FD03", ())
    _require_fd03_rc2_fast_forward(
        commit_count=2,
        delivery_parent=PINNED_FD03_RC2_START_HEAD,
    )
    for label, commit_count, parent in (
        ("FD03 missing RC2 commit", 1, PINNED_FD03_RC2_START_HEAD),
        ("FD03 extra commit", 3, PINNED_FD03_RC2_START_HEAD),
        ("FD03 wrong RC2 parent", 2, other_head),
    ):
        try:
            _require_fd03_rc2_fast_forward(
                commit_count=commit_count,
                delivery_parent=parent,
            )
        except VerificationError as exc:
            if "exactly two fast-forward commits" not in str(exc):
                raise VerificationError(
                    f"offline self-check {label!r} failed for the wrong reason"
                ) from exc
        else:
            raise VerificationError(
                f"offline self-check unexpectedly accepted {label!r}"
            )

    try:
        _resolve_slice_contract(
            active_slice="C0",
            base_head=PINNED_BASE_HEAD,
            base_tree=PINNED_BASE_TREE,
            fd05_accepted_head=PINNED_R0_BASE_HEAD,
            fd05_accepted_tree=PINNED_R0_BASE_TREE,
        )
    except VerificationError as exc:
        if "C0 does not accept FD05 external pin arguments" not in str(exc):
            raise VerificationError(
                "offline C0 external-pin self-check failed for the wrong reason"
            ) from exc
    else:
        raise VerificationError("offline self-check let an R0 external pin leak into C0")

    valid_fd06 = {
        "active_slice": "FD06",
        "base_head": PINNED_FD06_BASE_HEAD,
        "base_tree": PINNED_FD06_BASE_TREE,
        "fd05_accepted_head": None,
        "fd05_accepted_tree": None,
    }
    fd06 = _resolve_slice_contract(**valid_fd06)
    invalid_fd06_contracts = (
        (
            "FD06 mismatched accepted FD03 head",
            {"base_head": other_head},
            "exact accepted FD03 HEAD/TREE",
        ),
        (
            "FD06 mismatched accepted FD03 tree",
            {"base_tree": other_tree},
            "exact accepted FD03 HEAD/TREE",
        ),
        (
            "FD06 uppercase accepted FD03 head",
            {"base_head": PINNED_FD06_BASE_HEAD.upper()},
            "base HEAD",
        ),
        (
            "FD06 unexpected external pin",
            {"fd05_accepted_head": PINNED_R0_BASE_HEAD},
            "does not accept external pin arguments",
        ),
    )
    for label, overrides, expected_error in invalid_fd06_contracts:
        candidate = {**valid_fd06, **overrides}
        try:
            _resolve_slice_contract(**candidate)  # type: ignore[arg-type]
        except VerificationError as exc:
            if expected_error not in str(exc):
                raise VerificationError(
                    f"offline self-check {label!r} failed for the wrong reason: {exc}"
                ) from exc
        else:
            raise VerificationError(
                f"offline self-check unexpectedly accepted {label!r}"
            )

    if len(ACTIVE_FD06_ALLOWLIST) != FD06_EXACT_PATH_COUNT:
        raise VerificationError("FD06 exact allowlist constant is not ten paths")
    _require_changed_path_contract(
        active_slice="FD06",
        changed=ACTIVE_FD06_ALLOWLIST,
        allowlist=ACTIVE_FD06_ALLOWLIST,
        exact_changed_paths=True,
    )
    fd06_path_negative_cases = 0
    for label, changed, expected_error in (
        (
            "FD06 eleventh path",
            ACTIVE_FD06_ALLOWLIST | {"software/conflict_analysis/domain/models.py"},
            "outside ACTIVE FD06 EXACT ALLOWLIST",
        ),
        (
            "FD06 missing bootstrap reconciliation",
            ACTIVE_FD06_ALLOWLIST
            - {
                "software/conflict_analysis/domain/tests/"
                "test_foundation_studio_bootstrap.py"
            },
            "FD06 changed paths must equal",
        ),
    ):
        fd06_path_negative_cases += 1
        try:
            _require_changed_path_contract(
                active_slice="FD06",
                changed=changed,
                allowlist=ACTIVE_FD06_ALLOWLIST,
                exact_changed_paths=True,
            )
        except VerificationError as exc:
            if expected_error not in str(exc):
                raise VerificationError(
                    f"offline self-check {label!r} failed for the wrong reason: {exc}"
                ) from exc
        else:
            raise VerificationError(
                f"offline self-check unexpectedly accepted {label!r}"
            )

    _resolve_fd06_route(
        event_name="push",
        event_ref=f"refs/heads/{FD06_TARGET_BRANCH}",
    )
    _resolve_fd06_route(
        event_name="pull_request",
        head_ref=FD06_TARGET_BRANCH,
        base_ref=FD06_BASE_BRANCH,
    )
    fd06_route_negative_cases = 0
    for route in (
        {"event_name": "push", "event_ref": f"refs/heads/{FD06_BASE_BRANCH}"},
        {
            "event_name": "pull_request",
            "head_ref": FD06_TARGET_BRANCH,
            "base_ref": "main",
        },
        {
            "event_name": "pull_request",
            "head_ref": FD06_BASE_BRANCH,
            "base_ref": FD06_BASE_BRANCH,
        },
        {"event_name": "workflow_dispatch"},
    ):
        fd06_route_negative_cases += 1
        try:
            _resolve_fd06_route(**route)
        except VerificationError as exc:
            if "FD06 routing accepts only" not in str(exc):
                raise VerificationError(
                    "offline FD06 routing self-check failed for the wrong reason"
                ) from exc
        else:
            raise VerificationError(
                "offline FD06 routing self-check accepted an invalid route"
            )

    _require_fd06_static_contract(
        exact_path_count=len(ACTIVE_FD06_ALLOWLIST),
        portable_count=len(FD06_PORTABLE_METHODS),
        concurrency_count=len(FD06_CONCURRENCY_METHODS),
        postgresql_total=FD06_POSTGRESQL_TOTAL,
        postgresql_skipped=FD06_POSTGRESQL_SKIPPED,
        sqlite_passed=FD06_SQLITE_PASSED,
        sqlite_skipped=FD06_SQLITE_SKIPPED,
    )
    fd06_static_negative_cases = 0
    valid_fd06_static = {
        "exact_path_count": FD06_EXACT_PATH_COUNT,
        "portable_count": 11,
        "concurrency_count": 4,
        "postgresql_total": FD06_POSTGRESQL_TOTAL,
        "postgresql_skipped": FD06_POSTGRESQL_SKIPPED,
        "sqlite_passed": FD06_SQLITE_PASSED,
        "sqlite_skipped": FD06_SQLITE_SKIPPED,
    }
    for field, invalid_value in (
        ("exact_path_count", 9),
        ("portable_count", 12),
        ("concurrency_count", 3),
        ("postgresql_total", 226),
        ("postgresql_skipped", 1),
        ("sqlite_passed", 211),
        ("sqlite_skipped", 14),
    ):
        fd06_static_negative_cases += 1
        try:
            _require_fd06_static_contract(
                **{**valid_fd06_static, field: invalid_value}
            )
        except VerificationError as exc:
            if "FD06 static path/test total contract drifted" not in str(exc):
                raise VerificationError(
                    f"offline FD06 {field} self-check failed for the wrong reason"
                ) from exc
        else:
            raise VerificationError(
                f"offline FD06 {field} self-check accepted drift"
            )

    _require_fd06_frozen_contract(
        exact_frozen_objects=dict(FD06_EXACT_FROZEN_OBJECTS),
        reopened_base_blobs=dict(FD06_REOPENED_BASE_BLOBS),
    )
    fd06_frozen_negative_cases = 0
    for label, frozen, reopened, expected_error in (
        (
            "frozen model blob",
            {
                **FD06_EXACT_FROZEN_OBJECTS,
                "software/conflict_analysis/domain/models.py": other_head,
            },
            dict(FD06_REOPENED_BASE_BLOBS),
            "exact frozen-object contract drifted",
        ),
        (
            "reopened URL base blob",
            dict(FD06_EXACT_FROZEN_OBJECTS),
            {
                **FD06_REOPENED_BASE_BLOBS,
                "software/conflict_analysis/domain/urls.py": other_head,
            },
            "reopened base-blob contract drifted",
        ),
    ):
        fd06_frozen_negative_cases += 1
        try:
            _require_fd06_frozen_contract(
                exact_frozen_objects=frozen,
                reopened_base_blobs=reopened,
            )
        except VerificationError as exc:
            if expected_error not in str(exc):
                raise VerificationError(
                    f"offline FD06 {label} self-check failed for the wrong reason"
                ) from exc
        else:
            raise VerificationError(
                f"offline FD06 {label} self-check accepted drift"
            )

    def render_test_class(class_name: str, methods: tuple[str, ...]) -> str:
        method_source = "".join(
            f"    def {method}(self):\n        pass\n" for method in methods
        )
        return f"class {class_name}:\n{method_source}"

    _require_exact_test_topology(
        source=render_test_class(FD06_PORTABLE_CLASS, FD06_PORTABLE_METHODS),
        class_name=FD06_PORTABLE_CLASS,
        expected_methods=FD06_PORTABLE_METHODS,
    )
    _require_exact_test_topology(
        source=render_test_class(FD06_CONCURRENCY_CLASS, FD06_CONCURRENCY_METHODS),
        class_name=FD06_CONCURRENCY_CLASS,
        expected_methods=FD06_CONCURRENCY_METHODS,
    )
    fd06_topology_negative_cases = 0
    for class_name, actual_methods, expected_methods in (
        (
            FD06_PORTABLE_CLASS,
            FD06_PORTABLE_METHODS[:-1],
            FD06_PORTABLE_METHODS,
        ),
        (
            FD06_CONCURRENCY_CLASS,
            tuple(reversed(FD06_CONCURRENCY_METHODS)),
            FD06_CONCURRENCY_METHODS,
        ),
    ):
        fd06_topology_negative_cases += 1
        try:
            _require_exact_test_topology(
                source=render_test_class(class_name, actual_methods),
                class_name=class_name,
                expected_methods=expected_methods,
            )
        except VerificationError as exc:
            if "test topology mismatch" not in str(exc):
                raise VerificationError(
                    "offline FD06 topology self-check failed for the wrong reason"
                ) from exc
        else:
            raise VerificationError(
                "offline FD06 topology self-check accepted registry drift"
            )

    delivery_head = "e" * 40
    _require_merge_free("FD06", ())
    valid_fd06_history = {
        "commit_count": 2,
        "delivery_head": delivery_head,
        "delivery_parent": PINNED_FD06_RC4_INTERMEDIATE_HEAD,
        "intermediate_parent": PINNED_FD06_BASE_HEAD,
        "intermediate_tree": PINNED_FD06_RC4_INTERMEDIATE_TREE,
        "ordered_commits": (PINNED_FD06_RC4_INTERMEDIATE_HEAD, delivery_head),
    }
    _require_fd06_rc5_public_history(**valid_fd06_history)
    fd06_history_negative_cases = 0
    try:
        _require_merge_free("FD06", ("synthetic-merge-object",))
    except VerificationError as exc:
        if "merge commits are forbidden after the exact FD06 base" not in str(exc):
            raise VerificationError(
                "offline FD06 merge-topology self-check failed for the wrong reason"
            ) from exc
        fd06_history_negative_cases += 1
    else:
        raise VerificationError("offline self-check accepted an FD06 merge commit")
    for label, overrides in (
        ("FD06 squashed history", {"commit_count": 1}),
        ("FD06 extra commit", {"commit_count": 3}),
        ("FD06 wrong delivery parent", {"delivery_parent": other_head}),
        ("FD06 wrong intermediate parent", {"intermediate_parent": other_head}),
        ("FD06 wrong intermediate tree", {"intermediate_tree": other_tree}),
        (
            "FD06 replaced intermediate",
            {"ordered_commits": (other_head, delivery_head)},
        ),
        (
            "FD06 wrong ordered delivery",
            {
                "ordered_commits": (
                    PINNED_FD06_RC4_INTERMEDIATE_HEAD,
                    other_head,
                )
            },
        ),
    ):
        try:
            _require_fd06_rc5_public_history(
                **{**valid_fd06_history, **overrides}  # type: ignore[arg-type]
            )
        except VerificationError as exc:
            if "FD06 RC5 public history must preserve" not in str(exc):
                raise VerificationError(
                    f"offline self-check {label!r} failed for the wrong reason"
                ) from exc
            fd06_history_negative_cases += 1
        else:
            raise VerificationError(
                f"offline self-check unexpectedly accepted {label!r}"
            )

    delivery_tree = "f" * 40
    _require_synthetic_merge_contract(
        expected_base_head=PINNED_FD06_BASE_HEAD,
        expected_delivery_head=delivery_head,
        actual_parents=(PINNED_FD06_BASE_HEAD, delivery_head),
        delivery_tree=delivery_tree,
        synthetic_tree=delivery_tree,
        independent_tree=delivery_tree,
    )
    fd06_synthetic_negative_cases = 0
    for label, parents, synthetic_tree, independent_tree, expected_error in (
        (
            "reversed parents",
            (delivery_head, PINNED_FD06_BASE_HEAD),
            delivery_tree,
            delivery_tree,
            "synthetic merge parents",
        ),
        (
            "synthetic tree drift",
            (PINNED_FD06_BASE_HEAD, delivery_head),
            other_tree,
            delivery_tree,
            "trees must be equal",
        ),
        (
            "independent merge-tree drift",
            (PINNED_FD06_BASE_HEAD, delivery_head),
            delivery_tree,
            other_tree,
            "trees must be equal",
        ),
    ):
        fd06_synthetic_negative_cases += 1
        try:
            _require_synthetic_merge_contract(
                expected_base_head=PINNED_FD06_BASE_HEAD,
                expected_delivery_head=delivery_head,
                actual_parents=parents,
                delivery_tree=delivery_tree,
                synthetic_tree=synthetic_tree,
                independent_tree=independent_tree,
            )
        except VerificationError as exc:
            if expected_error not in str(exc):
                raise VerificationError(
                    f"offline FD06 synthetic {label} failed for the wrong reason"
                ) from exc
        else:
            raise VerificationError(
                f"offline FD06 synthetic {label} was unexpectedly accepted"
            )

    valid_fd07 = {
        "active_slice": "FD07",
        "base_head": PINNED_FD07_BASE_HEAD,
        "base_tree": PINNED_FD07_BASE_TREE,
        "fd05_accepted_head": None,
        "fd05_accepted_tree": None,
    }
    fd07 = _resolve_slice_contract(**valid_fd07)
    invalid_fd07_contracts = (
        (
            "FD07 mismatched accepted FD06 head",
            {"base_head": other_head},
            "exact accepted FD06 HEAD/TREE",
        ),
        (
            "FD07 mismatched accepted FD06 tree",
            {"base_tree": other_tree},
            "exact accepted FD06 HEAD/TREE",
        ),
        (
            "FD07 uppercase accepted FD06 head",
            {"base_head": PINNED_FD07_BASE_HEAD.upper()},
            "base HEAD",
        ),
        (
            "FD07 unexpected external pin",
            {"fd05_accepted_head": PINNED_R0_BASE_HEAD},
            "does not accept external pin arguments",
        ),
    )
    for label, overrides, expected_error in invalid_fd07_contracts:
        candidate = {**valid_fd07, **overrides}
        try:
            _resolve_slice_contract(**candidate)  # type: ignore[arg-type]
        except VerificationError as exc:
            if expected_error not in str(exc):
                raise VerificationError(
                    f"offline self-check {label!r} failed for the wrong reason: {exc}"
                ) from exc
        else:
            raise VerificationError(
                f"offline self-check unexpectedly accepted {label!r}"
            )

    if len(ACTIVE_FD07_ALLOWLIST) != FD07_EXACT_PATH_COUNT:
        raise VerificationError("FD07 exact allowlist constant is not eight paths")
    _require_changed_path_contract(
        active_slice="FD07",
        changed=ACTIVE_FD07_ALLOWLIST,
        allowlist=ACTIVE_FD07_ALLOWLIST,
        exact_changed_paths=True,
    )
    fd07_path_negative_cases = 0
    for label, changed, expected_error in (
        (
            "FD07 ninth path",
            ACTIVE_FD07_ALLOWLIST | {"software/conflict_analysis/domain/models.py"},
            "outside ACTIVE FD07 EXACT ALLOWLIST",
        ),
        (
            "FD07 missing readiness registry",
            ACTIVE_FD07_ALLOWLIST
            - {
                "software/conflict_analysis/domain/tests/"
                "test_foundation_studio_publication_readiness.py"
            },
            "FD07 changed paths must equal",
        ),
    ):
        fd07_path_negative_cases += 1
        try:
            _require_changed_path_contract(
                active_slice="FD07",
                changed=changed,
                allowlist=ACTIVE_FD07_ALLOWLIST,
                exact_changed_paths=True,
            )
        except VerificationError as exc:
            if expected_error not in str(exc):
                raise VerificationError(
                    f"offline self-check {label!r} failed for the wrong reason: {exc}"
                ) from exc
        else:
            raise VerificationError(
                f"offline self-check unexpectedly accepted {label!r}"
            )

    _resolve_fd07_route(
        event_name="push",
        event_ref=f"refs/heads/{FD07_TARGET_BRANCH}",
    )
    _resolve_fd07_route(
        event_name="pull_request",
        head_ref=FD07_TARGET_BRANCH,
        base_ref=FD07_BASE_BRANCH,
    )
    fd07_route_negative_cases = 0
    for route in (
        {"event_name": "push", "event_ref": f"refs/heads/{FD07_BASE_BRANCH}"},
        {
            "event_name": "pull_request",
            "head_ref": FD07_TARGET_BRANCH,
            "base_ref": FD06_BASE_BRANCH,
        },
        {
            "event_name": "pull_request",
            "head_ref": FD07_BASE_BRANCH,
            "base_ref": FD07_BASE_BRANCH,
        },
        {"event_name": "workflow_dispatch"},
    ):
        fd07_route_negative_cases += 1
        try:
            _resolve_fd07_route(**route)
        except VerificationError as exc:
            if "FD07 routing accepts only" not in str(exc):
                raise VerificationError(
                    "offline FD07 routing self-check failed for the wrong reason"
                ) from exc
        else:
            raise VerificationError(
                "offline FD07 routing self-check accepted an invalid route"
            )

    _require_fd07_static_contract(
        exact_path_count=len(ACTIVE_FD07_ALLOWLIST),
        test_node_count=len(FD07_TEST_METHODS),
        postgresql_total=FD07_POSTGRESQL_TOTAL,
        postgresql_skipped=FD07_POSTGRESQL_SKIPPED,
        sqlite_passed=FD07_SQLITE_PASSED,
        sqlite_skipped=FD07_SQLITE_SKIPPED,
    )
    fd07_static_negative_cases = 0
    valid_fd07_static = {
        "exact_path_count": FD07_EXACT_PATH_COUNT,
        "test_node_count": 9,
        "postgresql_total": FD07_POSTGRESQL_TOTAL,
        "postgresql_skipped": FD07_POSTGRESQL_SKIPPED,
        "sqlite_passed": FD07_SQLITE_PASSED,
        "sqlite_skipped": FD07_SQLITE_SKIPPED,
    }
    for field, invalid_value in (
        ("exact_path_count", 7),
        ("test_node_count", 8),
        ("postgresql_total", 235),
        ("postgresql_skipped", 1),
        ("sqlite_passed", 220),
        ("sqlite_skipped", 14),
    ):
        fd07_static_negative_cases += 1
        try:
            _require_fd07_static_contract(
                **{**valid_fd07_static, field: invalid_value}
            )
        except VerificationError as exc:
            if "FD07 static path/test total contract drifted" not in str(exc):
                raise VerificationError(
                    f"offline FD07 {field} self-check failed for the wrong reason"
                ) from exc
        else:
            raise VerificationError(
                f"offline FD07 {field} self-check accepted drift"
            )

    _require_fd07_frozen_contract(
        exact_frozen_objects=dict(FD07_EXACT_FROZEN_OBJECTS),
        reopened_base_blobs=dict(FD07_REOPENED_BASE_BLOBS),
    )
    fd07_frozen_negative_cases = 0
    for label, frozen, reopened, expected_error in (
        (
            "frozen policies blob",
            {
                **FD07_EXACT_FROZEN_OBJECTS,
                "software/conflict_analysis/domain/policies.py": other_head,
            },
            dict(FD07_REOPENED_BASE_BLOBS),
            "exact frozen-object contract drifted",
        ),
        (
            "reopened workflow base blob",
            dict(FD07_EXACT_FROZEN_OBJECTS),
            {
                **FD07_REOPENED_BASE_BLOBS,
                ".github/workflows/conflict-analysis.yml": other_head,
            },
            "reopened base-blob contract drifted",
        ),
    ):
        fd07_frozen_negative_cases += 1
        try:
            _require_fd07_frozen_contract(
                exact_frozen_objects=frozen,
                reopened_base_blobs=reopened,
            )
        except VerificationError as exc:
            if expected_error not in str(exc):
                raise VerificationError(
                    f"offline FD07 {label} self-check failed for the wrong reason"
                ) from exc
        else:
            raise VerificationError(
                f"offline FD07 {label} self-check accepted drift"
            )

    _require_exact_test_topology(
        source=render_test_class(FD07_TEST_CLASS, FD07_TEST_METHODS),
        class_name=FD07_TEST_CLASS,
        expected_methods=FD07_TEST_METHODS,
    )
    fd07_topology_negative_cases = 0
    for actual_methods in (
        FD07_TEST_METHODS[:-1],
        tuple(reversed(FD07_TEST_METHODS)),
    ):
        fd07_topology_negative_cases += 1
        try:
            _require_exact_test_topology(
                source=render_test_class(FD07_TEST_CLASS, actual_methods),
                class_name=FD07_TEST_CLASS,
                expected_methods=FD07_TEST_METHODS,
            )
        except VerificationError as exc:
            if "test topology mismatch" not in str(exc):
                raise VerificationError(
                    "offline FD07 topology self-check failed for the wrong reason"
                ) from exc
        else:
            raise VerificationError(
                "offline FD07 topology self-check accepted registry drift"
            )

    fd07_delivery_head = "a" * 40
    _require_merge_free("FD07", ())
    _require_single_fast_forward_commit(
        active_slice="FD07",
        commit_count=1,
        delivery_parent=PINNED_FD07_BASE_HEAD,
        base_head=PINNED_FD07_BASE_HEAD,
    )
    fd07_history_negative_cases = 0
    try:
        _require_merge_free("FD07", ("synthetic-merge-object",))
    except VerificationError as exc:
        if "merge commits are forbidden after the exact FD07 base" not in str(exc):
            raise VerificationError(
                "offline FD07 merge-topology self-check failed for the wrong reason"
            ) from exc
        fd07_history_negative_cases += 1
    else:
        raise VerificationError("offline self-check accepted an FD07 merge commit")
    for label, count, parent in (
        ("FD07 missing delivery", 0, PINNED_FD07_BASE_HEAD),
        ("FD07 extra commit", 2, PINNED_FD07_BASE_HEAD),
        ("FD07 wrong parent", 1, other_head),
    ):
        try:
            _require_single_fast_forward_commit(
                active_slice="FD07",
                commit_count=count,
                delivery_parent=parent,
                base_head=PINNED_FD07_BASE_HEAD,
            )
        except VerificationError as exc:
            if "exactly one fast-forward commit" not in str(exc):
                raise VerificationError(
                    f"offline {label} self-check failed for the wrong reason"
                ) from exc
            fd07_history_negative_cases += 1
        else:
            raise VerificationError(f"offline self-check unexpectedly accepted {label}")

    _require_synthetic_merge_contract(
        expected_base_head=PINNED_FD07_BASE_HEAD,
        expected_delivery_head=fd07_delivery_head,
        actual_parents=(PINNED_FD07_BASE_HEAD, fd07_delivery_head),
        delivery_tree=delivery_tree,
        synthetic_tree=delivery_tree,
        independent_tree=delivery_tree,
    )
    fd07_synthetic_negative_cases = 0
    for label, parents, synthetic_tree, independent_tree, expected_error in (
        (
            "reversed parents",
            (fd07_delivery_head, PINNED_FD07_BASE_HEAD),
            delivery_tree,
            delivery_tree,
            "synthetic merge parents",
        ),
        (
            "synthetic tree drift",
            (PINNED_FD07_BASE_HEAD, fd07_delivery_head),
            other_tree,
            delivery_tree,
            "trees must be equal",
        ),
        (
            "independent merge-tree drift",
            (PINNED_FD07_BASE_HEAD, fd07_delivery_head),
            delivery_tree,
            other_tree,
            "trees must be equal",
        ),
    ):
        fd07_synthetic_negative_cases += 1
        try:
            _require_synthetic_merge_contract(
                expected_base_head=PINNED_FD07_BASE_HEAD,
                expected_delivery_head=fd07_delivery_head,
                actual_parents=parents,
                delivery_tree=delivery_tree,
                synthetic_tree=synthetic_tree,
                independent_tree=independent_tree,
            )
        except VerificationError as exc:
            if expected_error not in str(exc):
                raise VerificationError(
                    f"offline FD07 synthetic {label} failed for the wrong reason"
                ) from exc
        else:
            raise VerificationError(
                f"offline FD07 synthetic {label} was unexpectedly accepted"
            )

    return {
        "marker": "PRODUCTION_STUDIO_R0_VERIFIER_SELF_CHECK=PASS",
        "c1_marker": "PRODUCTION_STUDIO_C1_VERIFIER_SELF_CHECK=PASS",
        "fd02_marker": "FOUNDATION_FD02_VERIFIER_SELF_CHECK=PASS",
        "fd03_marker": "FOUNDATION_FD03_RC2_VERIFIER_SELF_CHECK=PASS",
        "fd06_marker": "FOUNDATION_FD06_VERIFIER_SELF_CHECK=PASS",
        "fd07_marker": "FOUNDATION_FD07_VERIFIER_SELF_CHECK=PASS",
        "network_access": False,
        "repository_access": False,
        "positive_slices": [
            c0["active_slice"],
            r0["active_slice"],
            c1["active_slice"],
            fd02["active_slice"],
            fd03["active_slice"],
            fd06["active_slice"],
            fd07["active_slice"],
        ],
        "negative_cases": (
            len(invalid_contracts)
            + len(invalid_c1_contracts)
            + path_negative_cases
            + 2
            + len(invalid_fd02_contracts)
            + fd02_path_negative_cases
            + 3
            + len(invalid_fd06_contracts)
            + fd06_path_negative_cases
            + fd06_route_negative_cases
            + fd06_static_negative_cases
            + fd06_frozen_negative_cases
            + fd06_topology_negative_cases
            + fd06_history_negative_cases
            + fd06_synthetic_negative_cases
            + len(invalid_fd03_contracts)
            + fd03_path_negative_cases
            + 3
            + len(invalid_fd07_contracts)
            + fd07_path_negative_cases
            + fd07_route_negative_cases
            + fd07_static_negative_cases
            + fd07_frozen_negative_cases
            + fd07_topology_negative_cases
            + fd07_history_negative_cases
            + fd07_synthetic_negative_cases
        ),
    }


def _render_successor_self_check_junit(contract: dict[str, object]) -> str:
    exact_nodes = contract.get("exact_nodes")
    exact_method_names = contract.get("exact_method_names")
    required_nodes = contract.get("required_nodes", ())
    expected_total = int(contract["expected_total"])
    if exact_nodes is not None:
        identities = list(exact_nodes)
    elif exact_method_names is not None:
        identities = [
            ("AuthorityUnpinnedChromiumClass", method)
            for method in exact_method_names
        ]
    else:
        identities = list(required_nodes)
    exact_skips = contract.get("exact_skipped_nodes")
    normalized_identities = {
        _normalized_test_node(class_name, method_name)
        for class_name, method_name in identities
    }
    for identity in exact_skips or ():
        normalized = _normalized_test_node(*identity)
        if normalized not in normalized_identities:
            identities.append(identity)
            normalized_identities.add(normalized)
    used = set(identities)
    filler = 0
    while len(identities) < expected_total:
        identity = ("SuccessorSelfCheckFiller", f"test_filler_{filler:04d}")
        filler += 1
        if identity not in used:
            identities.append(identity)
            used.add(identity)
    if len(identities) != expected_total:
        raise VerificationError("successor self-check JUnit contract overflows total")
    skip_nodes = {
        _normalized_test_node(class_name, method_name)
        for class_name, method_name in (exact_skips or ())
    }
    if exact_skips is None:
        skip_nodes = {
            _normalized_test_node(class_name, method_name)
            for class_name, method_name in identities[
                : int(contract["expected_skipped"])
            ]
        }
    suite = ET.Element("testsuite")
    for class_name, method_name in identities:
        case = ET.SubElement(
            suite,
            "testcase",
            {"classname": class_name, "name": method_name},
        )
        if _normalized_test_node(class_name, method_name) in skip_nodes:
            ET.SubElement(case, "skipped")
    return ET.tostring(suite, encoding="unicode")


def _write_successor_self_check_evidence(
    directory: Path,
    *,
    active_slice: str,
    base_head: str,
    base_tree: str,
    delivery_head: str,
    delivery_tree: str,
) -> None:
    directory.mkdir()
    junit_names = SUCCESSOR_JUNIT_FILES[active_slice]
    synthetic_name = "synthetic-tree.json" if active_slice == "C2A" else None
    identity = {
        "active_slice": active_slice,
        "base_head": base_head,
        "base_tree": base_tree,
        "delivery_head": delivery_head,
        "delivery_tree": delivery_tree,
    }
    manifest = {
        "schema": SUCCESSOR_EVIDENCE_SCHEMA,
        **identity,
        "junit_files": list(junit_names),
        "migration_evidence": "migration.json",
        "wheel_file": SUCCESSOR_WHEEL_NAME,
        "wheel_install_evidence": "wheel-install.json",
        "synthetic_tree_evidence": synthetic_name,
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    for name, contract in _successor_junit_contracts(active_slice).items():
        (directory / name).write_text(
            _render_successor_self_check_junit(contract), encoding="utf-8"
        )
    migration = {
        "schema": SUCCESSOR_MIGRATION_EVIDENCE_SCHEMA,
        **identity,
        "gates": list(SUCCESSOR_MIGRATION_GATES[active_slice]),
    }
    (directory / "migration.json").write_text(
        json.dumps(migration), encoding="utf-8"
    )
    wheel_path = directory / SUCCESSOR_WHEEL_NAME
    with ZipFile(wheel_path, "w") as archive:
        for member in sorted(SUCCESSOR_WHEEL_REQUIRED_MEMBERS[active_slice]):
            archive.writestr(member, b"successor-self-check\n")
    wheel = {
        "schema": SUCCESSOR_WHEEL_EVIDENCE_SCHEMA,
        **identity,
        "wheel_sha256": hashlib.sha256(wheel_path.read_bytes()).hexdigest(),
        "source_tree_fallback": False,
        "checks": list(SUCCESSOR_WHEEL_CHECKS[active_slice]),
    }
    (directory / "wheel-install.json").write_text(
        json.dumps(wheel), encoding="utf-8"
    )
    if active_slice == "C2A":
        synthetic = {
            "schema": C2A_SYNTHETIC_EVIDENCE_SCHEMA,
            "base_head": base_head,
            "delivery_head": delivery_head,
            "parents": [base_head, delivery_head],
            "delivery_tree": delivery_tree,
            "synthetic_tree": delivery_tree,
            "independent_tree": delivery_tree,
        }
        (directory / "synthetic-tree.json").write_text(
            json.dumps(synthetic), encoding="utf-8"
        )


def f0l_self_check() -> dict[str, object]:
    """Exercise F0L and successor declarations without network/caller-repo access."""

    _require_f0l_static_contract()
    _require_successor_static_contract()
    if _resolve_f0l_route(
        event_name="push", event_ref=f"refs/heads/{F0L_TARGET_BRANCH}"
    ) != "PINNED_FD07":
        raise VerificationError("F0L push self-check resolved the wrong base source")
    if _resolve_f0l_route(
        event_name="pull_request",
        head_ref=F0L_TARGET_BRANCH,
        base_ref=F0L_BASE_BRANCH,
    ) != "EVENT_FD07":
        raise VerificationError("F0L PR self-check resolved the wrong base source")
    if _resolve_post_f0l_route(
        active_slice="F1",
        event_name="pull_request",
        head_ref=F1_TARGET_BRANCH,
        base_ref=F0L_TARGET_BRANCH,
    ) != "EVENT_ACCEPTED_F0L":
        raise VerificationError("F1 route self-check resolved the wrong base source")
    if _resolve_post_f0l_route(
        active_slice="C2A",
        event_name="push",
        event_ref=f"refs/heads/{C2A_TARGET_BRANCH}",
    ) != "PINNED_ACCEPTED_F0L":
        raise VerificationError("C2A route self-check resolved the wrong base source")

    negative_cases = 0
    for call in (
        lambda: _resolve_f0l_route(
            event_name="pull_request",
            head_ref=F0L_TARGET_BRANCH,
            base_ref=F0L_TARGET_BRANCH,
        ),
        lambda: _resolve_post_f0l_route(
            active_slice="F1",
            event_name="pull_request",
            head_ref=F1_TARGET_BRANCH,
            base_ref=F0L_BASE_BRANCH,
        ),
        lambda: _resolve_post_f0l_route(
            active_slice="C2A",
            event_name="push",
            event_ref=f"refs/heads/{C2A_TARGET_BRANCH}-unexpected",
        ),
    ):
        try:
            call()
        except VerificationError:
            negative_cases += 1
        else:
            raise VerificationError("F0L routing self-check accepted a negative case")

    _require_changed_path_contract(
        active_slice="F0L",
        changed=ACTIVE_F0L_ALLOWLIST,
        allowlist=ACTIVE_F0L_ALLOWLIST,
        exact_changed_paths=True,
    )
    history_base = "a" * 40
    authorized_history = (
        *F0L_RATIFIED_EXISTING_COMMITS,
        "d" * 40,
    )
    for count in (1, 2, 3, 4, 5):
        _require_f0l_bounded_fast_forward_commits(
            commit_count=count,
            oldest_parent=history_base,
            base_head=history_base,
            ordered_commits=authorized_history[:count],
            delivery_parent=(
                history_base if count == 1 else authorized_history[count - 2]
            ),
        )
    for count, oldest_parent, ordered_commits, delivery_parent in (
        (0, history_base, (), history_base),
        (6, history_base, (*authorized_history, "e" * 40), authorized_history[-1]),
        (1, "b" * 40, authorized_history[:1], history_base),
        (
            3,
            history_base,
            ("c" * 40, *authorized_history[1:3]),
            authorized_history[1],
        ),
        (5, history_base, authorized_history, "e" * 40),
        (
            5,
            history_base,
            (*authorized_history[:3], "c" * 40, authorized_history[4]),
            "c" * 40,
        ),
    ):
        try:
            _require_f0l_bounded_fast_forward_commits(
                commit_count=count,
                oldest_parent=oldest_parent,
                base_head=history_base,
                ordered_commits=ordered_commits,
                delivery_parent=delivery_parent,
            )
        except VerificationError:
            negative_cases += 1
        else:
            raise VerificationError(
                "F0L history self-check accepted out-of-bounds delivery history"
            )
    _require_f0l_correction_4_paths(commit_count=3, changed_paths=None)
    _require_f0l_correction_4_paths(
        commit_count=4,
        changed_paths=set(F0L_CORRECTION_4_PATHS),
    )
    _require_f0l_correction_4_paths(
        commit_count=5,
        changed_paths=set(F0L_CORRECTION_4_PATHS),
    )
    for commit_count, changed_paths in (
        (3, set(F0L_CORRECTION_4_PATHS)),
        (4, None),
        (4, set(F0L_CORRECTION_4_PATHS) - {sorted(F0L_CORRECTION_4_PATHS)[0]}),
        (4, set(F0L_CORRECTION_4_PATHS) | {"unauthorized/fourth-path"}),
        (5, None),
    ):
        try:
            _require_f0l_correction_4_paths(
                commit_count=commit_count,
                changed_paths=changed_paths,
            )
        except VerificationError:
            negative_cases += 1
        else:
            raise VerificationError(
                "F0L correction-4 path self-check accepted scope drift"
            )
    _require_f0l_correction_5_paths(commit_count=4, changed_paths=None)
    _require_f0l_correction_5_paths(
        commit_count=5,
        changed_paths=set(F0L_CORRECTION_5_PATHS),
    )
    for commit_count, changed_paths in (
        (4, set(F0L_CORRECTION_5_PATHS)),
        (5, None),
        (5, set(F0L_CORRECTION_5_PATHS) - {sorted(F0L_CORRECTION_5_PATHS)[0]}),
        (5, set(F0L_CORRECTION_5_PATHS) | {"unauthorized/fifth-path"}),
    ):
        try:
            _require_f0l_correction_5_paths(
                commit_count=commit_count,
                changed_paths=changed_paths,
            )
        except VerificationError:
            negative_cases += 1
        else:
            raise VerificationError(
                "F0L correction-5 path self-check accepted scope drift"
            )
    _require_f0l_clean_status("")
    try:
        _require_f0l_clean_status(" M authorized-but-uncommitted.py")
    except VerificationError:
        negative_cases += 1
    else:
        raise VerificationError("F0L clean-status self-check accepted dirty state")
    fixture_path = sorted(F0L_FIXTURE_DELTAS)[0]
    for changed in (
        ACTIVE_F0L_ALLOWLIST - {fixture_path},
        ACTIVE_F0L_ALLOWLIST | {"unauthorized/27th-path"},
    ):
        try:
            _require_changed_path_contract(
                active_slice="F0L",
                changed=changed,
                allowlist=ACTIVE_F0L_ALLOWLIST,
                exact_changed_paths=True,
            )
        except VerificationError:
            negative_cases += 1
        else:
            raise VerificationError("F0L path self-check accepted a negative case")

    fixture_specification: dict[str, int | str] = {
        "call_line": 2,
        "call_source": "call",
        "insert_after_line": 3,
        "insert_after_source": "anchor",
    }
    base_fixture_source = "before\ncall\nanchor\nafter\n"
    exact_fixture_source = (
        "before\ncall\nanchor\n"
        '            primary_language_tag="en",\n'
        '            primary_language_assignment="EXPLICIT",\n'
        "after\n"
    )
    _require_exact_fixture_delta_source(
        path="fixture.py",
        base_source=base_fixture_source,
        head_source=exact_fixture_source,
        specification=fixture_specification,
    )
    fixture_blob = "a" * 40
    _require_regular_blob_tree_entry(
        path="fixture.py",
        revision="HEAD",
        entry=f"100644 blob {fixture_blob}\tfixture.py",
        expected_blob=fixture_blob,
    )
    for invalid_fixture_entry in (
        f"120000 blob {fixture_blob}\tfixture.py",
        f"100644 tree {fixture_blob}\tfixture.py",
        f"100644 blob {'b' * 40}\tfixture.py",
        f"100644 blob {fixture_blob}\tother.py",
    ):
        try:
            _require_regular_blob_tree_entry(
                path="fixture.py",
                revision="HEAD",
                entry=invalid_fixture_entry,
                expected_blob=fixture_blob,
            )
        except VerificationError:
            negative_cases += 1
        else:
            raise VerificationError(
                "F0L fixture self-check accepted tree-entry drift"
            )
    for invalid_fixture_source in (
        base_fixture_source,
        exact_fixture_source.replace("after\n", "unrelated\nafter\n"),
    ):
        try:
            _require_exact_fixture_delta_source(
                path="fixture.py",
                base_source=base_fixture_source,
                head_source=invalid_fixture_source,
                specification=fixture_specification,
            )
        except VerificationError:
            negative_cases += 1
        else:
            raise VerificationError("F0L fixture self-check accepted delta drift")

    pin_head = "a" * 40
    pin_tree = "b" * 40
    _require_f0l_accepted_pin(
        accepted_head=pin_head,
        accepted_tree=pin_tree,
        base_head=pin_head,
        base_tree=pin_tree,
    )
    for accepted_head, accepted_tree, base_head, base_tree in (
        (None, pin_tree, pin_head, pin_tree),
        (pin_head, None, pin_head, pin_tree),
        (pin_head.upper(), pin_tree, pin_head, pin_tree),
        (pin_head, pin_tree, "c" * 40, pin_tree),
        (pin_head, pin_tree, pin_head, "d" * 40),
    ):
        try:
            _require_f0l_accepted_pin(
                accepted_head=accepted_head,
                accepted_tree=accepted_tree,
                base_head=base_head,
                base_tree=base_tree,
            )
        except VerificationError:
            negative_cases += 1
        else:
            raise VerificationError("accepted-F0L pin self-check accepted drift")

    def render(class_name: str, methods: tuple[str, ...]) -> str:
        body = "\n".join(f"    def {name}(self):\n        pass" for name in methods)
        return f"class {class_name}:\n{body}\n"

    synthetic_models = """
_PROJECT_LANGUAGE_LOOKUP_PREFIXES = (
    "primary_language_tag__",
    "primary_language_assignment__",
)
class ProjectPrimaryLanguageAssignment:
    EXPLICIT = "EXPLICIT"
    LEGACY_UNKNOWN = "LEGACY_UNKNOWN"
class ProjectQuerySet:
    @staticmethod
    def _prevalidate_project_language_request(*sources):
        if key.startswith(_PROJECT_LANGUAGE_LOOKUP_PREFIXES):
            raise ValueError("project_primary_language_lookup_forbidden")
        value = callable(value)
        value = canonicalize_language_tag(value)
        assignment = ProjectPrimaryLanguageAssignment.EXPLICIT
        assignment = ProjectPrimaryLanguageAssignment.LEGACY_UNKNOWN
        message = "Project language identity values are inconsistent."
    def _assert_prevalidated_language_matches(self):
        pass
    def _get_or_create_prevalidated(self):
        self._assert_prevalidated_language_matches()
    def get_or_create(self):
        requested = self._prevalidate_project_language_request()
        return self._get_or_create_prevalidated()
    def update_or_create(self):
        requested = self._prevalidate_project_language_request()
        return self.select_for_update()._get_or_create_prevalidated()
"""
    async_lines = "\n".join(
        f"            await objects.{entrypoint}()"
        for entrypoint in F0L_ASYNC_ORM_ENTRYPOINTS
    )
    synthetic_tests = (
        f"class {PROJECT_LANGUAGE_TEST_CLASS}:\n"
        f"    def {PROJECT_LANGUAGE_TEST_METHODS[0]}(self):\n"
        "        async def exercise():\n"
        f"{async_lines}\n"
        "        async_to_sync(exercise)()\n"
    )
    _require_f0l_correction_4_evidence(
        models_source=synthetic_models,
        tests_source=synthetic_tests,
    )
    for invalid_models, invalid_tests in (
        (
            synthetic_models.replace(
                "primary_language_assignment__",
                "primary_language_assignment_",
            ),
            synthetic_tests,
        ),
        (
            synthetic_models,
            synthetic_tests.replace(".abulk_update()", ".bulk_update()"),
        ),
        (
            synthetic_models,
            synthetic_tests.replace("        async_to_sync(exercise)()\n", ""),
        ),
        (
            synthetic_models.replace(
                "            raise ValueError(\"project_primary_language_lookup_forbidden\")",
                "            code = \"project_primary_language_lookup_forbidden\"",
            ),
            synthetic_tests,
        ),
        (
            synthetic_models.replace(
                "        if key.startswith(_PROJECT_LANGUAGE_LOOKUP_PREFIXES):",
                "        if not key.startswith(_PROJECT_LANGUAGE_LOOKUP_PREFIXES):",
            ),
            synthetic_tests,
        ),
        (
            synthetic_models.replace(
                "        if key.startswith(_PROJECT_LANGUAGE_LOOKUP_PREFIXES):\n"
                "            raise ValueError(\"project_primary_language_lookup_forbidden\")",
                "        if key.startswith(_PROJECT_LANGUAGE_LOOKUP_PREFIXES):\n"
                "            pass\n"
                "        else:\n"
                "            raise ValueError(\"project_primary_language_lookup_forbidden\")",
            ),
            synthetic_tests,
        ),
        (
            synthetic_models.replace(
                "    def get_or_create(self):\n"
                "        requested = self._prevalidate_project_language_request()\n",
                "    def get_or_create(self):\n"
                "        project = self.get()\n"
                "        requested = self._prevalidate_project_language_request()\n",
            ),
            synthetic_tests,
        ),
        (
            synthetic_models.replace(
                "    def update_or_create(self):\n"
                "        requested = self._prevalidate_project_language_request()\n",
                "    def update_or_create(self):\n"
                "        project = self.select_for_update()\n"
                "        requested = self._prevalidate_project_language_request()\n",
            ),
            synthetic_tests,
        ),
    ):
        try:
            _require_f0l_correction_4_evidence(
                models_source=invalid_models,
                tests_source=invalid_tests,
            )
        except VerificationError:
            negative_cases += 1
        else:
            raise VerificationError(
                "F0L correction-4 self-check accepted guard or async drift"
            )

    for class_name, methods in (
        (PROJECT_LANGUAGE_TEST_CLASS, PROJECT_LANGUAGE_TEST_METHODS),
        (PROJECT_LANGUAGE_WRITE_TEST_CLASS, PROJECT_LANGUAGE_WRITE_TEST_METHODS),
        (PROJECT_LANGUAGE_HTTP_TEST_CLASS, PROJECT_LANGUAGE_HTTP_TEST_METHODS),
        (PROJECT_LANGUAGE_MIGRATION_TEST_CLASS, PROJECT_LANGUAGE_MIGRATION_TEST_METHODS),
    ):
        _require_exact_test_topology(
            source=render(class_name, methods),
            class_name=class_name,
            expected_methods=methods,
        )
        try:
            _require_exact_test_topology(
                source=render(class_name, methods[:-1]),
                class_name=class_name,
                expected_methods=methods,
            )
        except VerificationError:
            negative_cases += 1
        else:
            raise VerificationError("F0L topology self-check accepted registry drift")

    successor_sources = {
        "F1": "\n".join(
            (
                render(F1_PORTABLE_TEST_CLASS, F1_PORTABLE_TEST_METHODS),
                render(F1_MIGRATION_TEST_CLASS, F1_MIGRATION_TEST_METHODS),
            )
        ),
        "C2A": "\n".join(
            (
                render(C2A_PORTABLE_TEST_CLASS, C2A_PORTABLE_TEST_METHODS),
                render("AuthorityUnpinnedChromiumClass", C2A_CHROMIUM_TEST_METHODS),
            )
        ),
    }
    for active_slice, source in successor_sources.items():
        _require_successor_test_source_topology(
            source,
            active_slice=active_slice,
        )
        for invalid_source in (
            source + "\ndef test_unauthorized_module_node():\n    pass\n",
            source.replace(
                (F1_PORTABLE_TEST_METHODS if active_slice == "F1" else C2A_CHROMIUM_TEST_METHODS)[-1],
                "test_registry_drift",
                1,
            ),
            source + "\nclass UnauthorizedExtraTests:\n    def test_extra(self):\n        pass\n",
        ):
            try:
                _require_successor_test_source_topology(
                    invalid_source,
                    active_slice=active_slice,
                )
            except VerificationError:
                negative_cases += 1
            else:
                raise VerificationError(
                    f"{active_slice} successor topology self-check accepted drift"
                )

    workflow_source = "\n".join(_successor_workflow_required_tokens())
    _require_successor_workflow_contract(workflow_source)
    for token in dict.fromkeys(_successor_workflow_required_tokens()):
        try:
            _require_successor_workflow_contract(
                workflow_source.replace(token, "SELF_CHECK_REMOVED", 1)
            )
        except VerificationError:
            negative_cases += 1
        else:
            raise VerificationError(
                f"successor workflow self-check accepted missing token: {token}"
            )
    terminal_cli = '--successor-evidence-dir "$RUNNER_TEMP/successor-evidence"'
    try:
        _require_successor_workflow_contract(
            workflow_source + "\n" + terminal_cli
        )
    except VerificationError:
        negative_cases += 1
    else:
        raise VerificationError(
            "successor workflow self-check accepted duplicate terminal invocation"
        )

    with TemporaryDirectory(prefix="f0l-successor-self-check-") as temp_name:
        temp_root = Path(temp_name)
        synthetic_repo = temp_root / "repo"
        synthetic_repo.mkdir()
        _git(synthetic_repo, "init", "--quiet")
        _git(synthetic_repo, "config", "user.name", "F0L Self Check")
        _git(synthetic_repo, "config", "user.email", "f0l-self-check@example.invalid")
        probe_path = synthetic_repo / "probe.txt"
        probe_path.write_text("base\n", encoding="utf-8")
        _git(synthetic_repo, "add", "probe.txt")
        _git(synthetic_repo, "commit", "--quiet", "-m", "base")
        synthetic_base_head = _git(synthetic_repo, "rev-parse", "HEAD")
        synthetic_base_tree = _git(synthetic_repo, "rev-parse", "HEAD^{tree}")
        probe_path.write_text("delivery\n", encoding="utf-8")
        _git(synthetic_repo, "add", "probe.txt")
        _git(synthetic_repo, "commit", "--quiet", "-m", "delivery")
        synthetic_delivery_head = _git(synthetic_repo, "rev-parse", "HEAD")
        synthetic_delivery_tree = _git(synthetic_repo, "rev-parse", "HEAD^{tree}")

        def require_evidence(directory: Path, active_slice: str) -> None:
            _require_successor_ci_evidence(
                directory,
                repo=synthetic_repo,
                active_slice=active_slice,
                base_head=synthetic_base_head,
                base_tree=synthetic_base_tree,
                delivery_head=synthetic_delivery_head,
                delivery_tree=synthetic_delivery_tree,
            )

        for active_slice in ("F1", "C2A"):
            positive_dir = temp_root / f"{active_slice.lower()}-positive"
            _write_successor_self_check_evidence(
                positive_dir,
                active_slice=active_slice,
                base_head=synthetic_base_head,
                base_tree=synthetic_base_tree,
                delivery_head=synthetic_delivery_head,
                delivery_tree=synthetic_delivery_tree,
            )
            require_evidence(positive_dir, active_slice)

            mutations = [
                "extra-file",
                "missing-junit",
                "stale-manifest",
                "junit-failure",
                "migration-gates",
                "wheel-fallback",
                "wheel-repository-doc",
            ]
            if active_slice == "C2A":
                mutations.extend(("synthetic-tree", "independent-tree"))
            for mutation_index, mutation in enumerate(mutations):
                evidence_dir = temp_root / (
                    f"{active_slice.lower()}-negative-{mutation_index}"
                )
                _write_successor_self_check_evidence(
                    evidence_dir,
                    active_slice=active_slice,
                    base_head=synthetic_base_head,
                    base_tree=synthetic_base_tree,
                    delivery_head=synthetic_delivery_head,
                    delivery_tree=synthetic_delivery_tree,
                )
                if mutation == "extra-file":
                    (evidence_dir / "unexpected.txt").write_text(
                        "unexpected\n", encoding="utf-8"
                    )
                elif mutation == "missing-junit":
                    (evidence_dir / SUCCESSOR_JUNIT_FILES[active_slice][0]).unlink()
                elif mutation == "stale-manifest":
                    path = evidence_dir / "manifest.json"
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    payload["base_head"] = "f" * 40
                    path.write_text(json.dumps(payload), encoding="utf-8")
                elif mutation == "junit-failure":
                    path = evidence_dir / SUCCESSOR_JUNIT_FILES[active_slice][0]
                    tree = ET.fromstring(path.read_text(encoding="utf-8"))
                    ET.SubElement(tree.find(".//testcase"), "failure")
                    path.write_text(ET.tostring(tree, encoding="unicode"), encoding="utf-8")
                elif mutation == "migration-gates":
                    path = evidence_dir / "migration.json"
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    payload["gates"] = list(reversed(payload["gates"]))
                    path.write_text(json.dumps(payload), encoding="utf-8")
                elif mutation == "wheel-fallback":
                    path = evidence_dir / "wheel-install.json"
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    payload["source_tree_fallback"] = True
                    path.write_text(json.dumps(payload), encoding="utf-8")
                elif mutation == "wheel-repository-doc":
                    wheel_path = evidence_dir / SUCCESSOR_WHEEL_NAME
                    repository_only = sorted(
                        SUCCESSOR_REPOSITORY_ONLY_WHEEL_PATHS[active_slice]
                    )[0]
                    with ZipFile(wheel_path, "a") as archive:
                        archive.writestr(
                            f"unauthorized-prefix/{repository_only}",
                            b"must remain Git-only\n",
                        )
                    path = evidence_dir / "wheel-install.json"
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    payload["wheel_sha256"] = hashlib.sha256(
                        wheel_path.read_bytes()
                    ).hexdigest()
                    path.write_text(json.dumps(payload), encoding="utf-8")
                elif mutation in {"synthetic-tree", "independent-tree"}:
                    path = evidence_dir / "synthetic-tree.json"
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    payload[mutation.replace("-", "_")] = "e" * 40
                    path.write_text(json.dumps(payload), encoding="utf-8")
                try:
                    require_evidence(evidence_dir, active_slice)
                except VerificationError:
                    negative_cases += 1
                else:
                    raise VerificationError(
                        f"{active_slice} evidence self-check accepted {mutation}"
                    )

        try:
            _require_successor_ci_evidence(
                None,
                repo=synthetic_repo,
                active_slice="F1",
                base_head=synthetic_base_head,
                base_tree=synthetic_base_tree,
                delivery_head=synthetic_delivery_head,
                delivery_tree=synthetic_delivery_tree,
            )
        except VerificationError:
            negative_cases += 1
        else:
            raise VerificationError(
                "successor evidence self-check accepted absent evidence directory"
            )

    return {
        "marker": "PROJECT_LANGUAGE_F0L_VERIFIER_SELF_CHECK=PASS",
        "correction_4_marker": "F0L_CORRECTION_4_GUARD_ASYNC_SELF_CHECK=PASS",
        "downstream_marker": "POST_F0L_F1_C2A_EXECUTABLE_CI_SELF_CHECK=PASS",
        "network_access": False,
        "caller_repository_access": False,
        "temporary_repository_access": True,
        "positive_slices": ["F0L", "F1", "C2A"],
        "negative_cases": negative_cases,
    }


def verify(
    repo: Path,
    *,
    base_head: str,
    base_tree: str,
    active_slice: str = "C0",
    fd05_accepted_head: str | None = None,
    fd05_accepted_tree: str | None = None,
) -> dict[str, object]:
    contract = _resolve_slice_contract(
        active_slice=active_slice,
        base_head=base_head,
        base_tree=base_tree,
        fd05_accepted_head=fd05_accepted_head,
        fd05_accepted_tree=fd05_accepted_tree,
    )
    actual_base_tree = _git(repo, "rev-parse", f"{base_head}^{{tree}}")
    if actual_base_tree != base_tree:
        raise VerificationError(
            f"base tree mismatch: expected {base_tree}, resolved {actual_base_tree}"
        )
    if _git(repo, "merge-base", base_head, "HEAD") != base_head:
        raise VerificationError(
            f"HEAD is not a descendant of the exact {active_slice} base"
        )

    if active_slice == "C1":
        accepted_head = contract["fd05_accepted_head"]
        accepted_tree = contract["fd05_accepted_tree"]
        if not isinstance(accepted_head, str) or not isinstance(accepted_tree, str):
            raise VerificationError("internal C1 FD05 accepted-pin contract is invalid")
        resolved_accepted_tree = _git(
            repo,
            "rev-parse",
            f"{accepted_head}^{{tree}}",
        )
        if resolved_accepted_tree != accepted_tree:
            raise VerificationError(
                "FD05 accepted tree mismatch: "
                f"expected {accepted_tree}, resolved {resolved_accepted_tree}"
            )
        if _git(repo, "merge-base", accepted_head, base_head) != accepted_head:
            raise VerificationError(
                "the exact C1 R0 START is not a descendant of accepted FD05 H2"
            )
        accepted_to_start_merges = tuple(
            item
            for item in _git(
                repo,
                "rev-list",
                "--merges",
                f"{accepted_head}..{base_head}",
            ).splitlines()
            if item
        )
        _require_merge_free("C1 accepted H2-to-R0 START", accepted_to_start_merges)

    if active_slice in {"R0", "C1", "FD02", "FD03", "FD06", "FD07"}:
        merge_commits = tuple(
            item
            for item in _git(
                repo,
                "rev-list",
                "--merges",
                f"{base_head}..HEAD",
            ).splitlines()
            if item
        )
        _require_merge_free(active_slice, merge_commits)

    delivery_commit_count: int | None = None
    delivery_parent: str | None = None
    fd06_intermediate_parent: str | None = None
    fd06_intermediate_tree: str | None = None
    fd06_ordered_commits: tuple[str, ...] | None = None
    if active_slice in {"FD02", "FD03", "FD06", "FD07"}:
        delivery_commit_count = int(
            _git(repo, "rev-list", "--count", f"{base_head}..HEAD")
        )
        delivery_parent = _git(repo, "rev-parse", "HEAD^")
        if active_slice in {"FD02", "FD07"}:
            _require_single_fast_forward_commit(
                active_slice=active_slice,
                commit_count=delivery_commit_count,
                delivery_parent=delivery_parent,
                base_head=base_head,
            )
        elif active_slice == "FD06":
            fd06_intermediate_parent = _git(
                repo,
                "rev-parse",
                f"{PINNED_FD06_RC4_INTERMEDIATE_HEAD}^",
            )
            fd06_intermediate_tree = _git(
                repo,
                "rev-parse",
                f"{PINNED_FD06_RC4_INTERMEDIATE_HEAD}^{{tree}}",
            )
            fd06_ordered_commits = tuple(
                item
                for item in _git(
                    repo,
                    "rev-list",
                    "--reverse",
                    f"{base_head}..HEAD",
                ).splitlines()
                if item
            )
            if (
                _git(repo, "merge-base", PINNED_FD06_RC4_INTERMEDIATE_HEAD, "HEAD")
                != PINNED_FD06_RC4_INTERMEDIATE_HEAD
            ):
                raise VerificationError(
                    "FD06 RC5 HEAD is not a descendant of the exact RC4 intermediate"
                )
            _require_fd06_rc5_public_history(
                commit_count=delivery_commit_count,
                delivery_head=_git(repo, "rev-parse", "HEAD"),
                delivery_parent=delivery_parent,
                intermediate_parent=fd06_intermediate_parent,
                intermediate_tree=fd06_intermediate_tree,
                ordered_commits=fd06_ordered_commits,
            )
        else:
            if (
                _git(repo, "rev-parse", f"{PINNED_FD03_RC2_START_HEAD}^{{tree}}")
                != PINNED_FD03_RC2_START_TREE
                or _git(repo, "rev-parse", f"{PINNED_FD03_RC2_START_HEAD}^")
                != base_head
                or _git(repo, "merge-base", PINNED_FD03_RC2_START_HEAD, "HEAD")
                != PINNED_FD03_RC2_START_HEAD
            ):
                raise VerificationError(
                    "FD03 RC2 start HEAD/TREE/parent/ancestry drifted from authorization"
                )
            _require_fd03_rc2_fast_forward(
                commit_count=delivery_commit_count,
                delivery_parent=delivery_parent,
            )

    changed = _changed_paths(repo, base_head)
    allowlist = contract["allowlist"]
    if not isinstance(allowlist, frozenset):
        raise VerificationError("internal slice allowlist contract is invalid")
    exact_changed_paths = contract["exact_changed_paths"]
    if not isinstance(exact_changed_paths, bool):
        raise VerificationError("internal exact changed-path contract is invalid")
    _require_changed_path_contract(
        active_slice=active_slice,
        changed=changed,
        allowlist=allowlist,
        exact_changed_paths=exact_changed_paths,
    )
    aggregate_changed: set[str] | None = None
    if active_slice == "FD03":
        aggregate_changed = _changed_paths(repo, PINNED_FD02_BASE_HEAD)
        _require_changed_path_contract(
            active_slice="FD03_AGGREGATE",
            changed=aggregate_changed,
            allowlist=FD03_AGGREGATE_ALLOWLIST,
            exact_changed_paths=True,
        )

    domain_prefix = "software/conflict_analysis/domain/"
    changed_domain = sorted(path for path in changed if path.startswith(domain_prefix))
    if active_slice not in {"FD02", "FD03", "FD06", "FD07"} and changed_domain:
        raise VerificationError("domain/ is mechanically frozen: " + ", ".join(changed_domain))

    domain_tree = _git(
        repo,
        "rev-parse",
        f"{base_head}:software/conflict_analysis/domain",
    )
    expected_domain_tree = contract["domain_tree"]
    if not isinstance(expected_domain_tree, str):
        raise VerificationError("internal domain freeze contract is invalid")
    if domain_tree != expected_domain_tree:
        raise VerificationError(
            "pinned domain tree mismatch: "
            f"expected {expected_domain_tree}, got {domain_tree}"
        )
    if active_slice not in {"FD02", "FD03", "FD06", "FD07"} and _git(
        repo,
        "diff",
        "--name-only",
        base_head,
        "--",
        "software/conflict_analysis/domain",
    ):
        raise VerificationError("tracked domain/ bytes differ from the pinned base")

    migrations = tuple(
        line
        for line in _git(
            repo,
            "ls-files",
            "software/conflict_analysis/domain/migrations",
        ).splitlines()
        if line
    )
    if migrations != PINNED_MIGRATIONS:
        raise VerificationError(
            "migration filename set changed: "
            + json.dumps({"expected": PINNED_MIGRATIONS, "actual": migrations})
        )

    frozen_objects: dict[str, str] = {}
    if active_slice == "R0":
        r0_frozen_objects = {
            "software/conflict_analysis/domain": PINNED_R0_DOMAIN_TREE,
            "software/conflict_analysis/domain/migrations": PINNED_R0_MIGRATIONS_TREE,
            "software/conflict_analysis/domain/models.py": PINNED_R0_MODELS_BLOB,
            "software/conflict_analysis/domain/enums.py": PINNED_R0_ENUMS_BLOB,
            "software/conflict_analysis/production_studio": (
                PINNED_R0_PRODUCTION_STUDIO_TREE
            ),
            "software/conflict_analysis/production_studio/contracts": (
                PINNED_R0_CLAIM_CONTRACTS_TREE
            ),
        }
        for path, expected_object in r0_frozen_objects.items():
            base_object = _git(repo, "rev-parse", f"{base_head}:{path}")
            head_object = _git(repo, "rev-parse", f"HEAD:{path}")
            if base_object != expected_object or head_object != expected_object:
                raise VerificationError(
                    f"R0 frozen object drift at {path}: "
                    f"expected {expected_object}, base {base_object}, HEAD {head_object}"
                )
            frozen_objects[path] = expected_object
    elif active_slice == "C1":
        for path in C1_FROZEN_PATHS:
            start_object = _git(repo, "rev-parse", f"{base_head}:{path}")
            head_object = _git(repo, "rev-parse", f"HEAD:{path}")
            if head_object != start_object:
                raise VerificationError(
                    f"C1 frozen object drift at {path}: "
                    f"R0 start {start_object}, HEAD {head_object}"
                )
            frozen_objects[path] = start_object
    elif active_slice == "FD02":
        for path in FD02_FROZEN_PATHS:
            base_object = _git(repo, "rev-parse", f"{base_head}:{path}")
            head_object = _git(repo, "rev-parse", f"HEAD:{path}")
            if head_object != base_object:
                raise VerificationError(
                    f"FD02 frozen object drift at {path}: "
                    f"accepted C1 {base_object}, HEAD {head_object}"
                )
            frozen_objects[path] = base_object
    elif active_slice == "FD03":
        for path in FD03_FROZEN_PATHS:
            base_object = _git(repo, "rev-parse", f"{base_head}:{path}")
            head_object = _git(repo, "rev-parse", f"HEAD:{path}")
            if head_object != base_object:
                raise VerificationError(
                    f"FD03 frozen object drift at {path}: "
                    f"accepted FD02 {base_object}, HEAD {head_object}"
                )
            frozen_objects[path] = base_object

        domain_test_path = (
            "software/conflict_analysis/domain/tests/test_foundation_studio_http.py"
        )
        _require_exact_test_topology(
            source=(repo / domain_test_path).read_text(encoding="utf-8"),
            class_name=FD03_TEST_CLASS,
            expected_methods=FD03_TEST_METHODS,
        )

        c0_test_path = (
            "software/conflict_analysis/production_studio/tests/test_read_only_http.py"
        )
        base_c0_source = _git(repo, "show", f"{base_head}:{c0_test_path}")
        head_c0_source = (repo / c0_test_path).read_text(encoding="utf-8")
        if base_c0_source == head_c0_source:
            raise VerificationError("FD03 bounded C0 assertion node was not updated")
        if _normalized_authorized_method_body(
            base_c0_source,
            class_name=FD03_C0_CLASS,
            method_name=FD03_C0_METHOD,
        ) != _normalized_authorized_method_body(
            head_c0_source,
            class_name=FD03_C0_CLASS,
            method_name=FD03_C0_METHOD,
        ):
            raise VerificationError(
                "FD03 changed production_studio test bytes outside the one authorized C0 node body"
            )
    elif active_slice == "FD06":
        _require_fd06_static_contract(
            exact_path_count=len(ACTIVE_FD06_ALLOWLIST),
            portable_count=len(FD06_PORTABLE_METHODS),
            concurrency_count=len(FD06_CONCURRENCY_METHODS),
            postgresql_total=FD06_POSTGRESQL_TOTAL,
            postgresql_skipped=FD06_POSTGRESQL_SKIPPED,
            sqlite_passed=FD06_SQLITE_PASSED,
            sqlite_skipped=FD06_SQLITE_SKIPPED,
        )
        _require_fd06_frozen_contract(
            exact_frozen_objects=dict(FD06_EXACT_FROZEN_OBJECTS),
            reopened_base_blobs=dict(FD06_REOPENED_BASE_BLOBS),
        )
        for path, expected_object in FD06_EXACT_FROZEN_OBJECTS.items():
            base_object = _git(repo, "rev-parse", f"{base_head}:{path}")
            head_object = _git(repo, "rev-parse", f"HEAD:{path}")
            if base_object != expected_object or head_object != expected_object:
                raise VerificationError(
                    f"FD06 frozen object drift at {path}: expected "
                    f"{expected_object}, base {base_object}, HEAD {head_object}"
                )
            frozen_objects[path] = expected_object
        for path, expected_object in FD06_REOPENED_BASE_BLOBS.items():
            base_object = _git(repo, "rev-parse", f"{base_head}:{path}")
            if base_object != expected_object:
                raise VerificationError(
                    f"FD06 reopened base blob drift at {path}: expected "
                    f"{expected_object}, got {base_object}"
                )
        test_source = (
            repo / "software/conflict_analysis/domain/tests/test_foundation_studio_publication_reconciliation.py"
        ).read_text(encoding="utf-8")
        _require_exact_test_topology(
            source=test_source,
            class_name=FD06_PORTABLE_CLASS,
            expected_methods=FD06_PORTABLE_METHODS,
        )
        _require_exact_test_topology(
            source=test_source,
            class_name=FD06_CONCURRENCY_CLASS,
            expected_methods=FD06_CONCURRENCY_METHODS,
        )

        for path, class_name, method_name in (
            (
                "software/conflict_analysis/domain/tests/"
                "test_foundation_studio_http.py",
                FD06_HTTP_BOUNDED_CLASS,
                FD06_HTTP_BOUNDED_METHOD,
            ),
            (
                "software/conflict_analysis/domain/tests/"
                "test_foundation_studio_bootstrap.py",
                FD06_BOOTSTRAP_BOUNDED_CLASS,
                FD06_BOOTSTRAP_BOUNDED_METHOD,
            ),
        ):
            base_source = _git(repo, "show", f"{base_head}:{path}")
            head_source = (repo / path).read_text(encoding="utf-8")
            if base_source == head_source:
                raise VerificationError(
                    f"FD06 bounded regression node was not updated at {path}"
                )
            if _normalized_authorized_method_body(
                base_source,
                class_name=class_name,
                method_name=method_name,
            ) != _normalized_authorized_method_body(
                head_source,
                class_name=class_name,
                method_name=method_name,
            ):
                raise VerificationError(
                    f"FD06 changed {path} outside the one authorized method body"
                )
    elif active_slice == "FD07":
        _require_fd07_static_contract(
            exact_path_count=len(ACTIVE_FD07_ALLOWLIST),
            test_node_count=len(FD07_TEST_METHODS),
            postgresql_total=FD07_POSTGRESQL_TOTAL,
            postgresql_skipped=FD07_POSTGRESQL_SKIPPED,
            sqlite_passed=FD07_SQLITE_PASSED,
            sqlite_skipped=FD07_SQLITE_SKIPPED,
        )
        _require_fd07_frozen_contract(
            exact_frozen_objects=dict(FD07_EXACT_FROZEN_OBJECTS),
            reopened_base_blobs=dict(FD07_REOPENED_BASE_BLOBS),
        )
        for path, expected_object in FD07_EXACT_FROZEN_OBJECTS.items():
            base_object = _git(repo, "rev-parse", f"{base_head}:{path}")
            head_object = _git(repo, "rev-parse", f"HEAD:{path}")
            if base_object != expected_object or head_object != expected_object:
                raise VerificationError(
                    f"FD07 frozen object drift at {path}: expected "
                    f"{expected_object}, base {base_object}, HEAD {head_object}"
                )
            frozen_objects[path] = expected_object
        for path, expected_object in FD07_REOPENED_BASE_BLOBS.items():
            base_object = _git(repo, "rev-parse", f"{base_head}:{path}")
            if base_object != expected_object:
                raise VerificationError(
                    f"FD07 reopened base blob drift at {path}: expected "
                    f"{expected_object}, got {base_object}"
                )

        readiness_test_path = (
            "software/conflict_analysis/domain/tests/"
            "test_foundation_studio_publication_readiness.py"
        )
        if _git(
            repo,
            "ls-tree",
            "--name-only",
            base_head,
            "--",
            readiness_test_path,
        ):
            raise VerificationError("FD07 readiness test path must be absent at base")
        _require_exact_test_topology(
            source=(repo / readiness_test_path).read_text(encoding="utf-8"),
            class_name=FD07_TEST_CLASS,
            expected_methods=FD07_TEST_METHODS,
        )

        fd06_test_source = (
            repo
            / "software/conflict_analysis/domain/tests/"
            "test_foundation_studio_publication_reconciliation.py"
        ).read_text(encoding="utf-8")
        _require_exact_test_topology(
            source=fd06_test_source,
            class_name=FD06_PORTABLE_CLASS,
            expected_methods=FD06_PORTABLE_METHODS,
        )
        _require_exact_test_topology(
            source=fd06_test_source,
            class_name=FD06_CONCURRENCY_CLASS,
            expected_methods=FD06_CONCURRENCY_METHODS,
        )

    return {
        "active_slice": active_slice,
        "allowlist_result": "PASS",
        "base_head": base_head,
        "base_tree": base_tree,
        "changed_paths": sorted(changed),
        "aggregate_changed_paths": (
            sorted(aggregate_changed) if aggregate_changed is not None else None
        ),
        "domain_tree": domain_tree,
        "delivery_commit_count": delivery_commit_count,
        "delivery_parent": delivery_parent,
        "fd06_rc4_intermediate_head": (
            PINNED_FD06_RC4_INTERMEDIATE_HEAD if active_slice == "FD06" else None
        ),
        "fd06_rc4_intermediate_parent": fd06_intermediate_parent,
        "fd06_rc4_intermediate_tree": fd06_intermediate_tree,
        "fd06_ordered_delivery_commits": (
            list(fd06_ordered_commits)
            if fd06_ordered_commits is not None
            else None
        ),
        "fd06_public_history_exception": (
            "EXACT_RC4_INTERMEDIATE_PLUS_ONE_CHILD"
            if active_slice == "FD06"
            else None
        ),
        "domain_changed_paths": changed_domain,
        "domain_tree_unchanged": (
            None if active_slice in {"FD02", "FD03", "FD06", "FD07"} else True
        ),
        "exact_changed_paths": changed == allowlist if exact_changed_paths else None,
        "fd05_base_pin": contract["fd05_base_pin"],
        "fd05_accepted_head": contract["fd05_accepted_head"],
        "fd05_accepted_tree": contract["fd05_accepted_tree"],
        "frozen_objects": frozen_objects,
        "merge_commits_absent": (
            True
            if active_slice in {"R0", "C1", "FD02", "FD03", "FD06", "FD07"}
            else None
        ),
        "migration_filenames_unchanged": True,
        "r0_start_pin": contract["r0_start_pin"],
        "c1_base_pin": contract["c1_base_pin"],
        "fd02_base_pin": contract["fd02_base_pin"],
        "fd06_base_pin": contract.get("fd06_base_pin"),
        "fd03_test_node_count": len(FD03_TEST_METHODS) if active_slice == "FD03" else None,
        "fd03_c0_bounded_node_only": True if active_slice == "FD03" else None,
        "fd06_exact_path_count": (
            len(ACTIVE_FD06_ALLOWLIST) if active_slice == "FD06" else None
        ),
        "fd06_portable_test_node_count": (
            len(FD06_PORTABLE_METHODS)
            if active_slice in {"FD06", "FD07"}
            else None
        ),
        "fd06_postgresql_only_test_node_count": (
            len(FD06_CONCURRENCY_METHODS)
            if active_slice in {"FD06", "FD07"}
            else None
        ),
        "fd06_postgresql_expected": (
            {
                "passed": FD06_POSTGRESQL_TOTAL,
                "skipped": FD06_POSTGRESQL_SKIPPED,
            }
            if active_slice == "FD06"
            else None
        ),
        "fd06_sqlite_expected": (
            {"passed": FD06_SQLITE_PASSED, "skipped": FD06_SQLITE_SKIPPED}
            if active_slice == "FD06"
            else None
        ),
        "fd06_synthetic_merge_requirement": (
            {
                "parents": [base_head, "FINAL_FD06_HEAD"],
                "tree": "FINAL_FD06_TREE_EQUALS_INDEPENDENT_MERGE_TREE",
            }
            if active_slice == "FD06"
            else None
        ),
        "fd07_exact_path_count": (
            len(ACTIVE_FD07_ALLOWLIST) if active_slice == "FD07" else None
        ),
        "fd07_test_node_count": (
            len(FD07_TEST_METHODS) if active_slice == "FD07" else None
        ),
        "fd07_postgresql_expected": (
            {
                "passed": FD07_POSTGRESQL_TOTAL,
                "skipped": FD07_POSTGRESQL_SKIPPED,
            }
            if active_slice == "FD07"
            else None
        ),
        "fd07_sqlite_expected": (
            {"passed": FD07_SQLITE_PASSED, "skipped": FD07_SQLITE_SKIPPED}
            if active_slice == "FD07"
            else None
        ),
        "fd07_synthetic_merge_requirement": (
            {
                "parents": [base_head, "FINAL_FD07_HEAD"],
                "tree": "FINAL_FD07_TREE_EQUALS_INDEPENDENT_MERGE_TREE",
            }
            if active_slice == "FD07"
            else None
        ),
        "aggregate_exact_changed_paths": (
            aggregate_changed == FD03_AGGREGATE_ALLOWLIST
            if aggregate_changed is not None
            else None
        ),
    }


def verify_f0l(repo: Path, *, base_head: str, base_tree: str) -> dict[str, object]:
    """Verify the exact F0L delivery without making network/remote-state claims."""

    _require_f0l_static_contract()
    _require_successor_static_contract()
    base_head = _require_exact_object_id("F0L base HEAD", base_head)
    base_tree = _require_exact_object_id("F0L base TREE", base_tree)
    if base_head != PINNED_F0L_BASE_HEAD or base_tree != PINNED_F0L_BASE_TREE:
        raise VerificationError("F0L accepts only the exact authorized FD07 HEAD/TREE")
    if _git(repo, "rev-parse", base_head) != base_head:
        raise VerificationError("exact F0L base commit is unavailable")
    if _git(repo, "rev-parse", f"{base_head}^{{tree}}") != base_tree:
        raise VerificationError("exact F0L base tree does not match authorization")
    if _git(repo, "merge-base", base_head, "HEAD") != base_head:
        raise VerificationError("F0L HEAD is not a descendant of the exact FD07 base")

    ordered_commits = tuple(
        line
        for line in _git(
            repo,
            "rev-list",
            "--reverse",
            f"{base_head}..HEAD",
        ).splitlines()
        if line
    )
    commit_count = len(ordered_commits)
    delivery_parent = _git(repo, "rev-parse", "HEAD^") if commit_count else base_head
    oldest_parent = (
        _git(repo, "rev-parse", f"{ordered_commits[0]}^")
        if ordered_commits
        else base_head
    )
    _require_merge_free(
        "F0L",
        tuple(
            line
            for line in _git(repo, "rev-list", "--merges", f"{base_head}..HEAD").splitlines()
            if line
        ),
    )
    _require_f0l_bounded_fast_forward_commits(
        commit_count=commit_count,
        oldest_parent=oldest_parent,
        base_head=base_head,
        ordered_commits=ordered_commits,
        delivery_parent=delivery_parent,
    )

    _require_f0l_clean_status(
        _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    )
    correction_4_changed_paths = None
    if commit_count >= 4:
        if (
            _git(repo, "rev-parse", f"{PINNED_F0L_CORRECTION_4_HEAD}^{{tree}}")
            != PINNED_F0L_CORRECTION_4_TREE
        ):
            raise VerificationError("F0L correction-4 ratified TREE drifted")
        correction_4_changed_paths = _commit_changed_paths(
            repo, PINNED_F0L_CORRECTION_4_HEAD
        )
    _require_f0l_correction_4_paths(
        commit_count=commit_count,
        changed_paths=correction_4_changed_paths,
    )
    correction_5_changed_paths = (
        _commit_changed_paths(repo, ordered_commits[4])
        if commit_count >= 5
        else None
    )
    _require_f0l_correction_5_paths(
        commit_count=commit_count,
        changed_paths=correction_5_changed_paths,
    )

    changed = _changed_paths(repo, base_head)
    _require_changed_path_contract(
        active_slice="F0L",
        changed=changed,
        allowlist=ACTIVE_F0L_ALLOWLIST,
        exact_changed_paths=True,
    )

    for path, expected_blob in F0L_EXISTING_BASE_BLOBS.items():
        actual = _git(repo, "rev-parse", f"{base_head}:{path}")
        if actual != expected_blob:
            raise VerificationError(
                f"F0L existing-path base blob drift at {path}: "
                f"expected {expected_blob}, got {actual}"
            )

    _require_f0l_fixture_deltas(repo)

    frozen_objects: dict[str, str] = {}
    for path, expected_object in F0L_FROZEN_OBJECTS.items():
        base_object = _git(repo, "rev-parse", f"{base_head}:{path}")
        head_object = _git(repo, "rev-parse", f"HEAD:{path}")
        if base_object != expected_object or head_object != expected_object:
            raise VerificationError(
                f"F0L frozen object drift at {path}: expected {expected_object}, "
                f"base {base_object}, HEAD {head_object}"
            )
        frozen_objects[path] = expected_object

    for path in F0L_NEW_PATHS:
        if _git(repo, "ls-tree", "--name-only", base_head, "--", path):
            raise VerificationError(f"F0L new path unexpectedly exists at base: {path}")
        if not _git(repo, "ls-tree", "--name-only", "HEAD", "--", path):
            raise VerificationError(f"F0L required new path is absent at HEAD: {path}")

    migrations = tuple(
        line
        for line in _git(
            repo, "ls-files", "software/conflict_analysis/domain/migrations"
        ).splitlines()
        if line
    )
    if migrations != F0L_MIGRATIONS:
        raise VerificationError(
            "F0L migration filename set drifted: "
            + json.dumps({"expected": F0L_MIGRATIONS, "actual": migrations})
        )
    migration_path = (
        repo
        / "software/conflict_analysis/domain/migrations/0016_project_primary_language.py"
    )
    migration_source = migration_path.read_text(encoding="utf-8")
    if not re.search(
        r"dependencies\s*=\s*\[\s*\(\s*[\"']domain[\"']\s*,\s*"
        r"[\"']0015_foundation_studio_contract_constraints[\"']\s*\)\s*,?\s*\]",
        migration_source,
        re.DOTALL,
    ):
        raise VerificationError(
            "F0L migration must depend only on "
            "domain.0015_foundation_studio_contract_constraints"
        )

    for class_name, methods in (
        (PROJECT_LANGUAGE_TEST_CLASS, PROJECT_LANGUAGE_TEST_METHODS),
        (PROJECT_LANGUAGE_WRITE_TEST_CLASS, PROJECT_LANGUAGE_WRITE_TEST_METHODS),
        (PROJECT_LANGUAGE_HTTP_TEST_CLASS, PROJECT_LANGUAGE_HTTP_TEST_METHODS),
        (PROJECT_LANGUAGE_MIGRATION_TEST_CLASS, PROJECT_LANGUAGE_MIGRATION_TEST_METHODS),
    ):
        _require_exact_test_topology(
            source=_find_exact_test_class_source(repo, class_name),
            class_name=class_name,
            expected_methods=methods,
        )

    _require_package_restore_caller_registry(repo)
    models_source = (
        repo / "software/conflict_analysis/domain/models.py"
    ).read_text(encoding="utf-8")
    if "def restore_legacy_unknown_from_package(" not in models_source:
        raise VerificationError("sealed Project package-restore entrypoint is absent")
    _require_f0l_correction_4_evidence(
        models_source=models_source,
        tests_source=_find_exact_test_class_source(
            repo,
            PROJECT_LANGUAGE_TEST_CLASS,
        ),
    )
    workflow_source = (
        repo / ".github/workflows/conflict-analysis.yml"
    ).read_text(encoding="utf-8")
    _require_successor_workflow_contract(workflow_source)

    return {
        "active_slice": "F0L",
        "allowlist_result": "PASS",
        "base_head": base_head,
        "base_tree": base_tree,
        "delivery_head": _git(repo, "rev-parse", "HEAD"),
        "delivery_tree": _git(repo, "rev-parse", "HEAD^{tree}"),
        "delivery_commit_count": commit_count,
        "delivery_commits": list(ordered_commits),
        "delivery_parent": delivery_parent,
        "delivery_oldest_parent": oldest_parent,
        "correction_4_head": PINNED_F0L_CORRECTION_4_HEAD,
        "correction_4_tree": PINNED_F0L_CORRECTION_4_TREE,
        "correction_4_changed_paths": (
            sorted(correction_4_changed_paths)
            if correction_4_changed_paths is not None
            else None
        ),
        "correction_5_changed_paths": (
            sorted(correction_5_changed_paths)
            if correction_5_changed_paths is not None
            else None
        ),
        "changed_paths": sorted(changed),
        "exact_changed_path_count": len(changed),
        "new_paths": sorted(F0L_NEW_PATHS),
        "existing_base_blobs": dict(sorted(F0L_EXISTING_BASE_BLOBS.items())),
        "bounded_fixture_deltas": sorted(F0L_FIXTURE_DELTAS),
        "frozen_objects": frozen_objects,
        "migration_filenames": list(migrations),
        "portable_test_node_count": F0L_PORTABLE_TEST_COUNT,
        "postgresql_migration_test_node_count": F0L_POSTGRESQL_MIGRATION_TEST_COUNT,
        "language_lookup_expression_prefixes": list(F0L_LANGUAGE_LOOKUP_PREFIXES),
        "prevalidation_before_lookup_or_lock": True,
        "async_orm_runtime_entrypoints": list(F0L_ASYNC_ORM_ENTRYPOINTS),
        "package_restore_production_callers": [
            "software/conflict_analysis/domain/services/project_packages.py"
        ],
        "downstream_f1_path_count": len(F1_POST_F0L_ALLOWLIST),
        "downstream_c2a_path_count": len(C2A_POST_F0L_ALLOWLIST),
        "downstream_own_diff_intersection": 0,
        "successor_executable_ci_contract": True,
        "merge_commits_absent": True,
        "network_access": False,
    }


def verify_post_f0l(
    repo: Path,
    *,
    active_slice: str,
    base_head: str,
    base_tree: str,
    accepted_head: str | None,
    accepted_tree: str | None,
    evidence_dir: Path | None,
) -> dict[str, object]:
    """Fail closed around externally accepted F0L pins for future F1/C2A."""

    if active_slice not in {"F1", "C2A"}:
        raise VerificationError("post-F0L verifier supports only F1 or C2A")
    _require_f0l_static_contract()
    _require_successor_static_contract()
    base_head = _require_exact_object_id("post-F0L base HEAD", base_head)
    base_tree = _require_exact_object_id("post-F0L base TREE", base_tree)
    _require_f0l_accepted_pin(
        accepted_head=accepted_head,
        accepted_tree=accepted_tree,
        base_head=base_head,
        base_tree=base_tree,
    )
    if _git(repo, "rev-parse", f"{base_head}^{{tree}}") != base_tree:
        raise VerificationError("accepted-F0L commit TREE does not match its pin")
    if _git(repo, "merge-base", base_head, "HEAD") != base_head:
        raise VerificationError(f"{active_slice} is not based on accepted F0L")
    commit_count = int(_git(repo, "rev-list", "--count", f"{base_head}..HEAD"))
    delivery_parent = _git(repo, "rev-parse", "HEAD^") if commit_count else base_head
    _require_merge_free(
        active_slice,
        tuple(
            line
            for line in _git(repo, "rev-list", "--merges", f"{base_head}..HEAD").splitlines()
            if line
        ),
    )
    _require_single_fast_forward_commit(
        active_slice=active_slice,
        commit_count=commit_count,
        delivery_parent=delivery_parent,
        base_head=base_head,
    )
    _require_f0l_clean_status(
        _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    )
    allowlist = (
        F1_POST_F0L_ALLOWLIST if active_slice == "F1" else C2A_POST_F0L_ALLOWLIST
    )
    changed = _changed_paths(repo, base_head)
    _require_changed_path_contract(
        active_slice=active_slice,
        changed=changed,
        allowlist=allowlist,
        exact_changed_paths=True,
    )
    repository_contract = _require_successor_repository_contract(
        repo,
        active_slice=active_slice,
        base_head=base_head,
    )
    _require_successor_test_topology(repo, active_slice=active_slice)
    workflow_source = (
        repo / ".github/workflows/conflict-analysis.yml"
    ).read_text(encoding="utf-8")
    _require_successor_workflow_contract(workflow_source)
    delivery_head = _require_exact_object_id(
        f"{active_slice} delivery HEAD",
        _git(repo, "rev-parse", "HEAD"),
    )
    delivery_tree = _require_exact_object_id(
        f"{active_slice} delivery TREE",
        _git(repo, "rev-parse", "HEAD^{tree}"),
    )
    evidence = _require_successor_ci_evidence(
        evidence_dir,
        repo=repo,
        active_slice=active_slice,
        base_head=base_head,
        base_tree=base_tree,
        delivery_head=delivery_head,
        delivery_tree=delivery_tree,
    )
    return {
        "active_slice": active_slice,
        "allowlist_result": "PASS",
        "base_head": base_head,
        "base_tree": base_tree,
        "f0l_accepted_head": accepted_head,
        "f0l_accepted_tree": accepted_tree,
        "delivery_head": delivery_head,
        "delivery_tree": delivery_tree,
        "changed_paths": sorted(changed),
        "delivery_commit_count": commit_count,
        "delivery_parent": delivery_parent,
        "new_paths": repository_contract["new_paths"],
        "existing_base_blobs": repository_contract["existing_base_blobs"],
        "frozen_objects": repository_contract["frozen_objects"],
        "migration_filenames": repository_contract["migration_filenames"],
        "functional_ci_evidence": "PASS",
        "successor_ci_evidence": evidence,
        "inherited_foundation_c0_c1_frozen_by_exact_allowlist": True,
        "merge_commits_absent": True,
        "network_access": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--slice",
        choices=(
            "C0",
            "R0",
            "C1",
            "FD02",
            "FD03",
            "FD06",
            "FD07",
            "F0L",
            "F1",
            "C2A",
        ),
        default="C0",
    )
    parser.add_argument("--base-head", default=PINNED_BASE_HEAD)
    parser.add_argument("--base-tree", default=PINNED_BASE_TREE)
    parser.add_argument("--fd05-accepted-head")
    parser.add_argument("--fd05-accepted-tree")
    parser.add_argument("--f0l-accepted-head")
    parser.add_argument("--f0l-accepted-tree")
    parser.add_argument("--successor-evidence-dir", type=Path)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.self_check:
            result = self_check()
            f0l_result = f0l_self_check()
            result["f0l_marker"] = f0l_result["marker"]
            result["f0l_correction_4_marker"] = f0l_result["correction_4_marker"]
            result["post_f0l_marker"] = f0l_result["downstream_marker"]
            result["positive_slices"] = [
                *result["positive_slices"],
                *f0l_result["positive_slices"],
            ]
            result["negative_cases"] = (
                int(result["negative_cases"]) + int(f0l_result["negative_cases"])
            )
        elif args.slice == "F0L":
            result = verify_f0l(
                _repo_root(args.repo.resolve()),
                base_head=args.base_head,
                base_tree=args.base_tree,
            )
        elif args.slice in {"F1", "C2A"}:
            result = verify_post_f0l(
                _repo_root(args.repo.resolve()),
                active_slice=args.slice,
                base_head=args.base_head,
                base_tree=args.base_tree,
                accepted_head=args.f0l_accepted_head,
                accepted_tree=args.f0l_accepted_tree,
                evidence_dir=args.successor_evidence_dir,
            )
        else:
            result = verify(
                _repo_root(args.repo.resolve()),
                active_slice=args.slice,
                base_head=args.base_head,
                base_tree=args.base_tree,
                fd05_accepted_head=args.fd05_accepted_head,
                fd05_accepted_tree=args.fd05_accepted_tree,
            )
    except VerificationError as exc:
        print(json.dumps({"allowlist_result": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1
    if args.self_check:
        print(result["marker"])
        print(result["c1_marker"])
        print(result["fd02_marker"])
        print(result["fd03_marker"])
        print(result["fd06_marker"])
        print(result["fd07_marker"])
        print(result["f0l_marker"])
        print(result["f0l_correction_4_marker"])
        print(result["post_f0l_marker"])
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
