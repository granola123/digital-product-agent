@echo off
REM Double-click this to build the next batch of pending cuisines.
REM Pass a number to change the batch size, e.g.:  run-next-batch.bat 3
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-next-batch.ps1" %*
echo.
pause
