@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Star Kids Reward - Launcher

set "PY=C:\Users\Lenovo\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" start.py %*
if errorlevel 1 (
  echo.
  echo [ERROR] Start failed. See message above.
  pause
)
