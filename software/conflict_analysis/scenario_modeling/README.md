# PR-3 Scenario Modeling MVP

`Scenario = baseline + override`. Baseline — существующий неизменяемый
`CalculationSnapshot` из PR-2; override — список внутри `ScenarioModel`.

```text
Experiment → Baseline Snapshot → Scenario Override → CalculationAdapter
           → Scenario CalculationRun → Result View
```

## Запуск и UI

Из `software/conflict_analysis`, в существующем Python 3.12 окружении:

```text
python manage.py check --settings=player_integration.settings
python manage.py runserver --settings=player_integration.settings
```

Для локальной раздачи static через runserver: `DJANGO_DEBUG=true`.
Для deployment используйте обычный collectstatic с этим же профилем.
Подключение к PostgreSQL задаётся существующими `POSTGRES_*`.

1. Откройте `/player/calculations/` с существующей Player G8 session.
2. Выберите Experiment/TimeSlice, задайте beta-веса и получите результат PR-2.
3. Нажмите «Создать сценарий из этого расчёта».
4. Выберите известный параметр POS, KVS (SAL), RGU или KVPTN. Измените число
   или slider, затем нажмите «Применить и пересчитать».
5. Добавляйте изменения, удаляйте отдельные override или сбросьте весь список.
   «Пересчитать сценарий» воспроизводит сохранённую комбинацию.

Результат показывает baseline UNO, scenario UNO, delta UNO, статусы,
completeness, список изменений, источники baseline, предупреждения Core,
PTN-результаты и JSON для offline replay. Ноль отображается как 0,
отсутствующий результат — «Недостаточно данных». Delta недоступна,
если хотя бы один UNO отсутствует.

Для объяснения влияния каждый override отдельно применяется к baseline и
вычисляется Core. Эти отдельные delta не аддитивны и не являются причинными
оценками. Общий результат всегда вычисляется заново со всем списком override.

## Контракт и изоляция

- Baseline сохраняется целиком, включая hash, topology, исходные статусы,
  source ID/version, Experiment, AssessmentSet и TimeSlice. Повторные запросы
  не захватывают новый snapshot и не перечитывают ParameterValue.
- `ScenarioModel` — frozen Python value object, не Django ORM-модель.
  Он содержит UUID, baseline и канонически упорядоченный tuple override.
  Изменение возвращает новый объект. Повторный override заменяет предыдущее
  значение того же параметра; возврат к baseline удаляет override.
- POS/KVS адресуются по relation; KVPTN — по PTN; RGU — по actor и применяется
  сразу во всех его PTN. Невозможны новые строки topology или cross-lane targets.
- Можно менять только известные числовые значения. UNKNOWN,
  INSUFFICIENT_DATA, NOT_APPLICABLE и OPEN_METHOD остаются исходными null,
  недоступны в selector и отклоняются при прямой отправке формы.
- Override — точное десятичное число: POS −10…10, остальные параметры 0…10,
  до 32 знаков после точки. Float/bool/NaN/Infinity не принимаются моделью.
  Slider имеет шаг 0,1; ввод точного числа не округляется через slider.
- Адаптер создаёт производный snapshot через immutable copy, сохраняя исходные
  scope/pins и неизменённые InputValue. Изменённые входы имеют PROVISIONAL
  и источник `SCENARIO:<scenario UUID>:<target>`. Это гипотетические входы,
  а не новые исходные оценки. Только существующий `calculation.calculate()`
  вычисляет поляризацию, UNO, trace и статус; W=0 остаётся NOT_COMPUTABLE.
- HUMAN и AI всегда принадлежат своим Experiment/AssessmentSet; сценарий не
  объединяет значения. Проверка Foundation admission выполняется при каждом
  запросе, в том числе после изменения прав, freeze и archive.
- Нет записей в AssessmentSet, ParameterValue, Experiment, AuditEvent или
  другие доменные таблицы; нет миграций, изменения Core или формулы.

## Хранение Scenario Model

MVP использует подписанный form state с baseline и overrides. Он передаётся
в hidden-поле `scenario_token`, привязан к user и Django session и проверяется
перед каждым действием. Это подпись, не шифрование. Token не попадает в URL,
cookie или browser storage; ответ имеет `no-store`, CSRF и CSP.

`POST /player/calculations/scenarios/` принимает form-urlencoded с
`scenario_token` и действием `start`, `set` (+ `parameter`, `value`),
`remove` (+ `parameter`), `recalculate` или `reset`.
Лишние и повторные поля отклоняются. JSON API PR-2 остаётся прежним.

Срок state — 8 часов бездействия, затем нужен новый сценарий из результата.
Новая авторизация/ротация session делает старый token недействительным.
Максимум 256 override и 1 000 000 символов подписанного state. Слишком большой
baseline по-прежнему доступен в PR-2, но без кнопки создания сценария.
Постоянного серверного каталога, shared editing и восстановления через URL нет.
Для сохранения скопируйте Scenario Model JSON; HTTP-импорт неподписанного
JSON не предоставляется. Offline Python replay:

```python
import json
from scenario_modeling.model import ScenarioModel
from scenario_modeling.adapter import CalculationAdapter, result_view

model = ScenarioModel.from_dict(json.loads(saved_model_json))
run = CalculationAdapter.run(model)
assert run.run.to_json() == saved_scenario_run_json
comparison = result_view(model)
```

Поставка, как PR-2, запускается из исходного дерева. Корневой wheel allowlist
и основной профиль проекта не изменены; standalone wheel не заявляется.

## Файлы

| Путь внутри `scenario_modeling/` | Назначение |
|---|---|
| `model.py` | Frozen baseline + overrides, scales, targets, JSON replay |
| `adapter.py` | Производный snapshot, Scenario CalculationRun, delta и объяснения через Core |
| `session.py` | Подписанный state, session binding, повторный Foundation admission |
| `views.py`, `urls.py`, `apps.py` | Form flow, validation и подключение Django |
| `templates/scenario_modeling/result.html` | Сравнение, параметры, список изменений и экспорт |
| `static/scenario_modeling/scenario.js`, `scenario.css` | Связь input/slider и адаптивная раскладка |
| `tests/test_model.py` | Числовые, immutable и isolation контракты |
| `tests/test_http.py` | Реальный Foundation/Player/Core flow без SQL writes |
| `tests/test_browser.py`, `tests/browser_e2e.mjs` | Chromium: формы, slider, replay, desktop/mobile |
| `pytest.ini`, `.gitignore` | Вход тестов и исключение артефактов |
| `VALIDATION.md` | Зафиксированные результаты проверки |

В `player_integration/` изменены только `settings.py`, `project_urls.py`,
`views.py` и два шаблона `base.html`, `result.html`: подключение приложения,
маршрута, assets и кнопки создания сценария из уже полученного результата.

## Тесты

```powershell
$env:USE_SQLITE = 'true'
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m pytest -c scenario_modeling/pytest.ini scenario_modeling/tests calculation/tests player_integration/tests/test_e2e.py -q -p no:cacheprovider
```

Browser E2E требует PostgreSQL, Node 22+ и Chromium (тот же CDP helper, что
в PR-2). Задайте `USE_SQLITE=false`, отдельную тестовую базу через `POSTGRES_*`,
`SCENARIO_BROWSER=1`; для регрессии браузера PR-2 также `PLAYER_INTEGRATION_BROWSER=1`:

```text
python -m pytest -c scenario_modeling/pytest.ini scenario_modeling/tests player_integration/tests/test_browser.py -q -p no:cacheprovider
```

На SQLite browser test пропускается: штатный TransactionTestCase flush
конфликтует с существующими Foundation protection triggers. Триггеры не
отключаются; на PostgreSQL проверяется полный жизненный цикл тестовой БД.
