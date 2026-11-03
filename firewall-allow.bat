@echo off
chcp 65001 >nul
title Star Kids - Allow LAN Access

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo.
  echo   [!] This needs Administrator rights.
  echo   Please RIGHT-CLICK this file and choose "Run as administrator".
  echo.
  pause
  exit /b 1
)

netsh advfirewall firewall add rule name="StarKids" dir=in action=allow protocol=TCP localport=8777 enable=yes profile=any

if %errorlevel% equ 0 (
  echo.
  echo   [OK] Port 8777 is now allowed through Windows Firewall.
  echo        Your phone / tablet should reach the app now.
  echo.
  echo   To undo later, run as administrator:
  echo   netsh advfirewall firewall delete rule name="StarKids"
) else (
  echo.
  echo   [FAIL] Could not add the firewall rule.
)
pause
