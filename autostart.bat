@echo off
:: Legt bot.exe als Windows-Autostart-Aufgabe an (laeuft beim Systemstart)
:: Als Administrator ausfuehren!

set "EXE_PATH=%~dp0bot.exe"

echo Erstelle Windows Aufgabenplanung fuer bot.exe...

schtasks /create ^
    /tn "WhatsApp Kalender Bot" ^
    /tr "%EXE_PATH%" ^
    /sc onstart ^
    /ru SYSTEM ^
    /rl HIGHEST ^
    /f

if errorlevel 1 (
    echo FEHLER: Bitte als Administrator ausfuehren.
    pause
    exit /b 1
)

echo.
echo Fertig! Bot startet automatisch bei jedem Systemstart.
echo.
echo Zum manuellen Starten jetzt:
schtasks /run /tn "WhatsApp Kalender Bot"
echo Bot wurde gestartet.
pause
