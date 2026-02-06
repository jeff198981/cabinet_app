@echo off
setlocal EnableExtensions

REM ============================================================
REM Build cabinet_status.exe using PyInstaller
REM - Double-click this file, or run it from a CMD window.
REM - Output: .\dist\cabinet_status.exe
REM ============================================================

chcp 65001 >nul

pushd "%~dp0" || (echo Failed to enter script folder.& pause & exit /b 1)

echo.
echo [1/4] Checking Python...
where python >nul 2>&1
if errorlevel 1 (
  echo Python not found in PATH. Please install Python and add it to PATH.
  popd
  pause
  exit /b 1
)
python -c "import sys;print('Python:',sys.version);print('Bitness:', '64-bit' if sys.maxsize>2**32 else '32-bit')"

echo.
echo [2/4] Installing dependencies...
if exist requirements.txt (
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
) else (
  echo WARNING: requirements.txt not found, skipping.
)
python -m pip install -U pyinstaller

echo.
echo [3/4] Building EXE (PyInstaller)...
if not exist cabinet_status_main.py (
  echo ERROR: cabinet_status_main.py not found in %CD%
  popd
  pause
  exit /b 1
)

set "ICON_ARGS="
if exist "assets\\app_icon.ico" (
  set "ICON_ARGS=--icon assets\\app_icon.ico --add-data assets\\app_icon.ico;assets"
) else if exist "personnel_register.ico" (
  set "ICON_ARGS=--icon personnel_register.ico --add-data personnel_register.ico;."
) else (
  echo NOTE: icon not found, building without icon.
)

python -m PyInstaller -F -w cabinet_status_main.py ^
  --name cabinet_status ^
  --clean ^
  --noconfirm ^
  %ICON_ARGS% ^
  --add-data "db_config.ini;." ^
  --add-data "app_style.qss;." ^
  --add-data "assets;assets" ^
  --hidden-import=pyodbc

if errorlevel 1 (
  echo.
  echo Build failed. Please read the errors above.
  popd
  pause
  exit /b 1
)

echo.
echo [4/4] Copying config to dist...
if exist db_config.ini copy /y "db_config.ini" "dist\" >nul
if exist app_style.qss copy /y "app_style.qss" "dist\" >nul
if exist assets xcopy /e /i /y "assets" "dist\assets" >nul
if exist "dist\db_config.ini" (
  powershell -NoProfile -Command "$p='dist\\db_config.ini'; $c=Get-Content $p; $c=$c -replace '^(\\s*server\\s*=).*','$1 192.168.10.219'; $c=$c -replace '^(\\s*password\\s*=).*','$1 Rivamed@2022'; Set-Content -Path $p -Value $c"
)

echo.
echo Done! Output folder: %CD%\dist
start "" explorer "%CD%\dist"

popd
pause
