@echo off
rem SJTU Assistant - debug launcher (keeps console for Python errors).
rem ASCII-only source: cmd.exe reads .bat in the OEM codepage (GBK here).
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set SJTU_CLIENT_DEBUG=1
"C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe" app.py
echo.
echo [exit code] %errorlevel%
pause
