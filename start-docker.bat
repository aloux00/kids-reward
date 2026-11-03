@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Star Kids Reward - Docker Launcher

rem NOTE: keep this file ASCII-only.
rem A .bat saved as UTF-8 is parsed by cmd using the local ANSI code page, so
rem Chinese text with full-width punctuation gets split into garbage commands.
rem All Chinese documentation lives in deploy\docker\README.md instead.

set "COMPOSE=docker compose -f docker-compose.yml -f docker-compose.dev.yml"
set "MODE=dev"

rem -prod starts the plain self-contained image instead: no source mount,
rem no auto reload. Use it to rehearse what the server will actually run.
if /i "%~1"=="-prod" (
  set "COMPOSE=docker compose"
  set "MODE=prod"
)

echo.
echo ============================================================
echo    Star Kids Reward  -  Docker Launcher
echo    mode: %MODE%
echo ============================================================
echo.

rem ---------------------------------------------------------------- 1. engine
docker info >nul 2>&1
if not errorlevel 1 goto engine_ready

echo [1/4] Engine not running, starting Docker Desktop...
echo       First start usually takes 30-60 seconds.
echo.

docker desktop start >nul 2>&1
if errorlevel 1 (
  set "DD=%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe"
  if exist "%DD%" (
    start "" "%DD%"
  ) else (
    echo [ERROR] Docker Desktop not found.
    echo         Start it from the Start Menu, then run this again.
    pause
    exit /b 1
  )
)

set /a WAITED=0
:wait_engine
ping -n 4 127.0.0.1 >nul
docker info >nul 2>&1
if not errorlevel 1 goto engine_ready
set /a WAITED+=3
if %WAITED% GEQ 180 (
  echo.
  echo [ERROR] Engine still not ready after 3 minutes.
  echo         Open Docker Desktop and check the indicator at bottom-left.
  echo         Troubleshooting: deploy\docker\README.md section 9.
  pause
  exit /b 1
)
<nul set /p "=."
goto wait_engine

:engine_ready
echo [1/4] Engine ready
echo.

rem ------------------------------------------------------- 2. build and start
rem --build is intentional, not redundant:
rem the image carries its own copy of the code. In dev mode the source is
rem mounted over it, but requirements.txt and the Dockerfile only take effect
rem after a rebuild - so always rebuilding removes a whole class of confusion.
rem Incremental build costs a few seconds.
echo [2/4] Building and starting container, incremental build...
%COMPOSE% up -d --build
if errorlevel 1 (
  echo.
  echo [ERROR] Startup failed. See the output above.
  pause
  exit /b 1
)
echo.

rem ------------------------------------------------------------- 3. health check
echo [3/4] Waiting for health check...
set /a WAITED=0
:wait_health
%COMPOSE% ps --format "{{.Status}}" 2>nul | findstr /i "healthy" >nul
if not errorlevel 1 goto ready
ping -n 3 127.0.0.1 >nul
set /a WAITED+=2
if %WAITED% GEQ 90 (
  echo.
  echo [WARN] Not healthy after 90 seconds. Check the logs:
  echo        %COMPOSE% logs --tail 50
  pause
  exit /b 1
)
goto wait_health

:ready
echo [4/4] Ready
echo.
echo ============================================================
echo    Running at  http://127.0.0.1:8777
echo ============================================================
echo.
echo    Parent demo login : dad / 1234
echo    Child demo login  : pick avatar "DouDou" + 1234
echo.

if /i "%MODE%"=="dev" (
  echo    Auto update : ON, built into the container
  echo      edit static\        -^> refresh the browser
  echo      edit app\           -^> reloads itself in about 1 second
  echo      edit requirements.txt or docker\Dockerfile
  echo                          -^> run this script again to rebuild
  echo.
  echo    Stop with: docker compose -f docker-compose.yml -f docker-compose.dev.yml down
) else (
  echo    Auto update : OFF, production image mode
  echo      after editing code run: docker compose up -d --build
)

echo.
start "" http://127.0.0.1:8777
ping -n 5 127.0.0.1 >nul
