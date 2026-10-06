# Zhanaozen 2011 — mapping scope freeze

AI preparation only. Зафиксированы идентичность реального CP3-кейса и область
подготовки будущего Factor Mapping. Это отдельный audit artifact с
`assessor_type=AI_PREPARATION`, вне Historical Assessment и ValidationPilot schemas.
Схемы не изменены. Завершённый Factor Mapping и эмпирическая валидация не заявляются.

Case UUID: `292d238f-9fee-578f-bddd-6f923163788a`. Это сообщения о трудовом споре
в Жанаозене и Мангистау, Казахстан; география описывает пакет, а не страновую оценку.
`ZHANAOZEN_2011_EXAMPLE` остаётся структурным примером без переназначения ID.
Cutoff и target time унаследованы из preregistration: `2011-12-15T23:59:59Z`.
Окно просмотра сообщений — `2011-05-17`–cutoff; зарегистрированные сообщения
заканчиваются `2011-11-27`. Это аналитическая область подготовки, не доказанные
начало/конец конфликта и не единое непрерывно наблюдаемое состояние.

[Identity/scope](CASE_IDENTITY_AND_EPISODE_SCOPE.json) фиксирует основания и UNKNOWN.
[Preparation](FACTOR_MAPPING_PREPARATION.json) связывает все 20 прежних CodingItems
и 58 прежних Fact–Fragment цепочек без нового отбора или ответов. CSV locators —
номера логических записей с заголовком под номером 1; JSON locators — JSON Pointer.
Новые scope/route identifiers служат навигации, а не заменяют Evidence UUID.
Отдельного исходного `evidence_id` в этих таблицах нет: используются типизированные
Fact/Fragment/DocumentVersion IDs. Все прежние отношения и спорные факты сохранены.

POS/KVS: только вопросы будущей проверки связи с точным actor/reference/time.
RGU/KVPTN: контекст идентичности единиц; согласно методическому freeze,
Evidence не является источником этих параметров исследовательского дизайна.
Числовые значения, шкалы и ответы здесь не создаются. Непроверенные переходы
AnalyticalElement → model PTN и сообщение → состояние на cutoff остаются UNKNOWN.

Открытые препятствия последующей работы:

- Все 12 recovery admission decisions остаются BLOCKED; для остальных 8 items
  этот recovery не выполнялся. Это не новый admission-проход.
- 17 выбранных fragments имеют унаследованное fragment proof; все 20 поздних
  редакций recovery остаются NOT_PROVEN как полные версии. Статус версии
  PROVEN_FRAGMENT_PRE_CUTOFF не распространяется на другие её fragments.
- Внешний CP3 и полные архивные payloads не вложены в Git: проверены локальные
  frozen extracts и их manifests, а не заново полученные внешние байты.
- Не установлены групповой мандат, полный охват reference и применимость
  сообщений к cutoff. Частное лицо, подгруппа, компания или отдельный орган
  не представляют автоматически всю исходную actor group.
- Состояние 28.11–15.12 UNKNOWN. Автоматический carry-forward запрещён;
  поздние snapshots, publication dates и PDF metadata не закрывают пробел.
- Три DISPUTED-факта, все непривязанные facts и возможные контрсвидетельства
  сохранены ссылками. Противоречия не разрешены, полнота поиска не заявляется.

HUMAN validation: NOT_PERFORMED. Admission/release прежних HUMAN packets не изменён.
Расчёты, публикация, release и deployment не выполнялись.

Проверка из корня checkout, Python 3.10+ с уже установленным `jsonschema`:

```powershell
python -B docs/scientific/pilots/ZHANAOZEN_2011_MAPPING_SCOPE_V1/validate_scope.py
git diff --check cb77ddbbc5cae3115f90a1512494d09be12c54d4
```

[Checks](SCOPE_AND_MAPPING_CHECKS.json) воспроизводятся read-only валидатором.
Он проверяет локальные bytes, pointers, связи, статусы, отрицательные fixtures
и неизменность всех прежних Git blobs, включая product tree. Проверки форматов
не удостоверяют историческую истинность или полноту Evidence. Новые audit JSON
не выдаются за объекты прежних schemas; существующие шаблоны проверяются этими
schemas, а AI_PREPARATION в Historical Assessment намеренно отклоняется.

[Manifest](FREEZE_MANIFEST.json) закрепляет inputs и пять остальных файлов через
Git blob SHA-1 и SHA-256. Сам manifest закрепляется commit и отдельными hashes
в PR delivery receipt; рекурсивный self-hash не используется. `--emit-checks`
печатает подготовительный receipt без проверки output pins; это не acceptance.
Обычный запуск обязательно проверяет все pins и точное совпадение receipt.
