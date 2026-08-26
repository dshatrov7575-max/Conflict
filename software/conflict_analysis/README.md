# Conflict Analysis

## Legacy package boundary

`project-package-1.0.0` is retained for historical round trips only.
`EvidenceSource`, `EvidenceLink`, `Scenario`, and `ScenarioOverride` are
`LEGACY_COMPATIBILITY_ONLY`; they neither form a second authoritative evidence
chain nor authorize a scenarios/modeling feature. Current Foundation evidence
uses `Source -> Document -> DocumentVersion/DocumentContent -> TextFragment ->
Fact -> Assessment/ParameterValue`. Unresolved v1 evidence remains an explicit
compatibility receipt/data gap, and Foundation 2.0.0 export uses only canonical
evidence sections.

## ConflictAnalysis Studio — исследовательский прототип

Issue #64 добавляет отдельный запускаемый showcase для партнёрского показа.
Это presentation-only интерфейс, а не production Studio: он работает только с
явно маркированным JSON `SHOWCASE_SESSION_V1` в текущей браузерной сессии и не
записывает данные в Foundation ORM или production database. Формат showcase не
является Foundation package и не может использоваться вместо него.

Из каталога `software/conflict_analysis` запустите:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_studio_showcase.ps1
```

По умолчанию интерфейс доступен на <http://127.0.0.1:8000/>. Адрес и порт можно
задать явно:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_studio_showcase.ps1 -ListenAddress 127.0.0.1 -Port 8010
```

`-ExecutionPolicy Bypass` действует только для этого процесса PowerShell и не
меняет системную policy. Если локальная policy уже разрешает подписанные или
локальные scripts, допустим также прямой вызов `.\scripts\run_studio_showcase.ps1`.

Launcher сначала использует `.venv\Scripts\python.exe` из каталога приложения
(затем из корня репозитория), а при его отсутствии — `py -3.12`. Если Python
3.12 или Django недоступны, команда завершится с точной диагностикой и не будет
пытаться изменить окружение. Установить зависимости можно отдельно:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Воспроизводимый ручной эквивалент запуска:

```powershell
$env:DJANGO_SETTINGS_MODULE = "conflict_analysis.studio_showcase_settings"
$env:DJANGO_DEBUG = "true"
$env:USE_SQLITE = "true"
py -3.12 manage.py check --settings conflict_analysis.studio_showcase_settings
py -3.12 manage.py runserver 127.0.0.1:8000 --settings conflict_analysis.studio_showcase_settings --noreload
```

Миграции перед этим запуском не нужны: showcase settings используют только
in-memory SQLite для системной конфигурации Django, а showcase views не вызывают
ORM. Проектные изменения живут в памяти страницы; `Открыть`, `Импорт` и
`Экспорт` обмениваются только `SHOWCASE_SESSION_V1`. В `localStorage` допустимы
только versioned UI preferences: ширины панелей и активная правая вкладка.

Границы showcase неизменны: нет ORM-моделей и миграций, authoritative
publication, формул, Calculation Core, scalar Power/`POW`, `POW × SAL`,
prediction, risk score, recommendations или scenario/modeling engine.
`Опубликовать` не имитирует успех; `Чат` отключён до отдельного provider/RAG
gate. Подробное решение зафиксировано в
[`docs/adr/ADR_STUDIO_SHOWCASE_002A.md`](docs/adr/ADR_STUDIO_SHOWCASE_002A.md).

Локальная сфокусированная проверка:

```powershell
$env:DJANGO_SETTINGS_MODULE = "conflict_analysis.studio_showcase_settings"
py -3.12 manage.py check --settings conflict_analysis.studio_showcase_settings
$env:USE_SQLITE = "true"
py -3.12 -m pytest domain/tests/test_studio_showcase_session.py domain/tests/test_studio_showcase_http.py domain/tests/test_studio_showcase_static_contracts.py
```

Каркас первой итерации — модульный монолит на Python 3.12, Django 5.2 LTS,
Django REST Framework и PostgreSQL 18. Доменный модуль расположен в `domain/`;
проектная конфигурация и точки входа — в `conflict_analysis/`.

PostgreSQL 18 является единственной штатной и интеграционной базой. Docker
Compose фиксирует основную версию 18 через образ `postgres:18-alpine` и
монтирует именованный volume в штатный для PostgreSQL 18 путь
`/var/lib/postgresql`.
Контракт PostgreSQL gate для этой итерации проверяется на чистой одноразовой
PostgreSQL 18.4: миграции применяются с нуля, затем выполняются
`manage.py check` и сфокусированный набор тестов с `USE_SQLITE=false`. SQLite
включается только явно и предназначен для быстрых локальных тестов; успешный
прогон на SQLite не заменяет PostgreSQL 18.4 gate.

## Запуск через Docker Compose

При необходимости скопируйте `.env.example` в `.env` и замените локальные
секреты. Затем выполните:

```bash
docker compose up --build
```

Compose ожидает готовности PostgreSQL 18 по healthcheck, применяет миграции и
запускает сервер на <http://localhost:8000>.

Полезные команды:

```bash
docker compose run --rm web python manage.py migrate --noinput
# Legacy V1 compatibility/regression seed only; current V4 data uses the
# versioned Foundation import boundary documented in docs/foundation-package-v2.md.
docker compose run --rm web python manage.py seed_zhanaozen
docker compose run --rm web pytest
docker compose run --rm web python manage.py check
```

Для чистой проверки миграций удалите только именованный volume этого Compose
проекта и снова запустите миграцию:

```bash
docker compose down --volumes
docker compose run --rm web python manage.py migrate --noinput
```

Команда `down --volumes` удаляет локальные данные PostgreSQL этого Compose
проекта; не используйте её для базы с нужными данными.

## Локальный запуск без Docker

Нужны Python 3.12 и доступный PostgreSQL 18. Установите приложение с test extras:

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python manage.py migrate
python manage.py runserver
```

POSIX shell:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python manage.py migrate
python manage.py runserver
```

Параметры подключения задаются переменными `POSTGRES_DB`, `POSTGRES_USER`,
`POSTGRES_PASSWORD`, `POSTGRES_HOST` и `POSTGRES_PORT`. По умолчанию приложение
ищет PostgreSQL на `localhost:5432`.

Быстрый тестовый прогон на SQLite требует явного opt-in:

```bash
USE_SQLITE=true pytest
```

В PowerShell эквивалентная команда:

```powershell
$env:USE_SQLITE = "true"
python -m pytest
```

Перед интеграционной поставкой верните `USE_SQLITE=false` и выполните миграции,
`manage.py check` и сфокусированные тесты на чистой PostgreSQL 18.4 базе.

## Границы архитектуры

`conflict_analysis/` содержит только composition root: настройки, URL и
ASGI/WSGI. Доменная модель, policy, импорт/экспорт и management commands живут
в приложении `domain`. Такое разделение оставляет возможность вынести API,
хранилище или фоновые процессы позднее, не меняя устойчивые доменные UUID,
коды и версионированный формат проектного пакета.
