# MVP7 R2 — итог двух независимых AI-кодировщиков

## Результат
- AI1: GPT-6 Astra Pro, 12 записей, исходный валидатор PASS.
- AI2: Claude Opus 5.5 (claude-opus-5-5), 12 записей, embedded JSON Schema PASS; исходный semantic validator FAIL из-за заполненных `conflict_alternatives` у NUMERIC/UNKNOWN.
- Оригинал AI2 не переписан. Создана только механическая validator-проекция: 14 явно отвергнутых альтернатив из 12 записей перенесены в ledger; статус, значение, gates, evidence, rationale, confidence и temporal не менялись.
- Диагностическое сравнение после проекции: 6 NUMERIC_CONSENSUS_CANDIDATE, 1 SHARED_UNKNOWN, 5 TARGETED_REVIEW.
- Выполнен единственный разрешённый targeted review без новых источников и новых прогонов.
- Финал: 6 NUMERIC source-statement records и 6 UNKNOWN.

## Финальные значения
| Unit | POS_AO2 | KVS_AO2 |
|---|---:|---:|
| AO2S-C1-01 | UNKNOWN | UNKNOWN |
| AO2S-C1-02 | UNKNOWN | UNKNOWN |
| AO2S-C1-03 | -5 | 5 |
| AO2S-C1-04 | -5 | 5 |
| AO2S-C1-05 | UNKNOWN | 5 |
| AO2S-C1-06 | +5 | UNKNOWN |

## Критическое решение по расхождению
Для AO2S-C1-05 POS фраза `a review of salaries` означает требование пересмотра, но не задаёт явного направления изменения зарплаты. Закрытый якорь -5 требует явного требования изменить существенный компонент; поэтому итог остаётся UNKNOWN.

## Граница расчёта
Все результаты относятся к датированным сообщениям, `as_of_time_utc=null`, `carry_forward_policy=NONE`. Они не являются состоянием на 15.12.2011. Реальный CalculationSnapshot не создаётся: нет сопоставленных во времени полных actor rows с одновременно известными POS и KVS. RGU/KVPTN и веса не исправляют этот пробел. UNO = NOT_COMPUTED.
