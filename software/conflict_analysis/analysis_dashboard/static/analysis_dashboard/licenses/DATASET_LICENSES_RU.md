# Картографические источники R1

Получено 2026-09-16. Ответственный за воспроизводимую сборку: Conflict
Analysis R1 build process (build_dataset.py, Python 3.12, pyshp 2.3.1,
Shapely 2.1.2). Точные URL, revisions, размеры и SHA-256 каждого raw-файла
в RAW_SOURCES_LOCK.json; derived-файлы перечислены в MAP_DATASET_MANIFEST.json.

* MapLibre GL JS 5.6.2 — BSD-3-Clause. Три CSP/CSS-файла и LICENSE.txt
  скопированы без преобразования из exact npm tarball. Сборка CSP использует
  локальный worker; glyph server, CDN, sprites и tiles отсутствуют.
* Natural Earth release 5.1.2, commit
  f1890d9f152c896d250a77557a5751a93d494776 — Public Domain.
  [Источник](https://github.com/nvkelso/natural-earth-vector/tree/v5.1.2).
  Внутренние версии ADM0 5.1.1, disputed 5.1.0, populated places 5.1.2;
  version-файлы и terms snapshot закреплены хешами.
* geoBoundaries KAZ-ADM1-16772668, commit
  9469f09592ced973a3448cf66b6100b741b64c0d, boundaryYear **2017**,
  buildDate Dec 12, 2023. [Источник](https://github.com/wmgeolab/geoBoundaries/tree/9469f09592ced973a3448cf66b6100b741b64c0d/releaseData/gbOpen/KAZ/ADM1).
  **Administrative boundaries: geoBoundaries, CC BY 4.0.**
  Дополнительные исходные права по metadata: **© OpenStreetMap contributors,
  Wambacher; Open Data Commons Open Database License 1.0 (ODbL).**
  CC BY 4.0 относится к продукту/производным работам geoBoundaries и не
  отменяет ODbL исходного слоя. Пользователь явно согласовал обе атрибуции
  и историческую дату 2017 вместо предположения «только CC BY 4.0» из пакета.

Производная база kazakhstan_admin1.geojson распространяется под ODbL 1.0;
машиночитаемая база доступна локально в том же каталоге maps, вместе с
воспроизводимым преобразованием и exact raw source URL/SHA-256. Изменения:
clip extent, make_valid при необходимости, simplify 0.01 degree,
добавление русских названий и каноническая сериализация; исходные shapeID
и shapeISO сохранены. См. ODBL_1_0.txt, GEOBOUNDARIES_METADATA.json,
GEOBOUNDARIES_CITATION.txt, GEOBOUNDARIES_CC_BY_4_0.txt.

Рекомендуемая ссылка из исходного geoBoundaries citation: Runfola et al.
(2020), geoBoundaries: A global database of political administrative
boundaries, DOI 10.1371/journal.pone.0231866.

Русские подписи — локальный versioned словарь по stable feature ID.
Для Астаны и Алматы применены названия из owner pack; геометрия исходных
Natural Earth объектов не перемещалась. Подписи получены из открытого
набора и owner pack; закрытые картографические интерфейсы не использовались.

R1_MAP_TRANSPORT=LOCAL_GEOJSON; R1_PMTILES_REQUIRED=false;
R1_OSM_BASEMAP_USED=false; OSM_DERIVED_ADM1_USED=true.
