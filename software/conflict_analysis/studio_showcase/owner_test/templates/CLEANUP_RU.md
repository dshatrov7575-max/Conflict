# Остановка и удаление

1. В окне launcher нажмите `Ctrl+C` и дождитесь возврата приглашения PowerShell.
2. Убедитесь, что `http://127.0.0.1:<порт>/health/` больше недоступен.
3. Закройте вкладку браузера. При необходимости удалите только UI-настройки с
   префиксом `conflict-analysis-studio:` из localStorage этого loopback origin.
4. Удалите распакованный каталог OWNER-TEST целиком. Виртуальная среда `.venv`
   находится только внутри него.

Showcase не создаёт migrations, SQLite-файл или записи Foundation. Не используйте
команды очистки production database.

`RUN_BROWSER_SMOKE.ps1` удаляет собственный временный профиль Chrome/Edge в
блоке `finally`. Для полного удаления OWNER-TEST достаточно остановить launcher
и удалить только распакованный каталог; системные данные и production database
затрагивать не нужно.
