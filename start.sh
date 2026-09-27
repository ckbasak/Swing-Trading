#!/bin/bash
export BOT_STARTED_BY_SCRIPT=1

# Determine port (Render assigns $PORT, fallback to 10000)
PORT_TO_USE="${PORT:-10000}"

# Start self-healing 5-Bot Telegram daemon runner in background AFTER Streamlit binds to port
(
  sleep 15
  while true; do
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Starting 5-bot unified runner (start_unified_bots.py)..." >> bot.log 2>&1
    python -u start_unified_bots.py >> bot.log 2>&1
    EXIT_CODE=$?
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] start_unified_bots.py exited with code ${EXIT_CODE}. Restarting in 10s..." >> bot.log 2>&1
    sleep 10
  done
) &

# Determine target Streamlit app script to run
TARGET_APP="${STRATEGY_APP:-app.py}"
if [ ! -f "$TARGET_APP" ]; then
    TARGET_APP="app.py"
fi

echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Launching Streamlit UI for $TARGET_APP on port $PORT_TO_USE..."

# Start the Streamlit app immediately in the foreground
exec streamlit run "$TARGET_APP" --server.port "$PORT_TO_USE" --server.address 0.0.0.0 --server.fileWatcherType none --server.headless true
