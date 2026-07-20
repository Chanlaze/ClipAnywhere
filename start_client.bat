@echo off
title ClipAnywhere Clipboard Sync
cd /d "%~dp0"
echo Starting ClipAnywhere Clipboard Sync...
echo Status messages will appear below.
C:\python\python.exe "%~dp0start_client.py" --config "%~dp0client_config.json"
pause
