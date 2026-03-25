@echo off
setlocal enabledelayedexpansion

REM === Путь к виртуальному окружению (измените при необходимости) ===
set VENV_DIR=%~dp0venv

if exist "%VENV_DIR%\Scripts\activate.bat" (
    call "%VENV_DIR%\Scripts\activate.bat"
) else (
    echo [INFO] Виртуальное окружение не найдено по пути %VENV_DIR%
    echo [INFO] Продолжаем с глобальной установкой Python.
)

echo.
echo ========================================
echo [INFO] Определение IP-адресов сервера...
echo ========================================
echo.

REM Получаем IP-адреса через PowerShell
powershell -Command "$ips = Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*'} | Select-Object -ExpandProperty IPAddress; if ($ips) { foreach ($ip in $ips) { Write-Host '[INFO] Сервер доступен по адресу: http://' $ip ':8000' } } else { Write-Host '[INFO] IP-адреса не найдены через PowerShell' }" 2>nul

REM Дополнительно получаем IP через ipconfig (на случай если PowerShell не сработал)
echo.
echo [INFO] Альтернативный способ получения IP:
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i /c:"IPv4"') do (
    set IP_LINE=%%a
    set IP_LINE=!IP_LINE: =!
    if not "!IP_LINE!"=="" (
        if not "!IP_LINE!"=="127.0.0.1" (
            if not "!IP_LINE:~0,7!"=="169.254" (
                echo [INFO] Сервер доступен по адресу: http://!IP_LINE!:8000
            )
        )
    )
)

echo.
echo ========================================
echo [INFO] Запуск Waitress на 0.0.0.0:8000 (доступен из сети)...
echo [INFO] Мониторинг: http://localhost:8000/monitor.html
echo ========================================
echo.
python -m waitress --listen=0.0.0.0:8000 wsgi:application

if errorlevel 1 (
    echo [ERROR] Waitress завершилась с ошибкой.
    pause
) else (
    echo [INFO] Сервер остановлен.
)

endlocal

