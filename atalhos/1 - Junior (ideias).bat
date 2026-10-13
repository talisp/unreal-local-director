@echo off
chcp 65001 >nul
title Director - Junior
cd /d "%~dp0.."
"venv\Scripts\python.exe" tools\rotina.py junior
echo.
echo Pode fechar esta janela.
pause
