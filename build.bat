@echo off
echo ============================================
echo  WhatsApp Kalender-Bot - Build
echo ============================================
echo.

:: Python pruefen
python --version >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Python nicht gefunden. https://python.org
    pause & exit /b 1
)

:: Node.js pruefen
node --version >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Node.js nicht gefunden. https://nodejs.org
    pause & exit /b 1
)

echo [1/4] Installiere Python-Abhaengigkeiten...
pip install -r requirements.txt --quiet
pip install pyinstaller --quiet
if errorlevel 1 ( echo FEHLER. & pause & exit /b 1 )

echo [2/4] Installiere Node.js-Abhaengigkeiten (WhatsApp Bridge)...
cd whatsapp-bridge
npm install
cd ..
if errorlevel 1 ( echo FEHLER. & pause & exit /b 1 )

echo [3/4] Baue bot.exe...
pyinstaller --onefile --noconsole --name bot ^
    --hidden-import=apscheduler.triggers.date ^
    --hidden-import=apscheduler.triggers.interval ^
    --hidden-import=recurring_ical_events ^
    --hidden-import=icalendar ^
    bot.py
if errorlevel 1 ( echo FEHLER. & pause & exit /b 1 )

echo [4/4] Kopiere Dateien nach release\...
if not exist "release" mkdir release
if not exist "release\whatsapp-bridge" mkdir release\whatsapp-bridge
copy dist\bot.exe release\bot.exe >nul
copy config.ini release\config.ini >nul
copy start.bat release\start.bat >nul
copy autostart.bat release\autostart.bat >nul
xcopy /E /I /Q whatsapp-bridge\*.js release\whatsapp-bridge\ >nul
xcopy /E /I /Q whatsapp-bridge\package*.json release\whatsapp-bridge\ >nul
xcopy /E /I /Q whatsapp-bridge\node_modules release\whatsapp-bridge\node_modules\ >nul 2>&1

echo.
echo ============================================
echo  Fertig! Alles in: release\
echo ============================================
echo.
echo Auf den Server kopieren: den kompletten release\ Ordner
echo.
echo ERSTER START:
echo   1. release\ Ordner auf Server kopieren
echo   2. start.bat starten
echo   3. Im Bridge-Fenster erscheint ein QR-Code
echo   4. QR-Code mit WhatsApp scannen (Geraete verknuepfen)
echo   5. Fertig! Du kannst dem Bot jetzt Nachrichten schicken.
echo.
echo NAECHSTE STARTS: Einfach start.bat doppelklicken
echo.
pause
