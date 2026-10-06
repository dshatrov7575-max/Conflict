# EXPERT_C_CLAUDE_FABLE_5_1

AI_EXCEPTION_REVIEW_V1 · standalone blind packet · PREPARED_NOT_RUN

Одинаковый фактический материал: SHA-256 `767da0d3f4fc189e587efd9084ea20ecb546f4f102c85e11f0153bc9d40a04fa` (canonical material + canonical units).

## Задание и границы

Это независимый AI exception review качества Evidence и привязок. Не выполняйте HUMAN coding, POS/KVS scoring, UNO, RGU/KVPTN, оценку модели или adjudication. Никакого ключа правильных ответов нет. Не назначайте числовой или категориальный ответ факторам; confidence ниже относится только к обоснованности вашего review.

Рассматривайте только 42 перечисленные единицы: 9 AVAILABILITY, 12 MAPPING и 21 TRANSLATION. Все цепочки и reference statements сохранены как объекты проверки, а не как доказанная истина. Исходные Fact имеют статус PROVISIONAL. Не перепривязывайте Fact/Fragment/DocumentVersion/Source и не сужайте frozen actor/reference/time, чтобы получить удобный вывод. Приложение содержит 20 версий только потому, что их фрагменты входят в эти задачи; для остальных 11 версий новой задачи availability нет.

Работайте в отдельном новом чате только с этим файлом, без общего проекта/памяти/предыдущих обсуждений. Не ищите другие экспертные пакеты, прежние отчёты, ключи, consensus или ответы другого эксперта. Не используйте исход конфликта, сведения после cutoff или собственную память об исходе. Cutoff: **2011-12-15T23:59:59Z**. Идентичность кейса не замаскирована; изоляция чата не устраняет знание из обучения модели. Если оно повлияло или в ходе поиска увиден исход, честно отметьте outcome_contamination_detected; не пересказывайте исход в ответе.

Для внешнего поиска используйте только точные названия/URL/фрагменты и исторические snapshots до cutoff, publisher archives, официальные зеркала и независимые preservation/custody witnesses. Не открывайте общие ретроспективы, комментарии/рекомендации современных страниц или поиски об исходе. Воспроизводимые URL/UUID, timestamp, locator, сохранённые bytes/hash и точный фрагмент обязательны для найденного доказательства. Хэш вычисляйте инструментом из реальных bytes/UTF-8, не придумывайте. Если инструмента/доступа нет, не объявляйте вопрос закрытым. Отсутствие результата поиска не является доказательством отсутствия исторического документа.

Дата публикации, печатная дата, PDF CreationDate, path /2011/ или нынешняя копия сами по себе не доказывают доступность конкретного текста до cutoff. Все frozen DocumentVersions записаны как captured_at 2026-08-24. Их capture files не предоставлены; записанный content_hash — идентификатор для проверки, не подтверждённые bytes. Совпадение только фрагмента означает PROVEN_FRAGMENT_PRE_CUTOFF и отдельный availability witness, а не тождество поздней редакции. PROVEN_PRE_CUTOFF допустим только при аутентификации всей конкретной frozen редакции. Для MONTH нельзя превратить первое число месяца в установленный день. Никакого rebinding задним числом.

В witness_records приложены только наблюдаемые archive URL/timestamp/digests и точные совпадения, без прежних выводов. Это проверяемые записи, не авторитетный ответ. Новое доказательство сохраняйте отдельно, указывая исходный target_id. Нынешние страницы разрешены лишь как указатели к архиву; их контекст нельзя молча считать историческим. Не копируйте целые статьи: используйте минимальную точную цитату для доказательства и locator.

## Что означает решение по единице

- RESOLVED: поставленный вопрос закрыт приведённым достаточным проверяемым доказательством; remaining_unknowns и material_issues пусты. Для availability достаточно всех выбранных exact fragments при явно ограниченном fragment scope; полная поздняя редакция при этом остаётся недоказанной и не входит в этот fragment claim. Только часть фрагментов — NOT_RESOLVED. Для mapping должны быть обоснованы все шесть dimensions в неизменном actor × element × reference × time. Это не требование вывести число POS/KVS: корректно определённая единица может впоследствии допускать UNKNOWN у кодера.
- NOT_RESOLVED: поиски/анализ не закрыли точный вопрос; перечислите недостающее и проверенные основания. Найденный дефект mapping не становится RESOLVED только потому, что дефект обнаружен.
- NEED_HUMAN: назовите конкретную проверку, требующую человека (например, недоступный custody record, языковая компетенция или неоднозначный мандат). Не назначайте человека и не начинайте его работу.

MAPPING: отдельно обоснуйте actor_attribution (кто говорит/действует и о ком), group_coverage (границы и представительство frozen группы), reference_coverage (релевантность точному R без приписывания позиции), time_coverage (дата события/высказывания и применимость к target time без предположения неизменности), chain_support (каждый Fact → Fragment → DocumentVersion → Source), context_sufficiency (достаточный окружающий исторический текст). Не подменяйте собственный голос актора внешней оценкой. Действие, статистика или участие в событии не дают автоматически мандат на всю группу. Отмечайте реальные противоречия как CONTRADICTED и описывайте их в material_issues.

TRANSLATION: выполните собственный русский перевод оригинала; прежний кандидат скрыт. Сохраните говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Объясните ключевые языковые решения в language_explanation; при недостатке контекста укажите оставшуюся неоднозначность. Не добавляйте в перевод actor exclusions или оценки из Fact/reference. Перевод может быть лингвистически разрешён, пока доступность источника остаётся отдельным открытым вопросом. Это AI-перевод, не HUMAN certification.

## Формат ответа

Верните один завершённый JSON по схеме ниже, все 42 answers, без markdown вокруг JSON. Сохраняйте local_id и target_id из пустой формы. Не оставляйте null в обязательных полях завершённого ответа. actual_model_label — фактически использованная модель/интерфейс (не выдумывайте версию); session_id — уникальная метка данного изолированного сеанса; completed_at_utc — фактическое время. Все attestations заполните правдиво; обнаруженную контаминацию нельзя скрывать ради допуска файла к сравнению.

У каждого ответа обязательны status, exact evidence, URL/UUID, reason, confidence [0,1], remaining_unknowns. Даже при NOT_RESOLVED приведите в evidence точный проверенный фрагмент/запись из приложения как недоказательную основу (decisive=false); отсутствие witness объясните отдельно. evidence_id — существующий Evidence UUID/witness_id либо NEW_WITNESS:<ваша метка>. quote_sha256 = SHA-256 точной строки exact_quote в UTF-8. payload_sha256 = hash реального сохранённого файла, не hash URL; при FROZEN_FRAGMENT без внешнего файла может быть null. preserved_at_utc — время независимой сохранности, не время нынешней загрузки, и null, если его нет. locator — страница/абзац/смещение с методом отсчёта. authentication_method объясняет проверку, а не только называет хэш. fragment_ids содержит только относящиеся к единице IDs. claim_scope задаёт точную доказанную область. supports_dimensions перечисляет dimensions, которые это доказательство поддерживает; для остальных видов — [].

Для decisive availability/mapping evidence требуется PRESERVATION_WITNESS не позднее cutoff; CURRENT_COPY и SEARCH_RECORD не закрывают их. В translation допустим FROZEN_FRAGMENT: его наличие в данном пакете не доказывает историческую доступность. Finding для неподходящих видов: availability=null, full_edition_identity_proven=false, mapping_dimensions=NOT_APPLICABLE, translation_ru/language_explanation=null. В MAPPING используйте SUPPORTED / NOT_ESTABLISHED / CONTRADICTED. Не заполняйте поля иных видов.

Приложенные пустые формы — заготовки, а не ответы. Не считайте заполненные служебные IDs и NOT_ESTABLISHED предварительным экспертным решением. Условие и формат одинаковы для всех независимых сеансов; алгоритм будущего голосования и другие ответы здесь не раскрываются.

## Единицы в случайном порядке

```json
[
  {
    "local_id": "Q01",
    "kind": "MAPPING",
    "target_id": "79748746-11e6-506c-82d5-bc5fe877beb0",
    "label": "GU08-E06",
    "fragment_ids": [
      "150704f4-c65a-50f4-b758-b9b456f909ff",
      "82d1bacf-3ed4-5b42-9d8c-7ee7cd105e94",
      "b344006d-0950-57af-b0e7-60eb7b4f5217"
    ],
    "fact_ids": [
      "5f708929-3f45-50d7-820d-2a72b84f83de",
      "6c268a9d-0b29-5274-98d2-6d3008ff459b",
      "e1bc2da7-5d64-5a43-b6ab-5ee9eea97b43"
    ],
    "target_time_utc": "2011-12-15T23:59:59Z",
    "question": "Проверьте неизменную привязку GU08-E06 во всех шести dimensions: actor attribution, group coverage, exact reference coverage, target-time coverage, каждую связанную Fact → Fragment → DocumentVersion → Source цепочку и контекст. Укажите точный источник, основание мандата/охвата и даты. Не присваивайте ответ POS/KVS."
  },
  {
    "local_id": "Q02",
    "kind": "TRANSLATION",
    "target_id": "6295e487-c225-5445-ae8b-653d1691579a",
    "label": "D21 / en",
    "fragment_ids": [
      "6295e487-c225-5445-ae8b-653d1691579a"
    ],
    "original_language": "en",
    "target_language": "ru",
    "question": "Выполните независимый перевод exact fragment на русский; проверьте говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Обоснуйте языковое решение исходным текстом и необходимым контекстом, не добавляя смысл из Fact/reference. Если точный смысл не установлен, перечислите неоднозначности."
  },
  {
    "local_id": "Q03",
    "kind": "AVAILABILITY",
    "target_id": "2d63f3f4-cb01-5b8c-b4ec-9bedb09b4363",
    "label": "D15",
    "fragment_ids": [
      "3832d42b-4806-56e6-8281-575100f9201b",
      "3c9cca86-6ba6-58ee-a6a1-b4c6aade6f54"
    ],
    "frozen_content_hash": "105f0a4475fd676a900c9d2686789a5f92a42eb246bc3626f312757fdaf1ad26",
    "question": "Найдите независимое preservation evidence доступности конкретного текста не позднее cutoff. Проверьте каждый выбранный exact fragment; различите полную frozen редакцию и отдельное свидетельство фрагмента. Дату публикации не используйте как доказательство. Сохраните frozen цепочки без rebinding."
  },
  {
    "local_id": "Q04",
    "kind": "AVAILABILITY",
    "target_id": "e92b6b89-4e75-5f64-ac26-7dd8005c3d56",
    "label": "D17",
    "fragment_ids": [
      "15e6b7e7-98f3-5830-8d5d-ae44862e445a",
      "51e5ac30-63a9-5433-8472-a22727f1db36"
    ],
    "frozen_content_hash": "ae9021062594bf5692b482841a39842034d940d987f613c030053a5f6b405a68",
    "question": "Найдите независимое preservation evidence доступности конкретного текста не позднее cutoff. Проверьте каждый выбранный exact fragment; различите полную frozen редакцию и отдельное свидетельство фрагмента. Дату публикации не используйте как доказательство. Сохраните frozen цепочки без rebinding."
  },
  {
    "local_id": "Q05",
    "kind": "TRANSLATION",
    "target_id": "2c47a771-1301-55be-a2ab-9b2ef1f82510",
    "label": "D09 / en",
    "fragment_ids": [
      "2c47a771-1301-55be-a2ab-9b2ef1f82510"
    ],
    "original_language": "en",
    "target_language": "ru",
    "question": "Выполните независимый перевод exact fragment на русский; проверьте говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Обоснуйте языковое решение исходным текстом и необходимым контекстом, не добавляя смысл из Fact/reference. Если точный смысл не установлен, перечислите неоднозначности."
  },
  {
    "local_id": "Q06",
    "kind": "TRANSLATION",
    "target_id": "a7869dd7-97d1-56de-86b4-aadf1e970c0a",
    "label": "D25 / en",
    "fragment_ids": [
      "a7869dd7-97d1-56de-86b4-aadf1e970c0a"
    ],
    "original_language": "en",
    "target_language": "ru",
    "question": "Выполните независимый перевод exact fragment на русский; проверьте говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Обоснуйте языковое решение исходным текстом и необходимым контекстом, не добавляя смысл из Fact/reference. Если точный смысл не установлен, перечислите неоднозначности."
  },
  {
    "local_id": "Q07",
    "kind": "TRANSLATION",
    "target_id": "150704f4-c65a-50f4-b758-b9b456f909ff",
    "label": "D20 / en",
    "fragment_ids": [
      "150704f4-c65a-50f4-b758-b9b456f909ff"
    ],
    "original_language": "en",
    "target_language": "ru",
    "question": "Выполните независимый перевод exact fragment на русский; проверьте говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Обоснуйте языковое решение исходным текстом и необходимым контекстом, не добавляя смысл из Fact/reference. Если точный смысл не установлен, перечислите неоднозначности."
  },
  {
    "local_id": "Q08",
    "kind": "TRANSLATION",
    "target_id": "56d19d98-707a-5deb-9472-d355b3835d79",
    "label": "D13 / en",
    "fragment_ids": [
      "56d19d98-707a-5deb-9472-d355b3835d79"
    ],
    "original_language": "en",
    "target_language": "ru",
    "question": "Выполните независимый перевод exact fragment на русский; проверьте говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Обоснуйте языковое решение исходным текстом и необходимым контекстом, не добавляя смысл из Fact/reference. Если точный смысл не установлен, перечислите неоднозначности."
  },
  {
    "local_id": "Q09",
    "kind": "TRANSLATION",
    "target_id": "51e5ac30-63a9-5433-8472-a22727f1db36",
    "label": "D17 / en",
    "fragment_ids": [
      "51e5ac30-63a9-5433-8472-a22727f1db36"
    ],
    "original_language": "en",
    "target_language": "ru",
    "question": "Выполните независимый перевод exact fragment на русский; проверьте говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Обоснуйте языковое решение исходным текстом и необходимым контекстом, не добавляя смысл из Fact/reference. Если точный смысл не установлен, перечислите неоднозначности."
  },
  {
    "local_id": "Q10",
    "kind": "TRANSLATION",
    "target_id": "ef7df23c-ba67-5903-9265-adbd1936ffa3",
    "label": "D25 / en",
    "fragment_ids": [
      "ef7df23c-ba67-5903-9265-adbd1936ffa3"
    ],
    "original_language": "en",
    "target_language": "ru",
    "question": "Выполните независимый перевод exact fragment на русский; проверьте говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Обоснуйте языковое решение исходным текстом и необходимым контекстом, не добавляя смысл из Fact/reference. Если точный смысл не установлен, перечислите неоднозначности."
  },
  {
    "local_id": "Q11",
    "kind": "TRANSLATION",
    "target_id": "d3e6a365-8150-545b-8005-c18c4939142b",
    "label": "D01 / en",
    "fragment_ids": [
      "d3e6a365-8150-545b-8005-c18c4939142b"
    ],
    "original_language": "en",
    "target_language": "ru",
    "question": "Выполните независимый перевод exact fragment на русский; проверьте говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Обоснуйте языковое решение исходным текстом и необходимым контекстом, не добавляя смысл из Fact/reference. Если точный смысл не установлен, перечислите неоднозначности."
  },
  {
    "local_id": "Q12",
    "kind": "MAPPING",
    "target_id": "092a3bde-2c62-5bae-a31d-b5c8751eb201",
    "label": "GU04-E04",
    "fragment_ids": [
      "d1067ad6-51d6-5a42-b6ea-8cf74c4fd71c",
      "f3130edc-588f-5f37-a88d-ffea7eca56c3",
      "facfa6e5-5707-5d1f-8a9e-a2386955211e"
    ],
    "fact_ids": [
      "94255747-5c61-51a9-892f-6a8d17cb3dee",
      "db691c24-5aa1-56b2-bc8a-da33ad1370ba",
      "fd69ed6e-d7ee-5dd2-a058-f10f0dac7429"
    ],
    "target_time_utc": "2011-12-15T23:59:59Z",
    "question": "Проверьте неизменную привязку GU04-E04 во всех шести dimensions: actor attribution, group coverage, exact reference coverage, target-time coverage, каждую связанную Fact → Fragment → DocumentVersion → Source цепочку и контекст. Укажите точный источник, основание мандата/охвата и даты. Не присваивайте ответ POS/KVS."
  },
  {
    "local_id": "Q13",
    "kind": "TRANSLATION",
    "target_id": "82d1bacf-3ed4-5b42-9d8c-7ee7cd105e94",
    "label": "D09 / en",
    "fragment_ids": [
      "82d1bacf-3ed4-5b42-9d8c-7ee7cd105e94"
    ],
    "original_language": "en",
    "target_language": "ru",
    "question": "Выполните независимый перевод exact fragment на русский; проверьте говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Обоснуйте языковое решение исходным текстом и необходимым контекстом, не добавляя смысл из Fact/reference. Если точный смысл не установлен, перечислите неоднозначности."
  },
  {
    "local_id": "Q14",
    "kind": "TRANSLATION",
    "target_id": "3ca46849-549e-544d-b72c-d62ef1706612",
    "label": "D25 / en",
    "fragment_ids": [
      "3ca46849-549e-544d-b72c-d62ef1706612"
    ],
    "original_language": "en",
    "target_language": "ru",
    "question": "Выполните независимый перевод exact fragment на русский; проверьте говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Обоснуйте языковое решение исходным текстом и необходимым контекстом, не добавляя смысл из Fact/reference. Если точный смысл не установлен, перечислите неоднозначности."
  },
  {
    "local_id": "Q15",
    "kind": "MAPPING",
    "target_id": "5e3146aa-0dfd-5be2-8f8d-39b94edee3ff",
    "label": "GU05-E04",
    "fragment_ids": [
      "3832d42b-4806-56e6-8281-575100f9201b",
      "3c9cca86-6ba6-58ee-a6a1-b4c6aade6f54",
      "7d82ddb5-b949-59af-90b3-3da2bc4691ad"
    ],
    "fact_ids": [
      "3a9fb283-1682-5dd5-9987-3efd5d5d95d7",
      "8591081b-af72-50fe-b017-c26625baacb1",
      "abecfa8f-31bb-57f0-8a9e-2496e9416609"
    ],
    "target_time_utc": "2011-12-15T23:59:59Z",
    "question": "Проверьте неизменную привязку GU05-E04 во всех шести dimensions: actor attribution, group coverage, exact reference coverage, target-time coverage, каждую связанную Fact → Fragment → DocumentVersion → Source цепочку и контекст. Укажите точный источник, основание мандата/охвата и даты. Не присваивайте ответ POS/KVS."
  },
  {
    "local_id": "Q16",
    "kind": "MAPPING",
    "target_id": "1abf6c8c-5295-5837-b75f-00c55daf3a8c",
    "label": "GU01-E02",
    "fragment_ids": [
      "15e6b7e7-98f3-5830-8d5d-ae44862e445a",
      "56d19d98-707a-5deb-9472-d355b3835d79",
      "cc839407-9eb7-5e05-acca-70f1577883d4",
      "d3e6a365-8150-545b-8005-c18c4939142b",
      "d521033f-59ce-5518-9227-b5fe9cb7570f"
    ],
    "fact_ids": [
      "a1aa979d-e0fe-51b3-8806-52d70351176b",
      "a208b943-38f3-5cd6-ad35-1f1de17a00e4",
      "b3f06151-26b2-5c65-bb42-17beab9f4ebf",
      "ddd0115a-c248-5be6-af50-ecc9c3eb26d5"
    ],
    "target_time_utc": "2011-12-15T23:59:59Z",
    "question": "Проверьте неизменную привязку GU01-E02 во всех шести dimensions: actor attribution, group coverage, exact reference coverage, target-time coverage, каждую связанную Fact → Fragment → DocumentVersion → Source цепочку и контекст. Укажите точный источник, основание мандата/охвата и даты. Не присваивайте ответ POS/KVS."
  },
  {
    "local_id": "Q17",
    "kind": "AVAILABILITY",
    "target_id": "9b1dfe95-b290-533c-9414-d8f18d880b1d",
    "label": "D29",
    "fragment_ids": [
      "b9981fe5-0c46-5bd0-91ad-1f2e8a1f2aff"
    ],
    "frozen_content_hash": "6ddd2bada0957498cd622a604d6f125113f2977f68915e5d6cc203776f558dcd",
    "question": "Найдите независимое preservation evidence доступности конкретного текста не позднее cutoff. Проверьте каждый выбранный exact fragment; различите полную frozen редакцию и отдельное свидетельство фрагмента. Дату публикации не используйте как доказательство. Сохраните frozen цепочки без rebinding."
  },
  {
    "local_id": "Q18",
    "kind": "TRANSLATION",
    "target_id": "d521033f-59ce-5518-9227-b5fe9cb7570f",
    "label": "D03 / en",
    "fragment_ids": [
      "d521033f-59ce-5518-9227-b5fe9cb7570f"
    ],
    "original_language": "en",
    "target_language": "ru",
    "question": "Выполните независимый перевод exact fragment на русский; проверьте говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Обоснуйте языковое решение исходным текстом и необходимым контекстом, не добавляя смысл из Fact/reference. Если точный смысл не установлен, перечислите неоднозначности."
  },
  {
    "local_id": "Q19",
    "kind": "MAPPING",
    "target_id": "3f4dc104-40c7-59db-ad5c-61f8a80232bc",
    "label": "GU04-E05",
    "fragment_ids": [
      "bbf0a151-afb1-57cd-9c19-cba3f5319e42",
      "d1067ad6-51d6-5a42-b6ea-8cf74c4fd71c"
    ],
    "fact_ids": [
      "daaf4605-8aa1-5463-876d-e32f561a0e1c",
      "db691c24-5aa1-56b2-bc8a-da33ad1370ba"
    ],
    "target_time_utc": "2011-12-15T23:59:59Z",
    "question": "Проверьте неизменную привязку GU04-E05 во всех шести dimensions: actor attribution, group coverage, exact reference coverage, target-time coverage, каждую связанную Fact → Fragment → DocumentVersion → Source цепочку и контекст. Укажите точный источник, основание мандата/охвата и даты. Не присваивайте ответ POS/KVS."
  },
  {
    "local_id": "Q20",
    "kind": "MAPPING",
    "target_id": "d0c7e8eb-6859-55ff-921a-f2e43e8f03d0",
    "label": "GU08-E05",
    "fragment_ids": [
      "150704f4-c65a-50f4-b758-b9b456f909ff",
      "2c47a771-1301-55be-a2ab-9b2ef1f82510",
      "82d1bacf-3ed4-5b42-9d8c-7ee7cd105e94"
    ],
    "fact_ids": [
      "064c967c-2147-5961-9bec-919fa695ef01",
      "5f708929-3f45-50d7-820d-2a72b84f83de",
      "e1bc2da7-5d64-5a43-b6ab-5ee9eea97b43"
    ],
    "target_time_utc": "2011-12-15T23:59:59Z",
    "question": "Проверьте неизменную привязку GU08-E05 во всех шести dimensions: actor attribution, group coverage, exact reference coverage, target-time coverage, каждую связанную Fact → Fragment → DocumentVersion → Source цепочку и контекст. Укажите точный источник, основание мандата/охвата и даты. Не присваивайте ответ POS/KVS."
  },
  {
    "local_id": "Q21",
    "kind": "AVAILABILITY",
    "target_id": "e85d2031-f492-5e93-b0ac-a7e84f27c7c7",
    "label": "D19",
    "fragment_ids": [
      "fcd2397b-c4e9-5035-9ff9-45969f55ecf4"
    ],
    "frozen_content_hash": "5a2c9a876ef8458620e84da179cfe25a300c7e795f09457c1223803f900dd42a",
    "question": "Найдите независимое preservation evidence доступности конкретного текста не позднее cutoff. Проверьте каждый выбранный exact fragment; различите полную frozen редакцию и отдельное свидетельство фрагмента. Дату публикации не используйте как доказательство. Сохраните frozen цепочки без rebinding."
  },
  {
    "local_id": "Q22",
    "kind": "AVAILABILITY",
    "target_id": "d2eefc78-82b0-5eb7-b1ae-533745cbbd79",
    "label": "D21",
    "fragment_ids": [
      "6295e487-c225-5445-ae8b-653d1691579a"
    ],
    "frozen_content_hash": "f37bed02661583fcd84a62c53ffb1a538adf18fdcc7fa4357170f74b013a04cc",
    "question": "Найдите независимое preservation evidence доступности конкретного текста не позднее cutoff. Проверьте каждый выбранный exact fragment; различите полную frozen редакцию и отдельное свидетельство фрагмента. Дату публикации не используйте как доказательство. Сохраните frozen цепочки без rebinding."
  },
  {
    "local_id": "Q23",
    "kind": "TRANSLATION",
    "target_id": "b5fdecb6-2ac4-5f56-aae6-6aef4bb7b956",
    "label": "D18 / en",
    "fragment_ids": [
      "b5fdecb6-2ac4-5f56-aae6-6aef4bb7b956"
    ],
    "original_language": "en",
    "target_language": "ru",
    "question": "Выполните независимый перевод exact fragment на русский; проверьте говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Обоснуйте языковое решение исходным текстом и необходимым контекстом, не добавляя смысл из Fact/reference. Если точный смысл не установлен, перечислите неоднозначности."
  },
  {
    "local_id": "Q24",
    "kind": "TRANSLATION",
    "target_id": "7f0b0752-387d-5def-ba3d-ab11c4f1414b",
    "label": "D04 / en",
    "fragment_ids": [
      "7f0b0752-387d-5def-ba3d-ab11c4f1414b"
    ],
    "original_language": "en",
    "target_language": "ru",
    "question": "Выполните независимый перевод exact fragment на русский; проверьте говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Обоснуйте языковое решение исходным текстом и необходимым контекстом, не добавляя смысл из Fact/reference. Если точный смысл не установлен, перечислите неоднозначности."
  },
  {
    "local_id": "Q25",
    "kind": "MAPPING",
    "target_id": "bc34ea72-a9ac-5e81-ab20-3f2efb729872",
    "label": "GU02-E05",
    "fragment_ids": [
      "15e6b7e7-98f3-5830-8d5d-ae44862e445a",
      "51e5ac30-63a9-5433-8472-a22727f1db36",
      "7f0b0752-387d-5def-ba3d-ab11c4f1414b"
    ],
    "fact_ids": [
      "4e55576e-cc85-5c77-adc4-b0d571b83502",
      "9e287255-de7d-5c16-9a21-291261933514",
      "c73a9fc6-181f-5a5a-84b3-f6885b4e77ce"
    ],
    "target_time_utc": "2011-12-15T23:59:59Z",
    "question": "Проверьте неизменную привязку GU02-E05 во всех шести dimensions: actor attribution, group coverage, exact reference coverage, target-time coverage, каждую связанную Fact → Fragment → DocumentVersion → Source цепочку и контекст. Укажите точный источник, основание мандата/охвата и даты. Не присваивайте ответ POS/KVS."
  },
  {
    "local_id": "Q26",
    "kind": "TRANSLATION",
    "target_id": "15e6b7e7-98f3-5830-8d5d-ae44862e445a",
    "label": "D17 / en",
    "fragment_ids": [
      "15e6b7e7-98f3-5830-8d5d-ae44862e445a"
    ],
    "original_language": "en",
    "target_language": "ru",
    "question": "Выполните независимый перевод exact fragment на русский; проверьте говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Обоснуйте языковое решение исходным текстом и необходимым контекстом, не добавляя смысл из Fact/reference. Если точный смысл не установлен, перечислите неоднозначности."
  },
  {
    "local_id": "Q27",
    "kind": "TRANSLATION",
    "target_id": "d1067ad6-51d6-5a42-b6ea-8cf74c4fd71c",
    "label": "D06 / kk",
    "fragment_ids": [
      "d1067ad6-51d6-5a42-b6ea-8cf74c4fd71c"
    ],
    "original_language": "kk",
    "target_language": "ru",
    "question": "Выполните независимый перевод exact fragment на русский; проверьте говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Обоснуйте языковое решение исходным текстом и необходимым контекстом, не добавляя смысл из Fact/reference. Если точный смысл не установлен, перечислите неоднозначности."
  },
  {
    "local_id": "Q28",
    "kind": "AVAILABILITY",
    "target_id": "26b9e671-5e1e-5460-a80c-2e803ca81ba6",
    "label": "D20",
    "fragment_ids": [
      "150704f4-c65a-50f4-b758-b9b456f909ff"
    ],
    "frozen_content_hash": "10c08f6e82a6adea0332429661d8abdab06f1d7a5b2d5b3db40107d2c83bb13d",
    "question": "Найдите независимое preservation evidence доступности конкретного текста не позднее cutoff. Проверьте каждый выбранный exact fragment; различите полную frozen редакцию и отдельное свидетельство фрагмента. Дату публикации не используйте как доказательство. Сохраните frozen цепочки без rebinding."
  },
  {
    "local_id": "Q29",
    "kind": "MAPPING",
    "target_id": "a6f0883a-d5fc-521b-8662-1c160fded750",
    "label": "GU07-E04",
    "fragment_ids": [
      "7d82ddb5-b949-59af-90b3-3da2bc4691ad",
      "ab55c516-12dc-5533-9e87-a950a6e61b3e",
      "b9981fe5-0c46-5bd0-91ad-1f2e8a1f2aff"
    ],
    "fact_ids": [
      "296ee01f-8379-5e8a-8cfb-d8b4b5e2deb0",
      "8591081b-af72-50fe-b017-c26625baacb1",
      "fa48d318-8754-5ee6-9880-b67273843e9a"
    ],
    "target_time_utc": "2011-12-15T23:59:59Z",
    "question": "Проверьте неизменную привязку GU07-E04 во всех шести dimensions: actor attribution, group coverage, exact reference coverage, target-time coverage, каждую связанную Fact → Fragment → DocumentVersion → Source цепочку и контекст. Укажите точный источник, основание мандата/охвата и даты. Не присваивайте ответ POS/KVS."
  },
  {
    "local_id": "Q30",
    "kind": "AVAILABILITY",
    "target_id": "02248e81-d235-5306-aef3-5dec2af93ebb",
    "label": "D23",
    "fragment_ids": [
      "7d82ddb5-b949-59af-90b3-3da2bc4691ad",
      "f3130edc-588f-5f37-a88d-ffea7eca56c3"
    ],
    "frozen_content_hash": "0e6a08c88995d51c55e14751f2f622feeb44bd136390ceb3cf246be0477be04c",
    "question": "Найдите независимое preservation evidence доступности конкретного текста не позднее cutoff. Проверьте каждый выбранный exact fragment; различите полную frozen редакцию и отдельное свидетельство фрагмента. Дату публикации не используйте как доказательство. Сохраните frozen цепочки без rebinding."
  },
  {
    "local_id": "Q31",
    "kind": "TRANSLATION",
    "target_id": "33ce2949-0da2-5839-9b01-566ae7e4bbf4",
    "label": "D18 / en",
    "fragment_ids": [
      "33ce2949-0da2-5839-9b01-566ae7e4bbf4"
    ],
    "original_language": "en",
    "target_language": "ru",
    "question": "Выполните независимый перевод exact fragment на русский; проверьте говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Обоснуйте языковое решение исходным текстом и необходимым контекстом, не добавляя смысл из Fact/reference. Если точный смысл не установлен, перечислите неоднозначности."
  },
  {
    "local_id": "Q32",
    "kind": "MAPPING",
    "target_id": "2c58ce09-3654-5a87-89be-4b1953f467c7",
    "label": "GU05-E02",
    "fragment_ids": [
      "3ca46849-549e-544d-b72c-d62ef1706612",
      "6295e487-c225-5445-ae8b-653d1691579a",
      "a7869dd7-97d1-56de-86b4-aadf1e970c0a"
    ],
    "fact_ids": [
      "6f26acf1-03dd-5731-a626-2c2c558b58cd",
      "9c6e13cb-60e5-595e-95ad-38ea95dc9f6e",
      "e00f9759-43f9-57a6-932c-412c24dc14ea"
    ],
    "target_time_utc": "2011-12-15T23:59:59Z",
    "question": "Проверьте неизменную привязку GU05-E02 во всех шести dimensions: actor attribution, group coverage, exact reference coverage, target-time coverage, каждую связанную Fact → Fragment → DocumentVersion → Source цепочку и контекст. Укажите точный источник, основание мандата/охвата и даты. Не присваивайте ответ POS/KVS."
  },
  {
    "local_id": "Q33",
    "kind": "TRANSLATION",
    "target_id": "cc839407-9eb7-5e05-acca-70f1577883d4",
    "label": "D03 / en",
    "fragment_ids": [
      "cc839407-9eb7-5e05-acca-70f1577883d4"
    ],
    "original_language": "en",
    "target_language": "ru",
    "question": "Выполните независимый перевод exact fragment на русский; проверьте говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Обоснуйте языковое решение исходным текстом и необходимым контекстом, не добавляя смысл из Fact/reference. Если точный смысл не установлен, перечислите неоднозначности."
  },
  {
    "local_id": "Q34",
    "kind": "TRANSLATION",
    "target_id": "b344006d-0950-57af-b0e7-60eb7b4f5217",
    "label": "D05 / en",
    "fragment_ids": [
      "b344006d-0950-57af-b0e7-60eb7b4f5217"
    ],
    "original_language": "en",
    "target_language": "ru",
    "question": "Выполните независимый перевод exact fragment на русский; проверьте говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Обоснуйте языковое решение исходным текстом и необходимым контекстом, не добавляя смысл из Fact/reference. Если точный смысл не установлен, перечислите неоднозначности."
  },
  {
    "local_id": "Q35",
    "kind": "MAPPING",
    "target_id": "cd9eb952-6af0-5708-8703-49673415cbe7",
    "label": "GU03-E06",
    "fragment_ids": [
      "04ab9fff-fe17-5b34-8733-f046d1b1ed06",
      "150704f4-c65a-50f4-b758-b9b456f909ff",
      "33ce2949-0da2-5839-9b01-566ae7e4bbf4",
      "82d1bacf-3ed4-5b42-9d8c-7ee7cd105e94",
      "fcd2397b-c4e9-5035-9ff9-45969f55ecf4"
    ],
    "fact_ids": [
      "136cb85c-abcb-5c65-a4ad-c118a560fca3",
      "5f708929-3f45-50d7-820d-2a72b84f83de",
      "a0955cfa-c21d-574b-9af0-abe5376d40de",
      "d206a449-91fa-558f-89ce-53eddd73be09"
    ],
    "target_time_utc": "2011-12-15T23:59:59Z",
    "question": "Проверьте неизменную привязку GU03-E06 во всех шести dimensions: actor attribution, group coverage, exact reference coverage, target-time coverage, каждую связанную Fact → Fragment → DocumentVersion → Source цепочку и контекст. Укажите точный источник, основание мандата/охвата и даты. Не присваивайте ответ POS/KVS."
  },
  {
    "local_id": "Q36",
    "kind": "MAPPING",
    "target_id": "951f300c-27d0-5a09-b312-e3fdad147f54",
    "label": "GU01-E06",
    "fragment_ids": [
      "04ab9fff-fe17-5b34-8733-f046d1b1ed06",
      "150704f4-c65a-50f4-b758-b9b456f909ff",
      "33ce2949-0da2-5839-9b01-566ae7e4bbf4",
      "82d1bacf-3ed4-5b42-9d8c-7ee7cd105e94",
      "b5fdecb6-2ac4-5f56-aae6-6aef4bb7b956"
    ],
    "fact_ids": [
      "136cb85c-abcb-5c65-a4ad-c118a560fca3",
      "5f708929-3f45-50d7-820d-2a72b84f83de",
      "98d4666a-d2e2-5fa3-817b-5ee545d9eda9",
      "a0955cfa-c21d-574b-9af0-abe5376d40de"
    ],
    "target_time_utc": "2011-12-15T23:59:59Z",
    "question": "Проверьте неизменную привязку GU01-E06 во всех шести dimensions: actor attribution, group coverage, exact reference coverage, target-time coverage, каждую связанную Fact → Fragment → DocumentVersion → Source цепочку и контекст. Укажите точный источник, основание мандата/охвата и даты. Не присваивайте ответ POS/KVS."
  },
  {
    "local_id": "Q37",
    "kind": "AVAILABILITY",
    "target_id": "3dcd5aa1-e2a9-5dd9-a2d9-992f9c80e835",
    "label": "D07",
    "fragment_ids": [
      "facfa6e5-5707-5d1f-8a9e-a2386955211e"
    ],
    "frozen_content_hash": "778d61386dbfd8044eab009c204df0e0744bf90781898c4484d79d284fbadaa6",
    "question": "Найдите независимое preservation evidence доступности конкретного текста не позднее cutoff. Проверьте каждый выбранный exact fragment; различите полную frozen редакцию и отдельное свидетельство фрагмента. Дату публикации не используйте как доказательство. Сохраните frozen цепочки без rebinding."
  },
  {
    "local_id": "Q38",
    "kind": "AVAILABILITY",
    "target_id": "d3b8d52c-3dbb-5d07-84bd-e07acf35fbbb",
    "label": "D24",
    "fragment_ids": [
      "bbf0a151-afb1-57cd-9c19-cba3f5319e42"
    ],
    "frozen_content_hash": "74b2caeaccf08d4d3a91c3f8108c0d20b210d5881b4638f0b234811fdba7448b",
    "question": "Найдите независимое preservation evidence доступности конкретного текста не позднее cutoff. Проверьте каждый выбранный exact fragment; различите полную frozen редакцию и отдельное свидетельство фрагмента. Дату публикации не используйте как доказательство. Сохраните frozen цепочки без rebinding."
  },
  {
    "local_id": "Q39",
    "kind": "MAPPING",
    "target_id": "3fba0d88-4c72-5d24-b879-52904c88a0e5",
    "label": "GU03-E02",
    "fragment_ids": [
      "49c356b3-3585-587c-9573-d4326e97de77",
      "56d19d98-707a-5deb-9472-d355b3835d79",
      "ef7df23c-ba67-5903-9265-adbd1936ffa3"
    ],
    "fact_ids": [
      "ddd0115a-c248-5be6-af50-ecc9c3eb26d5",
      "f1354988-add2-5149-938a-4f6a4221d4f1",
      "f25ddd8f-0810-5fdc-97cb-647c9d38074f"
    ],
    "target_time_utc": "2011-12-15T23:59:59Z",
    "question": "Проверьте неизменную привязку GU03-E02 во всех шести dimensions: actor attribution, group coverage, exact reference coverage, target-time coverage, каждую связанную Fact → Fragment → DocumentVersion → Source цепочку и контекст. Укажите точный источник, основание мандата/охвата и даты. Не присваивайте ответ POS/KVS."
  },
  {
    "local_id": "Q40",
    "kind": "TRANSLATION",
    "target_id": "49c356b3-3585-587c-9573-d4326e97de77",
    "label": "D14 / en",
    "fragment_ids": [
      "49c356b3-3585-587c-9573-d4326e97de77"
    ],
    "original_language": "en",
    "target_language": "ru",
    "question": "Выполните независимый перевод exact fragment на русский; проверьте говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Обоснуйте языковое решение исходным текстом и необходимым контекстом, не добавляя смысл из Fact/reference. Если точный смысл не установлен, перечислите неоднозначности."
  },
  {
    "local_id": "Q41",
    "kind": "TRANSLATION",
    "target_id": "04ab9fff-fe17-5b34-8733-f046d1b1ed06",
    "label": "D05 / en",
    "fragment_ids": [
      "04ab9fff-fe17-5b34-8733-f046d1b1ed06"
    ],
    "original_language": "en",
    "target_language": "ru",
    "question": "Выполните независимый перевод exact fragment на русский; проверьте говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Обоснуйте языковое решение исходным текстом и необходимым контекстом, не добавляя смысл из Fact/reference. Если точный смысл не установлен, перечислите неоднозначности."
  },
  {
    "local_id": "Q42",
    "kind": "TRANSLATION",
    "target_id": "fcd2397b-c4e9-5035-9ff9-45969f55ecf4",
    "label": "D19 / en",
    "fragment_ids": [
      "fcd2397b-c4e9-5035-9ff9-45969f55ecf4"
    ],
    "original_language": "en",
    "target_language": "ru",
    "question": "Выполните независимый перевод exact fragment на русский; проверьте говорящего, отрицание, модальность, интенсивность, кванторы, групповой и временной охват. Обоснуйте языковое решение исходным текстом и необходимым контекстом, не добавляя смысл из Fact/reference. Если точный смысл не установлен, перечислите неоднозначности."
  }
]
```

## Общий фактический материал и provenance

```json
{
  "cutoff_utc": "2011-12-15T23:59:59Z",
  "coding_items": [
    {
      "coding_item_id": "092a3bde-2c62-5bae-a31d-b5c8751eb201",
      "actor_id": "744feea3-d4d4-5a3c-9d65-394894389e67",
      "actor_code": "KZ.ZHANAOZEN.ACTOR.GU04",
      "actor_name": "Жители территории вне нефтегазовых трудовых групп",
      "element_id": "2fecb360-274b-55da-a7d4-6020a87de286",
      "element_code": "KZ.ZHANAOZEN.ELEMENT.E04",
      "element_name": "Доступ местных жителей к нефтегазовой занятости",
      "time_slice_id": "434c73fa-abfb-54f1-85cf-821431bf098b",
      "cutoff_date": "2011-12-15",
      "reference_statement": "Существующий доступ местных жителей к нефтегазовым рабочим местам достаточен и не требует существенного расширения."
    },
    {
      "coding_item_id": "1abf6c8c-5295-5837-b75f-00c55daf3a8c",
      "actor_id": "d31904bd-a9e2-52bc-886d-d959d8e6f86d",
      "actor_code": "KZ.ZHANAOZEN.ACTOR.GU01",
      "actor_name": "Работники основных нефтегазовых предприятий",
      "element_id": "74872afd-9303-5d0f-a70a-d5fe7154645c",
      "element_code": "KZ.ZHANAOZEN.ELEMENT.E02",
      "element_name": "Оплата труда и социальные гарантии в нефтегазовом секторе",
      "time_slice_id": "434c73fa-abfb-54f1-85cf-821431bf098b",
      "cutoff_date": "2011-12-15",
      "reference_statement": "Существующий порядок оплаты и социальных гарантий работников нефтегазового сектора является приемлемым и не требует существенного изменения."
    },
    {
      "coding_item_id": "2c58ce09-3654-5a87-89be-4b1953f467c7",
      "actor_id": "d803888d-ec24-5c7e-905b-96f88d01c36f",
      "actor_code": "KZ.ZHANAOZEN.ACTOR.GU05",
      "actor_name": "Работодатели нефтегазового сектора и подрядного контура",
      "element_id": "74872afd-9303-5d0f-a70a-d5fe7154645c",
      "element_code": "KZ.ZHANAOZEN.ELEMENT.E02",
      "element_name": "Оплата труда и социальные гарантии в нефтегазовом секторе",
      "time_slice_id": "434c73fa-abfb-54f1-85cf-821431bf098b",
      "cutoff_date": "2011-12-15",
      "reference_statement": "Существующий порядок оплаты и социальных гарантий работников нефтегазового сектора является приемлемым и не требует существенного изменения."
    },
    {
      "coding_item_id": "3f4dc104-40c7-59db-ad5c-61f8a80232bc",
      "actor_id": "744feea3-d4d4-5a3c-9d65-394894389e67",
      "actor_code": "KZ.ZHANAOZEN.ACTOR.GU04",
      "actor_name": "Жители территории вне нефтегазовых трудовых групп",
      "element_id": "728c8406-ba99-5787-9557-933b5670be7c",
      "element_code": "KZ.ZHANAOZEN.ELEMENT.E05",
      "element_name": "Представительство интересов и доступ к коллективным переговорам",
      "time_slice_id": "434c73fa-abfb-54f1-85cf-821431bf098b",
      "cutoff_date": "2011-12-15",
      "reference_statement": "Существующие механизмы представительства, переговоров и коллективных действий обеспечивают достаточный доступ к выражению и согласованию интересов."
    },
    {
      "coding_item_id": "3fba0d88-4c72-5d24-b879-52904c88a0e5",
      "actor_id": "6e5f84f6-8988-5e72-8fbd-bf67d4c8bb45",
      "actor_code": "KZ.ZHANAOZEN.ACTOR.GU03",
      "actor_name": "Уволенные и соискатели нефтегазовой занятости",
      "element_id": "74872afd-9303-5d0f-a70a-d5fe7154645c",
      "element_code": "KZ.ZHANAOZEN.ELEMENT.E02",
      "element_name": "Оплата труда и социальные гарантии в нефтегазовом секторе",
      "time_slice_id": "434c73fa-abfb-54f1-85cf-821431bf098b",
      "cutoff_date": "2011-12-15",
      "reference_statement": "Существующий порядок оплаты и социальных гарантий работников нефтегазового сектора является приемлемым и не требует существенного изменения."
    },
    {
      "coding_item_id": "5e3146aa-0dfd-5be2-8f8d-39b94edee3ff",
      "actor_id": "d803888d-ec24-5c7e-905b-96f88d01c36f",
      "actor_code": "KZ.ZHANAOZEN.ACTOR.GU05",
      "actor_name": "Работодатели нефтегазового сектора и подрядного контура",
      "element_id": "2fecb360-274b-55da-a7d4-6020a87de286",
      "element_code": "KZ.ZHANAOZEN.ELEMENT.E04",
      "element_name": "Доступ местных жителей к нефтегазовой занятости",
      "time_slice_id": "434c73fa-abfb-54f1-85cf-821431bf098b",
      "cutoff_date": "2011-12-15",
      "reference_statement": "Существующий доступ местных жителей к нефтегазовым рабочим местам достаточен и не требует существенного расширения."
    },
    {
      "coding_item_id": "79748746-11e6-506c-82d5-bc5fe877beb0",
      "actor_id": "6782018f-1868-5aa7-b40e-fb5ad11269ca",
      "actor_code": "KZ.ZHANAOZEN.ACTOR.GU08",
      "actor_name": "Правоохранительные, судебные и надзорные органы",
      "element_id": "0ca209e6-ca1a-5751-b27e-cbd0d180ffa9",
      "element_code": "KZ.ZHANAOZEN.ELEMENT.E06",
      "element_name": "Государственное принуждение и правовые процедуры в конфликте",
      "time_slice_id": "434c73fa-abfb-54f1-85cf-821431bf098b",
      "cutoff_date": "2011-12-15",
      "reference_statement": "Существующие правоохранительные и судебные процедуры реагирования на трудовой конфликт достаточны и соразмерны с точки зрения данного актора."
    },
    {
      "coding_item_id": "951f300c-27d0-5a09-b312-e3fdad147f54",
      "actor_id": "d31904bd-a9e2-52bc-886d-d959d8e6f86d",
      "actor_code": "KZ.ZHANAOZEN.ACTOR.GU01",
      "actor_name": "Работники основных нефтегазовых предприятий",
      "element_id": "0ca209e6-ca1a-5751-b27e-cbd0d180ffa9",
      "element_code": "KZ.ZHANAOZEN.ELEMENT.E06",
      "element_name": "Государственное принуждение и правовые процедуры в конфликте",
      "time_slice_id": "434c73fa-abfb-54f1-85cf-821431bf098b",
      "cutoff_date": "2011-12-15",
      "reference_statement": "Существующие правоохранительные и судебные процедуры реагирования на трудовой конфликт достаточны и соразмерны с точки зрения данного актора."
    },
    {
      "coding_item_id": "a6f0883a-d5fc-521b-8662-1c160fded750",
      "actor_id": "fd80f79b-7c39-58db-b122-7245b77ff0c5",
      "actor_code": "KZ.ZHANAOZEN.ACTOR.GU07",
      "actor_name": "Центральные органы государственной власти",
      "element_id": "2fecb360-274b-55da-a7d4-6020a87de286",
      "element_code": "KZ.ZHANAOZEN.ELEMENT.E04",
      "element_name": "Доступ местных жителей к нефтегазовой занятости",
      "time_slice_id": "434c73fa-abfb-54f1-85cf-821431bf098b",
      "cutoff_date": "2011-12-15",
      "reference_statement": "Существующий доступ местных жителей к нефтегазовым рабочим местам достаточен и не требует существенного расширения."
    },
    {
      "coding_item_id": "bc34ea72-a9ac-5e81-ab20-3f2efb729872",
      "actor_id": "4c215889-7a31-56ae-8a60-cc546c915241",
      "actor_code": "KZ.ZHANAOZEN.ACTOR.GU02",
      "actor_name": "Работники подрядных и нефтесервисных организаций",
      "element_id": "728c8406-ba99-5787-9557-933b5670be7c",
      "element_code": "KZ.ZHANAOZEN.ELEMENT.E05",
      "element_name": "Представительство интересов и доступ к коллективным переговорам",
      "time_slice_id": "434c73fa-abfb-54f1-85cf-821431bf098b",
      "cutoff_date": "2011-12-15",
      "reference_statement": "Существующие механизмы представительства, переговоров и коллективных действий обеспечивают достаточный доступ к выражению и согласованию интересов."
    },
    {
      "coding_item_id": "cd9eb952-6af0-5708-8703-49673415cbe7",
      "actor_id": "6e5f84f6-8988-5e72-8fbd-bf67d4c8bb45",
      "actor_code": "KZ.ZHANAOZEN.ACTOR.GU03",
      "actor_name": "Уволенные и соискатели нефтегазовой занятости",
      "element_id": "0ca209e6-ca1a-5751-b27e-cbd0d180ffa9",
      "element_code": "KZ.ZHANAOZEN.ELEMENT.E06",
      "element_name": "Государственное принуждение и правовые процедуры в конфликте",
      "time_slice_id": "434c73fa-abfb-54f1-85cf-821431bf098b",
      "cutoff_date": "2011-12-15",
      "reference_statement": "Существующие правоохранительные и судебные процедуры реагирования на трудовой конфликт достаточны и соразмерны с точки зрения данного актора."
    },
    {
      "coding_item_id": "d0c7e8eb-6859-55ff-921a-f2e43e8f03d0",
      "actor_id": "6782018f-1868-5aa7-b40e-fb5ad11269ca",
      "actor_code": "KZ.ZHANAOZEN.ACTOR.GU08",
      "actor_name": "Правоохранительные, судебные и надзорные органы",
      "element_id": "728c8406-ba99-5787-9557-933b5670be7c",
      "element_code": "KZ.ZHANAOZEN.ELEMENT.E05",
      "element_name": "Представительство интересов и доступ к коллективным переговорам",
      "time_slice_id": "434c73fa-abfb-54f1-85cf-821431bf098b",
      "cutoff_date": "2011-12-15",
      "reference_statement": "Существующие механизмы представительства, переговоров и коллективных действий обеспечивают достаточный доступ к выражению и согласованию интересов."
    }
  ],
  "actors": [
    {
      "actor_id": "4c215889-7a31-56ae-8a60-cc546c915241",
      "code": "KZ.ZHANAOZEN.ACTOR.GU02",
      "display_name": "Работники подрядных и нефтесервисных организаций",
      "actor_type": "SOCIAL_GROUP",
      "notes": "Подрядчики, субподрядчики, нефтесервис и транспортно-сервисный контур."
    },
    {
      "actor_id": "6782018f-1868-5aa7-b40e-fb5ad11269ca",
      "code": "KZ.ZHANAOZEN.ACTOR.GU08",
      "display_name": "Правоохранительные, судебные и надзорные органы",
      "actor_type": "PUBLIC_AUTHORITY_GROUP",
      "notes": "Конкретные органы сохраняются раздельно в evidence, даже если агрегируются как actor group."
    },
    {
      "actor_id": "6e5f84f6-8988-5e72-8fbd-bf67d4c8bb45",
      "code": "KZ.ZHANAOZEN.ACTOR.GU03",
      "display_name": "Уволенные и соискатели нефтегазовой занятости",
      "actor_type": "SOCIAL_GROUP",
      "notes": "Уволенные, бывшие работники и местные соискатели рабочих мест."
    },
    {
      "actor_id": "744feea3-d4d4-5a3c-9d65-394894389e67",
      "code": "KZ.ZHANAOZEN.ACTOR.GU04",
      "display_name": "Жители территории вне нефтегазовых трудовых групп",
      "actor_type": "SOCIAL_GROUP",
      "notes": "Агрегированная социальная группа; использовать консервативную уверенность."
    },
    {
      "actor_id": "d31904bd-a9e2-52bc-886d-d959d8e6f86d",
      "code": "KZ.ZHANAOZEN.ACTOR.GU01",
      "display_name": "Работники основных нефтегазовых предприятий",
      "actor_type": "SOCIAL_GROUP",
      "notes": "Не включает работников подрядчиков."
    },
    {
      "actor_id": "d803888d-ec24-5c7e-905b-96f88d01c36f",
      "code": "KZ.ZHANAOZEN.ACTOR.GU05",
      "display_name": "Работодатели нефтегазового сектора и подрядного контура",
      "actor_type": "ORGANIZATIONAL_ACTOR_GROUP",
      "notes": "Руководство основных компаний, подрядчиков и сервисных организаций."
    },
    {
      "actor_id": "fd80f79b-7c39-58db-b122-7245b77ff0c5",
      "code": "KZ.ZHANAOZEN.ACTOR.GU07",
      "display_name": "Центральные органы государственной власти",
      "actor_type": "PUBLIC_AUTHORITY_GROUP",
      "notes": "Правительство, профильные министерства и иные центральные органы."
    }
  ],
  "analytical_elements": [
    {
      "element_id": "0ca209e6-ca1a-5751-b27e-cbd0d180ffa9",
      "code": "KZ.ZHANAOZEN.ELEMENT.E06",
      "element_type": "INSTITUTIONAL_RESPONSE",
      "display_name": "Государственное принуждение и правовые процедуры в конфликте",
      "reference_statement": "Существующие правоохранительные и судебные процедуры реагирования на трудовой конфликт достаточны и соразмерны с точки зрения данного актора."
    },
    {
      "element_id": "2fecb360-274b-55da-a7d4-6020a87de286",
      "code": "KZ.ZHANAOZEN.ELEMENT.E04",
      "element_type": "STRUCTURAL_DRIVER",
      "display_name": "Доступ местных жителей к нефтегазовой занятости",
      "reference_statement": "Существующий доступ местных жителей к нефтегазовым рабочим местам достаточен и не требует существенного расширения."
    },
    {
      "element_id": "728c8406-ba99-5787-9557-933b5670be7c",
      "code": "KZ.ZHANAOZEN.ELEMENT.E05",
      "element_type": "PROCESS",
      "display_name": "Представительство интересов и доступ к коллективным переговорам",
      "reference_statement": "Существующие механизмы представительства, переговоров и коллективных действий обеспечивают достаточный доступ к выражению и согласованию интересов."
    },
    {
      "element_id": "74872afd-9303-5d0f-a70a-d5fe7154645c",
      "code": "KZ.ZHANAOZEN.ELEMENT.E02",
      "element_type": "CONFLICT_ISSUE",
      "display_name": "Оплата труда и социальные гарантии в нефтегазовом секторе",
      "reference_statement": "Существующий порядок оплаты и социальных гарантий работников нефтегазового сектора является приемлемым и не требует существенного изменения."
    }
  ],
  "time_slices": [
    {
      "time_slice_id": "434c73fa-abfb-54f1-85cf-821431bf098b",
      "label": "Жанаозен — contemporaneous slice 2011",
      "cutoff_date": "2011-12-15",
      "knowledge_mode": "CONTEMPORANEOUS"
    }
  ],
  "coding_item_fact_links": [
    {
      "link_id": "02d40bd0-2dfa-588c-b8ee-7cc056d6a1db",
      "coding_item_id": "a6f0883a-d5fc-521b-8662-1c160fded750",
      "fact_id": "8591081b-af72-50fe-b017-c26625baacb1",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "043f00d5-a034-5c7a-8ec5-a2b20e8a5ee6",
      "coding_item_id": "3f4dc104-40c7-59db-ad5c-61f8a80232bc",
      "fact_id": "db691c24-5aa1-56b2-bc8a-da33ad1370ba",
      "role": "PRIMARY_SUPPORT"
    },
    {
      "link_id": "06e56a70-44d2-5797-9b26-59e64facfb66",
      "coding_item_id": "951f300c-27d0-5a09-b312-e3fdad147f54",
      "fact_id": "a0955cfa-c21d-574b-9af0-abe5376d40de",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "0e5871e6-afef-53f7-a8cd-95170b45641d",
      "coding_item_id": "bc34ea72-a9ac-5e81-ab20-3f2efb729872",
      "fact_id": "9e287255-de7d-5c16-9a21-291261933514",
      "role": "PRIMARY_SUPPORT"
    },
    {
      "link_id": "1366d429-3f5b-5dd4-b4f6-d301aa2855e4",
      "coding_item_id": "a6f0883a-d5fc-521b-8662-1c160fded750",
      "fact_id": "fa48d318-8754-5ee6-9880-b67273843e9a",
      "role": "PRIMARY_SUPPORT"
    },
    {
      "link_id": "1651b5fe-79f9-5664-b62a-66645053b438",
      "coding_item_id": "79748746-11e6-506c-82d5-bc5fe877beb0",
      "fact_id": "e1bc2da7-5d64-5a43-b6ab-5ee9eea97b43",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "1c1e9eb1-877e-5153-83eb-b6c4bdc3b44e",
      "coding_item_id": "cd9eb952-6af0-5708-8703-49673415cbe7",
      "fact_id": "a0955cfa-c21d-574b-9af0-abe5376d40de",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "2594c60f-a911-5390-aeb0-6fbf87ef0f4e",
      "coding_item_id": "79748746-11e6-506c-82d5-bc5fe877beb0",
      "fact_id": "5f708929-3f45-50d7-820d-2a72b84f83de",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "4038e6a1-ee3e-5f9d-b14c-761e18d97912",
      "coding_item_id": "d0c7e8eb-6859-55ff-921a-f2e43e8f03d0",
      "fact_id": "5f708929-3f45-50d7-820d-2a72b84f83de",
      "role": "PRIMARY_SUPPORT"
    },
    {
      "link_id": "4ec3f71f-cfb7-5e74-b62a-1d4a4fa2c5d5",
      "coding_item_id": "5e3146aa-0dfd-5be2-8f8d-39b94edee3ff",
      "fact_id": "abecfa8f-31bb-57f0-8a9e-2496e9416609",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "54c952ba-0c40-5494-8592-545e5e50cb08",
      "coding_item_id": "1abf6c8c-5295-5837-b75f-00c55daf3a8c",
      "fact_id": "ddd0115a-c248-5be6-af50-ecc9c3eb26d5",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "5c92a9d9-4637-55d1-ab1b-1683cee85f3c",
      "coding_item_id": "951f300c-27d0-5a09-b312-e3fdad147f54",
      "fact_id": "5f708929-3f45-50d7-820d-2a72b84f83de",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "668afc2a-ce63-51f4-a475-8f3db1cdd99c",
      "coding_item_id": "092a3bde-2c62-5bae-a31d-b5c8751eb201",
      "fact_id": "94255747-5c61-51a9-892f-6a8d17cb3dee",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "69155ce0-39b6-5416-acbc-79d4081e059e",
      "coding_item_id": "092a3bde-2c62-5bae-a31d-b5c8751eb201",
      "fact_id": "fd69ed6e-d7ee-5dd2-a058-f10f0dac7429",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "69615021-a032-501c-8055-af9631b47f90",
      "coding_item_id": "bc34ea72-a9ac-5e81-ab20-3f2efb729872",
      "fact_id": "c73a9fc6-181f-5a5a-84b3-f6885b4e77ce",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "72996190-93cb-5413-93a8-941a885d12ed",
      "coding_item_id": "3f4dc104-40c7-59db-ad5c-61f8a80232bc",
      "fact_id": "daaf4605-8aa1-5463-876d-e32f561a0e1c",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "743eb695-9df3-5557-addc-759ff726af5c",
      "coding_item_id": "1abf6c8c-5295-5837-b75f-00c55daf3a8c",
      "fact_id": "a208b943-38f3-5cd6-ad35-1f1de17a00e4",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "80067969-da12-5ccd-8f3a-dbe2bb28930c",
      "coding_item_id": "1abf6c8c-5295-5837-b75f-00c55daf3a8c",
      "fact_id": "a1aa979d-e0fe-51b3-8806-52d70351176b",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "822e4a06-7a43-5912-aabc-ca2e67001e95",
      "coding_item_id": "1abf6c8c-5295-5837-b75f-00c55daf3a8c",
      "fact_id": "b3f06151-26b2-5c65-bb42-17beab9f4ebf",
      "role": "PRIMARY_SUPPORT"
    },
    {
      "link_id": "82af7ff0-bd54-5d7b-abf6-cf13a77324e2",
      "coding_item_id": "d0c7e8eb-6859-55ff-921a-f2e43e8f03d0",
      "fact_id": "064c967c-2147-5961-9bec-919fa695ef01",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "a0b4f08c-150f-582a-abf2-7742dec34c20",
      "coding_item_id": "3fba0d88-4c72-5d24-b879-52904c88a0e5",
      "fact_id": "f1354988-add2-5149-938a-4f6a4221d4f1",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "afe8009e-c16d-5bb3-bc97-633e2bc109b8",
      "coding_item_id": "d0c7e8eb-6859-55ff-921a-f2e43e8f03d0",
      "fact_id": "e1bc2da7-5d64-5a43-b6ab-5ee9eea97b43",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "b933bed3-fc16-527a-9f96-bb240f337320",
      "coding_item_id": "2c58ce09-3654-5a87-89be-4b1953f467c7",
      "fact_id": "e00f9759-43f9-57a6-932c-412c24dc14ea",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "bc4770a0-3ef8-5d4b-96dd-8b925db4aab3",
      "coding_item_id": "3fba0d88-4c72-5d24-b879-52904c88a0e5",
      "fact_id": "f25ddd8f-0810-5fdc-97cb-647c9d38074f",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "bc50dd89-1a14-53cb-a50c-b906b5e8ae30",
      "coding_item_id": "bc34ea72-a9ac-5e81-ab20-3f2efb729872",
      "fact_id": "4e55576e-cc85-5c77-adc4-b0d571b83502",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "bf7a147c-6dec-5305-bffa-7ec7c6863802",
      "coding_item_id": "092a3bde-2c62-5bae-a31d-b5c8751eb201",
      "fact_id": "db691c24-5aa1-56b2-bc8a-da33ad1370ba",
      "role": "PRIMARY_SUPPORT"
    },
    {
      "link_id": "c605ee71-740a-5232-97d0-bf5b700a3b93",
      "coding_item_id": "951f300c-27d0-5a09-b312-e3fdad147f54",
      "fact_id": "98d4666a-d2e2-5fa3-817b-5ee545d9eda9",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "c762d3db-99a1-5bf3-8e2e-2bd46b568253",
      "coding_item_id": "cd9eb952-6af0-5708-8703-49673415cbe7",
      "fact_id": "136cb85c-abcb-5c65-a4ad-c118a560fca3",
      "role": "PRIMARY_SUPPORT"
    },
    {
      "link_id": "cb821c7d-09c8-5231-b4bf-4c559bf44d6e",
      "coding_item_id": "951f300c-27d0-5a09-b312-e3fdad147f54",
      "fact_id": "136cb85c-abcb-5c65-a4ad-c118a560fca3",
      "role": "PRIMARY_SUPPORT"
    },
    {
      "link_id": "d5dda83a-2cf0-5b6a-9623-895cb4e8189a",
      "coding_item_id": "5e3146aa-0dfd-5be2-8f8d-39b94edee3ff",
      "fact_id": "3a9fb283-1682-5dd5-9987-3efd5d5d95d7",
      "role": "PRIMARY_SUPPORT"
    },
    {
      "link_id": "db567463-8e6c-5c8c-ae34-3824772e9f36",
      "coding_item_id": "cd9eb952-6af0-5708-8703-49673415cbe7",
      "fact_id": "5f708929-3f45-50d7-820d-2a72b84f83de",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "e83d76b4-ec9e-5f11-96a1-4c9637e39959",
      "coding_item_id": "5e3146aa-0dfd-5be2-8f8d-39b94edee3ff",
      "fact_id": "8591081b-af72-50fe-b017-c26625baacb1",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "f0fdc14f-71ae-5448-a1b0-7637eee65236",
      "coding_item_id": "79748746-11e6-506c-82d5-bc5fe877beb0",
      "fact_id": "6c268a9d-0b29-5274-98d2-6d3008ff459b",
      "role": "PRIMARY_SUPPORT"
    },
    {
      "link_id": "f121001b-af69-5186-ac1d-c83898bb5508",
      "coding_item_id": "2c58ce09-3654-5a87-89be-4b1953f467c7",
      "fact_id": "6f26acf1-03dd-5731-a626-2c2c558b58cd",
      "role": "PRIMARY_SUPPORT"
    },
    {
      "link_id": "f6381f5d-0131-5b9a-a39e-102dc5765c90",
      "coding_item_id": "3fba0d88-4c72-5d24-b879-52904c88a0e5",
      "fact_id": "ddd0115a-c248-5be6-af50-ecc9c3eb26d5",
      "role": "PRIMARY_SUPPORT"
    },
    {
      "link_id": "f97b4eec-7121-5d83-a227-2f0daa7393f9",
      "coding_item_id": "2c58ce09-3654-5a87-89be-4b1953f467c7",
      "fact_id": "9c6e13cb-60e5-595e-95ad-38ea95dc9f6e",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "fb7d55b5-4c08-5949-b437-6520476d5c34",
      "coding_item_id": "cd9eb952-6af0-5708-8703-49673415cbe7",
      "fact_id": "d206a449-91fa-558f-89ce-53eddd73be09",
      "role": "SECONDARY_SUPPORT"
    },
    {
      "link_id": "fbcb1210-a5b1-5275-a487-50fe1901e1f0",
      "coding_item_id": "a6f0883a-d5fc-521b-8662-1c160fded750",
      "fact_id": "296ee01f-8379-5e8a-8cfb-d8b4b5e2deb0",
      "role": "SECONDARY_SUPPORT"
    }
  ],
  "fact_fragment_links": [
    {
      "link_id": "06771a8f-8172-51a4-aed0-806c820c328f",
      "fact_id": "98d4666a-d2e2-5fa3-817b-5ee545d9eda9",
      "fragment_id": "b5fdecb6-2ac4-5f56-aae6-6aef4bb7b956",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "0a80d046-9dd0-58ac-b1df-41508cb34b5a",
      "fact_id": "a0955cfa-c21d-574b-9af0-abe5376d40de",
      "fragment_id": "33ce2949-0da2-5839-9b01-566ae7e4bbf4",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "0fac41c8-4af0-5808-8d16-28ebf4ba1616",
      "fact_id": "8591081b-af72-50fe-b017-c26625baacb1",
      "fragment_id": "7d82ddb5-b949-59af-90b3-3da2bc4691ad",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "1e7fec6b-118a-55ac-9b5e-cbfb14328c2e",
      "fact_id": "b3f06151-26b2-5c65-bb42-17beab9f4ebf",
      "fragment_id": "d3e6a365-8150-545b-8005-c18c4939142b",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "2dcee05b-f6d2-5660-a752-0108800a4088",
      "fact_id": "3a9fb283-1682-5dd5-9987-3efd5d5d95d7",
      "fragment_id": "3832d42b-4806-56e6-8281-575100f9201b",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "3375e9a8-4315-5451-a505-e354314c36b3",
      "fact_id": "6c268a9d-0b29-5274-98d2-6d3008ff459b",
      "fragment_id": "b344006d-0950-57af-b0e7-60eb7b4f5217",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "34c226d3-8e31-5734-ad74-cc42d758ee4f",
      "fact_id": "a1aa979d-e0fe-51b3-8806-52d70351176b",
      "fragment_id": "cc839407-9eb7-5e05-acca-70f1577883d4",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "47dd7a1c-a546-5108-b345-dcdc6c583a8c",
      "fact_id": "94255747-5c61-51a9-892f-6a8d17cb3dee",
      "fragment_id": "f3130edc-588f-5f37-a88d-ffea7eca56c3",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "4b6e8cd6-dff4-5d12-9092-e86477fee8a4",
      "fact_id": "ddd0115a-c248-5be6-af50-ecc9c3eb26d5",
      "fragment_id": "56d19d98-707a-5deb-9472-d355b3835d79",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "4d016edb-801c-5b2f-a4b7-0a2211f03711",
      "fact_id": "f1354988-add2-5149-938a-4f6a4221d4f1",
      "fragment_id": "49c356b3-3585-587c-9573-d4326e97de77",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "4e0565a6-c170-51e9-9997-a7190eb2b8a0",
      "fact_id": "a208b943-38f3-5cd6-ad35-1f1de17a00e4",
      "fragment_id": "d521033f-59ce-5518-9227-b5fe9cb7570f",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "6530b92f-e4d5-514d-a0e0-0640a25587a6",
      "fact_id": "5f708929-3f45-50d7-820d-2a72b84f83de",
      "fragment_id": "150704f4-c65a-50f4-b758-b9b456f909ff",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "73866456-884b-5cac-9940-3eb5b47f51fc",
      "fact_id": "fd69ed6e-d7ee-5dd2-a058-f10f0dac7429",
      "fragment_id": "facfa6e5-5707-5d1f-8a9e-a2386955211e",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "904af249-41ef-5986-9bea-1a00f59d9f19",
      "fact_id": "9c6e13cb-60e5-595e-95ad-38ea95dc9f6e",
      "fragment_id": "a7869dd7-97d1-56de-86b4-aadf1e970c0a",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "9b2a572b-bf18-55ba-9de3-1dbb0b8f04f6",
      "fact_id": "c73a9fc6-181f-5a5a-84b3-f6885b4e77ce",
      "fragment_id": "15e6b7e7-98f3-5830-8d5d-ae44862e445a",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "a012a5b0-6790-513d-b274-d759b2c8b950",
      "fact_id": "4e55576e-cc85-5c77-adc4-b0d571b83502",
      "fragment_id": "51e5ac30-63a9-5433-8472-a22727f1db36",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "a2b5e54e-c200-5a27-8bfa-f55758794fe2",
      "fact_id": "296ee01f-8379-5e8a-8cfb-d8b4b5e2deb0",
      "fragment_id": "b9981fe5-0c46-5bd0-91ad-1f2e8a1f2aff",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "a6efe35a-1792-5574-9fed-1d9ce640561b",
      "fact_id": "6f26acf1-03dd-5731-a626-2c2c558b58cd",
      "fragment_id": "3ca46849-549e-544d-b72c-d62ef1706612",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "b5751043-17fe-5475-bf3e-f2e16190d8ed",
      "fact_id": "fa48d318-8754-5ee6-9880-b67273843e9a",
      "fragment_id": "ab55c516-12dc-5533-9e87-a950a6e61b3e",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "b7c4c3a7-2f92-5f35-984c-9f6fc4c8c6db",
      "fact_id": "e1bc2da7-5d64-5a43-b6ab-5ee9eea97b43",
      "fragment_id": "150704f4-c65a-50f4-b758-b9b456f909ff",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "c17d0910-ff76-5f32-a278-fe97306b6ae8",
      "fact_id": "daaf4605-8aa1-5463-876d-e32f561a0e1c",
      "fragment_id": "bbf0a151-afb1-57cd-9c19-cba3f5319e42",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "c9036ec1-6b3c-55d0-aa15-7f63bea91fa6",
      "fact_id": "e00f9759-43f9-57a6-932c-412c24dc14ea",
      "fragment_id": "6295e487-c225-5445-ae8b-653d1691579a",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "cbcc9b78-9a8f-569d-b0be-738ec694d301",
      "fact_id": "b3f06151-26b2-5c65-bb42-17beab9f4ebf",
      "fragment_id": "15e6b7e7-98f3-5830-8d5d-ae44862e445a",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "cbf31553-ffdf-5d61-86ee-04e6dfe0b683",
      "fact_id": "d206a449-91fa-558f-89ce-53eddd73be09",
      "fragment_id": "fcd2397b-c4e9-5035-9ff9-45969f55ecf4",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "dadf11cf-66ca-594f-a7c3-30e4114b4a7a",
      "fact_id": "9e287255-de7d-5c16-9a21-291261933514",
      "fragment_id": "7f0b0752-387d-5def-ba3d-ab11c4f1414b",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "e096e9bc-09b3-5cf7-a598-e1cff13ad4a7",
      "fact_id": "5f708929-3f45-50d7-820d-2a72b84f83de",
      "fragment_id": "82d1bacf-3ed4-5b42-9d8c-7ee7cd105e94",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "e3286e30-8ddd-5598-a9c7-182ab890694f",
      "fact_id": "abecfa8f-31bb-57f0-8a9e-2496e9416609",
      "fragment_id": "3c9cca86-6ba6-58ee-a6a1-b4c6aade6f54",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "f07fb0c1-2fea-5341-bdab-96681a75de89",
      "fact_id": "f25ddd8f-0810-5fdc-97cb-647c9d38074f",
      "fragment_id": "ef7df23c-ba67-5903-9265-adbd1936ffa3",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "f2d96bce-433e-559a-b187-adacac6238e4",
      "fact_id": "064c967c-2147-5961-9bec-919fa695ef01",
      "fragment_id": "2c47a771-1301-55be-a2ab-9b2ef1f82510",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "fb265c9c-83c9-53b4-a2aa-3fbc6413a65a",
      "fact_id": "136cb85c-abcb-5c65-a4ad-c118a560fca3",
      "fragment_id": "04ab9fff-fe17-5b34-8733-f046d1b1ed06",
      "relation": "SUPPORTS"
    },
    {
      "link_id": "fc45dc13-eec5-5d41-8a2d-cf7568a5550e",
      "fact_id": "db691c24-5aa1-56b2-bc8a-da33ad1370ba",
      "fragment_id": "d1067ad6-51d6-5a42-b6ea-8cf74c4fd71c",
      "relation": "SUPPORTS"
    }
  ],
  "facts": [
    {
      "fact_id": "064c967c-2147-5961-9bec-919fa695ef01",
      "statement": "Суд также запретил Соколовой юридическую и общественную деятельность после освобождения.",
      "fact_type": "OBSERVED_EVENT",
      "time_start": "2011-08-08",
      "time_end": "2011-08-08",
      "geography": "Kazakhstan",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "136cb85c-abcb-5c65-a4ad-c118a560fca3",
      "statement": "После акции в Актау 5 июня были задержаны не менее 37 протестующих.",
      "fact_type": "OBSERVED_EVENT",
      "time_start": "2011-06-05",
      "time_end": "2011-06-05",
      "geography": "Aktau, Mangistau",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "296ee01f-8379-5e8a-8cfb-d8b4b5e2deb0",
      "statement": "Трудоустройство уволенных работников было заявлено как предмет последующей встречи.",
      "fact_type": "OBSERVED_EVENT",
      "time_start": "2011-11-14",
      "time_end": "2011-11-14",
      "geography": "Жанаозен",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "3a9fb283-1682-5dd5-9987-3efd5d5d95d7",
      "statement": "РД КМГ заявила, что не намерена восстанавливать уволенных нефтяников.",
      "fact_type": "OFFICIAL_CLAIM",
      "time_start": "2011-10-06",
      "time_end": "2011-10-06",
      "geography": "Zhanaozen",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "4e55576e-cc85-5c77-adc4-b0d571b83502",
      "statement": "IPHR/KIBHR сообщил, что тысячи нефтяников бастовали и протестовали несколько месяцев.",
      "fact_type": "EXPERT_INTERPRETATION",
      "time_start": "2011-10-01",
      "time_end": "2011-10-01",
      "geography": "Mangistau",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "5f708929-3f45-50d7-820d-2a72b84f83de",
      "statement": "Наталья Соколова в августе 2011 года была приговорена к шести годам лишения свободы.",
      "fact_type": "OBSERVED_EVENT",
      "time_start": "2011-08-08",
      "time_end": "2011-08-08",
      "geography": "Aktau / Mangistau",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "6c268a9d-0b29-5274-98d2-6d3008ff459b",
      "statement": "Генеральная прокуратура заявила, что действия полиции в Актау были законными.",
      "fact_type": "OFFICIAL_CLAIM",
      "time_start": "2011-06-06",
      "time_end": "2011-06-06",
      "geography": "Aktau / Kazakhstan",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "6f26acf1-03dd-5731-a626-2c2c558b58cd",
      "statement": "Eurasianet передал позицию РД КМГ о том, что работники получают справедливую оплату.",
      "fact_type": "ACTOR_CLAIM",
      "time_start": "2011-10-13",
      "time_end": "2011-10-13",
      "geography": "KMG EP / Mangistau",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "8591081b-af72-50fe-b017-c26625baacb1",
      "statement": "Заместитель акима заявил, что из 989 уволенных за трудоустройством обратились шесть человек.",
      "fact_type": "OFFICIAL_CLAIM",
      "time_start": "2011-11-22",
      "time_end": "2011-11-22",
      "geography": "Zhanaozen",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "94255747-5c61-51a9-892f-6a8d17cb3dee",
      "statement": "Заместитель акима области заявил о создании около 3000 рабочих мест в Жанаозене.",
      "fact_type": "OFFICIAL_CLAIM",
      "time_start": "2011-11-22",
      "time_end": "2011-11-22",
      "geography": "Zhanaozen",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "98d4666a-d2e2-5fa3-817b-5ee545d9eda9",
      "statement": "Миссия США при ОБСЕ выразила обеспокоенность шестилетним приговором Соколовой.",
      "fact_type": "OFFICIAL_CLAIM",
      "time_start": "2011-09-01",
      "time_end": "2011-09-01",
      "geography": "OSCE / Kazakhstan",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "9c6e13cb-60e5-595e-95ad-38ea95dc9f6e",
      "statement": "Eurasianet передал заявление РД КМГ о шести повышениях зарплаты с 2008 года.",
      "fact_type": "ACTOR_CLAIM",
      "time_start": "2011-10-13",
      "time_end": "2011-10-13",
      "geography": "KMG EP",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "9e287255-de7d-5c16-9a21-291261933514",
      "statement": "Бастующие требовали снятия ограничений с независимых профсоюзов.",
      "fact_type": "ACTOR_CLAIM",
      "time_start": "2011-05-27",
      "time_end": "2011-05-27",
      "geography": "Mangistau",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "a0955cfa-c21d-574b-9af0-abe5376d40de",
      "statement": "Миссия США при ОБСЕ заявила о признаках нарушений надлежащей процедуры в суде над Соколовой.",
      "fact_type": "OFFICIAL_CLAIM",
      "time_start": "2011-09-01",
      "time_end": "2011-09-01",
      "geography": "OSCE / Kazakhstan",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "a1aa979d-e0fe-51b3-8806-52d70351176b",
      "statement": "Работники ОзенМунайГаза требовали пересмотра коллективного договора.",
      "fact_type": "ACTOR_CLAIM",
      "time_start": "2011-05-26",
      "time_end": "2011-05-26",
      "geography": "Zhanaozen, Mangistau",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "a208b943-38f3-5cd6-ad35-1f1de17a00e4",
      "statement": "26 мая 14 работников ОзенМунайГаза начали голодовку.",
      "fact_type": "OBSERVED_EVENT",
      "time_start": "2011-05-26",
      "time_end": "2011-05-26",
      "geography": "Zhanaozen, Mangistau",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "abecfa8f-31bb-57f0-8a9e-2496e9416609",
      "statement": "РД КМГ заявила, что уволенным неоднократно предлагали работу в сервисных компаниях.",
      "fact_type": "OFFICIAL_CLAIM",
      "time_start": "2011-10-06",
      "time_end": "2011-10-06",
      "geography": "Zhanaozen / Mangistau",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "b3f06151-26b2-5c65-bb42-17beab9f4ebf",
      "statement": "Бастующие заявляли требование повышения оплаты труда.",
      "fact_type": "ACTOR_CLAIM",
      "time_start": "2011-05-17",
      "time_end": "2011-05-17",
      "geography": "Mangistau",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "c73a9fc6-181f-5a5a-84b3-f6885b4e77ce",
      "statement": "IPHR/KIBHR описал требования как справедливую оплату и условия труда.",
      "fact_type": "EXPERT_INTERPRETATION",
      "time_start": "2011-10-01",
      "time_end": "2011-10-01",
      "geography": "Mangistau",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "d206a449-91fa-558f-89ce-53eddd73be09",
      "statement": "ЕС призвал Казахстан обеспечить Соколовой свободное и справедливое судебное разбирательство.",
      "fact_type": "OFFICIAL_CLAIM",
      "time_start": "2011-09-02",
      "time_end": "2011-09-02",
      "geography": "OSCE / Kazakhstan",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "daaf4605-8aa1-5463-876d-e32f561a0e1c",
      "statement": "В конце ноября прошла трёхдневная встреча КМГ, бастующих, Минтруда и акимата.",
      "fact_type": "OBSERVED_EVENT",
      "time_start": "2011-11-27",
      "time_end": "2011-11-27",
      "geography": "Zhanaozen",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "db691c24-5aa1-56b2-bc8a-da33ad1370ba",
      "statement": "В июле нефтяники и часть жителей несколько дней находились на площади в Жанаозене.",
      "fact_type": "OBSERVED_EVENT",
      "time_start": "2011-07-11",
      "time_end": "2011-07-11",
      "geography": "Zhanaozen",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "ddd0115a-c248-5be6-af50-ecc9c3eb26d5",
      "statement": "В материале о бастующем работнике зафиксированы требования невыплаченных повышений и улучшения условий труда.",
      "fact_type": "ACTOR_CLAIM",
      "time_start": "2011-09-18",
      "time_end": "2011-09-18",
      "geography": "Zhanaozen",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "e00f9759-43f9-57a6-932c-412c24dc14ea",
      "statement": "РД КМГ связала часть снижения добычи и экспорта с забастовкой.",
      "fact_type": "ACTOR_CLAIM",
      "time_start": "2011-11-14",
      "time_end": "2011-11-14",
      "geography": "KMG EP / Mangistau",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "e1bc2da7-5d64-5a43-b6ab-5ee9eea97b43",
      "statement": "Делегация Казахстана при ОБСЕ подтвердила шестилетний приговор Соколовой.",
      "fact_type": "OFFICIAL_CLAIM",
      "time_start": "2011-11-03",
      "time_end": "2011-11-03",
      "geography": "OSCE / Kazakhstan",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "f1354988-add2-5149-938a-4f6a4221d4f1",
      "statement": "RFE/RL сообщил о 410 уволенных с начала забастовки.",
      "fact_type": "OBSERVED_EVENT",
      "time_start": "2011-09-27",
      "time_end": "2011-09-27",
      "geography": "Mangistau",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "f25ddd8f-0810-5fdc-97cb-647c9d38074f",
      "statement": "Уволенные работники, по сообщению Eurasianet, требовали восстановления и пересмотра зарплат.",
      "fact_type": "ACTOR_CLAIM",
      "time_start": "2011-10-13",
      "time_end": "2011-10-13",
      "geography": "Zhanaozen",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "fa48d318-8754-5ee6-9880-b67273843e9a",
      "statement": "Около 40 нефтяников участвовали в ноябрьской встрече с вице-министром и региональными чиновниками.",
      "fact_type": "OBSERVED_EVENT",
      "time_start": "2011-11-15",
      "time_end": "2011-11-15",
      "geography": "Zhanaozen",
      "status": "PROVISIONAL"
    },
    {
      "fact_id": "fd69ed6e-d7ee-5dd2-a058-f10f0dac7429",
      "statement": "РД КМГ сообщила о примерно 3400 резюме жителей региона на освободившиеся рабочие места.",
      "fact_type": "OFFICIAL_CLAIM",
      "time_start": "2011-07-28",
      "time_end": "2011-07-28",
      "geography": "Mangistau",
      "status": "PROVISIONAL"
    }
  ],
  "text_fragments": [
    {
      "fragment_id": "04ab9fff-fe17-5b34-8733-f046d1b1ed06",
      "document_version_id": "3186a5ae-1c7c-5570-90e6-f6a68b938f59",
      "exact_text": "At least 37 protesters were detained.",
      "fragment_hash": "ab4dc3c216b97bcee60d18ae1d4baaef37cb57874ca34ee2b3f15144387784d0",
      "page_section": ""
    },
    {
      "fragment_id": "150704f4-c65a-50f4-b758-b9b456f909ff",
      "document_version_id": "26b9e671-5e1e-5460-a80c-2e803ca81ba6",
      "exact_text": "Natalya Sokolova was sentenced to six years of imprisonment",
      "fragment_hash": "20167c0443bca4fe1ca09d3851f8e0cec3d3c9eb9d009796e0842abda2a3a937",
      "page_section": ""
    },
    {
      "fragment_id": "15e6b7e7-98f3-5830-8d5d-ae44862e445a",
      "document_version_id": "e92b6b89-4e75-5f64-ac26-7dd8005c3d56",
      "exact_text": "demanding fair pay and work conditions",
      "fragment_hash": "086dcc0d8d259aeddb5dc4abbb43dbecfdc2f2474675aa881fe00d2a2f6dadd6",
      "page_section": ""
    },
    {
      "fragment_id": "2c47a771-1301-55be-a2ab-9b2ef1f82510",
      "document_version_id": "f8c37ae0-cf47-50e7-844e-117d0da2d1e8",
      "exact_text": "barred from performing legal or social activities",
      "fragment_hash": "18eb28e3682e26881c00f5ad81dbdc60ded9be207f68e3f6b21b2e7da960a980",
      "page_section": ""
    },
    {
      "fragment_id": "33ce2949-0da2-5839-9b01-566ae7e4bbf4",
      "document_version_id": "17608513-7164-5d30-9d2e-521338e323d7",
      "exact_text": "trial appears to have been marred by violations of procedural due process",
      "fragment_hash": "adb59f91fd4d4ae7248581db6ff0d94ac88c9b1933c914af2065cd1254d7038a",
      "page_section": ""
    },
    {
      "fragment_id": "3832d42b-4806-56e6-8281-575100f9201b",
      "document_version_id": "2d63f3f4-cb01-5b8c-b4ec-9bedb09b4363",
      "exact_text": "не намерен восстанавливать на работе уволенных нефтяников",
      "fragment_hash": "83cd82e69db496d805d45278f441ea0f7c6a25de5a6610b8fe8eab9d0f869be4",
      "page_section": ""
    },
    {
      "fragment_id": "3c9cca86-6ba6-58ee-a6a1-b4c6aade6f54",
      "document_version_id": "2d63f3f4-cb01-5b8c-b4ec-9bedb09b4363",
      "exact_text": "уволенным неоднократно предлагалась работа в сервисных компаниях",
      "fragment_hash": "912ca9dbbf869b23e885ab3855ecb4c0c36b8bb64ff6e98b3f314cc66923e64e",
      "page_section": ""
    },
    {
      "fragment_id": "3ca46849-549e-544d-b72c-d62ef1706612",
      "document_version_id": "86135a7f-79d7-5d6f-870c-f8bdaa925023",
      "exact_text": "company insists that its employees are fairly compensated",
      "fragment_hash": "f7760687e7aaae5d2ed74a264f94485465395efdc8c17afd5deb89c452a4d86c",
      "page_section": ""
    },
    {
      "fragment_id": "49c356b3-3585-587c-9573-d4326e97de77",
      "document_version_id": "3fa6e3d7-8fac-5372-84f4-6924a8bf819e",
      "exact_text": "Some 410 of the workers have been fired since the strike began",
      "fragment_hash": "98437a034ea0d186a2958940f557068d943d9faa351a3aad6aa2c2014a7087da",
      "page_section": ""
    },
    {
      "fragment_id": "51e5ac30-63a9-5433-8472-a22727f1db36",
      "document_version_id": "e92b6b89-4e75-5f64-ac26-7dd8005c3d56",
      "exact_text": "thousands of oil industry workers have been striking and protesting",
      "fragment_hash": "5e6796f746e563e5a6fddabab4019c9d76bc0029a29821d2fc9ad8421ff057c5",
      "page_section": ""
    },
    {
      "fragment_id": "56d19d98-707a-5deb-9472-d355b3835d79",
      "document_version_id": "00527651-bbea-5b17-89b0-c79f68fb39f6",
      "exact_text": "demanding payment of unfulfilled wage hikes and better labor conditions",
      "fragment_hash": "0f6e3a6f15d8d509f36975eb0e400f93343a910a52a9d44f1d1933c7d61e7828",
      "page_section": ""
    },
    {
      "fragment_id": "6295e487-c225-5445-ae8b-653d1691579a",
      "document_version_id": "d2eefc78-82b0-5eb7-b1ae-533745cbbd79",
      "exact_text": "production and export decline due to the illegal strike",
      "fragment_hash": "d4c41baf5312f53d2607b18887ca0edac2a7a387fbd2f767f2abbddf2f5b47f2",
      "page_section": ""
    },
    {
      "fragment_id": "7d82ddb5-b949-59af-90b3-3da2bc4691ad",
      "document_version_id": "02248e81-d235-5306-aef3-5dec2af93ebb",
      "exact_text": "за трудоустройством обратилось всего шесть человек",
      "fragment_hash": "202a7d8190bc7f705cc8c450853308110a72f4fa2804f148eb9644e8b412924c",
      "page_section": ""
    },
    {
      "fragment_id": "7f0b0752-387d-5def-ba3d-ab11c4f1414b",
      "document_version_id": "adbcb401-ba65-5904-95c0-8ef2be653ed1",
      "exact_text": "lifting of restrictions on the activities of independent trade unions",
      "fragment_hash": "ac6e8cc659989a1ad7641a8c281b51f933f1c71cec3ac21505f917005f7d11fe",
      "page_section": ""
    },
    {
      "fragment_id": "82d1bacf-3ed4-5b42-9d8c-7ee7cd105e94",
      "document_version_id": "f8c37ae0-cf47-50e7-844e-117d0da2d1e8",
      "exact_text": "sentenced to six years in jail",
      "fragment_hash": "801c305068af1eba96cc54ba1006f05bb94bc72ca2f18555a94eeacac2f722c8",
      "page_section": ""
    },
    {
      "fragment_id": "a7869dd7-97d1-56de-86b4-aadf1e970c0a",
      "document_version_id": "86135a7f-79d7-5d6f-870c-f8bdaa925023",
      "exact_text": "has raised salaries six times since 2008",
      "fragment_hash": "57481ba5d7b8f7cc36f5f4ab9281d1e9a35e6b4e931cc6d4f3c427403cbb23b8",
      "page_section": ""
    },
    {
      "fragment_id": "ab55c516-12dc-5533-9e87-a950a6e61b3e",
      "document_version_id": "53cf6bd9-b51d-5f0a-b56f-addd0caa6af2",
      "exact_text": "На встречу пришли около 40 нефтяников",
      "fragment_hash": "b148d270bcae31abceaffc93ac1b5fb9319a992ceed42faf19acac5a221cff59",
      "page_section": ""
    },
    {
      "fragment_id": "b344006d-0950-57af-b0e7-60eb7b4f5217",
      "document_version_id": "3186a5ae-1c7c-5570-90e6-f6a68b938f59",
      "exact_text": "police action in Aqtau was legal",
      "fragment_hash": "e90581178df54e8aa90d72fcbe9c488fa57139002797126a3014ebeff56c1340",
      "page_section": ""
    },
    {
      "fragment_id": "b5fdecb6-2ac4-5f56-aae6-6aef4bb7b956",
      "document_version_id": "17608513-7164-5d30-9d2e-521338e323d7",
      "exact_text": "sentencing to six years imprisonment of Natalya Sokolova",
      "fragment_hash": "a4cd7f69647c69aac6ae7658e8bc3c7ecb7f1038ba3e427a139a5baf7f125c84",
      "page_section": ""
    },
    {
      "fragment_id": "b9981fe5-0c46-5bd0-91ad-1f2e8a1f2aff",
      "document_version_id": "9b1dfe95-b290-533c-9414-d8f18d880b1d",
      "exact_text": "вопросы трудоустройства уволенных рабочих",
      "fragment_hash": "2ecc78bf75c2e118de5f158d0934f5fa66221aa7f687b1bdb83eb0fc554e233b",
      "page_section": ""
    },
    {
      "fragment_id": "bbf0a151-afb1-57cd-9c19-cba3f5319e42",
      "document_version_id": "d3b8d52c-3dbb-5d07-84bd-e07acf35fbbb",
      "exact_text": "Три дня в городе Жанаозен проходила трехсторонняя встреча",
      "fragment_hash": "3d3cac8c646df7fb27557676849d966a50ecb64ddccf01c8afb9768bb05f7808",
      "page_section": ""
    },
    {
      "fragment_id": "cc839407-9eb7-5e05-acca-70f1577883d4",
      "document_version_id": "ed5b18f5-d4b4-57bf-99db-d59131945ed9",
      "exact_text": "demanding the revision of the collective contract",
      "fragment_hash": "280cab66370750738b1f3e917eedf2c571038385e7cd6829763f6a3955de093c",
      "page_section": ""
    },
    {
      "fragment_id": "d1067ad6-51d6-5a42-b6ea-8cf74c4fd71c",
      "document_version_id": "bb5c161c-2e58-55b9-abaf-a92a634ebf37",
      "exact_text": "мұнайшылар мен қала халқы бірнеше күн алаңда түнеді",
      "fragment_hash": "09c5ced1e64fcfd9a723ca63cba4eeca4827045e8da09294f02acf025e97cc81",
      "page_section": ""
    },
    {
      "fragment_id": "d3e6a365-8150-545b-8005-c18c4939142b",
      "document_version_id": "64f97ffe-8d27-5837-86bf-e5851257a76d",
      "exact_text": "strikers are demanding a pay rise",
      "fragment_hash": "fc3fefbdcd67497c70405602e47bb7a3d29bcac9e8ea5faba2dc5cfd68734901",
      "page_section": ""
    },
    {
      "fragment_id": "d521033f-59ce-5518-9227-b5fe9cb7570f",
      "document_version_id": "ed5b18f5-d4b4-57bf-99db-d59131945ed9",
      "exact_text": "Fourteen employees of the OzenMunaiGaz Oil Company",
      "fragment_hash": "258e18442bacd8552d907615438d8a4da4c405d4095ca13ee3a3f4051ad2f20a",
      "page_section": ""
    },
    {
      "fragment_id": "ef7df23c-ba67-5903-9265-adbd1936ffa3",
      "document_version_id": "86135a7f-79d7-5d6f-870c-f8bdaa925023",
      "exact_text": "demanding reinstatement and a review of salaries",
      "fragment_hash": "0a2f0dcd6186b9e872d21dabe4af51bf3e062ee1ff69970d0f89681271a9d84f",
      "page_section": ""
    },
    {
      "fragment_id": "f3130edc-588f-5f37-a88d-ffea7eca56c3",
      "document_version_id": "02248e81-d235-5306-aef3-5dec2af93ebb",
      "exact_text": "создано около 3000 рабочих мест",
      "fragment_hash": "59b487b92e58938aed664ea051d6add28e06d31cdc891039654a3db77d175f47",
      "page_section": ""
    },
    {
      "fragment_id": "facfa6e5-5707-5d1f-8a9e-a2386955211e",
      "document_version_id": "3dcd5aa1-e2a9-5dd9-a2d9-992f9c80e835",
      "exact_text": "около 3400 резюме, поступивших от жителей региона",
      "fragment_hash": "1333917bcc2659c501abac889b49c63c9fb7fae365bb1990586f8d7ba7bcb56e",
      "page_section": ""
    },
    {
      "fragment_id": "fcd2397b-c4e9-5035-9ff9-45969f55ecf4",
      "document_version_id": "e85d2031-f492-5e93-b0ac-a7e84f27c7c7",
      "exact_text": "ensure her a free and fair trial",
      "fragment_hash": "cf0ef0ea07ec46b2fb4aa088be92933afd88a58083ec7780b74856bb321ea134",
      "page_section": ""
    }
  ],
  "document_versions": [
    {
      "document_version_id": "00527651-bbea-5b17-89b0-c79f68fb39f6",
      "document_id": "46609b00-8ecc-5239-816f-e28da8ae18f3",
      "captured_at": "2026-08-24T12:00:00Z",
      "publication_date": "2011-09-18",
      "publication_date_precision": "DAY",
      "content_hash": "e853d18e16a1e105d4b568559855e801f51000d66315140044f1ede73d51d501",
      "content_type": "text/x-evidence-capture; charset=utf-8",
      "local_or_archive_locator": "zhanaozen_v4_2011_evidence_captures/D13_46609b00_capture.txt",
      "language": "en",
      "label": "D13"
    },
    {
      "document_version_id": "02248e81-d235-5306-aef3-5dec2af93ebb",
      "document_id": "1af09c53-eaae-5af8-94c9-574cdd8683dd",
      "captured_at": "2026-08-24T12:00:00Z",
      "publication_date": "2011-11-22",
      "publication_date_precision": "DAY",
      "content_hash": "0e6a08c88995d51c55e14751f2f622feeb44bd136390ceb3cf246be0477be04c",
      "content_type": "text/x-evidence-capture; charset=utf-8",
      "local_or_archive_locator": "zhanaozen_v4_2011_evidence_captures/D23_1af09c53_capture.txt",
      "language": "ru",
      "label": "D23"
    },
    {
      "document_version_id": "17608513-7164-5d30-9d2e-521338e323d7",
      "document_id": "fc776a08-7158-5bb1-bdf6-aee5264c6f61",
      "captured_at": "2026-08-24T12:00:00Z",
      "publication_date": "2011-09-01",
      "publication_date_precision": "DAY",
      "content_hash": "47a25deca65723e6b0285de06520f55189ef3b94d5f0ae271659c5b203a38f1e",
      "content_type": "text/x-evidence-capture; charset=utf-8",
      "local_or_archive_locator": "zhanaozen_v4_2011_evidence_captures/D18_fc776a08_capture.txt",
      "language": "en",
      "label": "D18"
    },
    {
      "document_version_id": "26b9e671-5e1e-5460-a80c-2e803ca81ba6",
      "document_id": "2d26ce81-e4f8-5e97-abea-e761ae250515",
      "captured_at": "2026-08-24T12:00:00Z",
      "publication_date": "2011-11-03",
      "publication_date_precision": "DAY",
      "content_hash": "10c08f6e82a6adea0332429661d8abdab06f1d7a5b2d5b3db40107d2c83bb13d",
      "content_type": "text/x-evidence-capture; charset=utf-8",
      "local_or_archive_locator": "zhanaozen_v4_2011_evidence_captures/D20_2d26ce81_capture.txt",
      "language": "en",
      "label": "D20"
    },
    {
      "document_version_id": "2d63f3f4-cb01-5b8c-b4ec-9bedb09b4363",
      "document_id": "71e85ab4-ac4d-5da6-a5f5-7498e118fc2d",
      "captured_at": "2026-08-24T12:00:00Z",
      "publication_date": "2011-10-06",
      "publication_date_precision": "DAY",
      "content_hash": "105f0a4475fd676a900c9d2686789a5f92a42eb246bc3626f312757fdaf1ad26",
      "content_type": "text/x-evidence-capture; charset=utf-8",
      "local_or_archive_locator": "zhanaozen_v4_2011_evidence_captures/D15_71e85ab4_capture.txt",
      "language": "ru",
      "label": "D15"
    },
    {
      "document_version_id": "3186a5ae-1c7c-5570-90e6-f6a68b938f59",
      "document_id": "c5f122b3-33f5-58bf-9c14-4d6f79657a59",
      "captured_at": "2026-08-24T12:00:00Z",
      "publication_date": "2011-06-06",
      "publication_date_precision": "DAY",
      "content_hash": "e1b888b372abc06b8fa68b255b94951d1b07d0cf09b56418bac38119a618c86c",
      "content_type": "text/x-evidence-capture; charset=utf-8",
      "local_or_archive_locator": "zhanaozen_v4_2011_evidence_captures/D05_c5f122b3_capture.txt",
      "language": "en",
      "label": "D05"
    },
    {
      "document_version_id": "3dcd5aa1-e2a9-5dd9-a2d9-992f9c80e835",
      "document_id": "d8d0cc9f-2091-5c78-8ac9-27ff273d274a",
      "captured_at": "2026-08-24T12:00:00Z",
      "publication_date": "2011-07-28",
      "publication_date_precision": "DAY",
      "content_hash": "778d61386dbfd8044eab009c204df0e0744bf90781898c4484d79d284fbadaa6",
      "content_type": "text/x-evidence-capture; charset=utf-8",
      "local_or_archive_locator": "zhanaozen_v4_2011_evidence_captures/D07_d8d0cc9f_capture.txt",
      "language": "ru",
      "label": "D07"
    },
    {
      "document_version_id": "3fa6e3d7-8fac-5372-84f4-6924a8bf819e",
      "document_id": "1fdb293f-696f-5b38-9a64-469dd0de7340",
      "captured_at": "2026-08-24T12:00:00Z",
      "publication_date": "2011-09-27",
      "publication_date_precision": "DAY",
      "content_hash": "8e85cf150955fd314fa1bad27ab9df16dc0de48662ea403f68258738357511a6",
      "content_type": "text/x-evidence-capture; charset=utf-8",
      "local_or_archive_locator": "zhanaozen_v4_2011_evidence_captures/D14_1fdb293f_capture.txt",
      "language": "en",
      "label": "D14"
    },
    {
      "document_version_id": "53cf6bd9-b51d-5f0a-b56f-addd0caa6af2",
      "document_id": "2c31843a-9181-5786-8ded-86762eae6779",
      "captured_at": "2026-08-24T12:00:00Z",
      "publication_date": "2011-11-17",
      "publication_date_precision": "DAY",
      "content_hash": "e6f07b15b2822e6af738be912d09f4abbacc4857c0761e6a485c8996733003ee",
      "content_type": "text/x-evidence-capture; charset=utf-8",
      "local_or_archive_locator": "zhanaozen_v4_2011_evidence_captures/D22_2c31843a_capture.txt",
      "language": "ru",
      "label": "D22"
    },
    {
      "document_version_id": "64f97ffe-8d27-5837-86bf-e5851257a76d",
      "document_id": "6d02a123-4cac-527f-9b96-a76af63cc16a",
      "captured_at": "2026-08-24T12:00:00Z",
      "publication_date": "2011-05-17",
      "publication_date_precision": "DAY",
      "content_hash": "02419a24e3be19ff11aef22863d4b6254b3d18f22ab7d223aa6b20403bac4950",
      "content_type": "text/x-evidence-capture; charset=utf-8",
      "local_or_archive_locator": "zhanaozen_v4_2011_evidence_captures/D01_6d02a123_capture.txt",
      "language": "en",
      "label": "D01"
    },
    {
      "document_version_id": "86135a7f-79d7-5d6f-870c-f8bdaa925023",
      "document_id": "43a82618-e2f4-5340-b3db-5a08a84dfed1",
      "captured_at": "2026-08-24T12:00:00Z",
      "publication_date": "2011-10-13",
      "publication_date_precision": "DAY",
      "content_hash": "58cdfe78806e6121a878875241d097db593aca2877f7f546b94a5b54b07b7034",
      "content_type": "text/x-evidence-capture; charset=utf-8",
      "local_or_archive_locator": "zhanaozen_v4_2011_evidence_captures/D25_43a82618_capture.txt",
      "language": "en",
      "label": "D25"
    },
    {
      "document_version_id": "9b1dfe95-b290-533c-9414-d8f18d880b1d",
      "document_id": "7a12d83f-30b7-5a83-9334-24066a9e3310",
      "captured_at": "2026-08-25T13:49:00Z",
      "publication_date": "2011-11-14",
      "publication_date_precision": "DAY",
      "content_hash": "6ddd2bada0957498cd622a604d6f125113f2977f68915e5d6cc203776f558dcd",
      "content_type": "text/x-evidence-capture; charset=utf-8",
      "local_or_archive_locator": "zhanaozen_v4_2011_evidence_captures/D29_7a12d83f_capture.txt",
      "language": "ru",
      "label": "D29"
    },
    {
      "document_version_id": "adbcb401-ba65-5904-95c0-8ef2be653ed1",
      "document_id": "2496aaf4-f84e-5c67-85e4-015f7e0519ec",
      "captured_at": "2026-08-24T12:00:00Z",
      "publication_date": "2011-05-27",
      "publication_date_precision": "DAY",
      "content_hash": "69532f7e9b56187dba62597ae82b6ee0943abf83c6aae8436dbe2c9ed8fe666f",
      "content_type": "text/x-evidence-capture; charset=utf-8",
      "local_or_archive_locator": "zhanaozen_v4_2011_evidence_captures/D04_2496aaf4_capture.txt",
      "language": "en",
      "label": "D04"
    },
    {
      "document_version_id": "bb5c161c-2e58-55b9-abaf-a92a634ebf37",
      "document_id": "a09bab6c-8f4c-5fa9-8a01-38cc05d7724c",
      "captured_at": "2026-08-24T12:00:00Z",
      "publication_date": "2011-07-11",
      "publication_date_precision": "DAY",
      "content_hash": "2b8dab7dff1adf0e64cbb01873a751dc429d608ba48ce38963350d8b4572c3a3",
      "content_type": "text/x-evidence-capture; charset=utf-8",
      "local_or_archive_locator": "zhanaozen_v4_2011_evidence_captures/D06_a09bab6c_capture.txt",
      "language": "kk",
      "label": "D06"
    },
    {
      "document_version_id": "d2eefc78-82b0-5eb7-b1ae-533745cbbd79",
      "document_id": "9d9fc2eb-87be-5b5e-8ba1-9d6ad38661ec",
      "captured_at": "2026-08-24T12:00:00Z",
      "publication_date": "2011-11-14",
      "publication_date_precision": "DAY",
      "content_hash": "f37bed02661583fcd84a62c53ffb1a538adf18fdcc7fa4357170f74b013a04cc",
      "content_type": "text/x-evidence-capture; charset=utf-8",
      "local_or_archive_locator": "zhanaozen_v4_2011_evidence_captures/D21_9d9fc2eb_capture.txt",
      "language": "en",
      "label": "D21"
    },
    {
      "document_version_id": "d3b8d52c-3dbb-5d07-84bd-e07acf35fbbb",
      "document_id": "79594336-74c1-58c6-bcdc-11fd4df9ff48",
      "captured_at": "2026-08-24T12:00:00Z",
      "publication_date": "2011-11-27",
      "publication_date_precision": "DAY",
      "content_hash": "74b2caeaccf08d4d3a91c3f8108c0d20b210d5881b4638f0b234811fdba7448b",
      "content_type": "text/x-evidence-capture; charset=utf-8",
      "local_or_archive_locator": "zhanaozen_v4_2011_evidence_captures/D24_79594336_capture.txt",
      "language": "ru",
      "label": "D24"
    },
    {
      "document_version_id": "e85d2031-f492-5e93-b0ac-a7e84f27c7c7",
      "document_id": "e7472144-acd9-592e-82c7-17827ed8812c",
      "captured_at": "2026-08-24T12:00:00Z",
      "publication_date": "2011-09-02",
      "publication_date_precision": "DAY",
      "content_hash": "5a2c9a876ef8458620e84da179cfe25a300c7e795f09457c1223803f900dd42a",
      "content_type": "text/x-evidence-capture; charset=utf-8",
      "local_or_archive_locator": "zhanaozen_v4_2011_evidence_captures/D19_e7472144_capture.txt",
      "language": "en",
      "label": "D19"
    },
    {
      "document_version_id": "e92b6b89-4e75-5f64-ac26-7dd8005c3d56",
      "document_id": "e16804b6-a082-5f9c-acf0-2e4291025136",
      "captured_at": "2026-08-24T12:00:00Z",
      "publication_date": "2011-10-01",
      "publication_date_precision": "MONTH",
      "content_hash": "ae9021062594bf5692b482841a39842034d940d987f613c030053a5f6b405a68",
      "content_type": "text/x-evidence-capture; charset=utf-8",
      "local_or_archive_locator": "zhanaozen_v4_2011_evidence_captures/D17_e16804b6_capture.txt",
      "language": "en",
      "label": "D17"
    },
    {
      "document_version_id": "ed5b18f5-d4b4-57bf-99db-d59131945ed9",
      "document_id": "2c117675-d4c1-5125-8f0b-88086e6bb887",
      "captured_at": "2026-08-24T12:00:00Z",
      "publication_date": "2011-05-26",
      "publication_date_precision": "DAY",
      "content_hash": "df51bb60f64b9e5cb31bad337983c8f0a892b1245ccccb316c800329b9509da6",
      "content_type": "text/x-evidence-capture; charset=utf-8",
      "local_or_archive_locator": "zhanaozen_v4_2011_evidence_captures/D03_2c117675_capture.txt",
      "language": "en",
      "label": "D03"
    },
    {
      "document_version_id": "f8c37ae0-cf47-50e7-844e-117d0da2d1e8",
      "document_id": "36796596-76fc-5e5c-b702-0627641d54e8",
      "captured_at": "2026-08-24T12:00:00Z",
      "publication_date": "2011-08-08",
      "publication_date_precision": "DAY",
      "content_hash": "c77d2581a452587eecaee70c4ee5956d181d12e681094ad1ae78b8bad632c465",
      "content_type": "text/x-evidence-capture; charset=utf-8",
      "local_or_archive_locator": "zhanaozen_v4_2011_evidence_captures/D09_36796596_capture.txt",
      "language": "en",
      "label": "D09"
    }
  ],
  "documents": [
    {
      "document_id": "1af09c53-eaae-5af8-94c9-574cdd8683dd",
      "source_id": "52cc7e9f-cf60-5cee-8c87-740ee516d575",
      "title": "Бастующим нефтяникам города Жанаозен 23 ноября будет предоставлена последняя возможность трудоустроиться",
      "document_type": "PUBLIC_WEB_DOCUMENT"
    },
    {
      "document_id": "1fdb293f-696f-5b38-9a64-469dd0de7340",
      "source_id": "0d49d515-8eee-58d3-891a-45b906138ef9",
      "title": "Jailed Lawyer Of Striking Kazakh Oil Workers Loses Appeal",
      "document_type": "PUBLIC_WEB_DOCUMENT"
    },
    {
      "document_id": "2496aaf4-f84e-5c67-85e4-015f7e0519ec",
      "source_id": "4e46c56c-9f35-5dbd-b634-2b6796d90391",
      "title": "Striking Oil Workers Fired In Kazakhstan",
      "document_type": "PUBLIC_WEB_DOCUMENT"
    },
    {
      "document_id": "2c117675-d4c1-5125-8f0b-88086e6bb887",
      "source_id": "041d7f7c-ad6e-50ac-8322-fa21fd7e8ce4",
      "title": "More Oil Workers Begin Hunger Strike In West Kazakhstan",
      "document_type": "PUBLIC_WEB_DOCUMENT"
    },
    {
      "document_id": "2c31843a-9181-5786-8ded-86762eae6779",
      "source_id": "ae117c91-c49a-5022-abb1-4e39a4e8c38d",
      "title": "Заместитель министра труда и социальной защиты населения встретился с бастующими нефтяниками Мангистау",
      "document_type": "PUBLIC_WEB_DOCUMENT"
    },
    {
      "document_id": "2d26ce81-e4f8-5e97-abea-e761ae250515",
      "source_id": "7197119d-d545-5cf2-9b85-a5212d3436c9",
      "title": "Response concerning Natalya Sokolova and striking employees in Mangistau",
      "document_type": "PUBLIC_WEB_DOCUMENT"
    },
    {
      "document_id": "36796596-76fc-5e5c-b702-0627641d54e8",
      "source_id": "bec0db84-f828-51e3-a57c-03b36e0655c5",
      "title": "Striking Kazakh Oil Workers' Lawyer Gets Six-Year Jail Term",
      "document_type": "PUBLIC_WEB_DOCUMENT"
    },
    {
      "document_id": "43a82618-e2f4-5340-b3db-5a08a84dfed1",
      "source_id": "93272924-00d5-527a-9ace-4ea593c021ad",
      "title": "Kazakhstan: Labor Dispute Dragging Energy Production Down",
      "document_type": "PUBLIC_WEB_DOCUMENT"
    },
    {
      "document_id": "46609b00-8ecc-5239-816f-e28da8ae18f3",
      "source_id": "a31e3834-1227-5f14-acfe-2e43bee2fe47",
      "title": "'We Don't Have Anything To Eat' -- Desperation and Poverty Growing As Kazakh Strikes Drag On",
      "document_type": "PUBLIC_WEB_DOCUMENT"
    },
    {
      "document_id": "6d02a123-4cac-527f-9b96-a76af63cc16a",
      "source_id": "fad22d7e-a495-55e7-85c3-25b774a3b87e",
      "title": "Oil Workers' Strike In Kazakhstan Grows",
      "document_type": "PUBLIC_WEB_DOCUMENT"
    },
    {
      "document_id": "71e85ab4-ac4d-5da6-a5f5-7498e118fc2d",
      "source_id": "e83bc2ab-c6b3-5c89-b8b1-0720ae400d19",
      "title": "«КазМунайГаз» не намерен восстанавливать на работе уволенных нефтяников",
      "document_type": "PUBLIC_WEB_DOCUMENT"
    },
    {
      "document_id": "79594336-74c1-58c6-bcdc-11fd4df9ff48",
      "source_id": "82043157-6a1a-5df4-9dd7-9ba42368d19b",
      "title": "Представители бастующих нефтяников города Жанаозен отказались подписывать протокол трехсторонней встречи",
      "document_type": "PUBLIC_WEB_DOCUMENT"
    },
    {
      "document_id": "7a12d83f-30b7-5a83-9334-24066a9e3310",
      "source_id": "55be8202-f086-55ce-87bd-a11b76f4d1f3",
      "title": "Вице-министр труда и соцзащиты населения встретился с бастующими нефтяниками в Жанаозене",
      "document_type": "PUBLIC_WEB_DOCUMENT"
    },
    {
      "document_id": "9d9fc2eb-87be-5b5e-8ba1-9d6ad38661ec",
      "source_id": "f1f97296-d368-5605-a262-e57e0f489187",
      "title": "The first nine months 2011 financial results — Press Release",
      "document_type": "PUBLIC_WEB_DOCUMENT"
    },
    {
      "document_id": "a09bab6c-8f4c-5fa9-8a01-38cc05d7724c",
      "source_id": "8872ed80-7dfe-5761-a8a7-5cb6a64dcec4",
      "title": "Жаңаөзендегі мұнайшылар наразылығына туыстары қосылды",
      "document_type": "PUBLIC_WEB_DOCUMENT"
    },
    {
      "document_id": "c5f122b3-33f5-58bf-9c14-4d6f79657a59",
      "source_id": "ddeaf877-0282-52a2-898a-311bd154a72b",
      "title": "Two Hospitalized After Oil-Worker Protest In Western Kazakhstan",
      "document_type": "PUBLIC_WEB_DOCUMENT"
    },
    {
      "document_id": "d8d0cc9f-2091-5c78-8ac9-27ff273d274a",
      "source_id": "ab02c333-f700-53c9-bf0e-e499b8152447",
      "title": "Суд над юристом нефтяников проходит закрыто",
      "document_type": "PUBLIC_WEB_DOCUMENT"
    },
    {
      "document_id": "e16804b6-a082-5f9c-acf0-2e4291025136",
      "source_id": "73b0f91b-778e-5238-89ee-636e22196efb",
      "title": "Repression of Labor Protests in Kazakhstan — Briefing Note, October 2011",
      "document_type": "PUBLIC_WEB_DOCUMENT"
    },
    {
      "document_id": "e7472144-acd9-592e-82c7-17827ed8812c",
      "source_id": "8581b365-808a-560c-b869-ca2787e4a6d1",
      "title": "EU statement on the rule of law and human rights issues in Kazakhstan",
      "document_type": "PUBLIC_WEB_DOCUMENT"
    },
    {
      "document_id": "fc776a08-7158-5bb1-bdf6-aee5264c6f61",
      "source_id": "4cc51c34-2212-5ab5-b3f1-f6bbfe309c6c",
      "title": "Statement on the Imprisonment of Natalya Sokolova",
      "document_type": "PUBLIC_WEB_DOCUMENT"
    }
  ],
  "sources": [
    {
      "source_id": "041d7f7c-ad6e-50ac-8322-fa21fd7e8ce4",
      "publisher_or_origin": "RFE/RL",
      "source_type": "NEWS",
      "language": "en",
      "url_or_locator": "https://www.rferl.org/a/more_oil_workers_hunger_strike_kazakhstan/24206131.html",
      "accessed_at": "2026-08-24T12:00:00Z",
      "independence_group": "IG-RFERL"
    },
    {
      "source_id": "0d49d515-8eee-58d3-891a-45b906138ef9",
      "publisher_or_origin": "RFE/RL",
      "source_type": "NEWS",
      "language": "en",
      "url_or_locator": "https://www.rferl.org/a/kazakhstan_oil_workers_lawyer/24341367.html",
      "accessed_at": "2026-08-24T12:00:00Z",
      "independence_group": "IG-RFERL"
    },
    {
      "source_id": "4cc51c34-2212-5ab5-b3f1-f6bbfe309c6c",
      "publisher_or_origin": "United States Mission to the OSCE",
      "source_type": "OFFICIAL",
      "language": "en",
      "url_or_locator": "https://www.osce.org/files/f/documents/4/b/82126.pdf",
      "accessed_at": "2026-08-24T12:00:00Z",
      "independence_group": "IG-US-OSCE"
    },
    {
      "source_id": "4e46c56c-9f35-5dbd-b634-2b6796d90391",
      "publisher_or_origin": "RFE/RL",
      "source_type": "NEWS",
      "language": "en",
      "url_or_locator": "https://www.rferl.org/a/striking_oil_workers_fired_in_kazakhstan/24207466.html",
      "accessed_at": "2026-08-24T12:00:00Z",
      "independence_group": "IG-RFERL"
    },
    {
      "source_id": "52cc7e9f-cf60-5cee-8c87-740ee516d575",
      "publisher_or_origin": "Lada.kz",
      "source_type": "LOCAL_MEDIA",
      "language": "ru",
      "url_or_locator": "https://www.lada.kz/aktau_news/society/1209-bastuyuschim-neftyanikam-zhanaozeni-23-noyabrya-budet-predostavlena-poslednyaya-vozmozhnost-trudoustroitsya.html",
      "accessed_at": "2026-08-24T12:00:00Z",
      "independence_group": "IG-LADA"
    },
    {
      "source_id": "55be8202-f086-55ce-87bd-a11b76f4d1f3",
      "publisher_or_origin": "Tengrinews",
      "source_type": "NEWS",
      "language": "ru",
      "url_or_locator": "https://tengrinews.kz/kazakhstan_news/vitse-ministr-truda-sotszaschityi-naseleniya-vstretilsya-201539/",
      "accessed_at": "2026-08-25T13:49:00Z",
      "independence_group": "IG-TENGRINEWS"
    },
    {
      "source_id": "7197119d-d545-5cf2-9b85-a5212d3436c9",
      "publisher_or_origin": "Delegation of Kazakhstan to the OSCE",
      "source_type": "OFFICIAL",
      "language": "en",
      "url_or_locator": "https://cdn.osce.org/sites/default/files/f/documents/3/b/85058.pdf",
      "accessed_at": "2026-08-24T12:00:00Z",
      "independence_group": "IG-KZ-OSCE"
    },
    {
      "source_id": "73b0f91b-778e-5238-89ee-636e22196efb",
      "publisher_or_origin": "IPHR / Kazakhstan International Bureau for Human Rights",
      "source_type": "NGO",
      "language": "en",
      "url_or_locator": "https://iphronline.org/wp-content/uploads/2011/10/eng_labor_protests_briefing_paper_oct_2011.pdf",
      "accessed_at": "2026-08-24T12:00:00Z",
      "independence_group": "IG-IPHR-KIBHR"
    },
    {
      "source_id": "82043157-6a1a-5df4-9dd7-9ba42368d19b",
      "publisher_or_origin": "Lada.kz",
      "source_type": "LOCAL_MEDIA",
      "language": "ru",
      "url_or_locator": "https://www.lada.kz/aktau_news/society/1264-bastuyuschie-neftyaniki-zhanaozenya-razocharovany-primiritelnaya-komissiya-okazalas-razyasnitelnoy.html",
      "accessed_at": "2026-08-24T12:00:00Z",
      "independence_group": "IG-LADA"
    },
    {
      "source_id": "8581b365-808a-560c-b869-ca2787e4a6d1",
      "publisher_or_origin": "European Union at the OSCE",
      "source_type": "OFFICIAL",
      "language": "en",
      "url_or_locator": "https://www.osce.org/files/f/documents/4/8/82141.pdf",
      "accessed_at": "2026-08-24T12:00:00Z",
      "independence_group": "IG-EU-OSCE"
    },
    {
      "source_id": "8872ed80-7dfe-5761-a8a7-5cb6a64dcec4",
      "publisher_or_origin": "Azattyq",
      "source_type": "LOCAL_MEDIA",
      "language": "kk",
      "url_or_locator": "https://www.azattyq.org/a/kazakhstan_zhangaozen_strike_oil_undustry_workers/24261582.html",
      "accessed_at": "2026-08-24T12:00:00Z",
      "independence_group": "IG-AZATTYQ"
    },
    {
      "source_id": "93272924-00d5-527a-9ace-4ea593c021ad",
      "publisher_or_origin": "Eurasianet",
      "source_type": "NEWS",
      "language": "en",
      "url_or_locator": "https://eurasianet.org/kazakhstan-labor-dispute-dragging-energy-production-down",
      "accessed_at": "2026-08-24T12:00:00Z",
      "independence_group": "IG-EURASIANET"
    },
    {
      "source_id": "a31e3834-1227-5f14-acfe-2e43bee2fe47",
      "publisher_or_origin": "RFE/RL",
      "source_type": "NEWS",
      "language": "en",
      "url_or_locator": "https://www.rferl.org/a/kazakhstan_oil_workers_strike_desperation_poverty/24331987.html",
      "accessed_at": "2026-08-24T12:00:00Z",
      "independence_group": "IG-RFERL"
    },
    {
      "source_id": "ab02c333-f700-53c9-bf0e-e499b8152447",
      "publisher_or_origin": "Azattyq",
      "source_type": "LOCAL_MEDIA",
      "language": "ru",
      "url_or_locator": "https://rus.azattyq.org/a/oil_workers_strike_kazakhstan/24279930.html",
      "accessed_at": "2026-08-24T12:00:00Z",
      "independence_group": "IG-AZATTYQ"
    },
    {
      "source_id": "ae117c91-c49a-5022-abb1-4e39a4e8c38d",
      "publisher_or_origin": "Lada.kz",
      "source_type": "LOCAL_MEDIA",
      "language": "ru",
      "url_or_locator": "https://www.lada.kz/society/society/1153-zamestitel-ministra-truda-i-socialnoy-zaschity-naseleniya-vstretilsya-s-bastuyuschimi-neftyanikami-mangistau.html",
      "accessed_at": "2026-08-24T12:00:00Z",
      "independence_group": "IG-LADA"
    },
    {
      "source_id": "bec0db84-f828-51e3-a57c-03b36e0655c5",
      "publisher_or_origin": "RFE/RL",
      "source_type": "NEWS",
      "language": "en",
      "url_or_locator": "https://www.rferl.org/a/striking_kazakh_oil_workers_lawyer_gets_six_year_jail_term/24290769.html",
      "accessed_at": "2026-08-24T12:00:00Z",
      "independence_group": "IG-RFERL"
    },
    {
      "source_id": "ddeaf877-0282-52a2-898a-311bd154a72b",
      "publisher_or_origin": "RFE/RL",
      "source_type": "NEWS",
      "language": "en",
      "url_or_locator": "https://www.rferl.org/a/kazakhstan_oil_workers_protests/24221366.html",
      "accessed_at": "2026-08-24T12:00:00Z",
      "independence_group": "IG-RFERL"
    },
    {
      "source_id": "e83bc2ab-c6b3-5c89-b8b1-0720ae400d19",
      "publisher_or_origin": "Azattyq",
      "source_type": "LOCAL_MEDIA",
      "language": "ru",
      "url_or_locator": "https://rus.azattyq.org/a/24350449.html",
      "accessed_at": "2026-08-24T12:00:00Z",
      "independence_group": "IG-AZATTYQ"
    },
    {
      "source_id": "f1f97296-d368-5605-a262-e57e0f489187",
      "publisher_or_origin": "JSC KazMunaiGas Exploration Production / KASE",
      "source_type": "ACTOR_SELF_STATEMENT",
      "language": "en",
      "url_or_locator": "https://kase.kz/files/emitters/RDGZ/rdgz_reliz_141111_e.pdf",
      "accessed_at": "2026-08-24T12:00:00Z",
      "independence_group": "IG-KMG-EP"
    },
    {
      "source_id": "fad22d7e-a495-55e7-85c3-25b774a3b87e",
      "publisher_or_origin": "RFE/RL",
      "source_type": "NEWS",
      "language": "en",
      "url_or_locator": "https://www.rferl.org/a/oil_workers_strike_in_kazakhstan_grows/24177839.html",
      "accessed_at": "2026-08-24T12:00:00Z",
      "independence_group": "IG-RFERL"
    }
  ],
  "witness_records": [
    {
      "witness_id": "AW-D01-20110521181520",
      "document_version_id": "64f97ffe-8d27-5837-86bf-e5851257a76d",
      "label": "D01",
      "witness_role": "PUBLISHER_PAGE_ARCHIVED_BY_INTERNET_ARCHIVE",
      "original_witness_url": "http://www.rferl.org:80/content/oil_workers_strike_in_kazakhstan_grows/24177839.html",
      "archive_replay_url": "https://web.archive.org/web/20110521181520id_/http://www.rferl.org:80/content/oil_workers_strike_in_kazakhstan_grows/24177839.html",
      "archive_capture_timestamp": "20110521181520",
      "memento_datetime": "Sat, 21 May 2011 18:15:20 GMT",
      "archive_digest_sha1_base32": "F4T26SQHE5VFDZVDTC3ZDI4P747ZQS6H",
      "retrieved_payload_sha1_base32": "F4T26SQHE5VFDZVDTC3ZDI4P747ZQS6H",
      "retrieved_payload_sha256": "5b171ee61f7e202da0b00899aef7659237e01ed6000c2626e4834f265ef66907",
      "payload_bytes": 61956,
      "retrieved_at_utc": "2026-09-26T15:45:15.814857+00:00",
      "match_policy": "HTML charset decode, character-reference decode, strip markup/script/style; exact case-sensitive substring in extracted text. No case-folding, stemming, synonyms or punctuation replacement. All matches also pass before whitespace normalization.",
      "locator_policy": "Offsets refer to whitespace-normalized visible replay text, solely for navigation; proof uses unnormalized extracted text.",
      "matched_fragments": [
        {
          "fragment_id": "d3e6a365-8150-545b-8005-c18c4939142b",
          "exact_frozen_fragment": "strikers are demanding a pay rise",
          "fragment_sha256": "fc3fefbdcd67497c70405602e47bb7a3d29bcac9e8ea5faba2dc5cfd68734901",
          "literal_in_extracted_text": true,
          "offset": 2396
        }
      ]
    },
    {
      "witness_id": "AW-D01-20110811165523",
      "document_version_id": "64f97ffe-8d27-5837-86bf-e5851257a76d",
      "label": "D01",
      "witness_role": "PUBLISHER_PAGE_ARCHIVED_BY_INTERNET_ARCHIVE",
      "original_witness_url": "http://www.rferl.org:80/content/oil_workers_strike_in_kazakhstan_grows/24177839.html",
      "archive_replay_url": "https://web.archive.org/web/20110811165523id_/http://www.rferl.org:80/content/oil_workers_strike_in_kazakhstan_grows/24177839.html",
      "archive_capture_timestamp": "20110811165523",
      "memento_datetime": "Thu, 11 Aug 2011 16:55:23 GMT",
      "archive_digest_sha1_base32": "AVIU5SXG6K2PWEVKLAZZ4LIEFHCUBQYG",
      "retrieved_payload_sha1_base32": "AVIU5SXG6K2PWEVKLAZZ4LIEFHCUBQYG",
      "retrieved_payload_sha256": "1c222969d2b8b5259ca5afca0d649f17ffcd8a12176d10502bd69c14b5fdaede",
      "payload_bytes": 62206,
      "retrieved_at_utc": "2026-09-26T15:45:15.815855+00:00",
      "match_policy": "HTML charset decode, character-reference decode, strip markup/script/style; exact case-sensitive substring in extracted text. No case-folding, stemming, synonyms or punctuation replacement. All matches also pass before whitespace normalization.",
      "locator_policy": "Offsets refer to whitespace-normalized visible replay text, solely for navigation; proof uses unnormalized extracted text.",
      "matched_fragments": [
        {
          "fragment_id": "d3e6a365-8150-545b-8005-c18c4939142b",
          "exact_frozen_fragment": "strikers are demanding a pay rise",
          "fragment_sha256": "fc3fefbdcd67497c70405602e47bb7a3d29bcac9e8ea5faba2dc5cfd68734901",
          "literal_in_extracted_text": true,
          "offset": 2187
        }
      ]
    },
    {
      "witness_id": "AW-D03-20110527054702",
      "document_version_id": "ed5b18f5-d4b4-57bf-99db-d59131945ed9",
      "label": "D03",
      "witness_role": "PUBLISHER_PAGE_ARCHIVED_BY_INTERNET_ARCHIVE",
      "original_witness_url": "http://www.rferl.org/content/more_oil_workers_hunger_strike_kazakhstan/24206131.html",
      "archive_replay_url": "https://web.archive.org/web/20110527054702id_/http://www.rferl.org/content/more_oil_workers_hunger_strike_kazakhstan/24206131.html",
      "archive_capture_timestamp": "20110527054702",
      "memento_datetime": "Fri, 27 May 2011 05:47:02 GMT",
      "archive_digest_sha1_base32": "GVDYFFDIQKST45T2HKS3JWFFUET4IPM3",
      "retrieved_payload_sha1_base32": "GVDYFFDIQKST45T2HKS3JWFFUET4IPM3",
      "retrieved_payload_sha256": "00fb548b56d73a1088aec39a202c8fa3df7d0295e3d56a55535ccae254030aee",
      "payload_bytes": 61546,
      "retrieved_at_utc": "2026-09-26T15:45:15.816872+00:00",
      "match_policy": "HTML charset decode, character-reference decode, strip markup/script/style; exact case-sensitive substring in extracted text. No case-folding, stemming, synonyms or punctuation replacement. All matches also pass before whitespace normalization.",
      "locator_policy": "Offsets refer to whitespace-normalized visible replay text, solely for navigation; proof uses unnormalized extracted text.",
      "matched_fragments": [
        {
          "fragment_id": "cc839407-9eb7-5e05-acca-70f1577883d4",
          "exact_frozen_fragment": "demanding the revision of the collective contract",
          "fragment_sha256": "280cab66370750738b1f3e917eedf2c571038385e7cd6829763f6a3955de093c",
          "literal_in_extracted_text": true,
          "offset": 2521
        },
        {
          "fragment_id": "d521033f-59ce-5518-9227-b5fe9cb7570f",
          "exact_frozen_fragment": "Fourteen employees of the OzenMunaiGaz Oil Company",
          "fragment_sha256": "258e18442bacd8552d907615438d8a4da4c405d4095ca13ee3a3f4051ad2f20a",
          "literal_in_extracted_text": true,
          "offset": 2175
        }
      ]
    },
    {
      "witness_id": "AW-D03-20110916223846",
      "document_version_id": "ed5b18f5-d4b4-57bf-99db-d59131945ed9",
      "label": "D03",
      "witness_role": "PUBLISHER_PAGE_ARCHIVED_BY_INTERNET_ARCHIVE",
      "original_witness_url": "http://www.rferl.org/content/more_oil_workers_hunger_strike_kazakhstan/24206131.html",
      "archive_replay_url": "https://web.archive.org/web/20110916223846id_/http://www.rferl.org/content/more_oil_workers_hunger_strike_kazakhstan/24206131.html",
      "archive_capture_timestamp": "20110916223846",
      "memento_datetime": "Fri, 16 Sep 2011 22:38:46 GMT",
      "archive_digest_sha1_base32": "VDCW4G4WVTHQJRWEPV7H65KOEDZ6C4AV",
      "retrieved_payload_sha1_base32": "VDCW4G4WVTHQJRWEPV7H65KOEDZ6C4AV",
      "retrieved_payload_sha256": "dcd1ca9c08888e731da60c70394760bab313cd7c4406caea64071439a749363e",
      "payload_bytes": 60145,
      "retrieved_at_utc": "2026-09-26T15:45:15.816872+00:00",
      "match_policy": "HTML charset decode, character-reference decode, strip markup/script/style; exact case-sensitive substring in extracted text. No case-folding, stemming, synonyms or punctuation replacement. All matches also pass before whitespace normalization.",
      "locator_policy": "Offsets refer to whitespace-normalized visible replay text, solely for navigation; proof uses unnormalized extracted text.",
      "matched_fragments": [
        {
          "fragment_id": "cc839407-9eb7-5e05-acca-70f1577883d4",
          "exact_frozen_fragment": "demanding the revision of the collective contract",
          "fragment_sha256": "280cab66370750738b1f3e917eedf2c571038385e7cd6829763f6a3955de093c",
          "literal_in_extracted_text": true,
          "offset": 2216
        },
        {
          "fragment_id": "d521033f-59ce-5518-9227-b5fe9cb7570f",
          "exact_frozen_fragment": "Fourteen employees of the OzenMunaiGaz Oil Company",
          "fragment_sha256": "258e18442bacd8552d907615438d8a4da4c405d4095ca13ee3a3f4051ad2f20a",
          "literal_in_extracted_text": true,
          "offset": 1870
        }
      ]
    },
    {
      "witness_id": "AW-D05-20110629041259",
      "document_version_id": "3186a5ae-1c7c-5570-90e6-f6a68b938f59",
      "label": "D05",
      "witness_role": "PUBLISHER_PAGE_ARCHIVED_BY_INTERNET_ARCHIVE",
      "original_witness_url": "http://www.rferl.org:80/content/kazakhstan_oil_workers_protests/24221366.html",
      "archive_replay_url": "https://web.archive.org/web/20110629041259id_/http://www.rferl.org:80/content/kazakhstan_oil_workers_protests/24221366.html",
      "archive_capture_timestamp": "20110629041259",
      "memento_datetime": "Wed, 29 Jun 2011 04:12:59 GMT",
      "archive_digest_sha1_base32": "2YFIVNIRTUIOGDM7ACG3IUT3DPVSQ6CW",
      "retrieved_payload_sha1_base32": "2YFIVNIRTUIOGDM7ACG3IUT3DPVSQ6CW",
      "retrieved_payload_sha256": "73cd2e04ddfbbdc126e2336d159d6af982ed8439527d6826a2e1271797a87d29",
      "payload_bytes": 61251,
      "retrieved_at_utc": "2026-09-26T15:45:17.782077+00:00",
      "match_policy": "HTML charset decode, character-reference decode, strip markup/script/style; exact case-sensitive substring in extracted text. No case-folding, stemming, synonyms or punctuation replacement. All matches also pass before whitespace normalization.",
      "locator_policy": "Offsets refer to whitespace-normalized visible replay text, solely for navigation; proof uses unnormalized extracted text.",
      "matched_fragments": [
        {
          "fragment_id": "04ab9fff-fe17-5b34-8733-f046d1b1ed06",
          "exact_frozen_fragment": "At least 37 protesters were detained.",
          "fragment_sha256": "ab4dc3c216b97bcee60d18ae1d4baaef37cb57874ca34ee2b3f15144387784d0",
          "literal_in_extracted_text": true,
          "offset": 2619
        },
        {
          "fragment_id": "b344006d-0950-57af-b0e7-60eb7b4f5217",
          "exact_frozen_fragment": "police action in Aqtau was legal",
          "fragment_sha256": "e90581178df54e8aa90d72fcbe9c488fa57139002797126a3014ebeff56c1340",
          "literal_in_extracted_text": true,
          "offset": 2714
        }
      ]
    },
    {
      "witness_id": "AW-D05-20110918081249",
      "document_version_id": "3186a5ae-1c7c-5570-90e6-f6a68b938f59",
      "label": "D05",
      "witness_role": "PUBLISHER_PAGE_ARCHIVED_BY_INTERNET_ARCHIVE",
      "original_witness_url": "http://www.rferl.org/content/kazakhstan_oil_workers_protests/24221366.html",
      "archive_replay_url": "https://web.archive.org/web/20110918081249id_/http://www.rferl.org/content/kazakhstan_oil_workers_protests/24221366.html",
      "archive_capture_timestamp": "20110918081249",
      "memento_datetime": "Sun, 18 Sep 2011 08:12:49 GMT",
      "archive_digest_sha1_base32": "2OMSDKFRDE52MI3GWBFW2AB2BQSUV4S3",
      "retrieved_payload_sha1_base32": "2OMSDKFRDE52MI3GWBFW2AB2BQSUV4S3",
      "retrieved_payload_sha256": "8a66bf2ff3285a3d43dc381675543d4e92986f31081ead9f126478b14998e48e",
      "payload_bytes": 60494,
      "retrieved_at_utc": "2026-09-26T15:45:18.522365+00:00",
      "match_policy": "HTML charset decode, character-reference decode, strip markup/script/style; exact case-sensitive substring in extracted text. No case-folding, stemming, synonyms or punctuation replacement. All matches also pass before whitespace normalization.",
      "locator_policy": "Offsets refer to whitespace-normalized visible replay text, solely for navigation; proof uses unnormalized extracted text.",
      "matched_fragments": [
        {
          "fragment_id": "04ab9fff-fe17-5b34-8733-f046d1b1ed06",
          "exact_frozen_fragment": "At least 37 protesters were detained.",
          "fragment_sha256": "ab4dc3c216b97bcee60d18ae1d4baaef37cb57874ca34ee2b3f15144387784d0",
          "literal_in_extracted_text": true,
          "offset": 2515
        },
        {
          "fragment_id": "b344006d-0950-57af-b0e7-60eb7b4f5217",
          "exact_frozen_fragment": "police action in Aqtau was legal",
          "fragment_sha256": "e90581178df54e8aa90d72fcbe9c488fa57139002797126a3014ebeff56c1340",
          "literal_in_extracted_text": true,
          "offset": 2610
        }
      ]
    },
    {
      "witness_id": "AW-D06-20110716171000",
      "document_version_id": "bb5c161c-2e58-55b9-abaf-a92a634ebf37",
      "label": "D06",
      "witness_role": "PUBLISHER_PAGE_ARCHIVED_BY_INTERNET_ARCHIVE",
      "original_witness_url": "http://www.azattyq.org:80/content/kazakhstan_zhangaozen_strike_oil_undustry_workers/24261582.html",
      "archive_replay_url": "https://web.archive.org/web/20110716171000id_/http://www.azattyq.org:80/content/kazakhstan_zhangaozen_strike_oil_undustry_workers/24261582.html",
      "archive_capture_timestamp": "20110716171000",
      "memento_datetime": "Sat, 16 Jul 2011 17:10:00 GMT",
      "archive_digest_sha1_base32": "U6N4P5R3XMZAUNAHZZPSHUDY3I524PPF",
      "retrieved_payload_sha1_base32": "U6N4P5R3XMZAUNAHZZPSHUDY3I524PPF",
      "retrieved_payload_sha256": "65cd8d29565cc4418e5216ce1b608d644870c556eaa16664683e5718986e507f",
      "payload_bytes": 159638,
      "retrieved_at_utc": "2026-09-26T15:45:18.570356+00:00",
      "match_policy": "HTML charset decode, character-reference decode, strip markup/script/style; exact case-sensitive substring in extracted text. No case-folding, stemming, synonyms or punctuation replacement. All matches also pass before whitespace normalization.",
      "locator_policy": "Offsets refer to whitespace-normalized visible replay text, solely for navigation; proof uses unnormalized extracted text.",
      "matched_fragments": [
        {
          "fragment_id": "d1067ad6-51d6-5a42-b6ea-8cf74c4fd71c",
          "exact_frozen_fragment": "мұнайшылар мен қала халқы бірнеше күн алаңда түнеді",
          "fragment_sha256": "09c5ced1e64fcfd9a723ca63cba4eeca4827045e8da09294f02acf025e97cc81",
          "literal_in_extracted_text": true,
          "offset": 1927
        }
      ]
    },
    {
      "witness_id": "AW-D09-20110809011049",
      "document_version_id": "f8c37ae0-cf47-50e7-844e-117d0da2d1e8",
      "label": "D09",
      "witness_role": "PUBLISHER_PAGE_ARCHIVED_BY_INTERNET_ARCHIVE",
      "original_witness_url": "http://www.rferl.org/content/striking_kazakh_oil_workers_lawyer_gets_six_year_jail_term/24290769.html",
      "archive_replay_url": "https://web.archive.org/web/20110809011049id_/http://www.rferl.org/content/striking_kazakh_oil_workers_lawyer_gets_six_year_jail_term/24290769.html",
      "archive_capture_timestamp": "20110809011049",
      "memento_datetime": "Tue, 09 Aug 2011 01:10:49 GMT",
      "archive_digest_sha1_base32": "4SBQWOS6PTPJBCJSXM3HFKJMPT6A3QWW",
      "retrieved_payload_sha1_base32": "4SBQWOS6PTPJBCJSXM3HFKJMPT6A3QWW",
      "retrieved_payload_sha256": "7ebc00cadfb38a435088a47305fa80696d269d01cd53b4d37d0c2e9adc7e349b",
      "payload_bytes": 69913,
      "retrieved_at_utc": "2026-09-26T15:45:19.971738+00:00",
      "match_policy": "HTML charset decode, character-reference decode, strip markup/script/style; exact case-sensitive substring in extracted text. No case-folding, stemming, synonyms or punctuation replacement. All matches also pass before whitespace normalization.",
      "locator_policy": "Offsets refer to whitespace-normalized visible replay text, solely for navigation; proof uses unnormalized extracted text.",
      "matched_fragments": [
        {
          "fragment_id": "2c47a771-1301-55be-a2ab-9b2ef1f82510",
          "exact_frozen_fragment": "barred from performing legal or social activities",
          "fragment_sha256": "18eb28e3682e26881c00f5ad81dbdc60ded9be207f68e3f6b21b2e7da960a980",
          "literal_in_extracted_text": true,
          "offset": 2221
        },
        {
          "fragment_id": "82d1bacf-3ed4-5b42-9d8c-7ee7cd105e94",
          "exact_frozen_fragment": "sentenced to six years in jail",
          "fragment_sha256": "801c305068af1eba96cc54ba1006f05bb94bc72ca2f18555a94eeacac2f722c8",
          "literal_in_extracted_text": true,
          "offset": 2027
        }
      ]
    },
    {
      "witness_id": "AW-D09-20111022101958",
      "document_version_id": "f8c37ae0-cf47-50e7-844e-117d0da2d1e8",
      "label": "D09",
      "witness_role": "PUBLISHER_PAGE_ARCHIVED_BY_INTERNET_ARCHIVE",
      "original_witness_url": "http://www.rferl.org/content/striking_kazakh_oil_workers_lawyer_gets_six_year_jail_term/24290769.html",
      "archive_replay_url": "https://web.archive.org/web/20111022101958id_/http://www.rferl.org/content/striking_kazakh_oil_workers_lawyer_gets_six_year_jail_term/24290769.html",
      "archive_capture_timestamp": "20111022101958",
      "memento_datetime": "Sat, 22 Oct 2011 10:19:58 GMT",
      "archive_digest_sha1_base32": "OAOPVERH3GP3GRBAH4323H6GWA7JTMCZ",
      "retrieved_payload_sha1_base32": "OAOPVERH3GP3GRBAH4323H6GWA7JTMCZ",
      "retrieved_payload_sha256": "b70cb626e740c244d8629b09cc1eaf59f86a0e9f030f8b9e6fd2d659e561622c",
      "payload_bytes": 64190,
      "retrieved_at_utc": "2026-09-26T15:45:20.246680+00:00",
      "match_policy": "HTML charset decode, character-reference decode, strip markup/script/style; exact case-sensitive substring in extracted text. No case-folding, stemming, synonyms or punctuation replacement. All matches also pass before whitespace normalization.",
      "locator_policy": "Offsets refer to whitespace-normalized visible replay text, solely for navigation; proof uses unnormalized extracted text.",
      "matched_fragments": [
        {
          "fragment_id": "2c47a771-1301-55be-a2ab-9b2ef1f82510",
          "exact_frozen_fragment": "barred from performing legal or social activities",
          "fragment_sha256": "18eb28e3682e26881c00f5ad81dbdc60ded9be207f68e3f6b21b2e7da960a980",
          "literal_in_extracted_text": true,
          "offset": 1738
        },
        {
          "fragment_id": "82d1bacf-3ed4-5b42-9d8c-7ee7cd105e94",
          "exact_frozen_fragment": "sentenced to six years in jail",
          "fragment_sha256": "801c305068af1eba96cc54ba1006f05bb94bc72ca2f18555a94eeacac2f722c8",
          "literal_in_extracted_text": true,
          "offset": 1544
        }
      ]
    },
    {
      "witness_id": "AW-D13-20110918124424",
      "document_version_id": "00527651-bbea-5b17-89b0-c79f68fb39f6",
      "label": "D13",
      "witness_role": "PUBLISHER_PAGE_ARCHIVED_BY_INTERNET_ARCHIVE",
      "original_witness_url": "http://www.rferl.org/content/kazakhstan_oil_workers_strike_desperation_poverty/24331987.html",
      "archive_replay_url": "https://web.archive.org/web/20110918124424id_/http://www.rferl.org/content/kazakhstan_oil_workers_strike_desperation_poverty/24331987.html",
      "archive_capture_timestamp": "20110918124424",
      "memento_datetime": "Sun, 18 Sep 2011 12:44:24 GMT",
      "archive_digest_sha1_base32": "Z47XLUTWPJGXYSZWTCRYO4Y33OSHDKIC",
      "retrieved_payload_sha1_base32": "Z47XLUTWPJGXYSZWTCRYO4Y33OSHDKIC",
      "retrieved_payload_sha256": "3ccbc77c868072e6b5d15daef180355467ddc4d25f828f052b241f44aafab51e",
      "payload_bytes": 68274,
      "retrieved_at_utc": "2026-09-26T15:45:20.856142+00:00",
      "match_policy": "HTML charset decode, character-reference decode, strip markup/script/style; exact case-sensitive substring in extracted text. No case-folding, stemming, synonyms or punctuation replacement. All matches also pass before whitespace normalization.",
      "locator_policy": "Offsets refer to whitespace-normalized visible replay text, solely for navigation; proof uses unnormalized extracted text.",
      "matched_fragments": [
        {
          "fragment_id": "56d19d98-707a-5deb-9472-d355b3835d79",
          "exact_frozen_fragment": "demanding payment of unfulfilled wage hikes and better labor conditions",
          "fragment_sha256": "0f6e3a6f15d8d509f36975eb0e400f93343a910a52a9d44f1d1933c7d61e7828",
          "literal_in_extracted_text": true,
          "offset": 2650
        }
      ]
    },
    {
      "witness_id": "AW-D13-20111024200546",
      "document_version_id": "00527651-bbea-5b17-89b0-c79f68fb39f6",
      "label": "D13",
      "witness_role": "PUBLISHER_PAGE_ARCHIVED_BY_INTERNET_ARCHIVE",
      "original_witness_url": "http://www.rferl.org/content/kazakhstan_oil_workers_strike_desperation_poverty/24331987.html",
      "archive_replay_url": "https://web.archive.org/web/20111024200546id_/http://www.rferl.org/content/kazakhstan_oil_workers_strike_desperation_poverty/24331987.html",
      "archive_capture_timestamp": "20111024200546",
      "memento_datetime": "Mon, 24 Oct 2011 20:05:46 GMT",
      "archive_digest_sha1_base32": "5KXSUM4HLQBRDSJHBUTP3ESECYZGGRRB",
      "retrieved_payload_sha1_base32": "5KXSUM4HLQBRDSJHBUTP3ESECYZGGRRB",
      "retrieved_payload_sha256": "8ad09640fa11403bc8fea68c60c248f7266e76430fc6b512cb2b9b056b854d9a",
      "payload_bytes": 71168,
      "retrieved_at_utc": "2026-09-26T15:45:20.893643+00:00",
      "match_policy": "HTML charset decode, character-reference decode, strip markup/script/style; exact case-sensitive substring in extracted text. No case-folding, stemming, synonyms or punctuation replacement. All matches also pass before whitespace normalization.",
      "locator_policy": "Offsets refer to whitespace-normalized visible replay text, solely for navigation; proof uses unnormalized extracted text.",
      "matched_fragments": [
        {
          "fragment_id": "56d19d98-707a-5deb-9472-d355b3835d79",
          "exact_frozen_fragment": "demanding payment of unfulfilled wage hikes and better labor conditions",
          "fragment_sha256": "0f6e3a6f15d8d509f36975eb0e400f93343a910a52a9d44f1d1933c7d61e7828",
          "literal_in_extracted_text": true,
          "offset": 2212
        }
      ]
    },
    {
      "witness_id": "AW-D14-20110927202906",
      "document_version_id": "3fa6e3d7-8fac-5372-84f4-6924a8bf819e",
      "label": "D14",
      "witness_role": "PUBLISHER_PAGE_ARCHIVED_BY_INTERNET_ARCHIVE",
      "original_witness_url": "http://www.rferl.org/content/kazakhstan_oil_workers_lawyer/24341367.html",
      "archive_replay_url": "https://web.archive.org/web/20110927202906id_/http://www.rferl.org/content/kazakhstan_oil_workers_lawyer/24341367.html",
      "archive_capture_timestamp": "20110927202906",
      "memento_datetime": "Tue, 27 Sep 2011 20:29:06 GMT",
      "archive_digest_sha1_base32": "BQZGJXT4UFSA6BJCY7CMUET4DJFOCE3C",
      "retrieved_payload_sha1_base32": "BQZGJXT4UFSA6BJCY7CMUET4DJFOCE3C",
      "retrieved_payload_sha256": "265765efbd21f05acedf2f7e6d12b7d35363f0aaefeb863a36879143d00897e6",
      "payload_bytes": 61531,
      "retrieved_at_utc": "2026-09-26T15:45:21.491550+00:00",
      "match_policy": "HTML charset decode, character-reference decode, strip markup/script/style; exact case-sensitive substring in extracted text. No case-folding, stemming, synonyms or punctuation replacement. All matches also pass before whitespace normalization.",
      "locator_policy": "Offsets refer to whitespace-normalized visible replay text, solely for navigation; proof uses unnormalized extracted text.",
      "matched_fragments": [
        {
          "fragment_id": "49c356b3-3585-587c-9573-d4326e97de77",
          "exact_frozen_fragment": "Some 410 of the workers have been fired since the strike began",
          "fragment_sha256": "98437a034ea0d186a2958940f557068d943d9faa351a3aad6aa2c2014a7087da",
          "literal_in_extracted_text": true,
          "offset": 2397
        }
      ]
    },
    {
      "witness_id": "AW-D14-20111106041751",
      "document_version_id": "3fa6e3d7-8fac-5372-84f4-6924a8bf819e",
      "label": "D14",
      "witness_role": "PUBLISHER_PAGE_ARCHIVED_BY_INTERNET_ARCHIVE",
      "original_witness_url": "http://www.rferl.org/content/kazakhstan_oil_workers_lawyer/24341367.html",
      "archive_replay_url": "https://web.archive.org/web/20111106041751id_/http://www.rferl.org/content/kazakhstan_oil_workers_lawyer/24341367.html",
      "archive_capture_timestamp": "20111106041751",
      "memento_datetime": "Sun, 06 Nov 2011 04:17:51 GMT",
      "archive_digest_sha1_base32": "CO5IBLFVMX7DWGL37DIDAFJHMB7WLQAS",
      "retrieved_payload_sha1_base32": "CO5IBLFVMX7DWGL37DIDAFJHMB7WLQAS",
      "retrieved_payload_sha256": "273b51c9961e9d61b4c63cefa76223bee2c7bcfcadda76e13a63f059b4ae7a94",
      "payload_bytes": 59511,
      "retrieved_at_utc": "2026-09-26T15:45:21.649713+00:00",
      "match_policy": "HTML charset decode, character-reference decode, strip markup/script/style; exact case-sensitive substring in extracted text. No case-folding, stemming, synonyms or punctuation replacement. All matches also pass before whitespace normalization.",
      "locator_policy": "Offsets refer to whitespace-normalized visible replay text, solely for navigation; proof uses unnormalized extracted text.",
      "matched_fragments": [
        {
          "fragment_id": "49c356b3-3585-587c-9573-d4326e97de77",
          "exact_frozen_fragment": "Some 410 of the workers have been fired since the strike began",
          "fragment_sha256": "98437a034ea0d186a2958940f557068d943d9faa351a3aad6aa2c2014a7087da",
          "literal_in_extracted_text": true,
          "offset": 2282
        }
      ]
    },
    {
      "witness_id": "AW-D25-20111016060958",
      "document_version_id": "86135a7f-79d7-5d6f-870c-f8bdaa925023",
      "label": "D25",
      "witness_role": "PUBLISHER_PAGE_ARCHIVED_BY_INTERNET_ARCHIVE",
      "original_witness_url": "http://www.eurasianet.org:80/node/64310",
      "archive_replay_url": "https://web.archive.org/web/20111016060958id_/http://www.eurasianet.org:80/node/64310",
      "archive_capture_timestamp": "20111016060958",
      "memento_datetime": "Sun, 16 Oct 2011 06:09:58 GMT",
      "archive_digest_sha1_base32": "XR7PYY6TK4LJPBKR4GRR75RSBY5STQT4",
      "retrieved_payload_sha1_base32": "XR7PYY6TK4LJPBKR4GRR75RSBY5STQT4",
      "retrieved_payload_sha256": "c6ae02c231a18cf574743016e307a1b2d302edbc6fe7386c8dc636c679395005",
      "payload_bytes": 56719,
      "retrieved_at_utc": "2026-09-26T15:45:22.997749+00:00",
      "match_policy": "HTML charset decode, character-reference decode, strip markup/script/style; exact case-sensitive substring in extracted text. No case-folding, stemming, synonyms or punctuation replacement. All matches also pass before whitespace normalization.",
      "locator_policy": "Offsets refer to whitespace-normalized visible replay text, solely for navigation; proof uses unnormalized extracted text.",
      "matched_fragments": [
        {
          "fragment_id": "3ca46849-549e-544d-b72c-d62ef1706612",
          "exact_frozen_fragment": "company insists that its employees are fairly compensated",
          "fragment_sha256": "f7760687e7aaae5d2ed74a264f94485465395efdc8c17afd5deb89c452a4d86c",
          "literal_in_extracted_text": true,
          "offset": 4009
        },
        {
          "fragment_id": "a7869dd7-97d1-56de-86b4-aadf1e970c0a",
          "exact_frozen_fragment": "has raised salaries six times since 2008",
          "fragment_sha256": "57481ba5d7b8f7cc36f5f4ab9281d1e9a35e6b4e931cc6d4f3c427403cbb23b8",
          "literal_in_extracted_text": true,
          "offset": 4083
        },
        {
          "fragment_id": "ef7df23c-ba67-5903-9265-adbd1936ffa3",
          "exact_frozen_fragment": "demanding reinstatement and a review of salaries",
          "fragment_sha256": "0a2f0dcd6186b9e872d21dabe4af51bf3e062ee1ff69970d0f89681271a9d84f",
          "literal_in_extracted_text": true,
          "offset": 4990
        }
      ]
    },
    {
      "witness_id": "AW-D25-20111116125247",
      "document_version_id": "86135a7f-79d7-5d6f-870c-f8bdaa925023",
      "label": "D25",
      "witness_role": "PUBLISHER_PAGE_ARCHIVED_BY_INTERNET_ARCHIVE",
      "original_witness_url": "http://www.eurasianet.org:80/node/64310",
      "archive_replay_url": "https://web.archive.org/web/20111116125247id_/http://www.eurasianet.org:80/node/64310",
      "archive_capture_timestamp": "20111116125247",
      "memento_datetime": "Wed, 16 Nov 2011 12:52:47 GMT",
      "archive_digest_sha1_base32": "7YHK6FDDO6SY5E65OBHLKWNVI3ZFCPL5",
      "retrieved_payload_sha1_base32": "7YHK6FDDO6SY5E65OBHLKWNVI3ZFCPL5",
      "retrieved_payload_sha256": "8f6f54a0cf2dcabe5a02e4f0cb4e60cbc6296e5822e5521498481d682353be35",
      "payload_bytes": 56599,
      "retrieved_at_utc": "2026-09-26T15:45:23.205176+00:00",
      "match_policy": "HTML charset decode, character-reference decode, strip markup/script/style; exact case-sensitive substring in extracted text. No case-folding, stemming, synonyms or punctuation replacement. All matches also pass before whitespace normalization.",
      "locator_policy": "Offsets refer to whitespace-normalized visible replay text, solely for navigation; proof uses unnormalized extracted text.",
      "matched_fragments": [
        {
          "fragment_id": "3ca46849-549e-544d-b72c-d62ef1706612",
          "exact_frozen_fragment": "company insists that its employees are fairly compensated",
          "fragment_sha256": "f7760687e7aaae5d2ed74a264f94485465395efdc8c17afd5deb89c452a4d86c",
          "literal_in_extracted_text": true,
          "offset": 3949
        },
        {
          "fragment_id": "a7869dd7-97d1-56de-86b4-aadf1e970c0a",
          "exact_frozen_fragment": "has raised salaries six times since 2008",
          "fragment_sha256": "57481ba5d7b8f7cc36f5f4ab9281d1e9a35e6b4e931cc6d4f3c427403cbb23b8",
          "literal_in_extracted_text": true,
          "offset": 4023
        },
        {
          "fragment_id": "ef7df23c-ba67-5903-9265-adbd1936ffa3",
          "exact_frozen_fragment": "demanding reinstatement and a review of salaries",
          "fragment_sha256": "0a2f0dcd6186b9e872d21dabe4af51bf3e062ee1ff69970d0f89681271a9d84f",
          "literal_in_extracted_text": true,
          "offset": 4930
        }
      ]
    },
    {
      "witness_id": "AW-D18-20111016234632",
      "document_version_id": "17608513-7164-5d30-9d2e-521338e323d7",
      "label": "D18",
      "witness_role": "OFFICIAL_US_MIRROR_ARCHIVED_BY_INTERNET_ARCHIVE",
      "original_witness_url": "http://iipdigital.usembassy.gov/st/english/texttrans/2011/09/20110901122736su0.701299.html",
      "archive_replay_url": "https://web.archive.org/web/20111016234632id_/http://iipdigital.usembassy.gov/st/english/texttrans/2011/09/20110901122736su0.701299.html",
      "archive_capture_timestamp": "20111016234632",
      "memento_datetime": "Sun, 16 Oct 2011 23:46:32 GMT",
      "archive_digest_sha1_base32": "ZKEE4EVLFL57VP2BUUNU37NWJT5KSAFS",
      "retrieved_payload_sha1_base32": "ZKEE4EVLFL57VP2BUUNU37NWJT5KSAFS",
      "retrieved_payload_sha256": "b6beec09616af212e46df988a4b2149f7bdb4524d9af774f5b6488e6e41358d3",
      "payload_bytes": 26520,
      "retrieved_at_utc": "2026-09-26T15:51:18.423361+00:00",
      "match_policy": "HTML charset decode, character-reference decode, strip markup/script/style; exact case-sensitive substring in extracted text. No case-folding, stemming, synonyms or punctuation replacement. All matches also pass before whitespace normalization.",
      "locator_policy": "Offsets refer to whitespace-normalized visible replay text, solely for navigation; proof uses unnormalized extracted text.",
      "matched_fragments": [
        {
          "fragment_id": "33ce2949-0da2-5839-9b01-566ae7e4bbf4",
          "exact_frozen_fragment": "trial appears to have been marred by violations of procedural due process",
          "fragment_sha256": "adb59f91fd4d4ae7248581db6ff0d94ac88c9b1933c914af2065cd1254d7038a",
          "literal_in_extracted_text": true,
          "offset": 969
        },
        {
          "fragment_id": "b5fdecb6-2ac4-5f56-aae6-6aef4bb7b956",
          "exact_frozen_fragment": "sentencing to six years imprisonment of Natalya Sokolova",
          "fragment_sha256": "a4cd7f69647c69aac6ae7658e8bc3c7ecb7f1038ba3e427a139a5baf7f125c84",
          "literal_in_extracted_text": true,
          "offset": 810
        }
      ]
    },
    {
      "witness_id": "AW-D04-20110529132216",
      "document_version_id": "adbcb401-ba65-5904-95c0-8ef2be653ed1",
      "label": "D04",
      "witness_role": "PUBLISHER_PAGE_ARCHIVED_BY_INTERNET_ARCHIVE",
      "original_witness_url": "http://www.rferl.org:80/content/striking_oil_workers_fired_in_kazakhstan/24207466.html",
      "archive_replay_url": "https://web.archive.org/web/20110529132216id_/http://www.rferl.org:80/content/striking_oil_workers_fired_in_kazakhstan/24207466.html",
      "archive_capture_timestamp": "20110529132216",
      "memento_datetime": "Sun, 29 May 2011 13:22:16 GMT",
      "archive_digest_sha1_base32": "QNZ5VOIFGVHFWCWUASBYDCBEVF7LSE52",
      "retrieved_payload_sha1_base32": "QNZ5VOIFGVHFWCWUASBYDCBEVF7LSE52",
      "retrieved_payload_sha256": "c294d06169104785025a0c564b8f7e4fb34dc5b4ead7a3104c9655b1e4d262a1",
      "payload_bytes": 63205,
      "retrieved_at_utc": "2026-09-26T15:54:40.957305+00:00",
      "match_policy": "HTML charset decode, character-reference decode, strip markup/script/style; exact case-sensitive substring in extracted text. No case-folding, stemming, synonyms or punctuation replacement. All matches also pass before whitespace normalization.",
      "locator_policy": "Offsets refer to whitespace-normalized visible replay text, solely for navigation; proof uses unnormalized extracted text.",
      "matched_fragments": [
        {
          "fragment_id": "7f0b0752-387d-5def-ba3d-ab11c4f1414b",
          "exact_frozen_fragment": "lifting of restrictions on the activities of independent trade unions",
          "fragment_sha256": "ac6e8cc659989a1ad7641a8c281b51f933f1c71cec3ac21505f917005f7d11fe",
          "literal_in_extracted_text": true,
          "offset": 2459
        }
      ]
    },
    {
      "witness_id": "AW-D22-20111120030853",
      "document_version_id": "53cf6bd9-b51d-5f0a-b56f-addd0caa6af2",
      "label": "D22",
      "witness_role": "PUBLISHER_PAGE_ARCHIVED_BY_INTERNET_ARCHIVE",
      "original_witness_url": "http://lada.kz:80/aktau_news/society/1153-zamestitel-ministra-truda-i-socialnoy-zaschity-naseleniya-vstretilsya-s-bastuyuschimi-neftyanikami-mangistau.html",
      "archive_replay_url": "https://web.archive.org/web/20111120030853id_/http://lada.kz:80/aktau_news/society/1153-zamestitel-ministra-truda-i-socialnoy-zaschity-naseleniya-vstretilsya-s-bastuyuschimi-neftyanikami-mangistau.html",
      "archive_capture_timestamp": "20111120030853",
      "memento_datetime": "Sun, 20 Nov 2011 03:08:53 GMT",
      "archive_digest_sha1_base32": "D6ZMCKKXPKQRTGOVCGBBAWGEHZAYFIBH",
      "retrieved_payload_sha1_base32": "D6ZMCKKXPKQRTGOVCGBBAWGEHZAYFIBH",
      "retrieved_payload_sha256": "f4052bb64f40c428c80ad987356bf118e91563e7b0a04e2e3c74393ab942885a",
      "payload_bytes": 82184,
      "retrieved_at_utc": "2026-09-26T15:54:40.958322+00:00",
      "match_policy": "HTML charset decode, character-reference decode, strip markup/script/style; exact case-sensitive substring in extracted text. No case-folding, stemming, synonyms or punctuation replacement. All matches also pass before whitespace normalization.",
      "locator_policy": "Offsets refer to whitespace-normalized visible replay text, solely for navigation; proof uses unnormalized extracted text.",
      "matched_fragments": [
        {
          "fragment_id": "ab55c516-12dc-5533-9e87-a950a6e61b3e",
          "exact_frozen_fragment": "На встречу пришли около 40 нефтяников",
          "fragment_sha256": "b148d270bcae31abceaffc93ac1b5fb9319a992ceed42faf19acac5a221cff59",
          "literal_in_extracted_text": true,
          "offset": 941
        }
      ]
    }
  ]
}
```

## Схема завершённого ответа

```json
{
  "type": "object",
  "properties": {
    "review_id": {
      "enum": [
        "AI_EXCEPTION_REVIEW_V1"
      ]
    },
    "expert_id": {
      "enum": [
        "EXPERT_C_CLAUDE_FABLE_5_1"
      ]
    },
    "actual_model_label": {
      "type": "string",
      "minLength": 1
    },
    "session_id": {
      "type": "string",
      "minLength": 1
    },
    "completed_at_utc": {
      "type": "string",
      "minLength": 1
    },
    "material_sha256": {
      "type": "string",
      "pattern": "[0-9a-f]{64}"
    },
    "attestation": {
      "type": "object",
      "properties": {
        "fresh_isolated_session": {
          "type": "boolean"
        },
        "no_other_expert_answers": {
          "type": "boolean"
        },
        "no_prior_review_decisions": {
          "type": "boolean"
        },
        "no_outcome_used": {
          "type": "boolean"
        },
        "no_factor_or_human_coding": {
          "type": "boolean"
        },
        "outcome_contamination_detected": {
          "type": "boolean"
        }
      },
      "required": [
        "fresh_isolated_session",
        "no_other_expert_answers",
        "no_prior_review_decisions",
        "no_outcome_used",
        "no_factor_or_human_coding",
        "outcome_contamination_detected"
      ],
      "additionalProperties": false
    },
    "answers": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "local_id": {
            "type": "string",
            "minLength": 1
          },
          "target_id": {
            "type": "string",
            "minLength": 1
          },
          "status": {
            "enum": [
              "RESOLVED",
              "NOT_RESOLVED",
              "NEED_HUMAN"
            ]
          },
          "evidence": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "evidence_id": {
                  "type": "string",
                  "minLength": 1
                },
                "evidence_kind": {
                  "enum": [
                    "PRESERVATION_WITNESS",
                    "FROZEN_FRAGMENT",
                    "CURRENT_COPY",
                    "SEARCH_RECORD"
                  ]
                },
                "target_id": {
                  "type": "string",
                  "minLength": 1
                },
                "fragment_ids": {
                  "type": "array",
                  "items": {
                    "type": "string",
                    "minLength": 1
                  },
                  "minItems": 0,
                  "uniqueItems": true
                },
                "url_or_identifier": {
                  "type": "string",
                  "minLength": 1
                },
                "preserved_at_utc": {
                  "type": [
                    "string",
                    "null"
                  ],
                  "minLength": 1
                },
                "payload_sha256": {
                  "type": [
                    "string",
                    "null"
                  ],
                  "pattern": "[0-9a-f]{64}"
                },
                "exact_quote": {
                  "type": "string",
                  "minLength": 1
                },
                "quote_sha256": {
                  "type": "string",
                  "pattern": "[0-9a-f]{64}"
                },
                "locator": {
                  "type": "string",
                  "minLength": 1
                },
                "authentication_method": {
                  "type": "string",
                  "minLength": 1
                },
                "claim_scope": {
                  "type": "string",
                  "minLength": 1
                },
                "supports_dimensions": {
                  "type": "array",
                  "items": {
                    "enum": [
                      "actor_attribution",
                      "group_coverage",
                      "reference_coverage",
                      "time_coverage",
                      "chain_support",
                      "context_sufficiency"
                    ]
                  },
                  "minItems": 0,
                  "uniqueItems": true
                },
                "decisive": {
                  "type": "boolean"
                }
              },
              "required": [
                "evidence_id",
                "evidence_kind",
                "target_id",
                "fragment_ids",
                "url_or_identifier",
                "preserved_at_utc",
                "payload_sha256",
                "exact_quote",
                "quote_sha256",
                "locator",
                "authentication_method",
                "claim_scope",
                "supports_dimensions",
                "decisive"
              ],
              "additionalProperties": false
            },
            "minItems": 1,
            "uniqueItems": false
          },
          "reason": {
            "type": "string",
            "minLength": 1
          },
          "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1
          },
          "remaining_unknowns": {
            "type": "array",
            "items": {
              "type": "string",
              "minLength": 1
            },
            "minItems": 0,
            "uniqueItems": false
          },
          "material_issues": {
            "type": "array",
            "items": {
              "type": "string",
              "minLength": 1
            },
            "minItems": 0,
            "uniqueItems": false
          },
          "search_log": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "query_or_check": {
                  "type": "string",
                  "minLength": 1
                },
                "url_or_identifier": {
                  "type": "string",
                  "minLength": 1
                },
                "result": {
                  "type": "string",
                  "minLength": 1
                }
              },
              "required": [
                "query_or_check",
                "url_or_identifier",
                "result"
              ],
              "additionalProperties": false
            },
            "minItems": 0,
            "uniqueItems": false
          },
          "finding": {
            "type": "object",
            "properties": {
              "kind": {
                "enum": [
                  "AVAILABILITY",
                  "MAPPING",
                  "TRANSLATION"
                ]
              },
              "availability": {
                "enum": [
                  null,
                  "PROVEN_PRE_CUTOFF",
                  "PROVEN_FRAGMENT_PRE_CUTOFF",
                  "NOT_PROVEN"
                ]
              },
              "full_edition_identity_proven": {
                "type": "boolean"
              },
              "mapping_dimensions": {
                "type": "object",
                "properties": {
                  "actor_attribution": {
                    "enum": [
                      "SUPPORTED",
                      "NOT_ESTABLISHED",
                      "CONTRADICTED",
                      "NOT_APPLICABLE"
                    ]
                  },
                  "group_coverage": {
                    "enum": [
                      "SUPPORTED",
                      "NOT_ESTABLISHED",
                      "CONTRADICTED",
                      "NOT_APPLICABLE"
                    ]
                  },
                  "reference_coverage": {
                    "enum": [
                      "SUPPORTED",
                      "NOT_ESTABLISHED",
                      "CONTRADICTED",
                      "NOT_APPLICABLE"
                    ]
                  },
                  "time_coverage": {
                    "enum": [
                      "SUPPORTED",
                      "NOT_ESTABLISHED",
                      "CONTRADICTED",
                      "NOT_APPLICABLE"
                    ]
                  },
                  "chain_support": {
                    "enum": [
                      "SUPPORTED",
                      "NOT_ESTABLISHED",
                      "CONTRADICTED",
                      "NOT_APPLICABLE"
                    ]
                  },
                  "context_sufficiency": {
                    "enum": [
                      "SUPPORTED",
                      "NOT_ESTABLISHED",
                      "CONTRADICTED",
                      "NOT_APPLICABLE"
                    ]
                  }
                },
                "required": [
                  "actor_attribution",
                  "group_coverage",
                  "reference_coverage",
                  "time_coverage",
                  "chain_support",
                  "context_sufficiency"
                ],
                "additionalProperties": false
              },
              "translation_ru": {
                "type": [
                  "string",
                  "null"
                ],
                "minLength": 1
              },
              "language_explanation": {
                "type": [
                  "string",
                  "null"
                ],
                "minLength": 1
              }
            },
            "required": [
              "kind",
              "availability",
              "full_edition_identity_proven",
              "mapping_dimensions",
              "translation_ru",
              "language_explanation"
            ],
            "additionalProperties": false
          }
        },
        "required": [
          "local_id",
          "target_id",
          "status",
          "evidence",
          "reason",
          "confidence",
          "remaining_unknowns",
          "material_issues",
          "search_log",
          "finding"
        ],
        "additionalProperties": false
      },
      "minItems": 1,
      "uniqueItems": false
    }
  },
  "required": [
    "review_id",
    "expert_id",
    "actual_model_label",
    "session_id",
    "completed_at_utc",
    "material_sha256",
    "attestation",
    "answers"
  ],
  "additionalProperties": false,
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:conflict:AI_EXCEPTION_REVIEW_V1:response",
  "title": "Completed independent AI exception review; blank templates intentionally invalid until filled"
}
```

## Пустая форма для заполнения

```json
{
  "review_id": "AI_EXCEPTION_REVIEW_V1",
  "expert_id": "EXPERT_C_CLAUDE_FABLE_5_1",
  "actual_model_label": null,
  "session_id": null,
  "completed_at_utc": null,
  "material_sha256": "767da0d3f4fc189e587efd9084ea20ecb546f4f102c85e11f0153bc9d40a04fa",
  "attestation": {
    "fresh_isolated_session": null,
    "no_other_expert_answers": null,
    "no_prior_review_decisions": null,
    "no_outcome_used": null,
    "no_factor_or_human_coding": null,
    "outcome_contamination_detected": null
  },
  "answers": [
    {
      "local_id": "Q01",
      "target_id": "79748746-11e6-506c-82d5-bc5fe877beb0",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "MAPPING",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_ESTABLISHED",
          "group_coverage": "NOT_ESTABLISHED",
          "reference_coverage": "NOT_ESTABLISHED",
          "time_coverage": "NOT_ESTABLISHED",
          "chain_support": "NOT_ESTABLISHED",
          "context_sufficiency": "NOT_ESTABLISHED"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q02",
      "target_id": "6295e487-c225-5445-ae8b-653d1691579a",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "TRANSLATION",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q03",
      "target_id": "2d63f3f4-cb01-5b8c-b4ec-9bedb09b4363",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "AVAILABILITY",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q04",
      "target_id": "e92b6b89-4e75-5f64-ac26-7dd8005c3d56",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "AVAILABILITY",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q05",
      "target_id": "2c47a771-1301-55be-a2ab-9b2ef1f82510",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "TRANSLATION",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q06",
      "target_id": "a7869dd7-97d1-56de-86b4-aadf1e970c0a",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "TRANSLATION",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q07",
      "target_id": "150704f4-c65a-50f4-b758-b9b456f909ff",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "TRANSLATION",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q08",
      "target_id": "56d19d98-707a-5deb-9472-d355b3835d79",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "TRANSLATION",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q09",
      "target_id": "51e5ac30-63a9-5433-8472-a22727f1db36",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "TRANSLATION",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q10",
      "target_id": "ef7df23c-ba67-5903-9265-adbd1936ffa3",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "TRANSLATION",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q11",
      "target_id": "d3e6a365-8150-545b-8005-c18c4939142b",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "TRANSLATION",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q12",
      "target_id": "092a3bde-2c62-5bae-a31d-b5c8751eb201",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "MAPPING",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_ESTABLISHED",
          "group_coverage": "NOT_ESTABLISHED",
          "reference_coverage": "NOT_ESTABLISHED",
          "time_coverage": "NOT_ESTABLISHED",
          "chain_support": "NOT_ESTABLISHED",
          "context_sufficiency": "NOT_ESTABLISHED"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q13",
      "target_id": "82d1bacf-3ed4-5b42-9d8c-7ee7cd105e94",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "TRANSLATION",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q14",
      "target_id": "3ca46849-549e-544d-b72c-d62ef1706612",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "TRANSLATION",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q15",
      "target_id": "5e3146aa-0dfd-5be2-8f8d-39b94edee3ff",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "MAPPING",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_ESTABLISHED",
          "group_coverage": "NOT_ESTABLISHED",
          "reference_coverage": "NOT_ESTABLISHED",
          "time_coverage": "NOT_ESTABLISHED",
          "chain_support": "NOT_ESTABLISHED",
          "context_sufficiency": "NOT_ESTABLISHED"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q16",
      "target_id": "1abf6c8c-5295-5837-b75f-00c55daf3a8c",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "MAPPING",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_ESTABLISHED",
          "group_coverage": "NOT_ESTABLISHED",
          "reference_coverage": "NOT_ESTABLISHED",
          "time_coverage": "NOT_ESTABLISHED",
          "chain_support": "NOT_ESTABLISHED",
          "context_sufficiency": "NOT_ESTABLISHED"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q17",
      "target_id": "9b1dfe95-b290-533c-9414-d8f18d880b1d",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "AVAILABILITY",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q18",
      "target_id": "d521033f-59ce-5518-9227-b5fe9cb7570f",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "TRANSLATION",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q19",
      "target_id": "3f4dc104-40c7-59db-ad5c-61f8a80232bc",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "MAPPING",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_ESTABLISHED",
          "group_coverage": "NOT_ESTABLISHED",
          "reference_coverage": "NOT_ESTABLISHED",
          "time_coverage": "NOT_ESTABLISHED",
          "chain_support": "NOT_ESTABLISHED",
          "context_sufficiency": "NOT_ESTABLISHED"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q20",
      "target_id": "d0c7e8eb-6859-55ff-921a-f2e43e8f03d0",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "MAPPING",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_ESTABLISHED",
          "group_coverage": "NOT_ESTABLISHED",
          "reference_coverage": "NOT_ESTABLISHED",
          "time_coverage": "NOT_ESTABLISHED",
          "chain_support": "NOT_ESTABLISHED",
          "context_sufficiency": "NOT_ESTABLISHED"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q21",
      "target_id": "e85d2031-f492-5e93-b0ac-a7e84f27c7c7",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "AVAILABILITY",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q22",
      "target_id": "d2eefc78-82b0-5eb7-b1ae-533745cbbd79",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "AVAILABILITY",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q23",
      "target_id": "b5fdecb6-2ac4-5f56-aae6-6aef4bb7b956",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "TRANSLATION",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q24",
      "target_id": "7f0b0752-387d-5def-ba3d-ab11c4f1414b",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "TRANSLATION",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q25",
      "target_id": "bc34ea72-a9ac-5e81-ab20-3f2efb729872",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "MAPPING",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_ESTABLISHED",
          "group_coverage": "NOT_ESTABLISHED",
          "reference_coverage": "NOT_ESTABLISHED",
          "time_coverage": "NOT_ESTABLISHED",
          "chain_support": "NOT_ESTABLISHED",
          "context_sufficiency": "NOT_ESTABLISHED"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q26",
      "target_id": "15e6b7e7-98f3-5830-8d5d-ae44862e445a",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "TRANSLATION",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q27",
      "target_id": "d1067ad6-51d6-5a42-b6ea-8cf74c4fd71c",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "TRANSLATION",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q28",
      "target_id": "26b9e671-5e1e-5460-a80c-2e803ca81ba6",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "AVAILABILITY",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q29",
      "target_id": "a6f0883a-d5fc-521b-8662-1c160fded750",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "MAPPING",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_ESTABLISHED",
          "group_coverage": "NOT_ESTABLISHED",
          "reference_coverage": "NOT_ESTABLISHED",
          "time_coverage": "NOT_ESTABLISHED",
          "chain_support": "NOT_ESTABLISHED",
          "context_sufficiency": "NOT_ESTABLISHED"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q30",
      "target_id": "02248e81-d235-5306-aef3-5dec2af93ebb",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "AVAILABILITY",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q31",
      "target_id": "33ce2949-0da2-5839-9b01-566ae7e4bbf4",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "TRANSLATION",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q32",
      "target_id": "2c58ce09-3654-5a87-89be-4b1953f467c7",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "MAPPING",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_ESTABLISHED",
          "group_coverage": "NOT_ESTABLISHED",
          "reference_coverage": "NOT_ESTABLISHED",
          "time_coverage": "NOT_ESTABLISHED",
          "chain_support": "NOT_ESTABLISHED",
          "context_sufficiency": "NOT_ESTABLISHED"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q33",
      "target_id": "cc839407-9eb7-5e05-acca-70f1577883d4",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "TRANSLATION",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q34",
      "target_id": "b344006d-0950-57af-b0e7-60eb7b4f5217",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "TRANSLATION",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q35",
      "target_id": "cd9eb952-6af0-5708-8703-49673415cbe7",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "MAPPING",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_ESTABLISHED",
          "group_coverage": "NOT_ESTABLISHED",
          "reference_coverage": "NOT_ESTABLISHED",
          "time_coverage": "NOT_ESTABLISHED",
          "chain_support": "NOT_ESTABLISHED",
          "context_sufficiency": "NOT_ESTABLISHED"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q36",
      "target_id": "951f300c-27d0-5a09-b312-e3fdad147f54",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "MAPPING",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_ESTABLISHED",
          "group_coverage": "NOT_ESTABLISHED",
          "reference_coverage": "NOT_ESTABLISHED",
          "time_coverage": "NOT_ESTABLISHED",
          "chain_support": "NOT_ESTABLISHED",
          "context_sufficiency": "NOT_ESTABLISHED"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q37",
      "target_id": "3dcd5aa1-e2a9-5dd9-a2d9-992f9c80e835",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "AVAILABILITY",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q38",
      "target_id": "d3b8d52c-3dbb-5d07-84bd-e07acf35fbbb",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "AVAILABILITY",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q39",
      "target_id": "3fba0d88-4c72-5d24-b879-52904c88a0e5",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "MAPPING",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_ESTABLISHED",
          "group_coverage": "NOT_ESTABLISHED",
          "reference_coverage": "NOT_ESTABLISHED",
          "time_coverage": "NOT_ESTABLISHED",
          "chain_support": "NOT_ESTABLISHED",
          "context_sufficiency": "NOT_ESTABLISHED"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q40",
      "target_id": "49c356b3-3585-587c-9573-d4326e97de77",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "TRANSLATION",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q41",
      "target_id": "04ab9fff-fe17-5b34-8733-f046d1b1ed06",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "TRANSLATION",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    },
    {
      "local_id": "Q42",
      "target_id": "fcd2397b-c4e9-5035-9ff9-45969f55ecf4",
      "status": null,
      "evidence": [],
      "reason": null,
      "confidence": null,
      "remaining_unknowns": [],
      "material_issues": [],
      "search_log": [],
      "finding": {
        "kind": "TRANSLATION",
        "availability": null,
        "full_edition_identity_proven": false,
        "mapping_dimensions": {
          "actor_attribution": "NOT_APPLICABLE",
          "group_coverage": "NOT_APPLICABLE",
          "reference_coverage": "NOT_APPLICABLE",
          "time_coverage": "NOT_APPLICABLE",
          "chain_support": "NOT_APPLICABLE",
          "context_sufficiency": "NOT_APPLICABLE"
        },
        "translation_ru": null,
        "language_explanation": null
      }
    }
  ]
}
```