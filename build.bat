@echo off
cd /d "%~dp0"
set BUILD_ICON=%TEMP%\Foldr-build.ico
for /f "delims=" %%v in ('python -c "from version import APP_VERSION; print(APP_VERSION)"') do set VERSION=%%v
if "%VERSION%"=="" goto fail
set SETUP_NAME=Foldr-Setup-%VERSION%
echo Building version %VERSION%
set ICON_SOURCE=%~dp0icon.png
echo Installing build tools...
python -m pip install -r requirements.txt pyinstaller -q
if errorlevel 1 goto fail

echo Generating icon from %ICON_SOURCE%...
python make_icon.py "%ICON_SOURCE%" "%BUILD_ICON%"
if errorlevel 1 goto fail

echo Building Foldr.exe (assets are baked in)...
python -m PyInstaller --clean --noconfirm --onefile --windowed --name Foldr --icon "%BUILD_ICON%" --add-data "icon.png;." --add-data "%BUILD_ICON%;." --add-data "assets;assets" --collect-all tkinterdnd2 foldr.py
if errorlevel 1 goto fail

echo Building %SETUP_NAME%.exe (Foldr.exe is bundled inside)...
python -m PyInstaller --clean --noconfirm --onefile --windowed --name "%SETUP_NAME%" --icon "%BUILD_ICON%" --add-data "dist\Foldr.exe;." --add-data "%BUILD_ICON%;." --add-data "icon.png;." installer.py
if errorlevel 1 goto fail

ie4uinit.exe -ClearIconCache >nul 2>&1
ie4uinit.exe -show >nul 2>&1

rmdir /S /Q build 2>nul
del Foldr.spec 2>nul
del "%SETUP_NAME%.spec" 2>nul
del "%BUILD_ICON%" 2>nul
echo.
echo Done! Installer: dist\%SETUP_NAME%.exe
pause
exit /b 0

:fail
del "%BUILD_ICON%" 2>nul
echo.
echo Build failed. See the error above.
pause
exit /b 1
