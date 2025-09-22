@echo off
REM Chronos Engine Version Checker for Windows
REM Usage: check_version.bat [production-server-url]

if "%1"=="" (
    echo Checking local version only...
    python check_version.py
) else (
    echo Comparing local vs production versions...
    python check_version.py %1
)

pause