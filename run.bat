@echo off
REM ==========================================================================
REM  RVM - Remote Video Monitoring   (EIE4428 Mini Project)
REM  One-click launcher: finds Python, builds a venv, installs the
REM  dependencies, opens the firewall port and starts the server.
REM
REM  Usage:  run.bat                      (webcam if present)
REM          run.bat --no-camera          (generated scene, no webcam needed)
REM          run.bat --port 8099          (any run_server.py option works)
REM ==========================================================================
setlocal
cd /d "%~dp0"

echo.
echo  ==========================================================
echo   RVM  -  Remote Video Monitoring  (EIE4428 Mini Project)
echo  ==========================================================
echo.

REM --- 1. locate a Python interpreter -------------------------------------
set "PYEXE="
where py >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE (
    where python >nul 2>&1 && set "PYEXE=python"
)
if not defined PYEXE (
    echo  [ERROR] Python was not found on PATH.
    echo          Install Python 3.10+ from https://www.python.org/downloads/
    echo          and tick "Add python.exe to PATH" during setup.
    echo.
    pause
    exit /b 1
)

%PYEXE% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python 3.10 or newer is required.
    echo.
    pause
    exit /b 1
)
echo  [1/4] Python found: %PYEXE%

REM --- 2. virtual environment ---------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo  [2/4] Creating the virtual environment ...
    %PYEXE% -m venv .venv
    if errorlevel 1 (
        echo  [ERROR] Could not create the virtual environment.
        echo.
        pause
        exit /b 1
    )
) else (
    echo  [2/4] Virtual environment already present.
)

REM --- 3. dependencies -----------------------------------------------------
echo  [3/4] Installing dependencies - this happens once, about 1-2 minutes ...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo         mirror unreachable, retrying against the default index ...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo  [ERROR] Dependency installation failed - check the network.
        echo.
        pause
        exit /b 1
    )
)

REM --- 4. firewall ---------------------------------------------------------
net session >nul 2>&1
if errorlevel 1 (
    echo  [!] Not running as administrator, so the firewall rule was skipped.
    echo      If a remote PC cannot connect, open an ADMINISTRATOR terminal and run:
    echo        netsh advfirewall firewall add rule name="RVM 8080" dir=in action=allow protocol=TCP localport=8080
) else (
    netsh advfirewall firewall show rule name="RVM 8080" >nul 2>&1
    if errorlevel 1 (
        netsh advfirewall firewall add rule name="RVM 8080" dir=in action=allow protocol=TCP localport=8080 >nul 2>&1
    )
    echo  [4/4] Firewall rule for TCP 8080 is in place.
)

echo.
echo  --------------------------------------------------------------
echo   Local view : http://localhost:8080
echo   Remote view: http://^<this-PC-IP^>:8080   (from any other PC)
echo   Stop the server with Ctrl+C.
echo  --------------------------------------------------------------
echo.

".venv\Scripts\python.exe" run_server.py %*

echo.
echo  Server stopped.
pause
endlocal
