@echo off
REM Resilient launcher for the TDS data-analyst Telegram bot.
REM Double-click this file (or run it in a terminal) and leave the window OPEN.
REM It restarts the bot automatically if it ever crashes.
cd /d "%~dp0"
echo ============================================================
echo  TDS Data-Analyst Bot - keep this window OPEN during grading
echo  Press Ctrl+C twice to stop.
echo ============================================================
:loop
python -u bot.py
echo.
echo [launcher] bot exited. Restarting in 5 seconds... (close window to stop)
timeout /t 5 /nobreak >nul
goto loop
