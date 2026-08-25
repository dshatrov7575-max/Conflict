# Известные ограничения OWNER-TEST

- Это исследовательский presentation-only прототип, а не production Studio.
- Данные существуют только в текущей браузерной сессии; публикации и записи в
  Foundation ORM/production database нет.
- Поддерживается только `SHOWCASE_SESSION_V1` JSON. OCR, XLSX, live LLM/RAG и
  production import здесь отсутствуют.
- Защитный лимит: не более 500 элементов в одной коллекции.
- Защитный лимит preview: не более 10 000 ячеек.
- Нет формул, Calculation Core, scalar Power/POW, POW×SAL, прогноза, risk score,
  ранжирования, рекомендаций или Response Engine.
- Чат отключён; Help локален. Установка зависимостей требует сети, дальнейший
  локальный запуск — нет.
