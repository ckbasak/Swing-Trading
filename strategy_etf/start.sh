#!/bin/bash
export PORT=${PORT:-10000}
echo "Starting ETF Swing Trade 1 Platform on port $PORT..."
python bot.py &
echo "Background Bot daemon started."
exec streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true