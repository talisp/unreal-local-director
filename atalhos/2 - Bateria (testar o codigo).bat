@echo off
chcp 65001 >nul
title Director - Bateria
cd /d "%~dp0.."
"venv\Scripts\python.exe" tools\rotina.py bateria
echo.
echo Pode fechar esta janela.
pause
