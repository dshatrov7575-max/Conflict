# PR-10 — MVP7 Methodology and Rubric Freeze

**Контрольная точка Главной 23. Статус поставки: замороженный методический пакет.**

Этот PR публикует сохранённые документы поверх PR #119 / commit
`89154c6e32a774c59e65bc665cd6ce7860a2a001`. Он добавляет только Markdown/JSON;
существующие версии, код, Calculation Core, формула и Evidence не меняются.

| Вход | Текущий статус / роль |
| --- | --- |
| POS | READY_FOR_DOUBLE_BLIND_HUMAN_PILOT; содержательная измеряемая переменная. |
| KVS | READY_FOR_DOUBLE_BLIND_HUMAN_PILOT; содержательная измеряемая переменная. |
| RGU | EXOGENOUS_ANALYTIC_WEIGHTS; вес исследовательского дизайна, не Evidence-derived оценка социального свойства. |
| KVPTN | EXOGENOUS_ANALYTIC_WEIGHTS; вес исследовательского дизайна, не Evidence-derived оценка важности проблемы. |

**HUMAN coding и UNO ещё не выполнены.** Этот freeze не назначает числовой
weight set, не запускает HUMAN pilot, не устанавливает исторические значения
факторов и не подтверждает эмпирическую валидность модели. Значения в synthetic
приложениях — ответы AI на вымышленные задания, не кодирование Zhanaozen.

## Что применяется сейчас

1. [Weight Semantics Decision](MVP7_WEIGHT_SEMANTICS_DECISION_PATCH_V1.md)
   задаёт принятую роль RGU/KVPTN. Она имеет приоритет над прежними
   гипотезами об эмпирическом измерении этих двух входов.
2. [Operationalization Rules](MVP7_FACTOR_OPERATIONALIZATION_RULES_V1.md)
   сохраняют общие правила допуска и POS/KVS; их прежние трактовки весов
   читаются с указанным semantic decision. Защищённые схемы и ontology
   в данном PR не синхронизируются и не переименовываются.
3. Числовая инструкция POS/KVS состоит из
   [Numeric Anchors v1](MVP7_POS_KVS_NUMERIC_ANCHORS_V1.md),
   [patch v1.1](MVP7_POS_KVS_RUBRIC_V1_1_PATCH.md) и узкого
   [patch v1.2](MVP7_POS_KVS_RUBRIC_V1_2_PATCH.md).
   Поздняя поправка заменяет только явно указанные положения.
   [Составная инструкция v1.2](synthetic/MVP7_POS_KVS_RUBRIC_HOLDOUT_V2/PATCHED_RUBRIC_FOR_CODERS.md)
   сохранена как точный вход завершённого synthetic holdout.
4. [Construct Review](MVP7_RGU_KVPTN_CONSTRUCT_REVIEW_V1.md) и
   [hostile review](MVP7_RGU_KVPTN_CONSTRUCT_HOSTILE_REVIEW_V1.md) — audit trail
   решения. Их гипотезы и прежние неопределённые статусы не превращаются
   в действующие Evidence-coding rules для RGU/KVPTN.

## Основание допуска POS/KVS

[Stress test 60](MVP7_POS_KVS_RUBRIC_STRESS_TEST_V1.md) и
[holdout v1.1, 48 случаев](MVP7_POS_KVS_RUBRIC_V1_1_HOLDOUT_REPORT.md)
сохранены со всеми обнаруженными дефектами. Их frozen keys не исправлены.
Текущий итог следует из [отчёта HOLDOUT V2](MVP7_POS_KVS_RUBRIC_V1_2_HOLDOUT_REPORT.md)
и [машиночитаемого результата](synthetic/MVP7_POS_KVS_RUBRIC_HOLDOUT_V2/RESULT.json):

- POS: новый targeted V2 — 36/36 intended answers поддержаны, 0 ошибок ключа,
  дефектов условий и неразрешённых неоднозначностей; -10/-5, 0/+5 и +5/+10
  имеют 4/4 пары у обоих AI при заранее заданном пороге ≥90%; 12/12 probes
  и все 72 обоснования поддержаны. Неизменённая -5/0 наследуется из v1.1 (2/2).
- KVS: неизменённые результаты v1.1 — 24/24 intended answers и обоснований,
  все четыре границы 2/2 у обоих AI при прежнем пороге ≥90%.
  **NOT_RETESTED_IN_V2**; этот PR не создаёт нового измерения KVS.

Это готовность инструкции к следующему HUMAN pilot, не HUMAN reliability
или проверка научной валидности индекса. Общая AI-модель, малая синтетическая
выборка, парная зависимость и общий файловый доступ остаются ограничениями.
Числовой дизайн весов и sensitivity analysis не выполнены этим freeze.

## Сохранность и состав публикации

[Freeze-manifest](MVP7_METHODOLOGY_RUBRIC_FREEZE_MANIFEST.json) содержит
точные пути, SHA-256, размеры, роли, приоритеты документов и исключения.
61 существующий документ/текстовое приложение перенесён побайтно. Два новых
файла — эта навигация и явный publication manifest. Предыдущие документы
не удалены, не нормализованы по окончаниям строк и не исправлены задним числом.

Фразы источников «локальный документ», «commit/PR не выполнялись», PROPOSAL,
PARTIAL и BLOCKED относятся к их исходным этапам. Они сохранены намеренно.
Текущий freeze не превращает индивидуальные PROPOSAL-документы в результаты
HUMAN coding и не переписывает прежний общий BLOCKED v1.1.

Synthetic packets, frozen keys, первичные AI-ответы и JSON-аудиты включены
как неизменённые текстовые методические приложения. Они не являются
существующими Evidence datasets. Python-генераторы и проверяющие скрипты
не включены. Их шесть точных путей и хешей перечислены в manifest.
Ссылки на эти скрипты и абсолютные локальные пути внутри исторических
отчётов/manifests сохранены: это provenance исходного запуска, не обещание
переносимого executable bundle. Код можно отдельно получить из исходной
локальной среды с проверкой опубликованных hashes; этот PR его не публикует.

Наличие исторических manifest-полей с путями и hashes реальных CP3 inputs
не означает публикацию самих inputs. Базовые файлы PR #119, его manifest
и закреплённые Evidence остаются неизменными.
