# Natural Earth builder — integration 1.0.1

Исходный builder-pack: `ceff5f4f9a126262dd073cf01d49520db406fcc354741bbe543e5a9c8f4de199`.
Исходный BUILD_NATURAL_EARTH_R1.py:
`c081496422025924cdb7813b5c6730010457f5ff3518468e38122a0f53acb194`.
VERIFY_NATURAL_EARTH_R1_OUTPUT.py сохранён без изменений:
`074813927d369cc6463d7b9aa12ac2781a90dfb439a0efe848bd75a32beb4954`.

Исправления выявлены на exact source, а не на синтетической карте:

1. В Admin 1 область Алматы и город Алматы имеют одинаковый ISO-код KZ-ALA.
   Первичный ключ — уникальный Natural Earth NE_ID; ISO и ADM1_CODE сохраняются
   атрибутами. Мангистау: NE_ID 1159314605, ADM1_CODE KAZ-3236, ISO KZ-MAN.
2. NAME_RU имеет приоритет над fallback overrides. Исходное значение сохранено
   в source_name_ru; labels_ru не изменяет координаты или геометрию.
3. Все FCLASS_* disputed attributes сохраняются; входной CRS проверяется.
4. Текстовые outputs используют LF независимо от ОС. Геометрия не упрощается
   и не обрезается: tolerance=0, фильтрация стран/территорий по source lock.
5. Dataset 1.0.1 создаёт новые immutable Foundation area identities; старые
   ревизии и территории не переписываются и не удаляются.

build_dataset.py проверяет пять raw SHA-256 до parsing. Его runtime manifest
сохраняет действующий Foundation hash contract (canonical JSON без terminal LF)
и охватывает все map/vendor/license assets. NATURAL_EARTH_BUILD_MANIFEST.json
сохраняет receipt builder (canonical JSON с LF). Supplied verifier проверяет
реальные runtime bytes через временное плоское представление этого receipt.
Это различие контейнеров и сериализации; географические данные не подменяются.

Сборка, включая output verifier и два идентичных результата:

```text
python BUILD_NATURAL_EARTH_R1.py --self-test
python build_dataset.py --raw-cache <external-cache> --output-static <empty-output> --verify-reproducible
python build_dataset.py --raw-cache <external-cache> --output-static <second-empty-output> --offline --verify-reproducible
```

Raw cache не включается в Git или wheel. Карта загружает только локальные assets.
