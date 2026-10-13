@echo off
chcp 65001 >nul
title Director - Unreal NOITE
cd /d "%~dp0.."
"venv\Scripts\python.exe" tools\rotina.py noite
echo.
echo Pode fechar esta janela.
pause
