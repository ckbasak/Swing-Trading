@echo off
title AI-Swing-Trade Dashboard (Port 8502)
cd /d "%~dp0"
echo Starting Streamlit Dashboard on port 8502...
streamlit run app.py --server.port 8502
pause
