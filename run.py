import sys
import os
import time
import webbrowser
import threading
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add current workspace root to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.config import config, DATA_DIR
from core.database import init_db
from core.security_controller import security_controller
from web.app import app

def open_browser():
    time.sleep(1.5)
    url = "http://127.0.0.1:5000"
    print(f"\n[System] Opening Command Center in your browser: {url}\n")
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"[System] Could not automatically open browser: {e}")

def main():
    print("=" * 65)
    print(" [SENTINEL AI] HOME INTRUDER & FACIAL RECOGNITION SYSTEM")
    print("=" * 65)
    print(f"[*] Workspace Root: {BASE_DIR}")
    print(f"[*] Data Directory: {DATA_DIR}")
    print(f"[*] Python Runtime: {sys.version.split()[0]}")
    print(f"[*] Default PIN Code: {config.get('pin_code', '1234')}")
    print(f"[*] Owner Alert Email: {config.get('owner_email', 'owner@example.com')}")
    print("-" * 65)

    # 1. Initialize Database
    init_db()

    # 2. Start Security Surveillance & Face Recognition Engine
    security_controller.start()

    # 3. Schedule Browser Auto-Open
    threading.Thread(target=open_browser, daemon=True).start()

    # 4. Start Web Command Center
    host = "127.0.0.1"
    port = 5000
    print(f"[*] Launching Web Command Center on http://{host}:{port}")
    print("[*] Press Ctrl+C in terminal to stop the system.\n")

    try:
        app.run(host=host, port=port, debug=False, threaded=True, use_reloader=False)
    except (KeyboardInterrupt, SystemExit):
        print("\n[System] Shutting down Sentinel Security System...")
    finally:
        security_controller.stop()
        print("[System] Security services terminated safely.")

if __name__ == "__main__":
    main()
