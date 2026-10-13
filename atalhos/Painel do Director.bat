@echo off
chcp 65001 >nul
title Director - Painel
cd /d "%~dp0.."
"venv\Scripts\python.exe" tools\rotina.py painel
