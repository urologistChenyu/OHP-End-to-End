@echo off
chcp 65001 >nul
set "TASK_ROOT=%~dp0"
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONNOUSERSITE=1"
"%TASK_ROOT%runtime\python312\python.exe" -B -s "%TASK_ROOT%tools\first_start.py" %*
if errorlevel 1 pause
