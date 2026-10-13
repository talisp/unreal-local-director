@echo off
chcp 65001 >nul
title Director - Unreal ENSAIO
cd /d "%~dp0.."
"venv\Scripts\python.exe" tools\rotina.py ensaio
echo.
echo Pode fechar esta janela.
pause
