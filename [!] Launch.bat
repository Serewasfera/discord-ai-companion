@echo off
chcp 65001 >nul
title Discord AI Companion - Запуск
call venv\scripts\activate
python main.py
pause