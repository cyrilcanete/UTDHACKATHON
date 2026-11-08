@echo off
cd /d "%~dp0"
py configure_nemotron.py --start --personal --port 5001
pause
