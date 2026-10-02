# Conflict Analysis — 15-minute demo script R6

**Integrated state:** `d72e03b1be0748df0dc461b5aa72a7fe21872474`  
**Owner visual acceptance:** `ACCEPTED_FOR_LIMITED_DEMO`  
**Publication / release / deployment:** `NOT_EXECUTED`

Mandatory banner:

`AI-кодирование; человеческая проверка не проводилась; исследовательская версия; прогнозная точность не установлена.`

## 00:00–01:00 — Start
Open `Conflict Analysis Demo` or `http://127.0.0.1:8775/`. Choose a role; login is automatic. State that the local build is isolated and not production.

## 01:00–05:00 — Редактор
Show compact work panels and contextual `?`. Save the DRAFT and show fresh readback plus the receipt SHA. Do not claim publication or scientific validity.

## 05:00–08:00 — Публикация
Show `Готово`, stable readiness SHA after refresh and no blockers. Do not execute a publication attempt.

## 08:00–12:00 — Оценки
Show HUMAN numeric `0` and AI `UNKNOWN`. Emphasize `UNKNOWN != 0`; HOLD lanes are not forced through Core.

## 12:00–14:00 — Scientific evidence
Show the release-gate output and hostile-review decision: RC with visible incompleteness; independent review `PASS_WITH_P1`; confirmed P0 = 0.

## 14:00–15:00 — Limits and close
State that PR #124 and PR #125 are merged into the integration branch, while `main`, publication, release and deployment remain unchanged/not executed. Repeat the mandatory banner.
