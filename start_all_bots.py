import os
import sys
import time
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

def get_services():
    port = os.environ.get("PORT", "10000")
    return [
        {
            "name": "Unified Telegram Bots Supervisor",
            "token_env": None,
            "cmd": [sys.executable, "-u", "start_unified_bots.py"],
            "cwd": PROJECT_ROOT,
        },
        {
            "name": "Streamlit Web Dashboard",
            "token_env": None,
            "cmd": [
                sys.executable, "-m", "streamlit", "run", "app.py",
                "--server.port", str(port),
                "--server.address", "0.0.0.0",
                "--server.headless=true",
                "--server.enableCORS=false",
                "--server.enableWebsocketCompression=false"
            ],
            "cwd": PROJECT_ROOT,
        }
    ]

def start_process(svc):
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    
    all_token_keys = ["TELEGRAM_BOT_TOKEN_1", "TELEGRAM_BOT_TOKEN_2", "TELEGRAM_BOT_TOKEN_3", "TELEGRAM_BOT_TOKEN_ETF", "TELEGRAM_BOT_TOKEN"]
    
    # Strict Token Isolation
    if svc.get("token_env"):
        target_token = env.get(svc["token_env"]) or ""
        # Remove all token keys first to prevent inheritance
        for k in all_token_keys:
            env.pop(k, None)
        # Set exact target token
        env["TELEGRAM_BOT_TOKEN"] = target_token
        env[svc["token_env"]] = target_token
        print(f"[SUPERVISOR] Injected isolated token for {svc['name']} (Key: {svc['token_env']})", flush=True)

    print(f"[SUPERVISOR] Starting {svc['name']} in {svc['cwd']}...", flush=True)
    proc = subprocess.Popen(svc["cmd"], cwd=svc["cwd"], env=env)
    svc["proc"] = proc
    svc["start_time"] = time.time()
    
    # Write PID file if service is a bot
    if svc.get("token_env"):
        pid_file = os.path.join(svc["cwd"], "bot.pid")
        try:
            with open(pid_file, "w") as f:
                f.write(str(proc.pid))
            print(f"[SUPERVISOR] Recorded PID {proc.pid} in {pid_file}", flush=True)
        except Exception as e:
            print(f"[SUPERVISOR] Failed writing PID file {pid_file}: {e}", flush=True)
            
    return proc

def main():
    print("[SUPERVISOR] Starting Multi-Bot and Streamlit Supervisor with Token Isolation...", flush=True)
    services = get_services()
    for svc in services:
        start_process(svc)
        
    print("[SUPERVISOR] All 5 processes launched. Entering health monitoring loop...", flush=True)
    while True:
        try:
            time.sleep(10)
            for svc in services:
                proc = svc.get("proc")
                if proc is None or proc.poll() is not None:
                    exit_code = proc.poll() if proc else "None"
                    print(f"[SUPERVISOR WARNING] Service '{svc['name']}' stopped (code {exit_code}). Restarting...", flush=True)
                    start_process(svc)
        except KeyboardInterrupt:
            print("[SUPERVISOR] Shutting down all processes...", flush=True)
            for svc in services:
                p = svc.get("proc")
                if p and p.poll() is None:
                    p.terminate()
            break
        except Exception as e:
            print(f"[SUPERVISOR ERROR] Error in supervisor loop: {e}", flush=True)

if __name__ == "__main__":
    main()
