# Conflict Analysis

Каркас первой итерации — модульный монолит на Python 3.12, Django 5.2 LTS,
Django REST Framework и PostgreSQL. Доменный модуль расположен в `domain/`;
проектная конфигурация и точки входа — в `conflict_analysis/`.

PostgreSQL является штатной и интеграционной базой. SQLite включается только
явно и предназначен для быстрых локальных тестов; успешный прогон на SQLite не
заменяет PostgreSQL gate.

## Запуск через Docker Compose

При необходимости скопируйте `.env.example` в `.env` и замените локальные
секреты. Затем выполните:

```bash
docker compose up --build
```

Compose ожидает готовности PostgreSQL по healthcheck, применяет миграции и
запускает сервер на <http://localhost:8000>.

Полезные команды:

```bash
docker compose run --rm web python manage.py migrate --noinput
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

Нужны Python 3.12 и доступный PostgreSQL. Установите приложение с test extras:

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

Перед интеграционной поставкой верните `USE_SQLITE=false` и выполните тесты на
чистой PostgreSQL базе.

## Границы архитектуры

`conflict_analysis/` содержит только composition root: настройки, URL и
ASGI/WSGI. Доменная модель, policy, импорт/экспорт и management commands живут
в приложении `domain`. Такое разделение оставляет возможность вынести API,
хранилище или фоновые процессы позднее, не меняя устойчивые доменные UUID,
коды и версионированный формат проектного пакета.
