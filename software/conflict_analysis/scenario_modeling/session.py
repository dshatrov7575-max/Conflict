"""Signed form-carried Scenario Model; no domain or Django-session writes."""
from django.core import signing
from django.utils.crypto import constant_time_compare, salted_hmac

from calculation import CalculationInputError
from player_integration.services import open_experiment

from .model import ScenarioModel

SALT = "scenario_modeling.session.v1"
MAX_TOKEN_LENGTH = 1_000_000
MAX_AGE = 8 * 60 * 60


class ScenarioCapacityError(CalculationInputError):
    """A baseline result remains usable even if it exceeds scenario transport."""


def _owner(request):
    if not request.user.is_authenticated or not request.session.session_key:
        raise CalculationInputError("Scenario requires an authenticated session.")
    return salted_hmac(SALT, f"{request.user.pk}:{request.session.session_key}").hexdigest()


def seal(request, model):
    token = signing.dumps({"owner": _owner(request), "model": model.as_dict()}, salt=SALT)
    if len(token) > MAX_TOKEN_LENGTH:
        raise ScenarioCapacityError("Scenario exceeds the MVP transport limit.")
    return token


def from_result(request, view):
    try:
        return seal(request, ScenarioModel.from_calculation(view.snapshot, view.run))
    except ScenarioCapacityError:
        return None


def restore(request, token):
    if type(token) is not str or not token or len(token) > MAX_TOKEN_LENGTH:
        raise CalculationInputError("Invalid scenario token size.")
    try:
        payload = signing.loads(token, salt=SALT, max_age=MAX_AGE)
        if not constant_time_compare(payload["owner"], _owner(request)):
            raise CalculationInputError("Scenario belongs to another session.")
        model = ScenarioModel.from_dict(payload["model"])
    except (signing.BadSignature, KeyError, TypeError, ValueError) as exc:
        raise CalculationInputError("Invalid or expired scenario session.") from exc
    # Re-admit on every request, including replay after corrections/freeze/archive.
    # Never capture a fresh baseline here or read values from another lane.
    experiment = open_experiment(user=request.user, experiment_id=model.baseline.experiment_id)
    if (str(experiment.assessment_set_id), str(experiment.workspace_id),
        str(experiment.workspace.project_id)) != (
        model.baseline.assessment_set_id, model.baseline.workspace_id, model.baseline.project_id,
    ):
        raise CalculationInputError("Scenario baseline scope mismatch.")
    return model, experiment
