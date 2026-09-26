# ZHANAOZEN_2011_HISTORICAL_AVAILABILITY_RECOVERY_REPORT

**Human Pilot Admission Gate: BLOCKED. 0 ADMITTED / 0 PARTIAL / 12 BLOCKED.**

База: PR #121, `0777f1704f920941198f68d8b62cb4f5cbf600eb`. Cutoff: **15.12.2011 23:59:59 UTC**.
Проверка: 2026-09-26T16:11:33.963531+00:00. Один завершённый автоматизированный блок по 20 версиям и 12 frozen items.
Материалы только для координатора / Главной 23; H1/H2 ничего не выдавалось.

## Результат recovery

- **0 PROVEN_PRE_CUTOFF / 11 PROVEN_FRAGMENT_PRE_CUTOFF / 9 NOT_PROVEN.**
- 18 успешно полученных pre-cutoff snapshots: их raw payload SHA-1 совпал с CDX digest,
  final capture timestamp не изменился и не вышел за cutoff; 17/29 уникальных frozen
  fragments найдены как literal case-sensitive substrings в decoded visible text.
- Для всех 20 поздних CP3 DocumentVersions идентичность всей редакции остаётся
  NOT_PROVEN. Witness — отдельная связь доступности; Source/DocumentVersion/Fragment/
  Fact/CodingItem links, captured_at и content_hash задним числом не переопределены.
- По всем 31 уникальным цепочкам / 43 прохождениям обновлена оценка контекста;
  для 17 fragments доступен исторически подтверждённый окружающий текст. Для 12
  остальных текущий publisher context остаётся отдельным кандидатом.
- Подготовлены 21 RU translation candidate (20 EN + 1 KK), с сохранением исходных
  фрагментов и модальности; 8 RU fragments перевода не требуют. Это AI desk review,
  не HUMAN/независимое удостоверение перевода и не присвоение значений факторов.

Публикационная дата, PDF CreationDate, filename, современный HTTP header или копия
2012/2013 года не использованы как доказательство доступности в 2011 году.
Отсутствие достаточного основания для числового ответа само по себе не блокирует
admission: допущенный input может законно привести человека к UNKNOWN. Здесь
остаются пробелы provenance, actor/group/reference/time Mapping и frozen input scope.

## Все 20 DocumentVersions

| Version / UUID | Статус | Fragments | Первый проверенный witness |
| --- | --- | --- | --- |
| D01 / `64f97ffe-8d27-5837-86bf-e5851257a76d` | PROVEN_FRAGMENT_PRE_CUTOFF | 1/1 | [20110521181520](https://web.archive.org/web/20110521181520id_/http://www.rferl.org:80/content/oil_workers_strike_in_kazakhstan_grows/24177839.html) |
| D03 / `ed5b18f5-d4b4-57bf-99db-d59131945ed9` | PROVEN_FRAGMENT_PRE_CUTOFF | 2/2 | [20110527054702](https://web.archive.org/web/20110527054702id_/http://www.rferl.org/content/more_oil_workers_hunger_strike_kazakhstan/24206131.html) |
| D04 / `adbcb401-ba65-5904-95c0-8ef2be653ed1` | PROVEN_FRAGMENT_PRE_CUTOFF | 1/1 | [20110529132216](https://web.archive.org/web/20110529132216id_/http://www.rferl.org:80/content/striking_oil_workers_fired_in_kazakhstan/24207466.html) |
| D05 / `3186a5ae-1c7c-5570-90e6-f6a68b938f59` | PROVEN_FRAGMENT_PRE_CUTOFF | 2/2 | [20110629041259](https://web.archive.org/web/20110629041259id_/http://www.rferl.org:80/content/kazakhstan_oil_workers_protests/24221366.html) |
| D06 / `bb5c161c-2e58-55b9-abaf-a92a634ebf37` | PROVEN_FRAGMENT_PRE_CUTOFF | 1/1 | [20110716171000](https://web.archive.org/web/20110716171000id_/http://www.azattyq.org:80/content/kazakhstan_zhangaozen_strike_oil_undustry_workers/24261582.html) |
| D07 / `3dcd5aa1-e2a9-5dd9-a2d9-992f9c80e835` | NOT_PROVEN | 0/1 | NOT_PROVEN |
| D09 / `f8c37ae0-cf47-50e7-844e-117d0da2d1e8` | PROVEN_FRAGMENT_PRE_CUTOFF | 2/2 | [20110809011049](https://web.archive.org/web/20110809011049id_/http://www.rferl.org/content/striking_kazakh_oil_workers_lawyer_gets_six_year_jail_term/24290769.html) |
| D13 / `00527651-bbea-5b17-89b0-c79f68fb39f6` | PROVEN_FRAGMENT_PRE_CUTOFF | 1/1 | [20110918124424](https://web.archive.org/web/20110918124424id_/http://www.rferl.org/content/kazakhstan_oil_workers_strike_desperation_poverty/24331987.html) |
| D14 / `3fa6e3d7-8fac-5372-84f4-6924a8bf819e` | PROVEN_FRAGMENT_PRE_CUTOFF | 1/1 | [20110927202906](https://web.archive.org/web/20110927202906id_/http://www.rferl.org/content/kazakhstan_oil_workers_lawyer/24341367.html) |
| D15 / `2d63f3f4-cb01-5b8c-b4ec-9bedb09b4363` | NOT_PROVEN | 0/2 | NOT_PROVEN |
| D17 / `e92b6b89-4e75-5f64-ac26-7dd8005c3d56` | NOT_PROVEN | 0/2 | NOT_PROVEN |
| D18 / `17608513-7164-5d30-9d2e-521338e323d7` | PROVEN_FRAGMENT_PRE_CUTOFF | 2/2 | [20111016234632](https://web.archive.org/web/20111016234632id_/http://iipdigital.usembassy.gov/st/english/texttrans/2011/09/20110901122736su0.701299.html) |
| D19 / `e85d2031-f492-5e93-b0ac-a7e84f27c7c7` | NOT_PROVEN | 0/1 | NOT_PROVEN |
| D20 / `26b9e671-5e1e-5460-a80c-2e803ca81ba6` | NOT_PROVEN | 0/1 | NOT_PROVEN |
| D21 / `d2eefc78-82b0-5eb7-b1ae-533745cbbd79` | NOT_PROVEN | 0/1 | NOT_PROVEN |
| D22 / `53cf6bd9-b51d-5f0a-b56f-addd0caa6af2` | PROVEN_FRAGMENT_PRE_CUTOFF | 1/1 | [20111120030853](https://web.archive.org/web/20111120030853id_/http://lada.kz:80/aktau_news/society/1153-zamestitel-ministra-truda-i-socialnoy-zaschity-naseleniya-vstretilsya-s-bastuyuschimi-neftyanikami-mangistau.html) |
| D23 / `02248e81-d235-5306-aef3-5dec2af93ebb` | NOT_PROVEN | 0/2 | NOT_PROVEN |
| D24 / `d3b8d52c-3dbb-5d07-84bd-e07acf35fbbb` | NOT_PROVEN | 0/1 | NOT_PROVEN |
| D25 / `86135a7f-79d7-5d6f-870c-f8bdaa925023` | PROVEN_FRAGMENT_PRE_CUTOFF | 3/3 | [20111016060958](https://web.archive.org/web/20111016060958id_/http://www.eurasianet.org:80/node/64310) |
| D29 / `9b1dfe95-b290-533c-9414-d8f18d880b1d` | NOT_PROVEN | 0/1 | NOT_PROVEN |

Статус PROVEN_FRAGMENT относится только к перечисленным exact fragments и отдельно
сохранённому witness context. Он не утверждает, что вся поздняя CP3 редакция либо
весь Fact существовали в таком виде на ту же дату. Полные replay URL, SHA-1/SHA-256,
fragment hashes, offsets и coverage находятся в [AVAILABILITY_WITNESSES.json](admission/ZHANAOZEN_2011_HISTORICAL_AVAILABILITY_RECOVERY_V1/AVAILABILITY_WITNESSES.json).

## Что восстановлено, а что не закрыто

- D03: архив теперь показывает пропущенное действие голодовки, компанию и говорящего.
  Это закрывает усечение на уровне отдельного witness, не переписывает frozen excerpt.
- D04: архив устанавливает именно QarazhanbasMunai. Это выявляет конкретный gap
  связи с GU02: принадлежность говорящих к подрядчикам не установлена.
- D05/D09: восстановлены прокуратура, судья, адресат решения, условия и даты.
  Слова этих субъектов не переносятся на работников или на все органы одновременно.
- D18: официальное зеркало IIP Digital сохранено 16.10.2011; оба фрагмента
  присутствуют. Говорящий — миссия США; это не собственный голос GU01/GU03.
- D22: исторический текст восстанавливает участников и дату встречи 15 ноября,
  согласующуюся с frozen Fact. Маркер ДОПОЛНЕНО уже есть в snapshot 20 ноября;
  он не заменяет проверку редакции датой публикации.
- D06: архив и перевод-кандидат не выделяют жителей вне нефтегазовых трудовых групп.
  D13/D25 дают индивидуальный голос/подгруппу уволенных/одну компанию; общего мандата
  на широкие GU01/GU03/GU05 они автоматически не создают.
- D17: текущий PDF показывает несколько предприятий, включая Ersai, но не имеет
  проверенного pre-cutoff witness. MONTH не доказывает day 01.10 и не подтверждает
  майскую дату другого Fact. D23 — региональный говорящий; D29 — ожидаемая повестка,
  а не принятое решение. Для них и прочих NOT_PROVEN поздняя редактура не исключена.

## Пересчёт всех 12 CodingItems

| H1 / H2 | Actor × Element | Статус | Закрыто recovery | Точная оставшаяся причина |
| --- | --- | --- | --- | --- |
| H1-10 / H2-08 | GU01 × E02 | BLOCKED | Исторический контекст D01/D03/D13 восстановил Соколову, пресс-секретаря компании и Лесова; действие голодовки D03 теперь видно в отдельном witness. | Октябрьская D17 и её майская связь остаются неподтверждёнными; нет основания распространять частные/пересказанные требования на всю GU01 и весь target time/reference. |
| H1-01 / H2-06 | GU01 × E06 | BLOCKED | D05/D09/D18 получили исторические witnesses и точных говорящих. | D20 NOT_PROVEN. США, прокуратура и суд не являются собственным коллективным голосом работников; групповой Mapping к GU01 не закрыт. |
| H1-03 / H2-05 | GU02 × E05 | BLOCKED | D04 теперь исторически подтверждён и явно относится к работникам QarazhanbasMunai. | Это не установленный состав подрядчиков GU02. D17 NOT_PROVEN; общее упоминание Ersai в текущем PDF не даёт права перенести все коллективные тезисы на GU02. |
| H1-07 / H2-09 | GU03 × E02 | BLOCKED | Все связанные exact fragments D13/D14/D25 получили pre-cutoff witnesses; названы индивидуальный работник, предприятия и подгруппа уволенных. | Группа GU03 также включает бывших работников и местных соискателей. Основание общего представительства и закреплённый Mapping к этой широкой группе/target time остаются отсутствующими; recovered context не включён в frozen H1/H2. |
| H1-02 / H2-10 | GU03 × E06 | BLOCKED | Исторически восстановлены контекст D05/D09 и голос США D18. | D19/D20 NOT_PROVEN. ЕС/США/делегация не представляют GU03; события о суде сами не закрывают Actor Mapping. |
| H1-06 / H2-11 | GU04 × E04 | BLOCKED | D06 имеет исторический witness и перевод-кандидат KK; текущие D07/D23 раскрывают источники статистики. | D07/D23 NOT_PROVEN; нефтяники/семьи/население не выделяют жителей вне трудовых групп. Статистика компании/акимата не становится голосом GU04. |
| H1-11 / H2-04 | GU04 × E05 | BLOCKED | Контекст D06 исторически восстановлен; в текущем D24 установлены перечисленные участники встречи. | D24 NOT_PROVEN; ни собрание нефтяников/семей, ни встреча ведомств/компаний не устанавливает представительство именно GU04. |
| H1-09 / H2-07 | GU05 × E02 | BLOCKED | D25 имеет исторический witness; компания KMG EP и авторство её утверждений отделены от слов уволенных работников. | D21 NOT_PROVEN. Одна компания не представляет автоматически весь основной/подрядный/сервисный контур GU05. Производственные потери не задают KVS. |
| H1-08 / H2-02 | GU05 × E04 | BLOCKED | Текущие D15/D23 раскрыли компанию и регионального заместителя акима как разных говорящих. | Обе версии NOT_PROVEN. Конкретное восстановление уволенных не равно доступу всех жителей; региональный чиновник не является всей GU05. |
| H1-12 / H2-01 | GU07 × E04 | BLOCKED | Исторический D22 подтверждает участие вице-министра 15 ноября и состав встречи; дата frozen Fact согласуется с witness. | D23/D29 NOT_PROVEN. Присутствие центрального чиновника, региональные числа и будущая повестка не дают установленного мандата на всё центральное actor/reference. |
| H1-04 / H2-12 | GU08 × E05 | BLOCKED | D09 исторически идентифицирует судью, приговор и адресата запрета деятельности. | D20 NOT_PROVEN. Конкретное судебное решение и ответ делегации не обосновывают объединённый голос всех органов GU08 по механизмам представительства. |
| H1-05 / H2-03 | GU08 × E06 | BLOCKED | D05 исторически приписывает слова о законности Генеральной прокуратуре; D09 устанавливает отдельный судебный акт. | D20 NOT_PROVEN. Законность одного действия и совокупная достаточность/соразмерность процедур — разные области утверждения; групповой мандат GU08 не закреплён. |

Только H1-07 / H2-09 (GU03 × E02) имеет witnesses для всех связанных fragments;
это не закрывает широкую групповую привязку и не включает новый контекст в frozen
пакеты. Для остальных 11 items дополнительно остаётся хотя бы одна NOT_PROVEN версия.
Поэтому READY_TO_DISTRIBUTE не достигнут; усреднение и исключение проблемных items
не применялись. Полные UUID/reference и шесть проверок каждого item:
[ADMISSION_REASSESSMENT.json](admission/ZHANAOZEN_2011_HISTORICAL_AVAILABILITY_RECOVERY_V1/ADMISSION_REASSESSMENT.json).

## Поиск, контроль leakage и сохранность

Выполнены 156 сетевых архивных discovery queries и 18 replay requests. Поиск включал
Wayback Available/CDX, старые /content/ и print/article routes, publisher-prefix,
Arquivo URL/fulltext, официальные US/EU/OSCE/KASE пути и независимые копии.
Это полный выполненный план по данной выборке, не заявление об исчерпании всего
Интернета. Тайм-аут/пустой индекс — не доказательство отсутствия старой копии.
Сначала sandbox запретил 94 socket requests; они повторены с разрешённым сетевым
доступом и исключены из числа 156. Автоматический approval review ничего не отклонял.

Даты ближайших snapshot после cutoff проверялись отдельно и отбрасывались:
например, найденный Nomad capture — 30.01.2013, короткий Tengrinews URL —
26.01.2012. Печатная дата на зеркале их не превращает в pre-cutoff witnesses.
Современные comments/widgets и поздние поисковые результаты не вошли в inputs;
поздние библиографии служили только поиску старых URL. Исход конфликта не использован
для Mapping, перевода, подбора значений или допуска. В 18 квалифицирующих snapshots
датировка и digest проверены; для остальных inputs отсутствие поздних правок не доказано.

Все 21 frozen файла #121 и три предыдущих admission artifacts сохранены побайтно.
CP3 JSON/XLSX/ZIP, H1/H2, рубрики/старые keys, код, Core и формула не изменены.
48 factor response records и coder identity/submission остаются пустыми.
HUMAN coding, UNO, RGU/KVPTN и adjudication не выполнялись.

Оставшиеся единицы для человеческого review, без уже закрытых архивных задач:
[HUMAN_REVIEW_QUEUE.md](admission/ZHANAOZEN_2011_HISTORICAL_AVAILABILITY_RECOVERY_V1/HUMAN_REVIEW_QUEUE.md).
Остальные приложения: [контекст/атрибуция/переводы](admission/ZHANAOZEN_2011_HISTORICAL_AVAILABILITY_RECOVERY_V1/CONTEXT_ATTRIBUTION_TRANSLATION.json),
[журнал поиска](admission/ZHANAOZEN_2011_HISTORICAL_AVAILABILITY_RECOVERY_V1/SEARCH_LEDGER.json),
[проверки](admission/ZHANAOZEN_2011_HISTORICAL_AVAILABILITY_RECOVERY_V1/RECOVERY_CHECKS.json),
[freeze manifest](admission/ZHANAOZEN_2011_HISTORICAL_AVAILABILITY_RECOVERY_V1/FREEZE_MANIFEST.json).

**HOLD_DO_NOT_DISTRIBUTE. Остановка до HUMAN coding.** Изменение входов потребовало бы
отдельной разрешённой версии и freeze; текущий recovery annex не выдан людям и не
является новым coder packet.
