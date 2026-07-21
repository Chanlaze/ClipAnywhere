@echo off
cd /d "%~dp0"
echo Starting ClipAnywhere tray launcher... > "%~dp0clipanywhere_tray_launch.log"
if exist "C:\python\pythonw.exe" (
  echo Using C:\python\pythonw.exe >> "%~dp0clipanywhere_tray_launch.log"
  start "ClipAnywhere Tray" "C:\python\pythonw.exe" "%~dp0start_client_tray.pyw"
) else (
  echo C:\python\pythonw.exe not found, using C:\python\python.exe >> "%~dp0clipanywhere_tray_launch.log"
  start "ClipAnywhere Tray" "C:\python\python.exe" "%~dp0start_client_tray.pyw"
)
