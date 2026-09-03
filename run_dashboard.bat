@echo off
title AI-Swing-Trade-1 Dashboard (Port 8501)
cd /d "%~dp0"
echo Starting Streamlit Dashboard #1 on port 8501...
streamlit run app.py --server.port 8501
pause
