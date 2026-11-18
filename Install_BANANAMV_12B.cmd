@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "ROOT=F:\BANANAMV_12B_STUDIO"
set "APP=%ROOT%\App"
set "BRANCH=experiment/rtx5070-gemma3-12b"
set "REPO=https://github.com/haohao1130-bit/banana-grandmaster-27b.git"
if not exist "F:\" (
    echo ERROR: F drive not found.
    pause
    exit /b 1
)
if exist "%APP%\tools\install_12b.ps1" goto RUN
where git >nul 2>&1
if errorlevel 1 goto FETCH
if exist "%APP%" (
    echo ERROR: Existing App directory is incomplete; refusing to overwrite it.
    pause
    exit /b 1
)
echo Cloning Gemma 12B experiment branch using Git credentials...
git clone --single-branch --branch "%BRANCH%" "%REPO%" "%APP%"
if not errorlevel 1 goto RUN
:FETCH
echo Trying public installer bootstrap...
set "BOOTSTRAP=%TEMP%\BANANAMV_12B_install.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/haohao1130-bit/banana-grandmaster-27b/experiment/rtx5070-gemma3-12b/tools/install_12b.ps1' -OutFile '%BOOTSTRAP%'"
if errorlevel 1 (
    echo ERROR: Installer could not be obtained; check GitHub authentication and internet access.
    pause
    exit /b 1
)
set "INSTALLER=%BOOTSTRAP%"
goto INSTALL
:RUN
set "INSTALLER=%APP%\tools\install_12b.ps1"
:INSTALL
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%INSTALLER%" -Root "%ROOT%"
if errorlevel 1 (
    echo ERROR: Installation failed. Check %ROOT%\Logs\install_12b.log
    pause
    exit /b 1
)
endlocal
