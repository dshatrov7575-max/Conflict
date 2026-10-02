# Независимый hostile review — OMG Episode E1

**Объект:** `AI_ONLY_SINGLE_PTN_EPISODE_SCENARIO`  
**Проверяемый интервал:** 26.05–28.06.2011  
**PTN:** `E02_PAY`  
**Итоговый verdict:** `HOLD_EXTERNAL_SCIENTIFIC_RELEASE`  
**Допустимый внутренний статус:** `PASS_INTERNAL_TECHNICAL_DEMO_ONLY`

## A. Integrity and provenance

### A1. Целостность пакета — PASS

Два primary output сохранены раздельно и содержат разные `run_id`, модели и attestations. Comparator фиксирует четыре расхождения, а не маскирует их. Первичные ответы не переписаны после review.

### A2. Worker source P1 — PARTIAL/PASS для source-statement

`04_PROVENANCE_VERIFICATION.json` сообщает, что coordinator повторно прочитал архивный payload `AW-D03-20110527054702`, подтвердил payload SHA-256 и буквальное присутствие полного контекста. Выявлен дефект standalone: `context_sha256` относился только к последнему предложению, а не к полному контексту. Поэтому отказ AI1 от B3 был методически обоснован на доступном ему пакете. Последующее подтверждение допустимо как coordinator source authentication, но не превращает primary AI1 в числовое согласие.

### A3. Company source P2 — PARTIAL

Набор P2-признаков поддерживает content-level историческое source-statement: официальный статический PDF, pre-cutoff Last-Modified, встроенные PDF-даты, публикационный маркер, датированный индекс и contemporaneous reproduction. При этом exact byte identity файла, реально отданного в 2011 году, не доказана. Для ограниченного source-statement этого достаточно только при явном статусе `PROVISIONAL` и confidence cap `MEDIUM`; для строгой frozen-edition identity — недостаточно.

### A4. Решающие provenance-подтверждения после primary runs — PARTIAL

Оба primary coder работали не с одинаково верифицируемой полнотой provenance. AI1 отказал B3 по двум источникам; coordinator затем подтвердил архивный payload, индекс и reproduction. Это легитимно для coordinator adjudication, но означает, что итоговый numeric record не является результатом двух независимых кодировщиков, работавших с одинаковым завершённым evidence package.

## B. Primary-coder independence and disagreement

### B1. Независимость — PASS

Attestations обоих primary runs фиксируют отсутствие доступа к другому ответу, прежним episode outputs, outcome и внешнему поиску.

### B2. Воспроизводимость кодирования — FAIL/NOT_PROVEN

До targeted review совпадение было **0/4**:

- AI1: четыре `UNKNOWN`;
- AI2: четыре `NUMERIC` (`-5, 5, +5, 5`).

Следовательно, пакет не демонстрирует независимую AI-reliability даже на четырёх полях. Он демонстрирует, что один coder применил жёсткий admission gate, а другой принял provenance и anchor predicates.

## C. Targeted-review legitimacy

### C1. Review как исправление provenance — PASS/PARTIAL

Для workers POS/KVS и company POS coordinator устранил конкретные provenance/packaging gaps и применил заранее заданные anchors. Это допустимый один review-round, если результат маркируется как `COORDINATOR_ADJUDICATED_PROVISIONAL`.

### C2. Company KVS=5 — PARTIAL / независимая воспроизводимость NOT_PROVEN

AI1 прямо утверждал, что formal response и позиция «demands unfounded» не образуют однозначный actor-defined formal decision set для KVS=5. AI2 и coordinator приняли более широкое чтение: официальный ответ компании включает вопрос оплаты в собственный formal response/decision set. Оба чтения совместимы с неидеально узкой формулировкой рубрики. Coordinator выбрал одно из них, но это не доказательство межкодировочной воспроизводимости.

### C3. Термин `VERIFIED_NUMERIC_AFTER_TARGETED_REVIEW` — OVERCLAIM

Более точный статус: `COORDINATOR_ADJUDICATED_PROVISIONAL_AFTER_PRIMARY_DISAGREEMENT`. Слово `VERIFIED` может ошибочно восприниматься как независимая подтверждённость значения, тогда как проверены главным образом provenance и соответствие выбранному чтению рубрики.

## D. Temporal construct

### D1. Граница эпизода — PASS

Интервал 26.05–28.06.2011 явно задан, а carry-forward за пределы эпизода запрещён.

### D2. Одновременность позиций — NOT_PROVEN

Worker statement относится к 26 мая, company response — к 28 июня. Пакет объединяет их как две позиции внутри одного интервала, но не доказывает, что позиция работников 26 мая оставалась неизменной 28 июня или что это синхронный snapshot. Поэтому объект должен называться **interval-assembled source-statement scenario**, а не историческим состоянием в одну дату.

### D3. Декабрьский срез — PASS по запрету

Пакет последовательно запрещает перенос результата на 15.12.2011. Декабрьский snapshot и area-level historical UNO не установлены.

## E. Factor-by-factor audit

| Actor / factor | Статус hostile review | Основание |
|---|---|---|
| Workers POS = -5 | PASS для bounded source-statement | Требование повышения оплаты и изменения pay scale явно противоречит приемлемости текущего pay component; whole-reference rejection не доказан. |
| Workers KVS = 5 | PARTIAL | Оплата входит в заявленный demand set. Атрибуция косвенная через company spokesman; pay-specific conditionality отсутствует. |
| Company POS = +5 | PASS/PARTIAL | `demands ... unfounded` поддерживает защиту текущего pay component, но не всего composite reference. P2 provenance ограничивает confidence. |
| Company KVS = 5 | PARTIAL / NOT_PROVEN as reproducible | Число зависит от широкого чтения «formal response/decision set». AI1 отверг этот predicate, AI2 принял. Нужна более точная будущая рубрика или отдельный replication-run на исправленном идентичном пакете. |

## F. Calculation and sensitivity

### F1. Арифметика Core — PASS

При `POS=(-5,+5)`, `KVS=(5,5)`, `RGU=(1,1)`, `KVPTN=1` exact Core replay даёт:

- `P=25`;
- `N=25`;
- `A=50`;
- `B=0`;
- `Pol=50`;
- status `COMPLETE` для 2/2 actor rows и 1/1 PTN.

Snapshot и result digests зафиксированы; standalone baseline совпадает с pinned Core.

### F2. Baseline 1:1 — не нейтральная центральная оценка

При симметричных позициях `-5/+5` и равных KVS значение `Pol` максимизируется, когда effective actor weights равны. Поэтому baseline 1:1 математически даёт верхнюю границу основной положительной grid (`Pol=50`), а не «среднюю» или эмпирически наиболее вероятную конфигурацию. То, что baseline был frozen до ответов, снимает post-hoc cherry-picking, но не делает его содержательно нейтральным.

### F3. Sensitivity — PASS технически, MAJOR LIMITATION содержательно

В positive-RGU grid `Pol` изменяется от `9.09090909` до `50.00000000`. Это сильная зависимость от exogenous design. Результат нельзя называть robust без заранее обоснованного критерия. `A=50` остаётся постоянным из-за симметричной абсолютной величины двух coarse anchors, а не из-за эмпирически доказанной стабильности конфликта.

### F4. `Core_UNO_field=50` — запрещён area-level claim

В one-PTN topology поле Core численно равно `Pol`; оно не является историческим областным UNO. Текущая claim boundary это правильно запрещает.

## G. Claims matrix

| Claim | Verdict |
|---|---|
| Exact technical replay of the chosen inputs | PASS |
| Internal demonstration of Core traceability | PASS |
| Bounded interval-assembled AI-coded scenario | PARTIAL / допустимо только с major limitations |
| Two-model reproducibility / AI reliability | FAIL / NOT_PROVEN |
| HUMAN validation or reliability | FAIL / не проводились |
| Historical state of actors on one date | NOT_PROVEN |
| Snapshot at 15.12.2011 | FAIL / не установлен |
| Area-level historical UNO | FAIL / не вычислен |
| Predictive probability/risk validation | FAIL / не заявлять |
| Construct validity of POS/KVS/RGU/KVPTN/Pol | NOT_PROVEN |
| Scientific external release as validated measurement | HOLD |

## H. Blockers and exact corrective actions

1. **Исправить release status:** заменить `RELEASED_AS_AI_ONLY_EPISODE_SCENARIO` на `INTERNAL_TECHNICAL_DEMO_SCIENTIFIC_RELEASE_HOLD` либо явно разделить technical release и scientific release.
2. **Исправить measurement status:** `VERIFIED_NUMERIC` → `COORDINATOR_ADJUDICATED_PROVISIONAL`.
3. **Уточнить temporal label:** `AI_ONLY_INTERVAL_ASSEMBLED_SINGLE_PTN_SOURCE_STATEMENT_SCENARIO`.
4. **Не называть 1:1 центральным/нейтральным результатом:** это analytic normalization и максимум `Pol` в frozen positive grid.
5. **Отдельно раскрыть 0/4 primary agreement** во всех external-facing summaries.
6. **Для company KVS=5:** либо оставить как coordinator-adjudicated candidate, либо провести новую prospectively frozen replication на исправленном identical evidence packet; старые primary outputs не переписывать.
7. **Не расширять claims:** никакого historical area UNO, декабрьского snapshot, HUMAN validation, prediction или probability.

# FINAL VERDICT

`HOLD_EXTERNAL_SCIENTIFIC_RELEASE`

Одновременно объект проходит как `PASS_INTERNAL_TECHNICAL_DEMO_ONLY`: вычислительная трассировка и bounded scenario engineering воспроизводимы. Основная причина HOLD — не математика, а нулевая первичная согласованность 0/4, coordinator substitution for all final values, temporal non-simultaneity и высокая design sensitivity.
