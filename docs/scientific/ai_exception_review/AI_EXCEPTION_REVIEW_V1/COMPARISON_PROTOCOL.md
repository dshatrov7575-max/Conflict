# AI_EXCEPTION_REVIEW_V1 — зафиксированный протокол сравнения

Статус PREPARED_NOT_RUN. Правила фиксируются до получения ответов; предназначены
координатору и не входят в blind-пакеты. 42 единицы: 9 availability + 12 mapping +
21 translation (20 EN, 1 KK). Восемь RU fragments не являются переводческими задачами.

Сначала требуются все три полных ответа по RESPONSE_SCHEMA.json, точные local_id/target_id,
одинаковый material hash и три разных session_id. Это проверка формы, не доказательство
реальной независимости. Координатор проверяет отдельность сессий и фактические модели;
названия файлов обозначают запрос пользователя, а не свидетельство доступности/запуска
конкретной модели. Два ChatGPT-сеанса могут иметь общие модельные ошибки.

Пустая форма, пропущенная/повторённая единица, неправильный hash, неполный evidence,
ложная attestation или ошибочная структура останавливают весь batch как INVALID/WAITING;
никакого скрытого исключения строк или вычисления на двух ответах. При выявленной
outcome-contamination после трёх валидных форм все единицы помещаются в human queue
с причиной SESSION_OUTCOME_CONTAMINATION. Новая чистая AI-сессия возможна только как
отдельный задокументированный запуск, без перезаписи исходных ответов.

Правила с приоритетом сверху вниз:

1. Любой NEED_HUMAN или явно заявленный material_issue → HUMAN_EXCEPTION_QUEUE.
2. Существенно разные findings/evidence → HUMAN_EXCEPTION_QUEUE. Автомат не умеет
   надёжно отличать парафраз от смыслового расхождения: разные переводы, scope или
   locator/hash conservatively попадают туда с пометкой DIFFERENCE_REQUIRES_REVIEW,
   а не с ложным утверждением, что противоречие уже установлено.
3. 3/3 RESOLVED + одинаковые structured findings и decisive proof → AI_TRIAGE_RESOLVED.
4. 2/3 RESOLVED с одинаковыми findings/proof + один NOT_RESOLVED без противоречий →
   AI_TRIAGE_CANDIDATE, отдельная проверка evidence и остаточного возражения обязательна.
   CONTRADICTED у третьего эксперта имеет приоритет над большинством.
5. 0/3 или 1/3 RESOLVED → HUMAN_EXCEPTION_QUEUE; ни одна единица не теряется.

Совпадающее decisive proof означает одинаковые target_id, fragment_ids, evidence_kind,
preserved_at_utc, payload SHA-256, exact-quote SHA-256, locator и claim_scope. Порядок
evidence/fragment_ids не влияет. URL сам по себе недостаточен; официальное зеркало
с теми же bytes допустимо. Structured findings включают availability scope,
full-edition identity flag, все mapping dimensions и точный русский перевод.
Свободные reason/language_explanation/confidence не голосуют. Семантическое сравнение
переводов и эквивалентности разных locators не имитируется: автоматическая нормализация
ограничена сортировкой множеств, без стирания отрицаний, чисел или модальности.

RESOLVED availability требует каждого selected exact fragment в decisive quote;
только fragment proof никогда не закрывает полную позднюю edition identity. Mapping
требует положительных оснований всех шести dimensions, но не числа POS/KVS. Перевод
проверяется отдельно от исторической доступности. Неизвестное сохраняется; confidence
не компенсирует отсутствие evidence. Новые witnesses сохраняются отдельно, без rebinding.

compare_results.py проверяет JSON, IDs, exact-quote hashes, declared timestamps и
структурную согласованность. Он **не скачивает и не аутентифицирует** внешние files,
не подтверждает правильность claim/перевода и не доказывает независимость экспертов.
AI_TRIAGE_RESOLVED — результат AI triage, не изменение научного admission, H1/H2,
HUMAN validation или inter-coder reliability. Для инженерного backlog такой triage
можно использовать с явной маркировкой. Формальный HUMAN reliability pilot позже
может идти параллельно и не должен блокировать инженерную разработку.

Для кандидатов отдельная проверка фиксирует verifier, witness, точный scope,
смысл возражения, remaining_unknowns и CONFIRMED_EVIDENCE / HUMAN_EXCEPTION_QUEUE /
STILL_OPEN. Основное сравнение не перезаписывается, новых голосов в старый запуск
не добавлять. Сотрудникам передаются только HUMAN_EXCEPTION_QUEUE, связанный
исходный материал и нейтральные новые witness records; никаких AI ответов/consensus.
Список исключений сейчас не заполняется: независимых ответов ещё нет.