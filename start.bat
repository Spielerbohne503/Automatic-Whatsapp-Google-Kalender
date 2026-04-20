@echo off
echo ============================================
echo  WhatsApp Kalender-Bot starten
echo ============================================
echo.

:: WhatsApp Bridge starten (im Hintergrund)
echo [1/2] Starte WhatsApp Bridge...
cd whatsapp-bridge
start "WhatsApp Bridge" cmd /k "node index.js"
cd ..

echo Warte 8 Sekunden auf WhatsApp-Verbindung...
timeout /t 8 /nobreak > nul

:: Python Bot starten
echo [2/2] Starte Bot...
bot.exe

pause
