@echo off
echo ============================================
echo  WhatsApp Kalender-Bot - EXE Builder
echo ============================================
echo.

:: Pruefen ob Python vorhanden
python --version >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Python nicht gefunden.
    echo Bitte Python von https://python.org installieren.
    pause
    exit /b 1
)

:: Abhaengigkeiten installieren
echo [1/3] Installiere Abhaengigkeiten...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo FEHLER beim Installieren der Abhaengigkeiten.
    pause
    exit /b 1
)

pip install pyinstaller --quiet

:: EXE bauen
echo [2/3] Baue bot.exe...
pyinstaller --onefile --noconsole --name bot ^
    --hidden-import=apscheduler.triggers.date ^
    --hidden-import=apscheduler.triggers.interval ^
    --hidden-import=googleapiclient ^
    bot.py

if errorlevel 1 (
    echo FEHLER beim Bauen der EXE.
    pause
    exit /b 1
)

:: Ergebnis kopieren
echo [3/3] Kopiere Dateien...
if not exist "release" mkdir release
copy dist\bot.exe release\bot.exe >nul
copy requirements.txt release\ >nul 2>&1

echo.
echo ============================================
echo  Fertig! Die Dateien liegen in: release\
echo ============================================
echo.
echo Auf den Heimserver kopieren:
echo   - bot.exe
echo   - credentials.json  (von Google Cloud Console)
echo.
echo Beim ersten Start:
echo   1. bot.exe ausfuehren -> config.ini wird erstellt
echo   2. config.ini ausfullen
echo   3. bot.exe nochmal starten -> Browser oeffnet sich fuer Google-Login
echo   4. Fertig! Bot laeuft im Hintergrund.
echo.
pause
