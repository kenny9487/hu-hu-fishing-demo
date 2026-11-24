@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

rem ===== Configuration =====
set "MAIN_SCRIPT=main.py"
set "OUTPUT_NAME=fishing-helper"
set "VENV_NAME=fishing_venv"
set "ICON_FILE=resource\vicksy.ico"
set "RESOURCES=star_template.png first_catch_template.png first_catch_template_1024.png session_extend_template.png bucket_full_template.png bait_empty_template.png bucket_full.wav ouhuang.wav huiben.wav dawo.wav vicksy_fishing.png"
set "USE_CONSOLE=1"

 echo.
echo ===== Fishing helper build =====
echo Project folder: %CD%

echo.
echo [1/6] Checking main script...
if not exist "%MAIN_SCRIPT%" (
  echo [ERROR] Cannot find "%MAIN_SCRIPT%" in this folder.
  echo Put this BAT file beside main.py, then run it again.
  pause
  exit /b 1
)

if not exist "%ICON_FILE%" (
  echo [ERROR] Cannot find icon: "%ICON_FILE%"
  echo Edit ICON_FILE near the top of this BAT to match your actual .ico path.
  pause
  exit /b 1
)

echo [2/6] Checking resource files...
for %%F in (%RESOURCES%) do (
  if not exist "%%F" (
    echo [ERROR] Missing resource: %%F
    echo Put the file beside main.py, or edit RESOURCES in this BAT.
    pause
    exit /b 1
  )
)

if not exist "%VENV_NAME%\Scripts\python.exe" (
  echo [3/6] Creating virtual environment...
  py -3 -m venv "%VENV_NAME%"
  if errorlevel 1 (
    python -m venv "%VENV_NAME%"
  )
  if errorlevel 1 (
    echo [ERROR] Could not create venv. Check Python installation.
    pause
    exit /b 1
  )
)

set "PYTHON=%CD%\%VENV_NAME%\Scripts\python.exe"
echo [4/6] Installing dependencies...
"%PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto :fail
"%PYTHON%" -m pip install opencv-python-headless mss numpy pygetwindow pypiwin32 keyboard pyautogui pyinstaller pillow
if errorlevel 1 goto :fail

echo [5/6] Cleaning old build files...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "%OUTPUT_NAME%.spec" del /q "%OUTPUT_NAME%.spec"

 echo [6/6] Building EXE (console enabled for debugging)...
set "ARGS=--noconfirm --clean --onefile --console --name "%OUTPUT_NAME%" --icon "%ICON_FILE%""
for %%F in (%RESOURCES%) do set ARGS=!ARGS! --add-data "%%F;."
"%PYTHON%" -m PyInstaller !ARGS! "%MAIN_SCRIPT%"
if errorlevel 1 goto :fail

echo.
echo BUILD SUCCEEDED. EXE is in the dist folder.
explorer "%CD%\dist"
pause
exit /b 0

:fail
echo.
echo [ERROR] Build failed. Read the error lines above.
pause
exit /b 1
