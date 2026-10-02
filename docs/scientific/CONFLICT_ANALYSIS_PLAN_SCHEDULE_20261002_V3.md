# Conflict Analysis — актуальный план-график V3

**Дата обновления:** 02.10.2026  
**Область:** только Conflict Analysis / MVP7.  
**Научный статус:** `AI_ONLY_RESEARCH_BETA_RC_PASS_WITH_VISIBLE_INCOMPLETENESS`.  
**Независимая экспертиза:** `PASS_WITH_P1`; подтверждённых P0 нет.  
**Демо:** локальная изолированная сборка commit `eb22b479946b7f1a7d7188e0fd1c7c2a01c69f06`; полная репетиция — PASS.  
**Merge/release:** не выполнены; auto-merge запрещён.

## 1. Завершённые контрольные точки

| Срок | Контрольная точка | Итог |
|---|---|---|
| 29.09–01.10 | R1 evidence route, blind primary outputs, comparators, cohort, Core replay, release gate | R1 сохранён как `CLOSED_HOLD`; старые OMG `company KVS=5 / Pol=50` не восстановлены |
| 01.10 | V1.1 перспективный технический ремонт OMG | Два свежих primary; employer KVS сохранён как disagreement; OMG = `HOLD_DISAGREEMENT`, без Core replay |
| 01.10 | Fixed cohort и eligible-only Core replay | 12/12 triage rows; exact 11/12; numeric consensus 9/12; shared UNKNOWN 2/12; disagreement 1/12; KBM E02/E05 Core parity PASS |
| 01.10 | Frozen release gate V1.1 | G1–G8 PASS; `AI_ONLY_RESEARCH_BETA_RC_PASS_WITH_VISIBLE_INCOMPLETENESS` |
| 01–02.10 | Два независимых hostile review R2 и один patch-cycle | Qwen = PASS; DeepSeek = PASS_WITH_P1; консервативный итог `PASS_WITH_P1`; P0 = 0 |
| 01–02.10 | Строгий UI-tightening | PR #125; zero-copy рабочие экраны; контекстная помощь; `?` 12×12 px с hit-area 32×32 px; overlap guard |
| 02.10 | Изолированная локальная демо-сборка и полная репетиция | Editor save/readback PASS; Publisher readiness refresh PASS; HUMAN 0 ≠ AI UNKNOWN; passwordless roles PASS; 360/1440 overflow отсутствует |

## 2. Оставшиеся работы

| Срок | Контрольная точка | Критерий готовности |
|---|---|---|
| **02.10** | Финальная визуальная приёмка владельцем по PR #125 | Нет перекрытий, непонятных основных действий, лишней экранной прозы и блокирующих дефектов запуска; замечания фиксируются без изменения науки |
| **02–03.10** | Последний адресный UI/launch patch при необходимости | Только подтверждённые дефекты интерфейса или запуска; повторный full rehearsal PASS; PR #125 остаётся Draft до решения владельца |
| **03.10** | Freeze demo acceptance receipt | Exact commit, source tree, role-launch checks, Editor/Publisher/Assessor evidence, screenshots и ограничения зафиксированы |
| **03–04.10** | Финальный внешний пакет и сценарий показа | Не более 10 файлов; обязательные P1 disclosures; `UNKNOWN != 0`; HOLD lanes не проходят Core; historical area UNO не вычисляется |
| **04–05.10** | Демо владельцу/партнёру и решение | `PUBLISH_SCIENTIFIC_BETA` либо `HOLD` с точными blockers; никаких заявлений о HUMAN validation или predictive validity |
| **06–07.10** | Резерв | Только CI, упаковка, запуск и подтверждённые блокирующие дефекты; без recoding, adjudication, model shopping и изменения формулы |
| **08.10** | Крайний резерв прежнего графика | Используется только при новом P0/launch blocker; иначе проект должен быть показан раньше |

## 3. Текущий критический путь

1. Владелец визуально проверяет три режима локальной демо: **Редактор**, **Публикация**, **Оценки**.
2. Подтверждённые замечания исправляются одним адресным циклом; неподтверждённые улучшения не расширяют scope.
3. После чистой повторной репетиции фиксируется demo acceptance receipt.
4. PR #124 и PR #125 остаются без auto-merge. PR #125 является stacked PR над веткой PR #124; порядок интеграции должен сохранить scientific evidence route и UI commit identity.
5. Решение о публикации принимает владелец; отсутствие решения не интерпретируется как release.

## 4. Обязательные границы демо и публикации

- обязательный баннер: `AI-кодирование; человеческая проверка не проводилась; исследовательская версия; прогнозная точность не установлена.`;
- historical snapshot: `NOT_ESTABLISHED`;
- historical area UNO: `NOT_COMPUTED / BLOCKED`;
- HUMAN validation/reliability: `NOT_PERFORMED`;
- prediction/probability/risk validation: `NOT_CLAIMED`;
- Gemini AI2 identity: frozen UI binding + self-report, без независимого provider receipt;
- AI1 non-access: protocol-declared и Git-timestamped, но не service-audited;
- отсутствие всех скрытых внешних запусков: `NOT_PROVEN`;
- denominator 12: только repair-route triage rows; inherited KBM worker records исключены;
- `UNKNOWN != 0`;
- старые OMG `company KVS=5 / Pol=50` не восстанавливать;
- Core, формула, веса и факторные шкалы не менять;
- no auto-merge.

## 5. Оценка срока

Проект идёт **раньше прежнего графика**: научный RC, hostile review, UI-сборка и полная автоматизированная репетиция завершены 2 октября. При отсутствии нового блокирующего дефекта рабочее окно для демонстрации — **3–5 октября**, а 6–8 октября остаются резервом.
