@echo off
rem Donghuang combat balance simulator GUI launcher.
rem Double-click to open. Uses pyw (no console) when available, falls back to py.
cd /d "%~dp0"
where pyw >nul 2>nul
if %errorlevel%==0 (
  start "" pyw "tools\combat_sim_gui.py"
) else (
  start "" py "tools\combat_sim_gui.py"
)
