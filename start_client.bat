@echo off
cd /d "%~dp0"
C:\python\python.exe "%~dp0start_client.py" --config "%~dp0client_config.json"
pause

