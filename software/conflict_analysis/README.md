# Conflict Analysis

## Production Player G8: assessment experiments and bounded XLSX import

G8 adds independent HUMAN and AI assessment experiments to the accepted Player
workspace. The single Foundation route
`/api/foundation/player/workspaces/<workspace_id>/experiments/` retains the G7
GET contract and also accepts G8 experiment creation. Experiment values use the
existing `ParameterValue` record as the only numeric persistence lane. DRAFT,
FROZEN and ARCHIVED lifecycle rules, immutable successor corrections and exact
operation-key replay are enforced by Foundation services.

The browser sends a bounded raw XLSX upload with same-origin session and CSRF
protection. Foundation parses the archive through one bounded XML adapter,
rejects formulas including cached formula values, and performs a deterministic
zero-write preview before an atomic import. The packaged
`KZ_ZHANAOZEN_EXPERT_V2_A5_0_1` profile contains all 330 source records: 288 are
transferable with review, while 18 `METHOD_BLOCKED` and 24
`RECODING_REQUIRED` records remain `BETA_COMPATIBILITY_INPUT_ONLY`. A
`POLARIZATION_V1_IMPORT_SNAPSHOT_V1` receipt is stored only for a complete
330-row file and never acts as a second value store.

G8 does not create Fact, Document or Fragment records, write Product ORM data,
or implement evidence, calculation or modeling behavior. The decision and
runtime contracts are documented in
[`docs/adr/0015-production-player-g8-experiments-xlsx.md`](docs/adr/0015-production-player-g8-experiments-xlsx.md)
and
[`docs/production-player-g8-import-profile.md`](docs/production-player-g8-import-profile.md).

## Production Studio C2A: lifecycle publication

`C2A_LIFECYCLE_PUBLICATION` adds one Russian, server-rendered composition shell
at `/studio/lifecycle/definitions/<UUID>/`. It reads the accepted Foundation
definition and publication-readiness snapshots, optionally previews an initial
DRAFT, validates a successor, and prepares initial or successor publication.
The Studio view owns no model, lifecycle inference or mutation endpoint;
Foundation remains the sole object-scope, capability, validation, publication,
audit and recovery authority. Server-rendered presentation facts are derived
only through `studio_principal_from_user` and `StudioCapability`; an incoherent
permission set fails closed without Product-side permission reconstruction.

Every action is enabled from a fresh definition plus fresh no-store readiness
snapshot and both are fetched again before an attempt is prepared. Readiness is
advice only. Each semantic write attempt is sealed in memory with one visible
UUIDv4, exact route, strong `If-Match` and canonical body. The current same-origin
CSRF token is read only immediately before an allowed send; it is never part of
the sealed request identity or a recovery ticket. Exact action, definition UUID
and route equality are rechecked before preparation and again before send.

Validation and publication recovery are deliberately separate. Validation uses
`FOUNDATION_HUMAN_WRITE_RECOVERY_TICKET_V1` and may offer only an explicit,
byte-identical FD05 replay after fresh authority checks. Publication uses
`FOUNDATION_PUBLICATION_RECOVERY_TICKET_V1` and may perform only the exact
project/operation Foundation recovery GET; it can never reconstruct or replay a
publication POST. A ticket grants no authority and contains no cookie, CSRF,
credential, role or capability.

Starting a ticket download is only an export action and is not retention proof.
POST remains disabled until the HUMAN either pastes an exact byte-for-byte copy
of the canonical ticket or re-imports and verifies the exact downloaded bytes.
Unknown outcomes never trigger automatic mutation retry. Typed failures are
mapped through a bounded allowlist rather than rendering arbitrary server codes
or exception prose.

Publication success verification is channel-specific: a fresh FD06 POST,
reconciled FD06 result and operation-recovery GET have distinct required HTTP,
replay and cache contracts and are not interchangeable. Definitions, hashes,
lifecycle/readiness state, operation IDs, tickets, receipts, roles and workspace
fields are not written to browser persistence.

The checksum-bound public Russian claim contract is served at
`/studio/claim-boundaries/lifecycle-publication/v1/`. CI uses the pinned
Chrome-for-Testing `152.0.7977.64` archive with an exact verifier-enforced
SHA-256; it is a deterministic regression browser, not a dynamically current
browser. Package workflows, Document, Chat, formulas, scalar Power, prediction,
risk, ranking and recommendations remain unavailable. See
[`docs/adr/0009-production-studio-c-lifecycle-publication.md`](docs/adr/0009-production-studio-c-lifecycle-publication.md)
and the
[`Production Studio runtime runbook`](docs/production-studio-c-read-only-runtime.md).

## Production Studio C1: authenticated audited DRAFT

`C1_AUTHENTICATED_DRAFT` adds a testable Russian authoring shell without
creating a second persistence or validation authority. A pre-issued Django
session opens `/studio/drafts/` to bootstrap the first Project/DRAFT through
Foundation, or opens an exact existing UUID at
`/studio/drafts/definitions/<UUID>/`. The Studio server views remain GET-only;
browser writes go directly to the accepted same-origin Foundation HTTP
gateways.

The editor keeps one proposal in memory and exposes bounded windows for more
than 500 actors and analytical elements. It can rename, add, delete and reorder
those records, edit the Project snapshot, request canonical non-mutating
validation preview, and save with a strong Foundation ETag and a fresh UUIDv4
`Idempotency-Key`. A typed stale conflict is shown without force overwrite or
automatic retry. Manual reconciliation is available only for an ambiguous
outcome and repeats the exact operation key, raw body and `If-Match` token.
Successful saves display the immutable Foundation write receipt and survive an
exact-ID reload.

Foundation remains the sole persistence, lifecycle, authorization, validation,
audit, Help and package authority. Studio has no authoring model, migration,
session issuer, package implementation, validator or `/api/studio` mutation
alias. Browser persistence is limited to the bounded layout value under
`conflict-analysis-studio:audited-draft-layout:v1`; manifests, receipts,
operation keys and identities are never cached. Document, Chat, scientific
formula, scalar Power, prediction, risk and recommendation controls remain
disabled. The public checksum-bound C1 claim contract is available at
`/studio/claim-boundaries/audited-draft/v1/`.

The operational contract is documented in
[`docs/production-studio-c-read-only-runtime.md`](docs/production-studio-c-read-only-runtime.md),
and the C1 decision in
[`docs/adr/0008-production-studio-c-audited-draft.md`](docs/adr/0008-production-studio-c-audited-draft.md).

## Production Studio C0: authenticated read-only

`C0_AUTHENTICATED_READ_ONLY` is a Russian three-panel browser shell mounted at
`/studio/`. It accepts an exact definition UUID and reads only the accepted
Foundation endpoints for that object: the definition, its Foundation 2.1
export and, when the manifest supplies one exact bound tuple, Foundation Help.
The Project card is a snapshot from that definition's manifest; actor and
analytical-element lists use a bounded active DOM window.

Studio C0 has no login, logout, session issuance, credential form, model,
migration, direct ORM access or write endpoint. A Django session must be issued
before the measured Studio flow by the hosting authentication system. Every
Foundation request made by C0 is `GET`; `POST`, `PUT`, `PATCH`, `DELETE` and
`HEAD` Foundation calls are outside C0. Missing exact Help is shown as
unavailable without local fallback. The `Документ` evidence trace is explicitly
unavailable until a separately authorized future slice, and Chat and scientific
controls are disabled.

The only application value persisted in the browser is the bounded layout
object under `conflict-analysis-studio:read-only-layout:v1`. Project, definition,
actor, evidence and Help identities are never stored there. Permanent visible
limitations and the downloadable, checksum-bound claim contract state that
traceability and lifecycle status are not substantive correctness or scientific
validation. C0 provides no scalar or ranked Power, aggregate, formula,
prediction, probability, risk or recommendation.

Deployment and browser-role details are in
[`docs/production-studio-c-read-only-runtime.md`](docs/production-studio-c-read-only-runtime.md);
the authority and composition decision is in
[`docs/adr/0007-production-studio-c-read-only-first.md`](docs/adr/0007-production-studio-c-read-only-first.md).

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

## Production Player G7

Статус поставки — `PLAYER_PRODUCT_SLICE_DELIVERED`: реализуемый и проверяемый
продуктовый срез, а не готовый пакет владельца Studio + Player. Отдельный профиль
Player, Windows launcher и итоговая двухпрограммная поставка относятся к G10.

Отдельный интерфейс `/player/` открывает опубликованные определения проекта,
рабочие пространства и временные срезы через канонический Foundation Player API
`/api/foundation/player/`. Для входа нужна заранее выданная Django session
пользователя с точным семейством Player permissions и доступом к проекту;
формы регистрации, повышения роли или смешения со Studio здесь нет.

Перед первым созданием рабочего пространства оператор явно выполняет
`python manage.py provision_player_help`. Эта команда устанавливает замороженный
русскоязычный каталог справки. Обычные GET-запросы не создают и не исправляют
доменные данные. POST требует session, CSRF, UUID v4 операции и точного
`If-Match`; повтор той же операции возвращает сохранённый результат.

G7 позволяет создать непустое по имени рабочее пространство из опубликованного
определения и неизменяемый временной срез. Дерево структуры доступно только для
чтения. Расчёт значений, агрегация, моделирование, редактор документов, чат и
выполнение метода остаются недоступными границами следующего этапа, а не
имитируются интерфейсом. Проекция оценочных экспериментов остаётся FD08.

Архитектурные решения: [ADR-0014](docs/adr/0014-production-player-g7.md).
Запуск, контракт операций, проверки и изолированный wheel:
[Production Player G7 runtime](docs/production-player-g7-runtime.md).
Эти документы поставляются в исходном дереве; runtime wheel содержит приложение
Player, шаблоны, статические ресурсы и контракт заявлений с SHA-256 sidecar.