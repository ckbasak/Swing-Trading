import os
import sys
import time
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

def _load_env():
    env_file = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_file):
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
        except Exception:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() not in os.environ:
                            os.environ[k.strip()] = v.strip().strip("'").strip('"')
_load_env()

# Single-process RAM optimization: Limit internal thread pools & memory allocations
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["PYTHONMALLOC"] = "malloc"

DEFAULT_BOT_TOKENS = {
    "TELEGRAM_BOT_TOKEN_1": "8832604687:AAHYOy1ywIcK-FOnnsgQTGEoDr9SiBUp2mc",
    "TELEGRAM_BOT_TOKEN_2": "8776408528:AAGexszfsf0DmRHFtS5CrPo_QmsN06QXc_A",
    "TELEGRAM_BOT_TOKEN_3": "8821130913:AAHL-oB8ZVAHU95QguFC3I7kxVT5XaaOaWc",
    "TELEGRAM_BOT_TOKEN_ETF": "8847294226:AAE0GTApXUSPbzX3lzUmpziOaAbU02zxMVY",
    "TELEGRAM_BOT_TOKEN_MDP": "8846086245:AAHeM2s85bmfHpOy1MZ_f45l3myND4C3z3Y",
}

DEFAULT_SHEETS = {
    "strategy1": "NSE_Swing_Trading_Portfolio_1",
    "strategy2": "NSE_Swing_Trading_Portfolio_2",
    "strategy3": "NSE_Swing_Trading_Portfolio_3",
    "strategy_etf": "NSE_ETF_Swing_Trading_Portfolio_1",
    "strategy_mdp": "NSE_Dhan_Portfolio_Manager",
}

BOT_CONFIGS = [
    ("Strategy #1 Bot", "strategy1", "TELEGRAM_BOT_TOKEN_1"),
    ("Strategy #2 Bot", "strategy2", "TELEGRAM_BOT_TOKEN_2"),
    ("Strategy #3 Bot", "strategy3", "TELEGRAM_BOT_TOKEN_3"),
    ("ETF Strategy Bot", "strategy_etf", "TELEGRAM_BOT_TOKEN_ETF"),
    ("Manage-Dhan-Portfolio Bot", "strategy_mdp", "TELEGRAM_BOT_TOKEN_MDP"),
]

def launch_bot_process(name, strategy_dir, token_env):
    s_path = os.path.join(PROJECT_ROOT, strategy_dir)
    bot_script = os.path.join(s_path, "bot.py")
    if not os.path.exists(bot_script):
        print(f"[UNIFIED BOTS] {name}: bot.py missing at {bot_script}", flush=True)
        return None

    bot_token = os.environ.get(token_env) or DEFAULT_BOT_TOKENS.get(token_env)
    sheet_name = DEFAULT_SHEETS.get(strategy_dir)

    bot_env = os.environ.copy()
    if bot_token:
        bot_env[token_env] = bot_token
        bot_env["TELEGRAM_BOT_TOKEN"] = bot_token
    if sheet_name:
        bot_env["SPREADSHEET_NAME"] = sheet_name

    print(f"[UNIFIED BOTS] Spawning subprocess for {name} in {strategy_dir}...", flush=True)
    proc = subprocess.Popen([sys.executable, "-u", bot_script], cwd=s_path, env=bot_env)
    pid_file = os.path.join(s_path, "bot.pid")
    try:
        with open(pid_file, "w") as f:
            f.write(str(proc.pid))
    except Exception:
        pass
    return proc

import threading

def _start_keep_alive_thread():
    def _ping():
        app_url = os.environ.get("RENDER_EXTERNAL_URL") or "https://ck-swing-trading-master.onrender.com"
        import requests
        while True:
            time.sleep(720)  # Ping every 12 minutes to keep Render service awake
            try:
                r = requests.get(app_url, timeout=15)
                print(f"[KEEP-ALIVE] Ping {app_url} -> Status {r.status_code}", flush=True)
            except Exception as e:
                print(f"[KEEP-ALIVE] Ping {app_url} error: {e}", flush=True)

    t = threading.Thread(target=_ping, daemon=True)
    t.start()

def main():
    print("[UNIFIED BOTS] Master Process Watchdog starting 5 Bot Subprocesses...", flush=True)
    _start_keep_alive_thread()
    processes = {}
    
    for name, s_dir, t_env in BOT_CONFIGS:
        proc = launch_bot_process(name, s_dir, t_env)
        if proc:
            processes[s_dir] = (name, s_dir, t_env, proc)
        time.sleep(1)

    print("[UNIFIED BOTS] All 5 bot subprocesses spawned. Entering active supervision loop...", flush=True)
    while True:
        time.sleep(10)
        for s_dir, (name, strategy_dir, t_env, proc) in list(processes.items()):
            poll = proc.poll()
            if poll is not None:
                print(f"[UNIFIED BOTS WARNING] {name} exited with code {poll}. Auto-restarting in 2s...", flush=True)
                new_proc = launch_bot_process(name, strategy_dir, t_env)
                if new_proc:
                    processes[s_dir] = (name, strategy_dir, t_env, new_proc)

if __name__ == "__main__":
    main()
