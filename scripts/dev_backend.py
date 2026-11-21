"""Run both uvicorn reloaders in the same development terminal."""
import os
import json
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]

def running(port, route):
    try:
        with urlopen(f"http://127.0.0.1:{port}/openapi.json", timeout=2) as response:
            if route in json.load(response).get("paths", {}):
                print(f"Reusing service on {port}", flush=True)
                return True
    except (URLError, TimeoutError, ValueError):
        return False
    raise RuntimeError(f"Port {port} is occupied by another application")


def main():
    servers = [
        (8081, "/api/inquiries/{ident}/selection", ROOT, [sys.executable, "-m", "uvicorn", "src.api.main:app", "--reload-dir", "src/api"]),
        (8000, "/api/quote-drafts/search", ROOT / "src/backend", ["uv", "run", "--locked", "uvicorn", "app.main:app", "--reload-dir", "app"]),
    ]
    processes = []
    try:
        for port, route, cwd, command in servers:
            if running(port, route):
                continue
            options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                       else {"start_new_session": True})
            processes.append(subprocess.Popen([*command, "--host", "127.0.0.1", "--port", str(port), "--reload"], cwd=cwd, **options))
        if not processes:
            return 0
        while all(p.poll() is None for p in processes):
            time.sleep(0.3)
        return next(p.returncode for p in processes if p.returncode is not None)
    except KeyboardInterrupt:
        return 0
    finally:
        for process in processes:
            if process.poll() is None:
                if os.name == "nt":
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    os.killpg(process.pid, signal.SIGTERM)
        for process in processes:
            process.wait()


if __name__ == "__main__":
    sys.exit(main())
