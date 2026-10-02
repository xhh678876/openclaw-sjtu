@echo off
rem Build the SJTU Assistant standalone exe with PyInstaller.
rem ASCII-only source: cmd.exe reads .bat in the OEM codepage (GBK here).
rem
rem The resulting exe is a GUI shell: it still needs a system Python plus the
rem openclaw-sjtu skill directory, because the skill itself is Python scripts.
setlocal
cd /d "%~dp0"

set PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe
if not exist "%PY%" set PY=python

rem Note: no --specpath. PyInstaller resolves relative --add-data paths against
rem the .spec file's directory, so putting the spec under build\ makes it look
rem for build\ui and fail. The spec therefore lands next to app.py.
"%PY%" -m PyInstaller ^
  --noconfirm --clean --onefile --windowed ^
  --name SJTU-Assistant ^
  --icon app.ico ^
  --add-data "ui;ui" ^
  --add-data "app.ico;." ^
  --distpath dist ^
  --workpath build ^
  --exclude-module tkinter ^
  --exclude-module numpy ^
  --exclude-module pandas ^
  --exclude-module matplotlib ^
  --exclude-module PIL ^
  --exclude-module pytest ^
  app.py

echo.
if not exist "dist\SJTU-Assistant.exe" (
  echo [error] PyInstaller produced no exe
  endlocal
  exit /b 1
)
rem Renaming to the Chinese product name is delegated to Python: cmd.exe reads
rem this file in the OEM codepage, so a non-ASCII name here would be garbled.
"%PY%" post_build.py
endlocal
