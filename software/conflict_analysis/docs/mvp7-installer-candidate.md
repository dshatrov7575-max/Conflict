# MVP7 R1 Windows setup candidate

This branch contains packaging only. Application wheel source is always commit
85a253126bf270664c4786d159994e7359b5d2c5, tree
5567183dbe16fc6c7c8caac051b7694f37b92457. The installer has exactly one ordinary
commit above c8263b81adb8fcb90ec92b65342f9620884c929b. Product acceptance run:
35216652773. The wheel is built from git archive of C, not installer HEAD.
Installer source identity is separately bound in the manifest.

## Build and evidence

The Linux job runs on ubuntu-24.04. Existing owner-alpha OCI build, normalized
rootfs, manifest, SBOM, SHA256SUMS, exact archive membership, traversal,
case-collision and extra-file rejection are retained. The leaf migration is
0019. The package includes the exact C dashboard, Foundation Geography,
Natural Earth, MapLibre, licenses and Russian labels. Runtime initializes the
versioned Zhanaozen demo using its accepted service. All three demo principals
receive permission-free project/analysis-reader groups; only the editor gets
analysis-location-editor. No product roles or permission definitions change.

All downloaded inputs have URLs, byte lengths and SHA256 in
installer/external-inputs.lock.json. OCI manifest/config/layer descriptors are
also pinned. All inputs are verified before offline Docker build steps. Existing
immutable image digests are pulled only by CI. Runtime installation never runs a
resolver or download command.

windows-2025 is only a build/contract host. Official NSIS 3.12 ZIP and actual
Bin/makensis.exe are hash checked. Compiler files never enter Git or the payload.
Two EXEs are compiled with the same script inputs and compiler. Each EXE's
read-only /VERIFYONLY /PAYLOADOUT=... mode independently exposes and verifies the
embedded ZIP, then exits before host preflight/installation. It is not an
installation bypass. Reports bind both EXEs, inner ZIP, compiler and scripts.
Reports disclose EXE equality, PE COFF timestamps/checksums, and differing byte
ranges if equality is not achieved. No byte-identical claim is made without it.

## User boundary

The Russian NSIS installer requests asInvoker/user privileges. Installation is
per user under LOCALAPPDATA/Programs/ConflictPartnerDemo/MVP7; app payload lives
under app/ so its member inventory remains exact. The existing host must be
Windows 11 x64 with functioning WSL2, PowerShell 7 and Edge. Missing prerequisites
fail closed. No feature, policy, trusted publisher, Edge or WSL-host installation
or update is performed. Policy denial remains a denial; nothing uses Bypass.

State, WSL virtual disk and backups live under
LOCALAPPDATA/ConflictPartnerDemoState/mvp7. An absent state directory is FIRST
INSTALL. Private directories precede state access; installation.json is atomically
written only after successful WSL import and application initialization.
installation.pending.json prevents an incomplete import from being mistaken for
a completed installation. Do not delete its state automatically; retain it for
operator diagnosis. Reinstallation admits only matching manifest identity.

Start/stop/diagnostics/uninstall shortcuts are created in the current user's
Start Menu. The outer uninstall stops its package services and removes only its
validated program directory and known shortcuts/registration. It does not
unregister WSL or delete state/backups. The candidate is unsigned; no signing,
certificate import or policy workaround is supplied.

## Remaining mandatory smoke

WINDOWS11_WSL2_E2E=BLOCKED_NO_RUNNER
CLEAN_PC_SMOKE=NOT_EXECUTED
PARTNER_RELEASE_READY=false

On an independently prepared Windows 11 x64 WSL2 PC: receive the exact EXE,
disconnect external networking, INSTALL into absent demo state, START and inspect
all role sessions/Studio/Player/Analysis/Geography, edit/save/reload a project
location, STOP/START and verify data/session behavior, STOP, then uninstall and
compare saved state/backups. Preserve exact artifact identities and evidence.
Hosted Windows Server contracts and Linux container tests do not satisfy this
gate. No partner release is authorized by these build results.


## Профили MVP7 и отдельный R1 oracle

Для demo-проекта STUDIO_EDITOR сохраняет только studio-project scope.
STUDIO_PUBLISHER имеет studio-project, analysis-reader и analysis-location-editor.
PLAYER_ASSESSOR имеет studio-project и analysis-reader. Все группы zero-permission;
новых Django permissions нет. Runtime проверяет точную комбинацию по каждому
project scope, а также migration leaf 0019 и пустой migration plan.

Linux rootfs contract выполняет реальные loopback HTTP GET/POST с session,
CSRF, If-Match, X-Operation-ID, проверяет 403 для assessor и 404 без Analysis
capability, затем STOP/START и неизменность revision. Сам HTML shell /analysis/
в exact C не скрыт от authenticated editor; защищённые Foundation данные недоступны.
Это сохранённый product contract C.

Третий CI job отдельно проверяет immutable checkout C полным принятым R1 gate.
JUnit totals проверяются против source.lock.json: 379; 351 + 28 expected SKIP;
55/55; Chromium 8; lifecycle 15/15. Старые G10 totals не являются MVP7 oracle.
Этот job не меняет application wheel, который строится Linux packaging job
из git archive exact C.

START сохраняет три изолированных Edge profiles. Только publisher открывает
Studio и Analysis двумя вкладками одного запуска Edge; сохраняется один PID
этого запуска. Editor открывает Studio, assessor — Player. Assessor может
открыть /analysis/ в своём существующем профиле. GRANT выдаёт publisher также
Analysis read/location edit, assessor — Analysis read, без новых identities.


MVP7 preflight не требует стороннего зарегистрированного distro. Проверяются
Windows 11 x64, virtualization capability, наличие wsl.exe, успешные --version
и --help с --import. Пустой список distro допустим и не запрашивается.
Окончательное доказательство WSL2 — успешный импорт exact package rootfs с
--version 2. Ошибка импорта даёт BLOCKED_MVP7_WSL2_PACKAGE_IMPORT_FAILED с exit
code, если процесс его вернул. Host никогда автоматически не исправляется.
