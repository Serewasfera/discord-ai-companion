@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Discord AI Companion - Установка

echo [1/5] Проверка Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не найден в PATH!
    echo Установите Python с python.org и отметьте "Add Python to PATH"
    pause
    exit /b 1
)
python --version
echo.

echo [2/5] Создание venv...
if exist "venv\" (
    echo venv уже существует, пропускаем...
) else (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ОШИБКА] Не удалось создать venv
        pause
        exit /b 1
    )
    echo venv создан успешно.
)
echo.

echo [3/5] Установка зависимостей...
call venv\Scripts\activate.bat
pip install --upgrade pip >nul 2>&1
if exist "requirements.txt" (
    pip install -r requirements.txt
    echo Зависимости установлены.
) else (
    echo [ОШИБКА] requirements.txt не найден в текущей папке!
    pause
    exit /b 1
)
echo.

echo [4/5] Проверка конфигурации...
if not exist ".env" (
    if exist ".env.example" (
        echo Создаю .env из .env.example...
        copy ".env.example" ".env" >nul
        echo [ВНИМАНИЕ] Не забудьте отредактировать .env файл с вашими API ключами!
        echo.
    ) else (
        echo [ОШИБКА] .env.example не найден!
        pause
        exit /b 1
    )
) else (
    echo .env уже существует.
)

if not exist "config.yaml" (
    echo [ОШИБКА] config.yaml не найден!
    pause
    exit /b 1
)
echo config.yaml найден.
echo.

echo [5/5] Установка завершена!
pause