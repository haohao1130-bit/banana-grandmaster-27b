@echo off
setlocal
chcp 65001 >nul
set "BOOTSTRAP=%TEMP%\BANANAMV_12B_install.ps1"
echo BANANAMV Gemma 3 12B Q5 - downloading installer...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/haohao1130-bit/banana-grandmaster-27b/experiment/rtx5070-gemma3-12b/tools/install_12b.ps1' -OutFile '%BOOTSTRAP%'"
if errorlevel 1 (
    echo Installer download failed. Check internet or GitHub access.
    pause
    exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%BOOTSTRAP%" -Root "F:\BANANAMV_12B_STUDIO"
if errorlevel 1 (
    echo Installation failed. Check F:\BANANAMV_12B_STUDIO\Logs\install_12b.log
    pause
    exit /b 1
)
endlocal
