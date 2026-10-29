@echo off
cd /d "%~dp0"
echo Starting ClipAnywhere tray launcher... > "%~dp0clipanywhere_tray_launch.log"
if exist "C:\python\python.exe" (
  echo Using C:\python\python.exe (the tray launcher hides its console) >> "%~dp0clipanywhere_tray_launch.log"
  start "ClipAnywhere Tray" /min "C:\python\python.exe" "%~dp0start_client_tray.pyw"
) else (
  echo C:\python\python.exe not found >> "%~dp0clipanywhere_tray_launch.log"
)
