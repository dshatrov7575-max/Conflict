# Conflict Analysis

## Foundation Studio contract addendum

Production definition authoring uses the single persisted
`ProjectDefinitionVersion.manifest` authority and the typed schema
`project-definition-manifest-1.0.0`. Server-side services enforce DRAFT
create/open/clone/save, computed validation, and atomic first publication. The
first publication creates the exact initial workspace pin, versioned HelpTopic
bindings, one `ProjectPublication`, and exclusive definition/workspace audits
in one transaction. ADRs 0002–0005 define the typed manifest, authorization,
bootstrap, versioned-help, and additive Foundation 2.1 package boundaries.

No Studio-local structural tables, second publisher, caller-supplied
`valid:true`, formula/Calculation Core, scalar Power, prediction, risk score,
or recommendations are authorized by this boundary.

## Legacy package boundary

`project-package-1.0.0` is retained for historical round trips only.
`EvidenceSource`, `EvidenceLink`, `Scenario`, and `ScenarioOverride` are
`LEGACY_COMPATIBILITY_ONLY`; they neither form a second authoritative evidence
chain nor authorize a scenarios/modeling feature. Current Foundation evidence
uses `Source -> Document -> DocumentVersion/DocumentContent -> TextFragment ->
Fact -> Assessment/ParameterValue`. Unresolved v1 evidence remains an explicit
compatibility receipt/data gap, and Foundation 2.0.0 export uses only canonical
evidence sections.

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
