@echo off
chcp 65001 > nul
echo ==========================================================
echo    Подключение лаунчера к вашему GitHub репозиторию
echo ==========================================================
echo.
echo 1. Создайте новый публичный или приватный репозиторий на https://github.com/new
echo    (например, skyrim-coop-launcher)
echo 2. Скопируйте ссылку на ваш репозиторий.
echo.
set /p REPO_URL="Вставьте ссылку на ваш GitHub репозиторий: "

if "%REPO_URL%"=="" (
    echo [ОШИБКА] Ссылка не была введена.
    pause
    exit /b
)

git remote remove origin 2>nul
git remote add origin %REPO_URL%
git branch -M main

echo.
echo Отправка файлов в репозиторий GitHub...
git push -u origin main

if %ERRORLEVEL% equ 0 (
    echo.
    echo ==========================================================
    echo [УСПЕХ] Файлы успешно выгружены в ваш GitHub!
    echo ==========================================================
) else (
    echo.
    echo [ВНИМАНИЕ] Если GitHub запросил логин/токен, выполните вход через браузер.
)

echo.
pause
