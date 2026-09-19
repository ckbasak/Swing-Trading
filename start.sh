#!/bin/bash
export BOT_STARTED_BY_SCRIPT=1

# Start self-healing Telegram bot supervisor in the background
(
  while true; do
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Starting bot.py daemon..." >> bot.log 2>&1
    python -u bot.py >> bot.log 2>&1
    EXIT_CODE=$?
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] bot.py exited with code ${EXIT_CODE}. Restarting in 5s..." >> bot.log 2>&1
    sleep 5
  done
) &

# Start Streamlit dashboard in the foreground
PORT_NUM=${PORT:-8501}
echo "Starting Streamlit dashboard on port ${PORT_NUM}..."
streamlit run app.py --server.port ${PORT_NUM} --server.address 0.0.0.0 --server.fileWatcherType none --server.headless true
