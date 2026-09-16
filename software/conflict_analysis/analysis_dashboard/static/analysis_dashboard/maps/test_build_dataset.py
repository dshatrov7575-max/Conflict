"""Regression tests for the real-source builder failures and source boundary."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import BUILD_NATURAL_EARTH_R1 as builder
import build_dataset as runtime


class NaturalEarthBuilderTests(unittest.TestCase):
    def test_duplicate_ISO_codes_preserve_both_distinct_NE_IDs_and_geometry(self):
        geometry={"type":"Polygon","coordinates":[[[76,43],[77,43],[77,44],[76,43]]]}
        features=[{"type":"Feature","geometry":copy.deepcopy(geometry),"properties":{
            "ADM0_A3":"KAZ","ISO_3166_2":"KZ-ALA","NE_ID":identity,
            "ADM1_CODE":code,"NAME":name,"NAME_RU":ru}}
            for identity,code,name,ru in ((1159314735,"KAZ-3207","Almaty","Алматинская область"),
                                         (1159315881,"KAZ-4829","Almaty City","Алма-Ата"))]
        result=builder.build_admin1(features)["features"]
        self.assertEqual({f["id"] for f in result},{"1159314735","1159315881"})
        self.assertEqual(len(result),2)
        self.assertTrue(all(f["geometry"]==geometry for f in result))
        self.assertTrue(all(f["properties"]["iso_3166_2"]=="KZ-ALA" for f in result))

    def test_NAME_RU_precedes_overrides_and_missing_Russian_uses_fallback(self):
        self.assertEqual(builder.name_fields({"NAME":"Astana","NAME_RU":"Нур-Султан"},override="Астана")[1],"Нур-Султан")
        self.assertEqual(builder.name_fields({"NAME":"Astana"},override="Астана")[1],"Астана")

    def test_non_geographic_CRS_duplicate_keys_and_non_finite_numbers_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'input.json'
            for raw in ('{"type":"FeatureCollection","type":"FeatureCollection"}', '{"value":NaN}'):
                path.write_bytes(raw.encode())
                with self.assertRaises(builder.BuildError):builder.load_json(path)
            path.write_text(json.dumps({"type":"FeatureCollection","features":[],"crs":{"type":"name","properties":{"name":"EPSG:3857"}}}),encoding='utf8')
            with self.assertRaises(builder.BuildError):builder.feature_collection(path)

    def test_all_disputed_classifications_are_preserved(self):
        source={"NE_ID":1,"FEATURECLA":"Claim boundary","NAME":"Test","NOTE":"Claim",
                "FCLASS_RU":"Claim boundary","FCLASS_US":"Disputed","FCLASS_CN":"Reference"}
        geometry={"type":"LineString","coordinates":[[50,40],[51,41]]}
        row=builder.build_disputed([{"properties":source,"geometry":geometry}],(35,30,100,61))["features"][0]
        self.assertEqual(row["geometry"],geometry)
        for key in ("FCLASS_RU","FCLASS_US","FCLASS_CN"):self.assertEqual(row["properties"][key],source[key])

    def test_modified_raw_cache_is_rejected_before_transformation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);rows=[]
            for index in range(5):
                path=f'fixture-{index}.json';raw=b'{}\n';(root/path).write_bytes(raw)
                rows.append({"path":path,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"license":"Public Domain",
                             "url":f'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{runtime.COMMIT}/{path}'})
            lock={"source_commit":runtime.COMMIT,"sources":rows}
            with patch.object(runtime.builder,'load_json',return_value=lock):
                runtime.raw_sources(root,True)
                (root/rows[0]['path']).write_bytes(b'[]\n')
                with self.assertRaises(builder.BuildError):runtime.raw_sources(root,True)

    def test_generated_text_is_LF_and_two_builds_are_identical(self):
        lock=builder.load_json(builder.SOURCE_LOCK_PATH)
        overrides=builder.load_json(builder.LABEL_OVERRIDES_PATH)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);raw=root/'raw';builder.synthetic_raw(raw,lock)
            hashes=[]
            for name in ('one','two'):
                hashes.append(builder.assemble(source_lock=lock,overrides=overrides,raw_dir=raw,output_dir=root/name,offline=True))
                for filename in ('BOUNDARY_POLICY_RU.md','DATASET_LICENSES_RU.md','MAP_DATASET_MANIFEST.json.sha256'):
                    self.assertNotIn(b'\r\n',(root/name/filename).read_bytes())
            self.assertEqual(hashes[0],hashes[1])


if __name__=='__main__':unittest.main(verbosity=2)
