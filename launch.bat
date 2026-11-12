
@echo off
title PowerShell Script Launcher
color 0A

:MENU
cls
echo ========================================
echo     NU DENTALCONNECT SCRIPT LAUNCHER
echo ========================================
echo.
echo  [1] First Time Startup
echo  [2] Start Debug
echo  [3] Start Production
echo  [4] Quit
echo.
echo ========================================
set /p choice="Select an option (1-4): "

if "%choice%"=="1" goto FIRST-TIME-SETUP
if "%choice%"=="2" goto DEBUG
if "%choice%"=="3" goto PRODUCTION
if "%choice%"=="4" goto QUIT

echo.
echo Invalid choice. Please try again.
timeout /t 2 >nul
goto MENU

:FIRST-TIME-SETUP
echo.
echo Running first_time_startup.ps1...
powershell.exe -NoProfile -ExecutionPolicy Bypass -NoExit -File "%~dp0first_time_startup.ps1"
goto END

:DEBUG
echo.
echo Running start_debug.ps1...
powershell.exe -NoProfile -ExecutionPolicy Bypass -NoExit -File "%~dp0start_debug.ps1"
goto END

:PRODUCTION
echo.
echo Running start_production.ps1...
powershell.exe -NoProfile -ExecutionPolicy Bypass -NoExit -File "%~dp0start_production.ps1"
goto END

:QUIT
echo.
echo Goodbye!
exit /b 0

:END
echo.
echo ========================================
echo Script execution finished.
echo ========================================
echo.
pause
