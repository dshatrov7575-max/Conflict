# Conflict Analysis — сценарий демонстрации на 15 минут, R2

**Статус:** `READY_FOR_DEMO_2026-10-02`  
**Показывается:** проверяемый исследовательский workflow с видимой неполнотой.  
**Не заявляется:** HUMAN-валидация, исторический area UNO, прогнозная вероятность/риск.

Обязательный баннер на первом и последнем экране:

`AI-кодирование; человеческая проверка не проводилась; исследовательская версия; прогнозная точность не установлена.`

## 00:00–01:00 — Что именно демонстрируется

Открыть:

`CURRENT_STATE_20261001_R1.json`

Сказать:

- evidence, роли, правила и версии заморожены до результатов;
- два независимых AI-кодировщика работают без результата конфликта и внешнего поиска;
- comparator, cohort aggregation и release gate выполняются детерминированно;
- `UNKNOWN != 0`;
- система считает только допущенные lane и сохраняет disagreement/HOLD без ручной подстановки.

## 01:00–03:00 — Замороженный вход и provenance

На примере KBM E02 показать:

- actor binding и PTN/reference statement;
- frozen input SHA-256;
- допустимые evidence fragments;
- POS/KVS anchors;
- C1–C8 admission checks;
- отдельные роли AI1 и AI2.

Ключевая фраза: модель не получает свободу «угадать число»; она обязана пройти формализованные admission checks и выбрать только лицензированный anchor либо `UNKNOWN`/`DISPUTED`.

## 03:00–05:30 — Два свежих blind primary output OMG V1.1

Открыть рядом:

- `raw/OMG_NOV24_V101_AI1_COMPLETED.json`;
- `raw/OMG_NOV24_V101_AI2_COMPLETED.json`.

Показать:

- модели: GPT-5.6 Sol Pro и Gemini 3.1 Pro;
- разные `run_id`;
- чистые attestations;
- raw JSON сохранён без исправления;
- совпадение по трём решениям;
- расхождение по employer `KVS_AO2`: GPT=`UNKNOWN`, Gemini=`5`.

Не называть согласие моделей истиной и не скрывать расхождение.

## 05:30–07:00 — Frozen comparator

Открыть:

`derived/OMG_NOV24_V101_PRIMARY_COMPARISON.json`

Показать результат:

- workers POS `-5` → `CONSENSUS_NUMERIC`;
- workers KVS `5` → `CONSENSUS_NUMERIC`;
- employer POS `+5` → `CONSENSUS_NUMERIC`;
- employer KVS `UNKNOWN` против `5` → `HOLD_DISAGREEMENT`;
- `calculation_release=false`;
- coordinator adjudication запрещён;
- OMG Core replay не выполнялся.

Ключевая фраза: disagreement остаётся частью результата, а не ошибкой, которую координатор «исправляет».

## 07:00–09:30 — Допущенный read-only replay и Core parity

Открыть:

`../AI_ONLY_RESEARCH_BETA_V1/eligible_replay_r1/run_36844856009/ELIGIBLE_REPLAY_RESULT_R1.json`

Показать только две допущенные lane:

- `AI_ONLY_DYAD_KBM_E02_V100`;
- `AI_ONLY_PAIR_KBM_E05_V100`.

Для каждой:

- 15 frozen scenarios;
- exogenous RGU/KVPTN grid;
- pinned `POLARIZATION_V1_BETA / 1.0.0`;
- `PASS_CORE_PARITY`;
- стабильные result digests;
- JSON replay PASS;
- метрика — single-PTN research scenario, не historical area UNO.

## 09:30–11:30 — Честная неполнота в двух формах

### D25 E02

Показать:

`../AI_ONLY_RESEARCH_BETA_V1/executors/manual_dual_model_r1/derived/D25_E02_V100_PRIMARY_COMPARISON.json`

Объяснить:

- shared `UNKNOWN` сохраняется;
- lane=`HOLD_FACTOR_INCOMPLETE`;
- ноль не подставляется;
- расчёт не освобождается.

### OMG V1.1

Вернуться к сравнению OMG:

- evidence допускает разные решения по employer KVS;
- lane=`HOLD_DISAGREEMENT`;
- disagreement также не заменяется числом.

Ключевая фраза: система различает недостаточность evidence и межмодельное расхождение.

## 11:30–13:00 — Fail-closed и техническое восстановление протокола

Кратко показать R1:

- оба прежних OMG output были отклонены из-за отсутствующего обязательного `run_id`;
- координатор не дописывал ID и не ослаблял schema;
- R1 сохранился как HOLD.

Затем показать V1.1 repair boundary:

- шесть валидных R1 primary перенесены только по exact Git blob;
- только две невалидные OMG-роли перезапущены prospectively;
- замена Model B на Gemini была заморожена до AI2 response и по доступности сервиса;
- source input, prompt, comparator, Core, formula и weights не менялись;
- старый условный `company KVS=5 / Pol=50` не восстановлен.

## 13:00–14:30 — Полная когорта и release gate

Открыть:

- `derived/COHORT_AGGREGATE_V1_1_R1.json`;
- `release_gate/RELEASE_GATE_OUTPUT_V1_1_R1.json`.

Показать:

- decisions: `12/12`;
- exact agreement: `11/12`;
- numeric consensus: `9/12`;
- shared UNKNOWN: `2/12`;
- disagreement: `1/12`;
- unresolved: `0/12`;
- G1–G8: PASS;
- итог: `AI_ONLY_RESEARCH_BETA_RC_PASS_WITH_VISIBLE_INCOMPLETENESS`.

Отдельно проговорить:

- external substantive historical measurement = HOLD;
- historical area UNO = BLOCKED / NOT COMPUTED;
- HUMAN validation/reliability = NOT PERFORMED;
- predictive/probability/risk validation = NOT CLAIMED.

## 14:30–15:00 — Финальный тезис

> Conflict Analysis — не генератор одного «правильного» числа. Это provenance-visible, fail-closed исследовательский workflow: он считает только допущенные данные, сохраняет UNKNOWN и disagreement и показывает точную границу каждого вывода.

Повторить обязательный баннер и не переводить PR из Draft, не выполнять merge и не обещать опубликованную научную валидацию.
