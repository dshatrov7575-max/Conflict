# Conflict Analysis — чек-лист репетиции демо R1

**Цель:** подтвердить, что 15-минутная демонстрация воспроизводима, не меняет научные данные и не выходит за claim boundary.

## A. До начала

- [ ] PR #124 остаётся `Draft / open / not merged`.
- [ ] Открыта ветка `review/ai-only-research-beta-v1-1-fast-repair`.
- [ ] На первом экране размещён обязательный баннер:
  `AI-кодирование; человеческая проверка не проводилась; исследовательская версия; прогнозная точность не установлена.`
- [ ] Подготовлены вкладки в порядке сценария R2.
- [ ] Масштаб браузера позволяет видеть путь файла, route/state и ключевые поля одновременно.
- [ ] Отключены любые live-редактирование, ручная adjudication и автоматический merge.

## B. Обязательные вкладки

1. `CURRENT_STATE_20261001_R1.json`
2. KBM E02 frozen packet и два raw primary output R1
3. `raw/OMG_NOV24_V101_AI1_COMPLETED.json`
4. `raw/OMG_NOV24_V101_AI2_COMPLETED.json`
5. `derived/OMG_NOV24_V101_PRIMARY_COMPARISON.json`
6. `../AI_ONLY_RESEARCH_BETA_V1/eligible_replay_r1/run_36844856009/ELIGIBLE_REPLAY_RESULT_R1.json`
7. `../AI_ONLY_RESEARCH_BETA_V1/executors/manual_dual_model_r1/derived/D25_E02_V100_PRIMARY_COMPARISON.json`
8. R1 OMG validation failure artifact
9. `derived/COHORT_AGGREGATE_V1_1_R1.json`
10. `release_gate/RELEASE_GATE_OUTPUT_V1_1_R1.json`

## C. Контрольные значения

- [ ] OMG workers POS: `-5 / -5`.
- [ ] OMG workers KVS: `5 / 5`.
- [ ] OMG employer POS: `5 / 5`.
- [ ] OMG employer KVS: GPT=`UNKNOWN`, Gemini=`5`.
- [ ] OMG lane: `HOLD_DISAGREEMENT`.
- [ ] OMG `calculation_release=false`.
- [ ] Cohort: expected=`12`, observed=`12`.
- [ ] Exact agreement=`11`.
- [ ] Numeric consensus=`9`.
- [ ] Shared UNKNOWN=`2`.
- [ ] Disagreement=`1`.
- [ ] Unresolved=`0`.
- [ ] Eligible replay lane ровно две: KBM E02 и KBM E05.
- [ ] Для обеих replay lane: `PASS_CORE_PARITY`, 15 scenarios, stable digests.
- [ ] Release gate: G1–G8=`PASS`.
- [ ] Итоговый state: `AI_ONLY_RESEARCH_BETA_RC_PASS_WITH_VISIBLE_INCOMPLETENESS`.

## D. Запрещённые формулировки

Не говорить:

- «модель доказала историческую истину»;
- «получен исторический UNO»;
- «система предсказывает вероятность конфликта»;
- «результат проверен людьми»;
- «две модели согласились, значит число верно»;
- «OMG можно посчитать, взяв Gemini KVS=5»;
- «UNKNOWN равен нулю».

Допустимо говорить:

- «AI-кодирование по замороженной рубрике»;
- «межмодельное согласие/расхождение на данном frozen input»;
- «read-only sensitivity scenario»;
- «Core parity подтверждена для двух eligible lane»;
- «release candidate прошёл gate с видимой неполнотой».

## E. Fail-closed точки, которые должны быть показаны

- [ ] R1 OMG отклонён из-за отсутствующего `run_id`; координатор не исправлял raw output.
- [ ] D25 shared UNKNOWN не преобразован в ноль.
- [ ] OMG V1.1 disagreement не adjudicated.
- [ ] OMG V1.1 не направлен в Core replay.
- [ ] Старый условный `company KVS=5 / Pol=50` не восстановлен.
- [ ] Historical area UNO остаётся `NOT_COMPUTED / BLOCKED`.

## F. Хронометраж репетиции

- [ ] 01:00 — границы демонстрации объяснены.
- [ ] 03:00 — frozen input и admission checks завершены.
- [ ] 05:30 — два OMG primary output показаны.
- [ ] 07:00 — comparator показан.
- [ ] 09:30 — Core parity показана.
- [ ] 11:30 — два вида неполноты показаны.
- [ ] 13:00 — R1 failure и V1.1 repair boundary объяснены.
- [ ] 14:30 — cohort и gate завершены.
- [ ] 15:00 — финальный тезис и обязательный баннер повторены.

## G. Критерий готовности

Репетиция считается `PASS`, только если:

1. все контрольные значения совпали с frozen artifacts;
2. показ уложился в 15 минут ± 1 минуту;
3. не было ручного изменения JSON, чисел, ролей или состояний;
4. ни один запрещённый claim не прозвучал;
5. PR остался Draft и не был merged.

Любое несовпадение означает `HOLD_DEMO_REHEARSAL` до выяснения причины; запрещено исправлять научные artifacts ради удобства презентации.
