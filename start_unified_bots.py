import os
import sys
import time
import threading

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

def run_single_bot(name, strategy_dir, token_env):
    token = os.environ.get(token_env) or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print(f"[UNIFIED BOTS] Skip {name} - token {token_env} missing", flush=True)
        return

    print(f"[UNIFIED BOTS] Starting thread for {name} in {strategy_dir}...", flush=True)
    
    s_path = os.path.join(PROJECT_ROOT, strategy_dir)
    if s_path not in sys.path:
        sys.path.insert(0, s_path)

    old_cwd = os.getcwd()
    try:
        os.chdir(s_path)
        pid_file = os.path.join(s_path, "bot.pid")
        with open(pid_file, "w") as f:
            f.write(str(os.getpid()))
            
        if strategy_dir == "strategy1":
            import strategy1.bot as b1
            b1.run_forever()
        elif strategy_dir == "strategy2":
            import strategy2.bot as b2
            b2.run_forever()
        elif strategy_dir == "strategy3":
            import strategy3.bot as b3
            b3.run_forever()
        elif strategy_dir == "strategy_etf":
            import strategy_etf.bot as b_etf
            b_etf.run_forever()
    except Exception as e:
        print(f"[UNIFIED BOTS ERROR] {name} exited with error: {e}", flush=True)
    finally:
        os.chdir(old_cwd)

def main():
    print("[UNIFIED BOTS] Starting 4 Telegram Bots in ONE Memory-Optimized Python Process...", flush=True)
    bot_configs = [
        ("Strategy #1 Bot", "strategy1", "TELEGRAM_BOT_TOKEN_1"),
        ("Strategy #2 Bot", "strategy2", "TELEGRAM_BOT_TOKEN_2"),
        ("Strategy #3 Bot", "strategy3", "TELEGRAM_BOT_TOKEN_3"),
        ("ETF Strategy Bot", "strategy_etf", "TELEGRAM_BOT_TOKEN_ETF"),
    ]

    threads = []
    for name, s_dir, t_env in bot_configs:
        t = threading.Thread(target=run_single_bot, args=(name, s_dir, t_env), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(2)  # Stagger startup to prevent memory spikes

    print("[UNIFIED BOTS] All 4 bot threads active. Monitoring...", flush=True)
    while True:
        time.sleep(30)

if __name__ == "__main__":
    main()

