@echo off
title AI-Swing-Trade-2 Dashboard (Port 8502)
cd /d "%~dp0"
echo Starting Streamlit Dashboard #2 on port 8502...
streamlit run app.py --server.port 8502
pause
