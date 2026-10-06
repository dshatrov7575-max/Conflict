# AI_EXCEPTION_REVIEW_V1 — будущий HUMAN_EXCEPTION_PACKET

Статус: WAITING_FOR_THREE_INDEPENDENT_RESPONSES. Это пустой шаблон, не выданное задание сотрудникам.
Состав HUMAN_EXCEPTION_QUEUE пока **не определён**; отсутствие строк не означает отсутствие исключений.

После трёх полных независимых ответов compare_results.py создаст компактный standalone
HUMAN_EXCEPTION_PACKET.md: только units с HUMAN_EXCEPTION_QUEUE, их связанный исходный
материал и отдельные пустые формы E1/E2. AI_TRIAGE_RESOLVED и AI_TRIAGE_CANDIDATE не
добавляются как задачи людям. Повторно используемые источники могут входить только как
контекст выбранного исключения. Предыдущие AI-ответы, голосование и confidence сотрудникам
не передаются. Для проверки предложенного нового witness сотрудники получают его точную
ссылку/цитату отдельным нейтральным evidence supplement, если он отсутствует в исходном
материале. Генератор автоматически включает нейтральные witness records только для
выбранных исключений и только из сеансов без outcome-contamination; AI-выводы и
голосование удалены. RUN_MANIFEST.json закрепляет hash полученного пакета.

E1 и E2 работают отдельно с одинаковыми материалами и не видят ответов друг друга.
На каждую единицу: RESOLVED / NOT_RESOLVED / NEED_HUMAN, exact evidence,
URL/UUID/locator/hash/time, причина, confidence [0,1], remaining_unknowns.
Проверяются только происхождение, сохранность, mapping/охват/время и язык.
Не выполнять HUMAN coding, POS/KVS/UNO/RGU/KVPTN или adjudication.

Cutoff: 2011-12-15T23:59:59Z. Не использовать исход конфликта; дата публикации не
доказывает доступность конкретной редакции. Frozen цепочки и H1/H2 неизменны.
Получение этого файла само по себе не запускает работу сотрудников.

AI consensus не является HUMAN validation или inter-coder reliability. Формальный
HUMAN reliability pilot может позже идти параллельно и не блокирует инженерную
разработку. Научный допуск/выдача frozen H1/H2 остаётся отдельным процессом.