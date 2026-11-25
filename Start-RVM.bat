@echo off
REM ==========================================================================
REM  RVM - one-click demo launcher (Windows)
REM
REM  Double-click this file.  The server keeps running on this machine and is
REM  reachable from the same LAN and from the Tailscale tailnet:
REM
REM      local      http://localhost:8080
REM      same LAN   http://<wlan-ip>:8080
REM      Tailscale  http://<tailscale-ip>:8080
REM
REM  First run only: Python 3.10+ on PATH (run.bat builds the environment) and
REM  one administrator approval to open inbound TCP 8080.
REM ==========================================================================
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [setup] No virtual environment yet - running run.bat first.
    call "%~dp0run.bat"
    exit /b
)

echo [1/3] Opening inbound TCP 8080 for LAN and Tailscale ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\enable-firewall.ps1"
if errorlevel 1 (
    echo [warn] The firewall rule could not be confirmed.
    echo        Viewers on other machines may be blocked until it is added.
)

echo.
echo [2/3] Addresses a viewer can open in a browser:
powershell -NoProfile -Command "$w=(Get-NetIPAddress -InterfaceAlias 'WLAN' -AddressFamily IPv4 -ErrorAction SilentlyContinue).IPAddress; $t=(Get-NetIPAddress -InterfaceAlias 'Tailscale' -AddressFamily IPv4 -ErrorAction SilentlyContinue).IPAddress; Write-Host '        local      : http://localhost:8080'; if ($w) { Write-Host ('        same LAN   : http://' + $w + ':8080') } else { Write-Host '        same LAN   : (no WLAN address)' }; if ($t) { Write-Host ('        Tailscale  : http://' + $t + ':8080') } else { Write-Host '        Tailscale  : (Tailscale not connected)' }"
echo.

netstat -ano | findstr ":8080" | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo [3/3] Port 8080 is already serving - opening the page only.
    start "" "http://localhost:8080"
    exit /b
)

echo [3/3] Starting the server in a new window.
echo        Close that window, or press Ctrl+C in it, to stop the server.
start "RVM server" cmd /k .venv\Scripts\python.exe run_server.py --port 8080 --open

exit /b
