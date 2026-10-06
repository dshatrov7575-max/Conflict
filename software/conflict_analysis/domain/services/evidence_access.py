"""Authorization-first discovery of Facts linked to one exact assessment entry.

The service is deliberately read-only.  It admits Project, Workspace and entry
identity before a relation to a Fact is queried, applies Fact visibility in the
database, and only then projects the small DTO consumed by Player.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from django.db.models import F, Q
from django.http import Http404

from domain.services.project_definitions import project_access_group_name


VISIBILITY_WORKSPACE_SHARED = "WORKSPACE_SHARED"
VISIBILITY_OWNER_ONLY = "OWNER_ONLY"
VISIBILITY_EXPERIMENT_PRIVATE = "EXPERIMENT_PRIVATE"


@dataclass(frozen=True, slots=True)
class AccessibleFactList:
    """Deterministic disclosure result for one already-admitted entry."""

    entry_kind: str
    entry_id: str
    facts: tuple[Mapping[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": "ACCESSIBLE_FACTS" if self.facts else "NO_ACCESSIBLE_FACT_EVIDENCE",
            "entry": {"kind": self.entry_kind, "id": self.entry_id},
            "facts": [dict(item) for item in self.facts],
        }


def _models() -> Any:
    from domain import models as domain_models

    return domain_models


def has_project_access(user: Any, project: Any) -> bool:
    """Use only server-owned identity and Project-group membership."""

    if not bool(getattr(user, "is_authenticated", False)):
        return False
    if bool(getattr(user, "is_superuser", False)):
        return True
    groups = getattr(user, "groups", None)
    return bool(
        groups is not None
        and groups.filter(name=project_access_group_name(project.pk)).exists()
    )


def private_fact_access(user: Any, fact: Any) -> bool:
    """Private Fact access is exact persisted author identity equality."""

    if bool(getattr(user, "is_superuser", False)):
        return True
    if not bool(getattr(user, "is_authenticated", False)):
        return False
    user_id = getattr(user, "pk", None)
    return user_id is not None and fact.coder_identifier == f"django-user:{user_id}"


def fact_visible_or_404(user: Any, fact: Any) -> None:
    """Apply the single Fact-visibility authority used by every read seam."""

    if fact.visibility == VISIBILITY_WORKSPACE_SHARED:
        return
    if fact.visibility in (VISIBILITY_OWNER_ONLY, VISIBILITY_EXPERIMENT_PRIVATE):
        if private_fact_access(user, fact):
            return
    raise Http404()


def project_or_404(user: Any, project_id: object) -> Any:
    models = _models()
    try:
        project = models.Project.objects.get(pk=project_id)
    except (models.Project.DoesNotExist, ValueError, TypeError) as exc:
        raise Http404() from exc
    if not has_project_access(user, project):
        raise Http404()
    return project


def workspace_or_404(project: Any, workspace_id: object) -> Any:
    models = _models()
    try:
        return models.ProjectWorkspace.objects.get(pk=workspace_id, project=project)
    except (models.ProjectWorkspace.DoesNotExist, ValueError, TypeError) as exc:
        raise Http404() from exc


def fact_or_404(workspace: Any, fact_id: object) -> Any:
    models = _models()
    try:
        return models.Fact.objects.get(pk=fact_id, workspace=workspace)
    except (models.Fact.DoesNotExist, ValueError, TypeError) as exc:
        raise Http404() from exc


def _parameter_value_or_404(project: Any, workspace: Any, entry_id: object) -> Any:
    """Admit an exact value and its G8 assessment lane before link access."""

    models = _models()
    try:
        return models.ParameterValue.objects.select_related(
            "assessment_set__experiment", "actor_element_assessment"
        ).get(
            pk=entry_id,
            project=project,
            workspace=workspace,
            assessment_set__project=project,
            assessment_set__workspace=workspace,
            assessment_set__experiment__workspace=workspace,
        )
    except (models.ParameterValue.DoesNotExist, ValueError, TypeError) as exc:
        raise Http404() from exc


def _assessment_or_404(project: Any, workspace: Any, entry_id: object) -> Any:
    """Admit an exact assessment and matching Experiment/AssessmentSet lane."""

    models = _models()
    try:
        return models.ActorElementAssessment.objects.select_related(
            "experiment", "assessment_set"
        ).get(
            pk=entry_id,
            workspace=workspace,
            assessment_set__project=project,
            assessment_set__workspace=workspace,
            experiment__workspace=workspace,
            experiment__assessment_set=F("assessment_set"),
        )
    except (models.ActorElementAssessment.DoesNotExist, ValueError, TypeError) as exc:
        raise Http404() from exc


def _visibility_filter(*, user: Any, experiment_id: Any) -> Q:
    """Build the database predicate before any Fact row is projected."""

    if bool(getattr(user, "is_superuser", False)):
        private = Q(fact__visibility=VISIBILITY_OWNER_ONLY)
        experiment_private = Q(
            fact__visibility=VISIBILITY_EXPERIMENT_PRIVATE,
            fact__experiment_id=experiment_id,
        )
    else:
        author = f"django-user:{getattr(user, 'pk', None)}"
        private = Q(
            fact__visibility=VISIBILITY_OWNER_ONLY,
            fact__coder_identifier=author,
        )
        experiment_private = Q(
            fact__visibility=VISIBILITY_EXPERIMENT_PRIVATE,
            fact__coder_identifier=author,
            fact__experiment_id=experiment_id,
        )
    return Q(fact__visibility=VISIBILITY_WORKSPACE_SHARED) | private | experiment_private


def _category_payload(fact: Any) -> dict[str, Any]:
    models = _models()
    assignment = (
        models.FactCategoryAssignment.objects.select_related("category__parent")
        .filter(fact=fact)
        .order_by("code", "pk")
        .first()
    )
    if assignment is None:
        return {
            "assignment_id": None,
            "classification_status": "UNCLASSIFIED",
            "category": None,
            "ancestor_path": [],
            "full_path": "",
        }
    category = assignment.category
    if category is None:
        return {
            "assignment_id": str(assignment.pk),
            "classification_status": assignment.classification_status,
            "category": None,
            "ancestor_path": [],
            "full_path": "",
        }
    path: list[dict[str, str]] = []
    current, seen = category, set()
    while current is not None:
        if current.pk in seen:
            path = []
            break
        seen.add(current.pk)
        path.append({"id": str(current.pk), "code": current.code, "version": current.version})
        current = current.parent
    path.reverse()
    return {
        "assignment_id": str(assignment.pk),
        "classification_status": assignment.classification_status,
        "category": {"id": str(category.pk), "code": category.code, "version": category.version},
        "ancestor_path": path,
        "full_path": "/".join(item["code"] for item in path),
    }


def _relation_payload(link: Any) -> dict[str, Any]:
    return {
        "id": str(link.pk),
        "code": link.code,
        "version": link.version,
        "role": link.role,
        "temporal_status": link.temporal_status,
        "learned_on": link.learned_on.isoformat() if link.learned_on else None,
        "rationale": link.rationale,
    }


def _fact_payload(fact: Any, links: Iterable[Any]) -> dict[str, Any]:
    return {
        "id": str(fact.pk),
        "code": fact.code,
        "version": fact.version,
        "fact_type": fact.fact_type,
        "statement": fact.statement,
        "origin": fact.origin,
        "directness": fact.directness,
        "status": fact.status,
        "temporal_status": fact.temporal_status,
        "category": _category_payload(fact),
        "entry_evidence": [_relation_payload(link) for link in links],
    }


def _list_links(*, user: Any, entry: Any, relation_model: Any, relation_field: str) -> tuple[Mapping[str, Any], ...]:
    experiment_id = entry.experiment_id if relation_field == "assessment" else entry.assessment_set.experiment.pk
    links = list(
        relation_model.objects.select_related("fact")
        .filter(**{relation_field: entry})
        .filter(_visibility_filter(user=user, experiment_id=experiment_id))
        .order_by("fact__code", "fact__pk", "role", "code", "pk")
    )
    grouped: list[dict[str, Any]] = []
    current_id: Any = None
    current_fact: Any = None
    current_links: list[Any] = []
    for link in links:
        if current_id is not None and link.fact_id != current_id:
            grouped.append(_fact_payload(current_fact, current_links))
            current_links = []
        current_id, current_fact = link.fact_id, link.fact
        current_links.append(link)
    if current_id is not None:
        grouped.append(_fact_payload(current_fact, current_links))
    return tuple(grouped)


def parameter_value_facts(*, user: Any, project_id: object, workspace_id: object, entry_id: object) -> AccessibleFactList:
    project = project_or_404(user, project_id)
    workspace = workspace_or_404(project, workspace_id)
    entry = _parameter_value_or_404(project, workspace, entry_id)
    models = _models()
    return AccessibleFactList(
        "parameter-value",
        str(entry.pk),
        _list_links(
            user=user,
            entry=entry,
            relation_model=models.ParameterValueEvidence,
            relation_field="parameter_value",
        ),
    )


def assessment_facts(*, user: Any, project_id: object, workspace_id: object, entry_id: object) -> AccessibleFactList:
    project = project_or_404(user, project_id)
    workspace = workspace_or_404(project, workspace_id)
    entry = _assessment_or_404(project, workspace, entry_id)
    models = _models()
    return AccessibleFactList(
        "actor-element-assessment",
        str(entry.pk),
        _list_links(
            user=user,
            entry=entry,
            relation_model=models.AssessmentEvidence,
            relation_field="assessment",
        ),
    )
