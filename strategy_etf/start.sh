#!/bin/bash
export BOT_STARTED_BY_SCRIPT=1

# Determine port (Render assigns $PORT, fallback to 10000)
PORT_TO_USE="${PORT:-10000}"

# Start Strategy ETF Telegram Bot daemon in background AFTER Streamlit binds to port
(
  sleep 15
  while true; do
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Starting ETF Strategy Bot daemon (bot.py)..." >> bot.log 2>&1
    python -u bot.py >> bot.log 2>&1
    EXIT_CODE=$?
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] ETF Strategy bot.py exited with code ${EXIT_CODE}. Restarting in 10s..." >> bot.log 2>&1
    sleep 10
  done
) &

echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Launching Strategy ETF Streamlit UI on port $PORT_TO_USE..."

# Start the Streamlit app immediately in the foreground
exec streamlit run app.py --server.port "$PORT_TO_USE" --server.address 0.0.0.0 --server.fileWatcherType none --server.headless true
