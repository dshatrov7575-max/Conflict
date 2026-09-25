# PR-2 Player Integration

`Experiment → CalculationSnapshot → CalculationRun → Result View` поверх
неизменённого `calculation` (`POLARIZATION_V1_BETA / 1.0.0`).

## Запуск

Из `software/conflict_analysis` в существующем Python 3.12 окружении:

```text
python manage.py check --settings=player_integration.settings
python manage.py runserver --settings=player_integration.settings
```

Для локальной раздачи CSS через runserver задайте `DJANGO_DEBUG=true`.
Для развёртывания используйте обычный Django staticfiles/collectstatic процесс
с тем же профилем настроек. Подключение к PostgreSQL задаётся существующими
переменными `POSTGRES_*`; интеграция не создаёт базу и не меняет миграции.

Откройте `/player/calculations/` с заранее выданной Django session Player G8.
Введите UUID эксперимента, выберите его временной срез, укажите явные beta-веса
или оставьте UNKNOWN и нажмите «Рассчитать». HUMAN/AI и профиль эксперта берутся
из допущенного Foundation эксперимента, а не из запроса.

Все новые файлы находятся в `player_integration/**`. Профиль
`player_integration.settings` добавляет приложение и отдельный composition root,
сохраняя существующие `/player/`, `/studio/` и `/api/foundation/` маршруты.
Исходный Player и конфигурация проекта не изменены: кнопка в существующем G8 UI
не добавляется. Профиль запуска и точка входа выше обеспечивают самостоятельный
рабочий путь в разрешённой области файлов.

Это поставка для исходного дерева: существующий корневой wheel allowlist не
содержит `player_integration`; подключение его к основному wheel/профилю и общей
CI-конфигурации потребует отдельно разрешённых изменений за пределами PR-2.

## Граница интеграции

- `admit_assessment_scope()` — существующая Foundation authority для session,
  точного набора Player permissions, доступа к проекту и assessment projection.
- Сервис повторяет admission под общим Project lock, затем вызывает существующий
  `capture_snapshot()` для одного точного Experiment/TimeSlice.
- Только `calculation.calculate()` вычисляет результат. Представление использует
  Core JSON без округления, формул, подстановок весов или агрегации HUMAN/AI.
- POS/SAL читаются из существующих терминальных ParameterValue revisions.
  Веса RGU/KVPTN передаются только через существующий `BetaWeights`; отсутствующие
  значения остаются UNKNOWN. Веса привязаны к Experiment/TimeSlice и topology.
- Расчёт не создаёт и не обновляет ParameterValue, Experiment, Assessment,
  ImportRun, AuditEvent или другие доменные записи. В интеграции нет моделей,
  миграций, хранилища результатов, фоновых запусков и browser storage.
- HTML показывает отдельную lane, provenance/pins, UNO, все PTN-метрики,
  completeness, предупреждения, trace, исходные статусы и source ID/version.
  Ноль отображается как `0`, отсутствие результата — как `—`/«Недостаточно данных».
- POST защищён стандартным Django CSRF. Ответы обработчиков имеют `no-store`,
  `Vary: Cookie`, CSP и `nosniff`. Caller identity/role override headers отклоняются.
- Снимки и запуски эфемерны. На Result View доступны точные JSON для копирования.
  Новый запуск читает текущие оценки; старый экспорт воспроизводится offline,
  включая после исправлений, заморозки и архивирования эксперимента.

## HTTP и Python

```text
GET /player/calculations/
GET /player/calculations/experiments/<experiment_uuid>/
GET /player/calculations/experiments/<experiment_uuid>/time-slices/<time_slice_uuid>/
POST /player/calculations/experiments/<experiment_uuid>/time-slices/<time_slice_uuid>/
```

GET последнего маршрута открывает форму. Form-urlencoded POST возвращает HTML.
JSON POST возвращает `PLAYER_CALCULATION_RESULT_V1` с `lane`, `snapshot`, `run` и
`result_digest`. Обе формы вызывают один сервис. JSON-запрос требует существующей
session и стандартного cookie/header CSRF, как HTML-форма.

Тело JSON ограничено 256 KiB; дополнительные/повторные поля отклоняются:

```json
{
  "experiment_id": "<experiment_uuid>",
  "time_slice_id": "<time_slice_uuid>",
  "rgu": {
    "<projected_actor_uuid>": {
      "status": "PROVISIONAL",
      "value": "1",
      "source_id": "beta-rgu-source",
      "source_version": "1"
    }
  },
  "kvptn": {
    "<projected_element_uuid>": {
      "status": "PROVISIONAL",
      "value": "1",
      "source_id": "beta-q-source",
      "source_version": "1"
    }
  }
}
```

Можно передать пустые `rgu`/`kvptn`. Каждая группа содержит до 1000 объектов.
Числа передаются обычными десятичными строками на шкале 0…10 (до 32 знаков после
точки), не JSON float и не экспонентой. UNKNOWN/INSUFFICIENT_DATA/
NOT_APPLICABLE/OPEN_METHOD требуют `null`. Источники и версии — непустые строки
до 255 символов. Числовой вес требует явного source_id, отличного от `ABSENT`.
Это ограничения HTTP-адаптера, не изменение числового контракта Core.

```python
from player_integration.services import calculate_experiment
from calculation import CalculationSnapshot, calculate

view = calculate_experiment(
    user=user, experiment_id=experiment_id, time_slice_id=time_slice_id,
    beta_weights=weights,  # существующий calculation.foundation.BetaWeights
)
payload = view.as_dict()
replayed = calculate(CalculationSnapshot.from_json(view.snapshot.to_json()))
assert replayed.to_json() == view.run.to_json()
```

## Тесты

Корневой pytest testpaths не изменён. Явный локальный entry point включает все
новые тесты и профиль интеграции. Быстрый прогон PowerShell:

```powershell
$env:USE_SQLITE = 'true'
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m pytest -c player_integration/pytest.ini player_integration/tests -p no:cacheprovider
python -m pytest calculation/tests -p no:cacheprovider
```

HTTP E2E создают тестовые эксперименты и оценки через реальный Foundation API,
затем проходят admission, Core capture/calculate и HTML/JSON Result View без
моков. Тесты проверяют отсутствие SQL INSERT/UPDATE/DELETE при интеграционных
запросах и неизменность всех ParameterValue. Создание тестовых исходных оценок
в fixture не является поведением расчёта.

Покрытие: COMPLETE/PARTIAL/NOT_COMPUTABLE; HUMAN/AI; отдельные временные срезы;
UNKNOWN и нули; отсутствующий KVPTN при доступных PTN-метриках; successor
correction и сохранение SAL lineage; replay после freeze/archive; scope,
permissions, CSRF, ошибки ввода; HTML escaping и точная сериализация.

Настоящий Chromium E2E использует существующий CDP helper проекта. Нужны Node
22+ и установленный Chrome/Chromium/Edge; при необходимости задайте
`STUDIO_CHROME_BIN` и `NODE_BIN`. В тесте запускается отдельный браузерный профиль,
а Django StaticLiveServer работает с тестовой БД:

```powershell
$env:PLAYER_INTEGRATION_BROWSER = '1'
python -m pytest -c player_integration/pytest.ini player_integration/tests -p no:cacheprovider
```

Без opt-in только browser-тест явно пропускается. Он проходит UI-выбор
эксперимента и среза, native form submit с CSRF, независимые результаты HUMAN=100
и AI=0, UNKNOWN без подстановок, загрузку CSS и отсутствие browser storage.

Для PostgreSQL задайте `USE_SQLITE=false` и `POSTGRES_*` для **одноразовой** базы,
примените миграции с нуля и выполните check и тот же набор. SQLite не проверяет
PostgreSQL row locks. Версия и фактические результаты проверки перечислены
в `VALIDATION.md`.

## Изменённые файлы

| Файлы внутри `player_integration/` | Назначение |
|---|---|
| `services.py` | Foundation admission, snapshot → run и эфемерный ResultView |
| `inputs.py` | Ограниченный JSON-контракт и форма beta-весов |
| `views.py`, `urls.py` | HTML/JSON HTTP-путь и защита запросов |
| `apps.py`, `settings.py`, `project_urls.py`, `__init__.py` | Подключаемый профиль без правок вне каталога |
| `templates/player_integration/*.html` | Выбор эксперимента/среза, форма и Result View |
| `static/player_integration/result.css` | Адаптивное оформление таблиц и результата |
| `tests/test_e2e.py`, `tests/__init__.py` | Полные HTTP-сценарии и Foundation fixtures |
| `tests/test_browser.py`, `tests/browser_e2e.mjs` | Настоящий браузерный E2E |
| `pytest.ini`, `.gitignore` | Локальный вход тестов и исключение временных артефактов |
| `README.md`, `VALIDATION.md` | Подключение, контракты, состав файлов и результаты проверки |
