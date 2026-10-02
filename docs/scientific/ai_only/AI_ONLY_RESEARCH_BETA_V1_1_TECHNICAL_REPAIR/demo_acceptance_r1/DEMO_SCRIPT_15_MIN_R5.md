# Conflict Analysis — 15-minute demo script R5

**Technical state:** `PASS`  
**Owner visual acceptance:** `PENDING_OWNER_DECISION`  
**Product UI commit:** `eb22b479946b7f1a7d7188e0fd1c7c2a01c69f06`

Mandatory banner:

`AI-кодирование; человеческая проверка не проводилась; исследовательская версия; прогнозная точность не установлена.`

## 00:00–01:00 — Start

Open `Conflict Analysis Demo` on the desktop or `http://127.0.0.1:8775/`. Choose a role; login is automatic. State that the build is local, isolated and not production.

## 01:00–05:00 — Редактор

Open **Редактор**. Show compact work panels and 12 px contextual `?`. Save the DRAFT and show fresh readback plus the receipt SHA. Do not claim publication or scientific validity.

## 05:00–08:00 — Публикация

Open **Публикация**. Show `Готово`, stable readiness SHA after refresh and no blockers. Do not execute a publication attempt.

## 08:00–12:00 — Оценки

Open **Оценки**. Show the same factor as HUMAN numeric `0` and AI `UNKNOWN`. Emphasize `UNKNOWN != 0`; no HOLD lane is forced through Core.

## 12:00–14:00 — Scientific evidence

Show the release-gate output and hostile-review decision. State: RC with visible incompleteness; independent review `PASS_WITH_P1`; confirmed P0 = 0.

## 14:00–15:00 — Limits and close

Repeat the mandatory banner. Historical snapshot is NOT_ESTABLISHED; historical area UNO is NOT_COMPUTED/BLOCKED; HUMAN validation is NOT_PERFORMED; predictive validity is NOT_CLAIMED. Publication and merge require a separate owner decision.
