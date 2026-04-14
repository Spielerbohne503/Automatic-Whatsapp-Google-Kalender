@echo off
echo ============================================
echo  WhatsApp Kalender-Bot - EXE Builder
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Python nicht gefunden.
    echo Bitte Python von https://python.org installieren.
    pause
    exit /b 1
)

echo [1/3] Installiere Abhaengigkeiten...
pip install -r requirements.txt --quiet
if errorlevel 1 ( echo FEHLER bei Abhaengigkeiten. & pause & exit /b 1 )

pip install pyinstaller --quiet

echo [2/3] Baue bot.exe...
pyinstaller --onefile --noconsole --name bot ^
    --hidden-import=apscheduler.triggers.date ^
    --hidden-import=apscheduler.triggers.interval ^
    --hidden-import=recurring_ical_events ^
    --hidden-import=icalendar ^
    bot.py

if errorlevel 1 ( echo FEHLER beim Bauen der EXE. & pause & exit /b 1 )

echo [3/3] Kopiere Dateien...
if not exist "release" mkdir release
copy dist\bot.exe release\bot.exe >nul

echo.
echo ============================================
echo  Fertig! Datei liegt in: release\bot.exe
echo ============================================
echo.
echo Auf den Heimserver kopieren:
echo   - bot.exe
echo.
echo Erster Start auf dem Server:
echo   1. bot.exe starten  ->  config.ini wird erstellt
echo   2. config.ini oeffnen und iCal-Links + CallMeBot-Key eintragen
echo   3. bot.exe nochmal starten  ->  laeuft sofort
echo.
pause
