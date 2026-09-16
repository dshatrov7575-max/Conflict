"""Rebuild exact offline assets: Python 3.12, pyshp 2.3.1, Shapely 2.1.2.

python build_dataset.py /path/to/raw-cache
Downloads are a build-time operation only. Runtime never invokes this script.
"""
import hashlib
import json
import sys
import tarfile
import urllib.request
from pathlib import Path

import shapefile
import shapely
from shapely.geometry import box, shape, mapping
from shapely import make_valid, union_all

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent
RAW = Path(sys.argv[1]).resolve()
RAW.mkdir(parents=True, exist_ok=True)
assert shapefile.__version__ == "2.3.1" and shapely.__version__ == "2.1.2"
SOURCES = json.loads((ROOT / "RAW_SOURCES_LOCK.json").read_text(encoding="utf8"))
for source in SOURCES:
    target = RAW / source["name"]
    if not target.exists():
        target.write_bytes(urllib.request.urlopen(source["url"], timeout=120).read())
    assert target.stat().st_size == source["bytes"], target
    assert hashlib.sha256(target.read_bytes()).hexdigest() == source["sha256"], target


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")).encode("utf8")


def write(name, value):
    (ROOT / name).write_bytes(canonical(value))


EXTENT = box(40, 30, 100, 65)
TOLERANCE = 0.01  # degrees; cartographic context, never a survey boundary
labels = []
counts = {}


def label(fid, name, point, kind, dataset, original):
    labels.append(dict(feature_id=fid, name_ru=name, coordinates=point, kind=kind, dataset=dataset, canonical_name=original))


def feature(fid, geom, props):
    if not geom.is_valid:
        geom = make_valid(geom)
    geom = geom.intersection(EXTENT).simplify(TOLERANCE, preserve_topology=True)
    assert geom.is_valid and not geom.is_empty, fid
    return dict(type="Feature", id=fid, properties=dict(feature_id=fid, **props), geometry=mapping(geom))


def collection(name, features):
    features.sort(key=lambda item: str(item["id"]))
    counts[name] = len(features)
    write(name, dict(type="FeatureCollection", features=features))


countries = []
country_lines = []
ru = {"KAZ":"Казахстан", "RUS":"Россия", "CHN":"Китай", "KGZ":"Кыргызстан", "UZB":"Узбекистан", "TKM":"Туркменистан", "MNG":"Монголия", "AZE":"Азербайджан", "IRN":"Иран"}
anchors = {"RUS":[66,59], "CHN":[90,40], "MNG":[95,48], "AZE":[47.6,40.6]}
for row in shapefile.Reader(str(RAW / "ne_10m_admin_0_countries")).iterShapeRecords():
    props = row.record.as_dict(); geom = shape(row.shape.__geo_interface__)
    if not geom.intersects(EXTENT):
        continue
    fid = props["ADM0_A3"]
    name = ru.get(fid) or props.get("NAME_RU") or props["NAME"] or fid
    countries.append(feature(fid, geom, {key: props[key] for key in ("NAME", "BRK_DIFF", "BRK_NAME", "NOTE_ADM0", "NOTE_BRK", "NE_ID", "FCLASS_ISO")} | {"name_ru":name}))
    # Clip the original outline, never the outline of a clipped polygon:
    # the latter would falsely draw our viewport extent as a state border.
    country_lines.append(feature(fid, geom.boundary, {"name_ru":name}))
    point = anchors.get(fid, [props["LABEL_X"], props["LABEL_Y"]])
    if fid in ru:
        label(fid, name, point, "country", "Natural Earth", props["NAME"])
collection("central_asia_admin0.geojson", countries)
collection("central_asia_admin0_lines.geojson", country_lines)

disputed = []
for row in shapefile.Reader(str(RAW / "ne_10m_admin_0_boundary_lines_disputed_areas")).iterShapeRecords():
    props = row.record.as_dict(); geom = shape(row.shape.__geo_interface__)
    if geom.intersects(EXTENT):
        disputed.append(feature(str(props["ne_id"]), geom, props))
assert disputed
collection("central_asia_disputed_lines.geojson", disputed)

regions = []
region_geometries = []
region_names = {"KZ-MAN":"Мангистауская область", "KZ-PAV":"Павлодарская область", "KZ-ZHA":"Жамбылская область", "KZ-KUS":"Костанайская область", "KZ-KAR":"Карагандинская область", "KZ-KZY":"Кызылординская область", "KZ-VOS":"Восточно-Казахстанская область", "KZ-AKT":"Актюбинская область", "KZ-ATY":"Атырауская область", "KZ-YUZ":"Южно-Казахстанская область (2017)", "KZ-AKM":"Акмолинская область", "KZ-ALM":"Алматинская область", "KZ-SEV":"Северо-Казахстанская область", "KZ-ALA":"Алматы", "KZ-ZAP":"Западно-Казахстанская область", "KZ-AST":"Астана"}
for row in json.loads((RAW / "gb-kaz.geojson").read_bytes())["features"]:
    props = row["properties"]; geom = shape(row["geometry"])
    region_geometries.append(make_valid(geom) if not geom.is_valid else geom)
    name = region_names[props["shapeISO"]]; fid = props["shapeID"]
    regions.append(feature(fid, geom, props | {"name_ru":name, "boundary_year":2017}))
    if props["shapeISO"] == "KZ-MAN":
        # Local cartographic label placement only; source geometry is unchanged.
        label(fid, name, [55.7,44.3], "region", "geoBoundaries", props["shapeName"])
collection("kazakhstan_admin1.geojson", regions)
# Only internal ADM1 lines: the outer country outline belongs exclusively to
# Natural Earth, not to a second source's country representation.
internal_lines = union_all([g.boundary for g in region_geometries]).difference(union_all(region_geometries).boundary)
collection("kazakhstan_admin1_lines.geojson", [feature("KAZ-ADM1-internal-2017", internal_lines, {"boundary_year":2017})])

places = []
place_ids = {1159142671:"Жанаозен",1159148679:"Актау",1159150111:"Атырау",1159150965:"Астана",1159150969:"Алматы"}
for row in shapefile.Reader(str(RAW / "ne_10m_populated_places")).iterShapeRecords():
    props = row.record.as_dict()
    if props["NE_ID"] in place_ids:
        fid = str(props["NE_ID"]); name = place_ids[props["NE_ID"]]
        places.append(feature(fid, shape(row.shape.__geo_interface__), {"name_ru":name,"canonical_name":props["NAME"]}))
        label(fid, name, [props["LONGITUDE"],props["LATITUDE"]], "place", "Natural Earth", props["NAME"])
assert len(places) == 5
collection("central_asia_places.geojson", places)

lakes=[]
for row in shapefile.Reader(str(RAW / "ne_10m_geography_marine_polys")).iterShapeRecords():
    props=row.record.as_dict()
    if "caspian" in str(props.get("name", "")).lower():
        fid=str(props["ne_id"]); geom=shape(row.shape.__geo_interface__)
        lakes.append(feature(fid,geom,{"name_ru":"Каспийское море"}))
        point=geom.representative_point()
        label(fid,"Каспийское море",[point.x,point.y],"water","Natural Earth",props["name"])
assert lakes
collection("central_asia_water.geojson",lakes)
write("labels_ru.json",dict(schema="CONFLICT_MAP_LABELS_RU_V1",version="1.0.0",labels=sorted(labels,key=lambda item:item["feature_id"])))

style={"version":8,"name":"Центральная Азия — политические границы", "sources":{}, "layers":[{"id":"background","type":"background","paint":{"background-color":"#dceaf0"}}]}
for name,file in (("admin0","central_asia_admin0.geojson"),("admin0-lines","central_asia_admin0_lines.geojson"),("admin1","kazakhstan_admin1.geojson"),("admin1-lines","kazakhstan_admin1_lines.geojson"),("disputed","central_asia_disputed_lines.geojson"),("places","central_asia_places.geojson"),("water","central_asia_water.geojson")):
    style["sources"][name]={"type":"geojson","data":"/static/analysis_dashboard/maps/"+file}
style["layers"] += [
    {"id":"countries-fill","type":"fill","source":"admin0","paint":{"fill-color":"#edf0e6"}},
    {"id":"water-fill","type":"fill","source":"water","paint":{"fill-color":"#dceaf0"}},
    {"id":"admin0-boundaries","type":"line","source":"admin0-lines","paint":{"line-color":"#394d57","line-width":1.5}},
    {"id":"mangystau-fill","type":"fill","source":"admin1","filter":["==",["get","shapeISO"],"KZ-MAN"],"paint":{"fill-color":"#66988d","fill-opacity":0.2}},
    {"id":"admin1-boundaries","type":"line","source":"admin1-lines","paint":{"line-color":"#667b86","line-width":1,"line-dasharray":[3,2]}},
    {"id":"disputed-halo","type":"line","source":"disputed","paint":{"line-color":"#edf0e6","line-width":5}},
    {"id":"disputed-boundaries","type":"line","source":"disputed","paint":{"line-color":"#7a375c","line-width":2,"line-dasharray":[2,2]}},
    {"id":"places","type":"circle","source":"places","paint":{"circle-radius":3,"circle-color":"#334653"}},
]
write("map_style.json",style)
vendor=STATIC/'vendor/maplibre'; vendor.mkdir(parents=True,exist_ok=True)
with tarfile.open(RAW/'maplibre-gl-5.6.2.tgz') as archive:
    for target,member in (("maplibre-gl-csp.js","dist/maplibre-gl-csp.js"),("maplibre-gl-csp-worker.js","dist/maplibre-gl-csp-worker.js"),("maplibre-gl.css","dist/maplibre-gl.css"),("MAPLIBRE_LICENSE.txt","LICENSE.txt")):
        (vendor/target).write_bytes(archive.extractfile('package/'+member).read())
licenses=STATIC/'licenses';licenses.mkdir(exist_ok=True)
for target,source in (("NATURAL_EARTH_TERMS.txt","ne-terms.txt"),("GEOBOUNDARIES_CC_BY_4_0.txt","cc-by.txt"),("GEOBOUNDARIES_CITATION.txt","gb-citation.txt"),("GEOBOUNDARIES_METADATA.json","gb-metadata.json"),("ODBL_1_0.txt","odbl.txt")):
    (licenses/target).write_bytes((RAW/source).read_bytes())
manifest={"schema":"CONFLICT_MAP_DATASET_MANIFEST_V1","dataset_code":"CA_CENTRAL_ASIA_POLITICAL_V1","dataset_version":"1.0.0","boundary_policy_version":"CA_BOUNDARY_POLICY_V1","built_at":"2026-09-16T00:00:00Z","source_head":"c6c7118080ab1a1dcb86216f4092dabcf8125be7","extent":[40,30,100,65],"crs":"EPSG:4326","simplification_tolerance_degrees":TOLERANCE,"build_tools":{"python":"3.12","pyshp":"2.3.1","shapely":"2.1.2","geos":shapely.geos_version_string},"raw_sources":SOURCES,"feature_counts":counts,"files":[]}
for directory in (ROOT,vendor,licenses):
    for p in sorted(directory.iterdir()):
        if not p.is_file() or p.name.startswith('MAP_DATASET_MANIFEST'):
            continue
        data=p.read_bytes();is_gb=p.name.startswith('kazakhstan')
        manifest['files'].append(dict(path=p.relative_to(STATIC).as_posix(),bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),source='geoBoundaries / OSM / Wambacher' if is_gb else 'Natural Earth / MapLibre / project; see raw_sources',source_version='KAZ-ADM1-16772668 (2017)' if is_gb else 'Natural Earth release 5.1.2; ADM0 5.1.1, disputed 5.1.0; MapLibre 5.6.2',license='ODbL-1.0; geoBoundaries attribution CC-BY-4.0' if is_gb else 'See license snapshots and DATASET_LICENSES_RU.md',transformations=['CRS EPSG:4326 (input verified)','make_valid only when required','clip [40,30,100,65]','simplify 0.01 degree preserve_topology','stable source IDs','versioned Russian labels','canonical JSON'] if p.suffix=='.geojson' else ['exact vendor/license copy or project authored asset']))
manifest['manifest_sha256']=hashlib.sha256(canonical(manifest)).hexdigest()
write('MAP_DATASET_MANIFEST.json',manifest)
(ROOT/'MAP_DATASET_MANIFEST.json.sha256').write_text(hashlib.sha256((ROOT/'MAP_DATASET_MANIFEST.json').read_bytes()).hexdigest()+'  MAP_DATASET_MANIFEST.json\n',encoding='ascii')
print(json.dumps({'counts':counts,'manifest_sha256':manifest['manifest_sha256']},indent=2))
