@echo off
cd /d "%~dp0"
chcp 65001 > nul
echo ================================================
echo  WhatsApp Kalender-Bot - Build
echo  Erstellt ein fertiges Paket in: release\
echo ================================================
echo.

echo Pruefe Python...
python --version
if errorlevel 1 goto :err_python
echo.

echo Pruefe Node.js...
node --version
if errorlevel 1 goto :err_node
echo.

echo [OK] Python und Node.js gefunden.
echo.

echo [1/5] Installiere WhatsApp Bridge Pakete (kann einige Minuten dauern)...
cd whatsapp-bridge
call npm install
if errorlevel 1 goto :err_npm
cd ..
echo.

echo [2/5] Lade portable Node.js fuer den Server herunter...
powershell -Command "Invoke-WebRequest -Uri 'https://nodejs.org/dist/v20.11.1/win-x64/node.exe' -OutFile 'whatsapp-bridge\node.exe' -UseBasicParsing"
if errorlevel 1 goto :err_download
echo [OK] node.exe heruntergeladen.
echo.

echo [3/5] Installiere Python-Pakete...
pip install -r requirements.txt --quiet
pip install pyinstaller --quiet
if errorlevel 1 goto :err_pip
echo.

echo [4/5] Baue bot.exe...
pyinstaller --onefile --noconsole --name bot --hidden-import=apscheduler.triggers.date --hidden-import=apscheduler.triggers.interval --hidden-import=recurring_ical_events --hidden-import=icalendar bot.py
if errorlevel 1 goto :err_exe
echo.

echo [5/5] Erstelle fertiges Paket in release\...
if exist release rmdir /s /q release
mkdir release
mkdir release\whatsapp-bridge

copy dist\bot.exe        release\bot.exe           >nul
copy config.ini          release\config.ini         >nul
copy start.bat           "release\Bot starten.bat"  >nul
copy autostart.bat       release\autostart.bat       >nul

xcopy /E /I /Y /Q whatsapp-bridge\*.js       release\whatsapp-bridge\ >nul
xcopy /E /I /Y /Q whatsapp-bridge\*.json     release\whatsapp-bridge\ >nul
xcopy /E /I /Y /Q whatsapp-bridge\node.exe   release\whatsapp-bridge\ >nul
xcopy /E /I /Y /Q whatsapp-bridge\node_modules release\whatsapp-bridge\node_modules\ >nul

echo.
echo ================================================
echo  FERTIG! Paket liegt in: release\
echo ================================================
echo.
echo EINRICHTUNG:
echo   1. release\config.ini oeffnen und ausfuellen
echo   2. release\Bot starten.bat doppelklicken
echo   3. Beim ersten Start: QR-Code scannen
echo.
pause
exit /b 0

:err_python
echo.
echo ================================================
echo  FEHLER: Python nicht installiert oder nicht in PATH!
echo ================================================
echo.
echo Bitte Python von https://python.org herunterladen.
echo WICHTIG: Bei der Installation den Haken bei
echo          "Add Python to PATH" setzen!
echo.
pause
exit /b 1

:err_node
echo.
echo ================================================
echo  FEHLER: Node.js nicht installiert!
echo ================================================
echo.
echo Bitte Node.js von https://nodejs.org herunterladen.
echo LTS-Version waehlen und installieren.
echo.
pause
exit /b 1

:err_npm
echo.
echo FEHLER bei npm install.
echo Pruefe Internetverbindung und versuche es erneut.
cd ..
pause
exit /b 1

:err_download
echo.
echo FEHLER beim Download von node.exe.
echo Manuell herunterladen von:
echo   https://nodejs.org/dist/v20.11.1/win-x64/node.exe
echo und nach whatsapp-bridge\node.exe speichern.
pause
exit /b 1

:err_pip
echo.
echo FEHLER bei pip install.
echo Pruefe Internetverbindung.
pause
exit /b 1

:err_exe
echo.
echo FEHLER beim Bauen der exe.
pause
exit /b 1
