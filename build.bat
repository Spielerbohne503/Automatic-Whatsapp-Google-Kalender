@echo off
cd /d "%~dp0"
chcp 65001 > nul
echo ================================================
echo  WhatsApp Kalender-Bot - Build
echo  Erstellt ein fertiges Paket in: release\
echo ================================================
echo.

:: ── Voraussetzungen pruefen ──────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Python nicht installiert.
    echo Download: https://python.org  (Haken bei "Add to PATH" setzen!)
    pause & exit /b 1
)

node --version >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Node.js nicht installiert.
    echo Download: https://nodejs.org  (LTS Version)
    pause & exit /b 1
)

echo [OK] Python und Node.js gefunden.
echo.

:: ── npm-Pakete installieren ──────────────────────
echo [1/5] Installiere WhatsApp Bridge Pakete (kann einige Minuten dauern)...
echo       (laedt auch Chromium fuer WhatsApp Web, ~200 MB)
echo.
cd whatsapp-bridge
call npm install
if errorlevel 1 ( echo FEHLER bei npm install. & cd .. & pause & exit /b 1 )
cd ..
echo.

:: ── Portable node.exe herunterladen ─────────────
echo [2/5] Lade portable Node.js fuer den Server herunter...
powershell -Command ^
  "Invoke-WebRequest -Uri 'https://nodejs.org/dist/v20.11.1/win-x64/node.exe' ^
  -OutFile 'whatsapp-bridge\node.exe' -UseBasicParsing"
if errorlevel 1 (
    echo FEHLER beim Download von node.exe.
    echo Bitte manuell herunterladen:
    echo   https://nodejs.org/dist/v20.11.1/win-x64/node.exe
    echo   -> nach whatsapp-bridge\node.exe speichern
    pause & exit /b 1
)
echo [OK] node.exe heruntergeladen.
echo.

:: ── Python-Abhaengigkeiten + PyInstaller ─────────
echo [3/5] Installiere Python-Pakete...
pip install -r requirements.txt --quiet
pip install pyinstaller --quiet
if errorlevel 1 ( echo FEHLER bei pip install. & pause & exit /b 1 )
echo.

:: ── bot.exe bauen ────────────────────────────────
echo [4/5] Baue bot.exe...
pyinstaller --onefile --noconsole --name bot ^
    --hidden-import=apscheduler.triggers.date ^
    --hidden-import=apscheduler.triggers.interval ^
    --hidden-import=recurring_ical_events ^
    --hidden-import=icalendar ^
    bot.py
if errorlevel 1 ( echo FEHLER beim Bauen der exe. & pause & exit /b 1 )
echo.

:: ── release-Paket zusammenstellen ───────────────
echo [5/5] Erstelle fertiges Paket in release\...
if exist release rmdir /s /q release
mkdir release
mkdir release\whatsapp-bridge

copy dist\bot.exe        release\bot.exe        >nul
copy config.ini          release\config.ini     >nul
copy start.bat           "release\Bot starten.bat" >nul
copy autostart.bat       release\autostart.bat  >nul

:: whatsapp-bridge komplett kopieren (inkl. node_modules + node.exe)
xcopy /E /I /Y /Q whatsapp-bridge\*.js       release\whatsapp-bridge\ >nul
xcopy /E /I /Y /Q whatsapp-bridge\*.json     release\whatsapp-bridge\ >nul
xcopy /E /I /Y /Q whatsapp-bridge\node.exe   release\whatsapp-bridge\ >nul
xcopy /E /I /Y /Q whatsapp-bridge\node_modules release\whatsapp-bridge\node_modules\ >nul

echo.
echo ================================================
echo  FERTIG! Paket liegt in: release\
echo ================================================
echo.
echo Auf den Heimserver kopieren: den gesamten release\ Ordner
echo.
echo EINRICHTUNG (einmalig):
echo   1. release\config.ini oeffnen und ausfuellen:
echo      - Groq_ApiKey  (kostenlos: console.groq.com)
echo      - iCal-URLs    (Google Kalender Einstellungen)
echo.
echo STARTEN:
echo   release\Bot starten.bat  doppelklicken
echo   Beim ersten Start: QR-Code mit WhatsApp scannen
echo   Danach: laeuft alles automatisch im Hintergrund
echo.
pause
