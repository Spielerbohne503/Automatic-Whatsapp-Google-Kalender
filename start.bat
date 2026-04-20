@echo off
chcp 65001 > nul
cd /d "%~dp0"
title WhatsApp Kalender-Bot

:: Pruefe ob Session existiert (nach erstem QR-Scan)
if exist "whatsapp-bridge\session" (
    echo [Bridge] Verbinde WhatsApp automatisch...
    start /min "WhatsApp Bridge" cmd /k "cd /d whatsapp-bridge && node.exe index.js"
) else (
    echo.
    echo ================================================
    echo  ERSTER START: QR-Code scannen!
    echo  WhatsApp > Geraete verknuepfen > QR-Code
    echo  Das Bridge-Fenster wird gleich geoeffnet.
    echo ================================================
    echo.
    start "WhatsApp Bridge - QR-Code scannen!" cmd /k "cd /d whatsapp-bridge && node.exe index.js"
)

echo Warte auf WhatsApp-Verbindung...
timeout /t 10 /nobreak > nul

echo Starte Bot...
start /b "" bot.exe

echo Bot laeuft im Hintergrund. Logs: bot.log
timeout /t 3 /nobreak > nul
