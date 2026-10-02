# Conflict Analysis — FAST TRACK после R1 CLOSED_HOLD

**Цель:** вынести демонстрацию вперёд с 08.10 на 02.10, не ослабляя fail-closed правила.

## Решение

Разделить две цели:

1. **Демо продукта и исследовательского контура** — не ждать финального Scientific Beta release gate. Для него уже есть проверяемая цепочка R1: blind coding, frozen comparator, честный `UNKNOWN`, read-only sensitivity, Core parity и release-gate HOLD.
2. **Scientific Beta V1.1** — закрыть единственный технический пробел двумя новыми OMG primary runs в отдельном перспективном route; шесть валидных R1 primary outputs переносить только по точным Git blob SHA.

## Ускоренный график

| Время, МСК | Работа | Выход |
|---|---|---|
| **01.10, 16:00–17:30** | Freeze V1.1 technical-repair protocol, carry-forward manifest, два standalone-пакета и validators | Все правила и хэши зафиксированы до новых ответов |
| **01.10, 17:30–19:00** | Владелец запускает два свежих чата параллельно: GPT-5.6 Sol Pro и Claude Opus 5.5 High | Два raw OMG JSON; один запуск на модель, без исправлений |
| **01.10, 19:00–20:00** | Frozen validation/comparison, обновлённая когортная агрегация; eligible-only sensitivity/Core replay | Машинные receipts и точный V1.1 state |
| **01.10, 19:00–21:00 параллельно** | Сборка demo-пакета и 10–15-минутного сценария из уже готовых R1 артефактов | Готовая внутренняя репетиция независимо от результата V1.1 |
| **02.10, утро** | **ДЕМО** | Показ полного контура, включая fail-closed HOLD; публикационный статус явно отделён |
| **02.10, день** | Два hostile review параллельно, не последовательно | Два независимых вердикта |
| **02.10, вечер** | Один patch-cycle только по P0/P1 упаковки/provenance/claim boundary; final gate | Scientific Beta PASS с видимой неполнотой либо точный HOLD |
| **03.10** | Резерв | Только CI/malformed-output/упаковка; без изменения науки |

## Что исключено из критического пути демо

- ожидание 8 октября;
- полный повтор всех восьми ролей;
- последовательные hostile reviews;
- исправление P2 до демонстрации;
- финальная публикационная упаковка до первой демонстрации;
- любой HUMAN validation claim.

## Почему только два новых OMG запуска допустимы

- шесть остальных outputs валидны по frozen validators и импортируются байт-в-байт;
- OMG выбран не по числам, а по объективному schema failure `MISSING_REQUIRED_RUN_ID`;
- новый route/version фиксируется до ответов;
- старые OMG outputs карантинируются и не показываются новым моделям;
- новый результат принимается любым: numeric, UNKNOWN, disagreement или malformed → HOLD;
- V1.1 честно маркируется как technical-repair route, а не как полный новый replication cohort.

## Демо 02.10 — что показываем

1. Исходное историческое evidence и provenance.
2. Два независимых AI primary coding outputs.
3. Frozen comparator без ручного adjudication.
4. KBM E02 и KBM E05: sensitivity + 15/15 scenario parity с Core.
5. D25 E02: `HOLD_FACTOR_INCOMPLETE`, демонстрация `UNKNOWN != 0`.
6. R1 OMG: автоматический отказ из-за malformed protocol output.
7. Release gate: система сама выдаёт PASS/HOLD и точные blockers.

Это уже полноценное демо метода и продукта, даже если V1.1 снова останется HOLD.

## Риски

- **Критика selective rerun.** Снижается отдельной версией, техническим selection rule, immutable carry-forward manifest и запретом смотреть старые OMG outputs.
- **Один новый ответ снова malformed.** Никаких follow-up исправлений; демо всё равно проходит на R1, V1.1 фиксируется HOLD.
- **Модель выдаст другие значения.** Принимаются без adjudication; график демо не ломается.
- **Hostile review найдёт P0.** Демонстрация workflow возможна, но публикация Scientific Beta переносится до закрытия P0.

## Новая целевая дата

- внутренняя репетиция: **01.10 вечером**;
- внешнее демо: **02.10 утром/днём**;
- Scientific Beta decision: **02.10 вечером**, резерв **03.10**.
