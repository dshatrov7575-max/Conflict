"""Read-only checks for pilot metadata, not empirical model validation.

Run from any directory with the project's Python (jsonschema is required).
No app imports, network access, database access, historical coding or replay.
Synthetic dates below exercise the contract; they are not Zhanaozen facts.
"""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import unittest
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker, ValidationError


ROOT = Path(__file__).resolve().parents[2]
SCIENTIFIC = ROOT / "docs/scientific"
SCHEMA = json.loads((SCIENTIFIC / "EMPIRICAL_VALIDATION_SCHEMA.json").read_text(encoding="utf-8"))
TEMPLATE = json.loads((SCIENTIFIC / "ZHANAOZEN_2011_VALIDATION_TEMPLATE.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
DATE_VALIDATOR = Draft202012Validator(SCHEMA["$defs"]["date"], format_checker=FormatChecker())
REFERENCES = (
    "evidence_package_reference", "case_mapping_reference", "factor_mapping_reference",
    "historical_assessment_reference", "observed_outcome_reference",
)


def validate_structure(pilot):
    """Validate JSON shape and cross-field dates; no readiness claim."""
    VALIDATOR.validate(pilot)
    if pilot["status"] == "STRUCTURE_ONLY":
        return
    start = pilot["event_period"]["start_date"]
    end = pilot["event_period"]["end_date"]
    if start > end:
        raise ValueError("Reversed event_period")
    if pilot["information_cutoff_date"] >= start:
        raise ValueError("Cutoff must strictly precede the event window")


def check_input_dates(pilot, availability_dates):
    """Check supplied source-version availability dates, not their veracity.

    These must be supported dates for the exact versions used, not dates of
    described events, file creation or an unverified publication timestamp.
    The caller must separately establish complete coverage and provenance.
    """
    validate_structure(pilot)
    if pilot["status"] == "STRUCTURE_ONLY":
        raise ValueError("A structure-only template cannot supply inputs")
    if not availability_dates:
        raise ValueError("Source-version availability is missing")
    for available_on in availability_dates:
        DATE_VALIDATOR.validate(available_on)
        if available_on > pilot["information_cutoff_date"]:
            raise ValueError("Post-cutoff source version cannot be an input")


def resolve_pointer(document, pointer):
    if pointer is None or pointer == "":
        return document
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(document, list):
            if not token.isascii() or not token.isdigit() or str(int(token)) != token:
                raise ValueError("Invalid JSON Pointer array index")
            document = document[int(token)]
        else:
            document = document[token]
    return document


def check_local_references(pilot):
    """Verify repository references; explicitly return unverified remote URLs.

    Remote existence is checked separately through an authenticated connector.
    A successful local check is never evidence of remote availability/hashes.
    """
    validate_structure(pilot)
    remote = []
    for field in REFERENCES:
        artifact = pilot[field]
        if artifact is None:
            continue
        ref = artifact["reference"]
        url = urlsplit(ref)
        if url.scheme:
            if url.scheme != "https" or not url.netloc:
                raise ValueError("Only HTTPS remote references are supported")
            remote.append(ref)
            continue
        path = (ROOT / ref).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise ValueError("Repository artifact does not exist within the repository")
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != artifact["sha256"]:
            raise ValueError("Repository artifact SHA-256 mismatch or missing pin")
        if path.suffix == ".json":
            document = json.loads(raw)
            structure_only = document.get("document_kind") == "STRUCTURE_ONLY" or document.get("record_kind") == "TEMPLATE"
            if structure_only and artifact["artifact_kind"] != "STRUCTURE_ONLY":
                raise ValueError("A template cannot be relabelled as data")
            selected = resolve_pointer(document, artifact["json_pointer"])
            if field == "case_mapping_reference" and selected.get("case_id") != pilot["case_id"]:
                raise ValueError("Pilot case_id does not match the referenced case")
        elif artifact["json_pointer"] is not None:
            raise ValueError("JSON Pointer requires a JSON artifact")
    return remote


def synthetic_preparation():
    """In-memory shape fixture only; never resolves these synthetic artifacts."""
    pilot = deepcopy(TEMPLATE)
    pilot.update(pilot_id="SYNTHETIC_PILOT", case_id="SYNTHETIC_CASE", country="SYNTHETIC",
                 status="PREPARATION", information_cutoff_date="2000-01-09",
                 event_period={"start_date": "2000-01-10", "end_date": "2000-01-12"})
    for field in REFERENCES[:3]:
        pilot[field] = {"reference": "synthetic-fixture.json", "sha256": "0" * 64,
                        "artifact_kind": "DATA", "json_pointer": None}
    return pilot


class PilotContractChecks(unittest.TestCase):
    def test_schema_and_template(self):
        Draft202012Validator.check_schema(SCHEMA)
        validate_structure(TEMPLATE)

    def test_template_is_unfilled(self):
        self.assertEqual(TEMPLATE["pilot_id"], "ZHANAOZEN_2011_VALIDATION_PILOT")
        for field in ("country", "information_cutoff_date", "historical_assessment_reference", "observed_outcome_reference"):
            self.assertIsNone(TEMPLATE[field])
        self.assertEqual(TEMPLATE["event_period"], {"start_date": None, "end_date": None})
        self.assertEqual(TEMPLATE["status"], "STRUCTURE_ONLY")

    def test_every_field_is_required(self):
        for field in SCHEMA["required"]:
            with self.subTest(field=field):
                pilot = deepcopy(TEMPLATE)
                del pilot[field]
                with self.assertRaises(ValidationError):
                    validate_structure(pilot)

    def test_cutoff_required_for_preparation(self):
        for cutoff in (None, "", "2011-02-30", "09/01/2000", "2000-1-9", "2000-01-09T00:00:00Z"):
            with self.subTest(cutoff=cutoff):
                pilot = synthetic_preparation()
                pilot["information_cutoff_date"] = cutoff
                with self.assertRaises(ValidationError):
                    validate_structure(pilot)

    def test_cutoff_before_event_and_no_reversed_period(self):
        for start, end, cutoff in (("2000-01-10", "2000-01-12", "2000-01-10"),
                                   ("2000-01-10", "2000-01-12", "2000-01-11"),
                                   ("2000-01-10", "2000-01-12", "2000-01-13"),
                                   ("2000-01-12", "2000-01-10", "2000-01-09")):
            with self.subTest(start=start, end=end, cutoff=cutoff):
                pilot = synthetic_preparation()
                pilot.update(event_period={"start_date": start, "end_date": end}, information_cutoff_date=cutoff)
                with self.assertRaises(ValueError):
                    validate_structure(pilot)

    def test_input_date_boundaries(self):
        pilot = synthetic_preparation()
        check_input_dates(pilot, ["1999-12-31", "2000-01-09"])
        for dates in ([], [None], ["2000-02-30"], ["2000-01-10"], ["2000-01-13"], ["1999-12-31", "2000-01-13"]):
            with self.subTest(dates=dates), self.assertRaises((ValueError, ValidationError)):
                check_input_dates(pilot, dates)
        # Even before the event, an input after an earlier cutoff is forbidden.
        pilot["information_cutoff_date"] = "2000-01-08"
        with self.assertRaises(ValueError):
            check_input_dates(pilot, ["2000-01-09"])

    def test_template_cannot_supply_inputs_or_accept_empirical_fields(self):
        with self.assertRaises(ValueError):
            check_input_dates(TEMPLATE, ["2000-01-01"])
        for field, value in (("country", "SYNTHETIC"), ("information_cutoff_date", "2000-01-09"),
                             ("event_period", {"start_date": "2000-01-10", "end_date": "2000-01-12"}),
                             ("historical_assessment_reference", synthetic_preparation()["evidence_package_reference"]),
                             ("observed_outcome_reference", synthetic_preparation()["evidence_package_reference"])):
            with self.subTest(field=field):
                pilot = deepcopy(TEMPLATE)
                pilot[field] = value
                with self.assertRaises(ValidationError):
                    validate_structure(pilot)

    def test_no_results_weights_or_validation_claim(self):
        for field in ("UNO", "weights", "rating", "forecast", "country_score", "calculated_result", "factor_values"):
            with self.subTest(field=field):
                pilot = deepcopy(TEMPLATE)
                pilot[field] = 1
                with self.assertRaises(ValidationError):
                    validate_structure(pilot)
        for status in ("VALIDATED", "PARTIAL", "COMPLETE"):
            pilot = deepcopy(TEMPLATE)
            pilot["status"] = status
            with self.assertRaises(ValidationError):
                validate_structure(pilot)

    def test_preparation_requires_pinned_data_and_complete_dates(self):
        for field in REFERENCES[:3]:
            for attr, value in (("sha256", None), ("artifact_kind", "STRUCTURE_ONLY")):
                pilot = synthetic_preparation()
                pilot[field][attr] = value
                with self.subTest(field=field, attr=attr), self.assertRaises(ValidationError):
                    validate_structure(pilot)
        for boundary in ("start_date", "end_date"):
            pilot = synthetic_preparation()
            pilot["event_period"][boundary] = None
            with self.assertRaises(ValidationError):
                validate_structure(pilot)

    def test_local_hashes_pointers_and_case_identity(self):
        remote = check_local_references(TEMPLATE)
        self.assertEqual(remote, [TEMPLATE["evidence_package_reference"]["reference"]])
        for attr, value in (("reference", "docs/scientific/DOES_NOT_EXIST.json"),
                            ("reference", "../outside-repository.json"),
                            ("sha256", "0" * 64), ("json_pointer", "/cases/99"),
                            ("json_pointer", "/cases/-1"), ("json_pointer", "/missing"),
                            ("artifact_kind", "DATA")):
            pilot = deepcopy(TEMPLATE)
            pilot["case_mapping_reference"][attr] = value
            with self.subTest(attr=attr, value=value), self.assertRaises((ValueError, IndexError, KeyError)):
                check_local_references(pilot)
        pilot = deepcopy(TEMPLATE)
        pilot["case_id"] = "WRONG_CASE"
        with self.assertRaises(ValueError):
            check_local_references(pilot)

    def test_reference_shape_and_limitations(self):
        for field, value in (("limitations", []), ("case_id", " "), ("evidence_package_reference", None)):
            pilot = deepcopy(TEMPLATE)
            pilot[field] = value
            with self.subTest(field=field), self.assertRaises(ValidationError):
                validate_structure(pilot)
        for attr, value in (("sha256", "not-a-hash"), ("json_pointer", "cases/0"), ("json_pointer", "/bad~2escape"), ("weight", 1)):
            pilot = deepcopy(TEMPLATE)
            pilot["case_mapping_reference"][attr] = value
            with self.subTest(attr=attr), self.assertRaises(ValidationError):
                validate_structure(pilot)

    def test_synthetic_positive_shapes(self):
        pilot = synthetic_preparation()
        validate_structure(pilot)
        pilot["event_period"]["end_date"] = pilot["event_period"]["start_date"]
        validate_structure(pilot)
        pilot["historical_assessment_reference"] = deepcopy(pilot["evidence_package_reference"])
        pilot["observed_outcome_reference"] = deepcopy(pilot["evidence_package_reference"])
        validate_structure(pilot)


if __name__ == "__main__":
    unittest.main(verbosity=2)
