# AI_EXCEPTION_REVIEW_V1

Статус: **PREPARED_NOT_RUN**. Подготовка на commit `176332bcbbdc9d3758dd79031037767cb57170ec` (PR #122).
Эксперты не запущены; HUMAN coding не начат. Новый commit/PR этим пакетом не создаётся.

## Выдача

Загрузить ровно один файл в каждый новый изолированный чат:

- `EXPERT_A_CHATGPT_PRO.md`
- `EXPERT_B_CHATGPT_PRO.md`
- `EXPERT_C_CLAUDE_FABLE_5_1.md`

Каждый файл standalone: одинаковые инструкции, весь фактический материал, 42 задачи,
schema и пустая response form внутри. Никаких соседних файлов эксперту не нужно.
Порядок всех 42 задач независимо рандомизирован и заморожен до ответов. Не менять
его по результатам. Не отправлять coordinator/, protocol, чужие пакеты или старые
отчёты. Общий материал SHA-256 `767da0d3f4fc189e587efd9084ea20ecb546f4f102c85e11f0153bc9d40a04fa`.

9 DocumentVersions: D07, D15, D17, D19, D20, D21, D23, D24, D29.
12 mapping tasks соответствуют ровно 12 frozen CodingItems; 21 translation task
соответствует каждому уникальному EN/KK fragment с непроверенным переводом.
Прежние AI переводы скрыты: эксперты делают свой перевод. Поддерживающие 11 versions
и 18 archive witness records входят как контекст, не новые availability задачи.
Старые verdicts, intended answers, outcomes и consensus не включены.

Модельные названия — назначенные пользователем роли; фактическую модель эксперт
указывает в ответе. Подготовленные файлы не подтверждают наличие/запуск конкретного
Claude или ChatGPT тарифа. Раздельные чаты обеспечивают процедурную изоляцию,
не статистическую независимость и не отсутствие знания кейса из обучения.

## После трёх ответов

Сохранить исходные JSON без правок вне этой frozen директории. Заполненные ответы
проверяются `RESPONSE_SCHEMA.json`; пустые формы намеренно не проходят финальную
валидацию. Утилита Python 3.10+ использует только standard library, не имеет сети,
не пишет в frozen файлы и не перезаписывает существующий output directory.

```text
python compare_results.py --self-test
python compare_results.py --a /path/to/A.json --b /path/to/B.json --c /path/to/C.json --out /path/to/new-run-directory
```

До ответов доступны `coordinator/COMPARISON_TEMPLATE.json` и
`HUMAN_EXCEPTION_PACKET_FUTURE.md`. После корректного полного batch появятся
COMPARISON_RESULTS.json, CANDIDATE_CHECK_TEMPLATE.json и HUMAN_EXCEPTION_PACKET.md
только с human exceptions и пустыми формами E1/E2. Ожидающая очередь не равна пустой.
Правила и ограничения — в COMPARISON_PROTOCOL.md. Никакие ответы сейчас не созданы.

AI consensus не является HUMAN validation/inter-coder reliability. Формальный
HUMAN reliability может позже выполняться параллельно и не блокирует инженерную
разработку. Это не разрешение выдавать frozen H1/H2: научный admission остаётся
отдельным, без автоматического изменения прежнего gate.

FREEZE_MANIFEST.json закрепляет новые файлы и входные hashes. PREPARATION_CHECKS.json
содержит проверки одинакового материала, рандомизации, ссылочной целостности,
границ scope и неизменности старого freeze. Application code, Core, формула,
существующие Evidence, старые keys и frozen H1/H2 не редактируются.