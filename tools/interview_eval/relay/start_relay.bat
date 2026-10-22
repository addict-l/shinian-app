@echo off
rem Starts the DeepSeek relay for the Shinian interview tests. Keep this window open.
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  for /f "delims=" %%p in ('where python 2^>nul ^| findstr /v /i "WindowsApps"') do if not defined PY set "PY="%%p""
)
if not defined PY (
  for /d %%d in ("%USERPROFILE%\.uv-python\cpython-3*") do if exist "%%d\python.exe" set "PY="%%d\python.exe""
)
if not defined PY (
  for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%d\python.exe" set "PY="%%d\python.exe""
)
if not defined PY (
  echo Python 3 was not found. Install it from https://www.python.org/downloads/ and run this again.
  pause
  exit /b 1
)
echo Using %PY%
%PY% ds_relay.py
pause
