# AI_ONLY_RESEARCH_BETA_V1.1 — независимый hostile review protocol R1

## 1. Цель

Провести два независимых hostile review одного и того же frozen V1.1 release-candidate package. Проверка должна установить, обоснован ли статус:

`AI_ONLY_RESEARCH_BETA_RC_PASS_WITH_VISIBLE_INCOMPLETENESS`

Проверяется не историческая истинность кодировок, а целостность исследовательского workflow, provenance, prospective repair design, детерминированность tooling, корректность release gate и честность claim boundary.

## 2. Frozen review target

Целевой manifest:

- path: `docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1_1_TECHNICAL_REPAIR/DEMO_PACKAGE_MANIFEST_R1.json`
- Git blob: `abca1f71455dc2c63d7f52736fb1004724cb90ce`

Источник V1.1 evaluation:

- GitHub Actions run: `36885038106`
- conclusion: `success`
- immutable artifact: `11174645764`
- artifact digest: `sha256:ff8c6cf0d6a4cc43e9ca4ab9a3fe54539fcb8fe9b5e31576cc1e33e7a0087ed6`

Demo-package preflight:

- GitHub Actions run: `36888617846`
- conclusion: `success`
- immutable artifact: `11176395011`
- artifact digest: `sha256:0741d01501ffbede5b6dbb29f819d40908d913a72ee3f9a800292e1f0b12daf7`

Review target не меняется после начала первого review. Любые последующие commits не входят в target, если они прямо не перечислены в frozen manifest.

## 3. Независимость

Каждый reviewer обязан:

- работать в отдельном свежем чате;
- не видеть output другого reviewer;
- не использовать прежние аудиты, coordinator opinions или известный исход конфликта;
- не использовать внешний поиск;
- не исправлять и не adjudicate primary coding;
- оценивать только frozen target и явно перечисленные artifacts;
- маркировать недоказанное как `NOT_PROVEN`.

Замена модели допустима только до получения её review output и только по доступности сервиса; причина и фактическая модель фиксируются в output.

## 4. Обязательные объекты проверки

1. Prospective technical-repair design и правило выборочного rerun.
2. Immutable carry-forward шести R1 primary outputs по exact Git blobs.
3. Независимость двух свежих OMG V1.1 primary runs, identity/run IDs/attestations.
4. Model B substitution: заморожена ли до AI2 response и не использовался ли AI1 output для выбора.
5. Frozen comparator: schema admission, C1–C8, disagreement/UNKNOWN handling, отсутствие coordinator substitution.
6. Cohort aggregation: фиксированный denominator, 12/12 coverage, корректность counts.
7. Eligible-only read-only replay: только KBM E02 и KBM E05, Core parity, отсутствие OMG replay.
8. Release gate G1–G8 и логическая совместимость PASS с visible incompleteness.
9. Provenance evaluation artifacts, receipts и exact blobs.
10. Demo script/checklist: соответствуют ли frozen scientific state и claim boundary.
11. Запрет восстановления старого условного `company KVS=5 / Pol=50`.
12. Отдельные границы: historical snapshot, historical area UNO, HUMAN validation/reliability, predictive/probability/risk validation.
13. Два ранних failed workflow attempts: являются ли они только orchestration failures либо компрометируют scientific output.
14. Selective-rerun, researcher degrees of freedom, outcome leakage, rerun-until-favorable и publication-bias risks.

## 5. Severity

- `P0` — дефект делает RC state недостоверным, нарушает frozen/provenance boundary или делает демо вводящим в заблуждение. Итоговый verdict обязан быть `HOLD_P0`.
- `P1` — существенный дефект упаковки, доказательности или claim boundary; демо возможно только при явной оговорке, исправление обязательно до публикационного статуса.
- `P2` — улучшение ясности/удобства без влияния на RC state и безопасность демо.

Reviewer не должен создавать finding ради количества. Отсутствие доказательства — `NOT_PROVEN`, а не автоматически P0.

## 6. Verdict

Допустимые состояния:

- `PASS` — P0/P1 отсутствуют; RC state и demo boundary поддержаны.
- `PASS_WITH_P1` — P0 отсутствуют, есть конкретные P1; demo допустимо при перечисленных ограничениях.
- `HOLD_P0` — найден хотя бы один подтверждённый P0.
- `NOT_PROVEN` — пакет недостаточен для обоснованного verdict.

`demo_allowed` и `rc_state_supported` оцениваются отдельно. Reviewer не имеет права переводить PR из Draft, выполнять merge или менять artifacts.

## 7. Evidence discipline

Каждый finding должен ссылаться на точный repository path и, когда он дан manifest/receipt, Git blob или run/artifact ID. Общие утверждения без evidence reference не считаются finding.

## 8. Выход

Вернуть ровно один JSON по `HOSTILE_REVIEW_RESPONSE_SCHEMA_R1.json`, без Markdown и пояснений. Raw output сохраняется неизменным. Сравнение двух reviews выполняется только после получения обоих output.
