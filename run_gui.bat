@echo off
setlocal
cd /d "%~dp0"
set "PYTHONNOUSERSITE=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
"%LOCALAPPDATA%\miniforge3\envs\BL62_Studio\pythonw.exe" "%~dp0app.py"
