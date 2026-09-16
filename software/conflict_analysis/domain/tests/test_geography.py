"""Executable geography oracles. Browser/wheel oracles run in the R1 CI job."""
import json
import os
from pathlib import Path
from uuid import uuid4

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "conflict_analysis.settings")
    import django
    django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import Client, TestCase, TransactionTestCase

from domain.models import GeographicArea, Project, ProjectLocationHead, ProjectLocationRevision, _canonical_geography_write
from domain.services.analysis_admission import analysis_reader_group_name, analysis_location_editor_group_name
from domain.services.project_definitions import project_access_group_name
from domain.services import geography as geo


def body(**changes):
    return dict(latitude="43.337", longitude="52.8619", location_kind="POINT", uncertainty_radius_m=0,
                area_id=None, label="Жанаозен", source_kind="MANUAL_COORDINATES", source_reference="test",
                rationale="Примерная локализация для проверки", supersedes_id=None,
                boundary_dataset_code=geo.DATASET, boundary_dataset_version=geo.VERSION,
                boundary_policy_version=geo.POLICY, **changes) if not changes else {**body(), **changes}


def fixture(suffix="test"):
    project = Project.objects.create(code=f"GEO-{suffix}", name="Geography test", primary_language_tag="ru", primary_language_assignment="EXPLICIT")
    user = get_user_model().objects.create_user(username=f"geo-{suffix}")
    groups = []
    for name in (project_access_group_name(project.pk), analysis_reader_group_name(project.pk), analysis_location_editor_group_name(project.pk)):
        group = Group.objects.create(name=name)
        user.groups.add(group)
        groups.append(group)
    geo.install_pinned_geographic_areas()
    return project, user, groups


class GeographyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.project, cls.user, cls.groups = fixture()

    def current(self):
        return geo.read_project_location(user=self.user, project_id=self.project.pk)

    def write(self, data=None, op=None, etag=None, **kwargs):
        return geo.create_project_location_revision(user=self.user, project_id=self.project.pk,
            body=data or body(), operation_id=str(op or uuid4()),
            if_match=etag or f'"{self.current()["etag_sha256"]}"', **kwargs)

    def test_GEO_01_through_08_numeric_oracles(self):
        vectors = json.loads((Path(__file__).parent / "fixtures/geography_v1_vectors.json").read_text(encoding="utf8"))["oracles"][:8]
        for vector in vectors:
            with self.subTest(oracle=vector["id"]):
                data = body(**vector["input"])
                if vector["expected"].get("accepted"):
                    geo.validate_body(data)
                    current = self.current()["head"]
                    data["supersedes_id"] = current["id"] if current else None
                    saved, replayed = self.write(data)
                    self.assertFalse(replayed)
                    self.assertEqual(saved["head"]["latitude"], geo.decimal_string(geo.Decimal(str(data["latitude"]))))
                else:
                    with self.assertRaises(geo.GeographyError) as caught:
                        geo.validate_body(data)
                    self.assertEqual((caught.exception.code, caught.exception.status), (vector["expected"]["code"], vector["expected"]["http"]))

    def test_GEO_09_10_28_29_lineage_and_order(self):
        first, _ = self.write()
        second, _ = self.write(body(supersedes_id=first["head"]["id"], latitude="44"))
        third, _ = self.write(body(supersedes_id=second["head"]["id"], latitude="45"))
        self.assertEqual(ProjectLocationRevision.objects.count(), 3)
        self.assertEqual(ProjectLocationHead.objects.count(), 1)
        self.assertEqual(self.current()["head"], third["head"])
        history = geo.read_project_location_history(user=self.user, project_id=self.project.pk)
        self.assertEqual([r["id"] for r in history["revisions"]], [third["head"]["id"], second["head"]["id"], first["head"]["id"]])
        other, user, _ = fixture("other")
        initial = geo.read_project_location(user=user, project_id=other.pk)
        with self.assertRaises(geo.GeographyError) as caught:
            geo.create_project_location_revision(user=user, project_id=other.pk, body=body(supersedes_id=first["head"]["id"]), operation_id=str(uuid4()), if_match=f'"{initial["etag_sha256"]}"')
        self.assertEqual(caught.exception.code, "GEOGRAPHY_INTEGRITY_CONFLICT")

    def test_GEO_11_12_immutable_instance_bulk_raw_SQL_and_head_authority(self):
        self.write()
        row = ProjectLocationRevision.objects.get()
        for operation in (lambda: row.save(), lambda: row.delete(),
                          lambda: ProjectLocationRevision.objects.update(label="rewrite"),
                          lambda: ProjectLocationRevision.objects.all().delete(),
                          lambda: ProjectLocationRevision.objects.bulk_update([row], ["label"]),
                          lambda: ProjectLocationHead.objects.update(etag_sha256="0" * 64),
                          lambda: ProjectLocationHead.objects.get().save(),
                          lambda: GeographicArea.objects.update(name_ru="rewrite")):
            with self.assertRaises(ValidationError):
                operation()
        for sql in ("UPDATE domain_projectlocationrevision SET label='changed'", "DELETE FROM domain_projectlocationrevision", "UPDATE domain_geographicarea SET name_ru='changed'", "DELETE FROM domain_projectlocationhead"):
            with self.assertRaises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql)
        self.assertEqual(ProjectLocationRevision.objects.get().label, "Жанаозен")

    def test_GEO_14_15_16_stale_and_exact_replay(self):
        etag = f'"{self.current()["etag_sha256"]}"'
        op = uuid4()
        first, replayed = self.write(op=op, etag=etag)
        self.assertFalse(replayed)
        same, replayed = self.write(op=op, etag=etag)
        self.assertTrue(replayed)
        self.assertEqual(geo.canonical_bytes(same), geo.canonical_bytes(first))
        for args, code in ((dict(etag=etag), "GEOGRAPHY_ETAG_CONFLICT"), (dict(data=body(label="other"), op=op, etag=etag), "GEOGRAPHY_OPERATION_CONFLICT")):
            with self.assertRaises(geo.GeographyError) as caught:
                self.write(**args)
            self.assertEqual(caught.exception.code, code)
        self.assertEqual(ProjectLocationRevision.objects.count(), 1)

    def test_GEO_17_18_19_20_authorization_first_and_zero_permissions(self):
        client = Client()
        url = f"/api/foundation/geography/v1/projects/{self.project.pk}/"
        self.assertEqual(client.get(url + "location/").status_code, 401)
        client.force_login(self.user)
        self.user.groups.remove(self.groups[1])
        hidden = client.post(url + "location-revisions/", "not json", content_type="application/json")
        missing = client.post(f"/api/foundation/geography/v1/projects/{uuid4()}/location-revisions/", "not json", content_type="application/json")
        self.assertEqual((hidden.status_code, hidden.content), (missing.status_code, missing.content))
        self.assertEqual(hidden.status_code, 404)
        self.user.groups.add(self.groups[1]); self.user.groups.remove(self.groups[2])
        payload = client.get(url + "location/")
        self.assertEqual(payload.status_code, 200)
        self.assertFalse(payload.json()["can_edit"])
        self.assertEqual(client.post(url + "location-revisions/", "{}", content_type="application/json").status_code, 403)
        self.assertFalse(self.groups[2].permissions.exists())
        self.assertFalse(self.user.user_permissions.exists())
        self.user.groups.add(self.groups[2])
        self.groups[2].permissions.add(Permission.objects.first())
        self.assertFalse(self.current()["can_edit"])

    def test_GEO_21_22_pins_and_parent(self):
        with self.assertRaises(geo.GeographyError):
            self.write(body(boundary_dataset_version="unknown"))
        parent = GeographicArea.objects.get(feature_id="KAZ")
        with self.assertRaises(ValidationError), _canonical_geography_write():
            GeographicArea.objects.create(code="OTHER", dataset_code="OTHER", dataset_version="1", feature_id="child", area_level="ADM1", name_ru="Область", iso_alpha2="KZ", parent=parent, boundary_policy_version=geo.POLICY)
        geo.install_pinned_geographic_areas()
        self.assertEqual(GeographicArea.objects.count(), 2)
        result, _ = self.write(body(area_id=str(geo.area_id(geo.CATALOG[1][0]))))
        self.assertEqual(result["head"]["area"]["name_ru"], "Мангистауская область")

    def test_catalog_matches_derived_Natural_Earth_identity_and_preserves_old_versions(self):
        from importlib.resources import files
        from uuid import uuid5, NAMESPACE_URL
        maps=files("analysis_dashboard").joinpath("static/analysis_dashboard/maps")
        adm1=json.loads(maps.joinpath("kazakhstan_admin1.geojson").read_text(encoding="utf8"))
        mangystau=[f for f in adm1["features"] if f["properties"]["iso_3166_2"]=="KZ-MAN"]
        self.assertEqual(len(mangystau),1)
        feature=mangystau[0]
        self.assertEqual(feature["id"],feature["properties"]["ne_id"])
        self.assertEqual(feature["id"],geo.CATALOG[1][0])
        self.assertEqual(feature["properties"]["adm1_code"],"KAZ-3236")
        area=GeographicArea.objects.get(feature_id=feature["id"])
        self.assertEqual(area.metadata["source"],"Natural Earth")
        self.assertEqual(area.metadata["source_commit"],"f1890d9f152c896d250a77557a5751a93d494776")
        self.assertEqual(area.metadata["license"],"Public Domain")
        self.assertEqual(area.dataset_version,"1.0.1")
        with _canonical_geography_write():
            legacy=GeographicArea.objects.create(id=uuid5(NAMESPACE_URL,f"{geo.DATASET}:1.0.0:KAZ"),
                code="GEO-KAZ",version="1.0.0",dataset_code=geo.DATASET,dataset_version="1.0.0",
                feature_id="KAZ",area_level="ADM0",name_ru="Казахстан",name_local="Kazakhstan",
                iso_alpha2="KZ",boundary_policy_version=geo.POLICY,metadata={"source":"retired fixture"})
        before=legacy.metadata.copy()
        geo.install_pinned_geographic_areas()
        legacy.refresh_from_db()
        self.assertEqual(legacy.metadata,before)
        self.assertEqual(GeographicArea.objects.count(),3)
        with self.assertRaises(geo.GeographyError):
            self.write(body(area_id=str(legacy.pk)))

    def test_strict_HTTP_CSRF_headers_bytes_history_and_no_mutation_routes(self):
        client = Client(enforce_csrf_checks=True); client.force_login(self.user)
        url = f"/api/foundation/geography/v1/projects/{self.project.pk}/"
        current = client.get(url + "location/")
        self.assertEqual(current.status_code, 200)
        headers = {"HTTP_IF_MATCH": current["ETag"], "HTTP_X_OPERATION_ID": str(uuid4())}
        post = lambda raw, extra: client.post(url + "location-revisions/", raw, content_type="application/json", **extra)
        self.assertEqual(post(json.dumps(body()), headers).status_code, 403)
        headers["HTTP_X_CSRFTOKEN"] = client.cookies["csrftoken"].value
        duplicate = json.dumps(body())[:-1] + ',"latitude":0}'
        for raw in (duplicate, json.dumps({**body(), "actor_identifier": "spoof"}), "NaN", "[]"):
            self.assertEqual(post(raw, headers).status_code, 400)
        accepted = post(json.dumps(body()), headers)
        self.assertEqual(accepted.status_code, 201, accepted.content)
        self.assertEqual(accepted["Content-Length"], str(len(accepted.content)))
        self.assertEqual(accepted["Cache-Control"], "no-store")
        self.assertEqual(geo.canonical_bytes(accepted.json()), accepted.content)
        self.assertEqual(post(json.dumps(body()), headers).content, accepted.content)
        for method in (client.patch, client.delete):
            self.assertEqual(method(url + "location-revisions/").status_code, 405)
        for query in ("?limit=0", "?limit=101", "?limit=1&limit=2", "?limit=x"):
            self.assertEqual(client.get(url + "location-history/" + query).status_code, 400)
        self.assertEqual(client.get(url + "location-history/?limit=1").status_code, 200)

    def test_extreme_values_and_atomic_rollback(self):
        for changes in (dict(latitude=True), dict(latitude="1e999"), dict(latitude="0.00000001"), dict(longitude=-180.00001), dict(uncertainty_radius_m=20000001), dict(uncertainty_radius_m=True), dict(rationale="  "), dict(location_kind="REGION", uncertainty_radius_m=None)):
            with self.subTest(changes=changes), self.assertRaises(geo.GeographyError):
                self.write(body(**changes))
        from unittest.mock import patch
        with patch.object(ProjectLocationHead, "save", side_effect=ValidationError("failure")), self.assertRaises(geo.GeographyError):
            self.write()
        self.assertEqual(ProjectLocationRevision.objects.count(), 0)
        self.write(body(latitude="-0", longitude=180, uncertainty_radius_m=20000000))
        self.assertEqual(self.current()["head"]["latitude"], "0")

    def test_GEO_38_method_state_unchanged(self):
        self.assertEqual(self.current()["method_state"], {"project_total_score": "METHOD_NOT_APPROVED", "regional_aggregate": "METHOD_NOT_APPROVED"})

    def test_history_follows_lineage_even_when_recorded_timestamps_tie(self):
        from datetime import datetime, timezone
        from unittest.mock import patch
        ids=[]
        with patch("django.utils.timezone.now", return_value=datetime(2026,9,16,12,tzinfo=timezone.utc)):
            for index in range(3):
                saved,_=self.write(body(latitude=str(index),supersedes_id=ids[-1] if ids else None))
                ids.append(saved["head"]["id"])
        snapshot=geo.read_project_location_history(user=self.user,project_id=self.project.pk,limit=2)
        self.assertEqual([r["id"] for r in snapshot["revisions"]],list(reversed(ids))[:2])
        self.assertTrue(snapshot["has_more"])


class GeographyMigrationTests(TransactionTestCase):
    def test_empty_reverse_and_forward_preserve_existing_schema(self):
        from django.db.migrations.executor import MigrationExecutor
        executor=MigrationExecutor(connection)
        try:
            executor.migrate([("domain","0018_workspace_assessment_projection")])
            self.assertNotIn("domain_projectlocationrevision", connection.introspection.table_names())
            self.assertIn("domain_projectworkspace", connection.introspection.table_names())
        finally:
            executor=MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
        self.assertIn("domain_projectlocationrevision", connection.introspection.table_names())


def race_gate():
    """Committed multi-connection race in a dedicated gate DB, on both engines."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from django.db import close_old_connections, connections
    project, user, _ = fixture("race-" + uuid4().hex[:8])
    initial = geo.read_project_location(user=user, project_id=project.pk)
    root, _ = geo.create_project_location_revision(user=user, project_id=project.pk, body=body(), if_match=f'"{initial["etag_sha256"]}"', operation_id=str(uuid4()))
    barrier = threading.Barrier(2)
    def writer(index):
        close_old_connections()
        try:
            actor = get_user_model().objects.get(pk=user.pk)
            barrier.wait(timeout=20)
            geo.create_project_location_revision(user=actor, project_id=project.pk,
                body=body(supersedes_id=root["head"]["id"], latitude=str(44+index)),
                if_match=f'"{root["etag_sha256"]}"', operation_id=str(uuid4()))
            return "CREATED"
        except geo.GeographyError as error:
            return error.code
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(writer,range(2)))
    assert sorted(outcomes)==["CREATED","GEOGRAPHY_ETAG_CONFLICT"], outcomes
    assert ProjectLocationHead.objects.filter(project=project).count()==1
    assert ProjectLocationRevision.objects.filter(project=project).count()==2
    assert ProjectLocationRevision.objects.filter(project=project,successor__isnull=True).count()==1
    print(json.dumps({"oracle":"GEO-13","backend":connection.vendor,"result":"PASS","outcomes":outcomes}))


def parity_gate(output):
    from datetime import datetime, timezone
    from unittest.mock import patch
    from uuid import UUID
    project=Project.objects.create(id=UUID("0946b4d3-73f5-4dc4-bc4b-3cb791759121"),code="GEO-PARITY",name="Parity",primary_language_tag="ru",primary_language_assignment="EXPLICIT")
    user=get_user_model().objects.create_user(id=880001,username="geo-parity")
    for name in (project_access_group_name(project.pk),analysis_reader_group_name(project.pk),analysis_location_editor_group_name(project.pk)):
        group=Group.objects.create(name=name);user.groups.add(group)
    geo.install_pinned_geographic_areas()
    initial=geo.read_project_location(user=user,project_id=project.pk)
    with patch("django.utils.timezone.now",return_value=datetime(2026,9,16,12,tzinfo=timezone.utc)):
        geo.create_project_location_revision(user=user,project_id=project.pk,body=body(latitude="0.0000001",longitude="-0.0000001",area_id=str(geo.area_id("KAZ"))),if_match=f'"{initial["etag_sha256"]}"',operation_id="0946b4d3-73f5-4dc4-bc4b-3cb791759122")
    client=Client();client.force_login(user)
    response=client.get(f"/api/foundation/geography/v1/projects/{project.pk}/location/")
    assert response.status_code==200,response.content
    Path(output).write_bytes(response.content)
    print("GEO-37 parity bytes exported",connection.vendor,len(response.content))


def inventory_gate(wheel):
    import hashlib
    from zipfile import ZipFile
    prefix="analysis_dashboard/static/analysis_dashboard/"
    with ZipFile(wheel) as archive:
        assert archive.testzip() is None
        manifest=json.loads(archive.read(prefix+"maps/MAP_DATASET_MANIFEST.json"))
        digest=manifest.pop("manifest_sha256")
        assert geo.sha256(manifest)==digest
        for row in manifest["files"]:
            data=archive.read(prefix+row["path"])
            assert len(data)==row["bytes"] and hashlib.sha256(data).hexdigest()==row["sha256"], row["path"]
        listed={prefix+row["path"] for row in manifest["files"]}
        actual={n for n in archive.namelist() if n.startswith(tuple(prefix+p for p in ("maps/","vendor/maplibre/","licenses/"))) and not n.endswith('/')}
        assert actual-listed=={prefix+"maps/MAP_DATASET_MANIFEST.json",prefix+"maps/MAP_DATASET_MANIFEST.json.sha256"}, actual-listed
        required={"MAPLIBRE_LICENSE.txt","NATURAL_EARTH_TERMS.txt","DATASET_LICENSES_RU.md","BOUNDARY_POLICY_RU.md"}
        assert required<={Path(n).name for n in listed}
        forbidden={"GEOBOUNDARIES_CC_BY_4_0.txt","GEOBOUNDARIES_CITATION.txt","GEOBOUNDARIES_METADATA.json","ODBL_1_0.txt"}
        assert not forbidden & {Path(n).name for n in archive.namelist()}
        assert manifest["source_commit"]=="f1890d9f152c896d250a77557a5751a93d494776"
        assert manifest["source_tag"]=="v5.1.2" and manifest["dataset_version"]==geo.VERSION
        assert all(manifest[flag] is False for flag in ("geoboundaries_used","odbl_data_used","osm_derived_data_used","pmtiles_used"))
        assert len(manifest["raw_sources"])==5
        assert all(len(row["sha256"])==64 and row["bytes"]>0 for row in manifest["raw_sources"])
        assert all(row["license"]=="Public Domain" and f'/{manifest["source_commit"]}/' in row["url"] for row in manifest["raw_sources"])
        actual_geojson={Path(n).name for n in actual if n.endswith('.geojson')}
        assert actual_geojson=={"central_asia_admin0.geojson","central_asia_disputed_lines.geojson","kazakhstan_admin1.geojson","central_asia_places.geojson"}
        adm1=json.loads(archive.read(prefix+'maps/kazakhstan_admin1.geojson'))
        match=[f for f in adm1['features'] if f['properties']['iso_3166_2']=='KZ-MAN']
        assert len(match)==1 and match[0]['id']==geo.CATALOG[1][0]==match[0]['properties']['ne_id']
        print(json.dumps({"oracles":["GEO-35","GEO-36"],"result":"PASS","assets":len(listed)}))


if __name__ == "__main__":
    import sys
    if sys.argv[1]=="--race": race_gate()
    elif sys.argv[1]=="--parity": parity_gate(sys.argv[2])
    elif sys.argv[1]=="--wheel": inventory_gate(sys.argv[2])
    else: raise SystemExit("Unknown gate")
