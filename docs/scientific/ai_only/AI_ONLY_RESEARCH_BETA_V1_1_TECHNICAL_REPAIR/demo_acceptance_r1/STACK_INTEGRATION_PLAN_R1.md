# Conflict Analysis — порядок интеграции scientific RC и UI R1

**Статус:** подготовлено; merge/release не разрешены автоматически.  
**Scientific PR:** #124 — `review/ai-only-research-beta-v1-1-fast-repair` → `review/ai-only-research-beta-v1`.  
**UI PR:** #125 — `codex/conflict-ui-tightening-20261001` → `review/ai-only-research-beta-v1-1-fast-repair`.  
**UI product commit:** `eb22b479946b7f1a7d7188e0fd1c7c2a01c69f06`.  
**Technical acceptance commit:** `de579a8674b10fb1f6cc0fbe2385bd6489ae78a5`.

## 1. Обязательный порядок

1. До явного решения владельца оба PR остаются Draft/open/not merged.
2. Scientific evidence route #124 рассматривается первым.
3. После допустимого решения по #124 UI PR #125 должен быть ретаргетирован на уже интегрированную scientific base либо слит вторым в том же порядке.
4. Нельзя сливать #125 раньше #124: UI PR является stacked PR и основан на head scientific PR.
5. После ретаргетинга #125 требуется повторно проверить, что diff содержит только UI, demo-acceptance и упаковочные изменения сверх scientific base.

## 2. Сохраняемые идентичности

- scientific RC commit до UI: `2549daba4f96cb61db7be0441881e8cc33a5fde6`;
- UI product state: `eb22b479946b7f1a7d7188e0fd1c7c2a01c69f06`;
- demo-acceptance documentation: `de579a8674b10fb1f6cc0fbe2385bd6489ae78a5`;
- local demo must continue to identify `eb22b479946b7f1a7d7188e0fd1c7c2a01c69f06` as the exact product source used for rehearsal.

A merge commit may add integration identity, but must not rewrite the evidence meaning or silently substitute a different UI source.

## 3. Pre-merge checks

- PR #124 and #125 are mergeable and have no unresolved P0 blocker.
- Technical demo acceptance is PASS.
- Owner visual acceptance is explicit and no longer `PENDING_OWNER_DECISION`.
- The external package contains exactly 10 flat files and its recorded SHA-256 matches the distributed archive.
- Mandatory P1 disclosures remain visible.
- `UNKNOWN != 0`; old OMG `company KVS=5 / Pol=50` is not restored.
- Calculation Core, formula, weights and factor scales are unchanged.
- No publication attempt, production-ready claim, HUMAN validation claim or predictive-validity claim is introduced.

## 4. Forbidden operations

- auto-merge;
- squash/rebase that obscures scientific and UI source identities without a replacement provenance receipt;
- merging #125 before #124;
- retargeting that accidentally includes unrelated commits;
- primary recoding, adjudication, model shopping, factor/weight tuning or formula changes;
- treating technical acceptance as owner acceptance or release authorization.

## 5. Owner decision gate

Canonical gate: `OWNER_DECISION_GATE_R1.json`.

Allowed decisions:
- `ACCEPT_UI_FOR_LIMITED_DEMO`;
- `REQUEST_TARGETED_UI_PATCH_WITH_EXACT_BLOCKERS`;
- `HOLD_DEMO_WITH_EXACT_BLOCKERS`.

Until one of these decisions is explicit, both PRs remain Draft and no merge/release action is allowed.
