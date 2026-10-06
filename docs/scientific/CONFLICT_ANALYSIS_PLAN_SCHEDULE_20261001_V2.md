# Conflict Analysis — обновлённый план-график работ V2

**Дата обновления:** 01.10.2026  
**Область:** только проект Conflict Analysis / MVP7.  
**Текущий статус:** `AI_ONLY_RESEARCH_BETA_V1 = CLOSED_HOLD`; PR #123 остаётся Draft / open / not merged; Core `POLARIZATION_V1_BETA / 1.0.0` и формула не изменены.

## 1. Что уже завершено

| Срок | Контрольная точка | Статус |
|---|---|---|
| 29.09 | R2 AI-кодирование, формальное сравнение, заморозка датированных SOURCE_STATEMENT | **Завершено** |
| 29–30.09 | Frozen SOURCE_STATEMENT; `UNKNOWN`/`DISPUTED` сохранены, без подстановки нулей | **Завершено** |
| 30.09–01.10 | `AI_ONLY_EPISODE_INPUT_V1`, четыре lane / восемь primary-role | **Завершено с техническим дефектом OMG** |
| 01.10 | Сравнение primary outputs и когортная агрегация | **Завершено**: 8/12 точных совпадений; 6 numeric; 2 shared `UNKNOWN`; 4 unresolved |
| 01.10 | Exogenous RGU/KVPTN sensitivity + Core replay | **PASS** для KBM E02 и KBM E05; D25 E02 = `HOLD_FACTOR_INCOMPLETE`; OMG не допущен |
| 01.10 | Frozen release gate R1 | **`AI_ONLY_RESEARCH_BETA_RC_HOLD`**; G2 и G4 FAIL, остальные G1/G3/G5/G6/G7/G8 PASS |

Причина HOLD — не научное расхождение: оба OMG-ответа совпали по содержанию, но не содержали обязательный `run_id`, поэтому frozen comparator обязан был их отклонить. Ремонт JSON, добавление `run_id` координатором или повтор R1 запрещены.

## 2. Рекомендуемый следующий маршрут

Запустить отдельный перспективный маршрут **`AI_ONLY_RESEARCH_BETA_V2`**. Он должен быть заморожен до новых ответов и не менять источники, факторные шкалы, веса, Core или формулу.

Чтобы избежать критики за выборочный повтор только неудавшегося OMG lane после просмотра результатов, V2 должен быть **полным чистым повтором всех 8 primary roles**, а не ремонтом одного lane.

## 3. Обновлённый план-график

| Срок | Контрольная точка | Критерий готовности |
|---|---|---|
| **01.10** | Закрытие R1 и сохранение полного evidence trail | **Выполнено:** R1 = `CLOSED_HOLD`; raw outputs, comparators, aggregate, Core receipts и release-gate receipts сохранены |
| **02.10** | Freeze `AI_ONLY_RESEARCH_BETA_V2`: новый route/cohort, явный обязательный `run_id`, точные модели `GPT-5.6 Sol Pro` и `Claude Opus 5.5 High`, 8 standalone-пакетов, stop-rule | Валидаторы и self-tests PASS; хэши всех 8 пакетов зафиксированы до первого ответа; новая ветка/PR отделены от PR #123 |
| **02–03.10** | Восемь свежих blind primary runs: 4 ChatGPT + 4 Claude | 8/8 валидных raw JSON; clean attestations; без внешнего поиска, sibling outputs, outcome и coordinator review; владелец только переносит промпты и ответы без правок |
| **03.10** | Frozen comparator по четырём lanes + когортная агрегация | Все четыре результата сохранены, включая `UNKNOWN`, disagreement или HOLD; без adjudication и coordinator substitution |
| **03–04.10** | Exogenous RGU/KVPTN baseline + sensitivity; read-only Core replay только для eligible lanes | Полный digest/JSON-replay parity; PTN metrics, completeness и warnings; historical area UNO не вычисляется |
| **04.10** | Два независимых hostile review; один адресный patch-cycle | Patch разрешён только для provenance, схем, валидаторов, упаковки и claim-boundary; запрещены повторное кодирование, targeted adjudication, модельный шопинг и настройка весов по результату |
| **05.10** | `AI_ONLY_RESEARCH_BETA_V2` release candidate + внешний пакет максимум 10 файлов | Frozen release gate; либо RC PASS с видимой неполнотой, либо HOLD с точными blockers |
| **06–07.10** | Резерв | CI, malformed output, упаковка и только блокирующие технические исправления; без изменения науки |
| **08.10** | Демо и решение владельца | Публикация Scientific Beta либо формальное `HOLD`; PR остаётся без auto-merge до решения владельца |

## 4. Критический путь

1. До первого нового ответа заморозить V2 и восемь точных пакетов.
2. Получить 8/8 новых blind outputs. Это единственная ручная операция владельца; содержательное человеческое кодирование не требуется.
3. Не допускать selective OMG-only rerun: он быстрее, но методологически слабее после уже увиденных результатов R1.
4. Не восстанавливать старые OMG `company KVS=5 / Pol=50`.
5. `UNKNOWN != 0`; любой неполный lane остаётся HOLD/NOT_COMPUTABLE.
6. PR #123 сохраняется как закрытый evidence route R1; V2 идёт в отдельной ветке и отдельном Draft PR.

## 5. Реалистичность срока

Целевая заморозка **5 октября** и демо **8 октября** сохраняются, если freeze V2 завершён 2 октября, а восемь ручных запусков получены не позднее 3 октября. Один день задержки поглощается резервом 6–7 октября; задержка более двух дней переносит RC и демо день-в-день.

## 6. Неизменяемые границы

- HUMAN validation / reliability: `NOT_PERFORMED`;
- prediction / probability / risk validation: `NOT_CLAIMED`;
- historical snapshot: `NOT_ESTABLISHED`;
- historical area UNO: `NOT_COMPUTED / BLOCKED`;
- Core и формула: без изменений;
- no auto-merge;
- никакого ремонта R1 outputs и никакого повторного R1.
