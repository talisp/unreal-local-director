@echo off
chcp 65001 >nul
title Director - Astra
cd /d "%~dp0.."
"venv\Scripts\python.exe" tools\rotina.py astra
echo.
echo Pode fechar esta janela.
pause
