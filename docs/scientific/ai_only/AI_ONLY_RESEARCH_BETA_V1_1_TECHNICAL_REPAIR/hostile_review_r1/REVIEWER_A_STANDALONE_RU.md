# MVP7 AI-only V1.1 — HOSTILE REVIEWER A

Ты — независимый hostile reviewer. Выполни только этот frozen review package.

## Frozen identity

- reviewer_role: `V1_1_HOSTILE_REVIEWER_A`
- response_schema: `AI_ONLY_RESEARCH_BETA_V1_1_HOSTILE_REVIEW_RESPONSE_R1`
- target manifest path: `docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1_1_TECHNICAL_REPAIR/DEMO_PACKAGE_MANIFEST_R1.json`
- target manifest Git blob: `abca1f71455dc2c63d7f52736fb1004724cb90ce`
- protocol path: `docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1_1_TECHNICAL_REPAIR/hostile_review_r1/HOSTILE_REVIEW_PROTOCOL_R1.md`
- response schema path: `docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1_1_TECHNICAL_REPAIR/hostile_review_r1/HOSTILE_REVIEW_RESPONSE_SCHEMA_R1.json`
- output filename: `V1_1_HOSTILE_REVIEW_A_COMPLETED.json`

## Запреты

Не используй:

- output Reviewer B;
- прежние аудиты и coordinator opinions;
- известный исторический исход;
- внешний поиск;
- память о других версиях пакета;
- предположения для заполнения отсутствующих доказательств.

Не исправляй raw primary outputs, не adjudicate employer KVS и не пересчитывай OMG. Не меняй route, Core, formula, weights, counts или release state.

## Задача

1. Открой protocol и response schema по указанным repository paths.
2. Открой frozen target manifest и каждый перечисленный в нём файл по точному path/Git blob.
3. Проверь все 14 domains D01–D14 из protocol.
4. Отделяй:
   - подтверждённый дефект;
   - риск, уже закрытый frozen controls;
   - недоказанное (`NOT_PROVEN`);
   - чистое улучшение P2.
5. Проверь, действительно ли статус `AI_ONLY_RESEARCH_BETA_RC_PASS_WITH_VISIBLE_INCOMPLETENESS` совместим с:
   - OMG `HOLD_DISAGREEMENT`;
   - D25 `HOLD_FACTOR_INCOMPLETE`;
   - eligible Core replay только KBM E02/E05;
   - отсутствием historical area UNO, HUMAN validation и predictive validation.
6. Проверь selective-rerun risk: был ли OMG rerun выбран по объективному schema failure до нового результата, были ли carry-forward outputs immutable и допускает ли пакет rerun-until-favorable.
7. Проверь два ранних failed workflow attempts: затронули ли они scientific output либо только orchestration expected-blob literals.
8. Проверь demo script/checklist на скрытое завышение claims.

Если файл или требуемое доказательство недоступно, не заменяй его общими знаниями: поставь соответствующему domain `NOT_PROVEN` и отрази влияние в verdict.

## Output contract

Верни ровно один JSON, без Markdown и без текста до/после него.

Обязательные значения:

- `schema`: `AI_ONLY_RESEARCH_BETA_V1_1_HOSTILE_REVIEW_RESPONSE_R1`
- `reviewer_role`: `V1_1_HOSTILE_REVIEWER_A`
- `actual_model_label`: фактическое название модели
- `model_label_source`: откуда взято название модели
- `run_id`: новый уникальный UUID или иной уникальный идентификатор
- `completed_at_utc`: UTC timestamp с `Z`
- все attestation values: `false`
- target identity — ровно как в response schema
- `domain_reviews`: ровно 14 записей, каждый D01–D14 ровно один раз
- counts должны арифметически совпадать с findings
- при любом подтверждённом P0 verdict=`HOLD_P0`

Не создавай findings ради количества. Верни `PASS`, если P0/P1 действительно отсутствуют; `PASS_WITH_P1`, если P0 нет, но есть подтверждённые P1; `NOT_PROVEN`, если пакет объективно недостаточен.
