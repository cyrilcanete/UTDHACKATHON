@echo off
setlocal
title Smart Mirror Demo
cd /d "%~dp0"
if not exist "mirror_runtime.py" (
  echo Extract the complete ZIP first, then open this launcher inside UTDHACKATHON.
  pause
  exit /b 1
)
py --version >nul 2>&1
if errorlevel 1 (
  echo Python is needed. Install Python 3.10 or newer from https://www.python.org/downloads/
  echo Then double-click OPEN_MIRROR_DEMO.cmd again.
  pause
  exit /b 1
)
py -c "from zoneinfo import ZoneInfo; ZoneInfo('America/Chicago')" >nul 2>&1
if errorlevel 1 (
  echo Installing timezone support for the demo...
  py -m pip install tzdata
  if errorlevel 1 (
    echo Timezone setup failed. Send the error above for help.
    pause
    exit /b 1
  )
)
set "MIRROR_PORT=5001"
set "MIRROR_DEMO=1"
py -c "import socket,sys; s=socket.socket(); s.settimeout(1); sys.exit(0 if s.connect_ex(('127.0.0.1',5001))==0 else 1)"
if not errorlevel 1 (
  echo Port 5001 is already in use. Stop the OLD mirror Python window with Ctrl+C first.
  echo Then double-click this new launcher again. Refreshing the browser alone does not update Python.
  pause
  exit /b 1
)
echo Opening the UPDATED mirror demo at http://127.0.0.1:5001
echo Keep this window open. Press Ctrl+C here to stop the demo.
start "" /min powershell.exe -NoProfile -Command "$url='http://127.0.0.1:5001'; for($i=0;$i -lt 60;$i++){try{$data=Invoke-RestMethod ($url+'/api/dashboard') -TimeoutSec 1; if($data.build -eq 'mirror-welcome-v3'){Start-Process $url; exit}}catch{}; Start-Sleep -Milliseconds 500}"
py ".\app.py"
echo.
echo If the app reported an error, send a screenshot of this window.
pause
