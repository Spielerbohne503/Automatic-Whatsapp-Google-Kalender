@echo off
cd /d "%~dp0"
:: Richtet automatischen Start bei Windows-Systemstart ein.
:: Als Administrator ausfuehren!

set "START_BAT=%~dp0Bot starten.bat"

echo Erstelle Windows Aufgabenplanung...
echo Startet: %START_BAT%
echo.

schtasks /create ^
    /tn "WhatsApp Kalender Bot" ^
    /tr "cmd /c \"%START_BAT%\"" ^
    /sc onstart ^
    /ru "%USERNAME%" ^
    /rl HIGHEST ^
    /f

if errorlevel 1 (
    echo FEHLER: Bitte als Administrator ausfuehren (Rechtsklick -> Als Administrator).
    pause & exit /b 1
)

echo.
echo [OK] Bot startet ab jetzt automatisch bei jedem Systemstart.
echo.
echo Zum sofortigen Starten:
schtasks /run /tn "WhatsApp Kalender Bot"
echo Bot wurde gestartet.
echo.
pause
