from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
EDGE_APP = REPO_ROOT / "edge_app" / "app.py"
CLOUD_APP = REPO_ROOT / "cloud_analytics" / "app.py"
GATEWAY_BRIDGE = REPO_ROOT / "gateway_sync" / "gateway_bridge.py"


def _python() -> list[str]:
    return [sys.executable]


def _streamlit_cmd(app_path: Path, port: int) -> list[str]:
    return _python() + [
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.port",
        str(port),
        "--server.headless",
        "false",
        "--server.address",
        "localhost",
        "--browser.gatherUsageStats",
        "false",
    ]


def _gateway_cmd() -> list[str]:
    return _python() + [str(GATEWAY_BRIDGE)]


def main() -> int:
    ap = argparse.ArgumentParser(description="Launch edge app + gateway sync + cloud dashboard together.")
    ap.add_argument("--edge-port", type=int, default=8502, help="Port for edge Streamlit app")
    ap.add_argument("--cloud-port", type=int, default=8503, help="Port for cloud analytics Streamlit app")
    ap.add_argument(
        "--gateway-ingest-url",
        default=os.environ.get("CLOUD_INGEST_URL", ""),
        help="Ingest URL for gateway bridge (sets CLOUD_INGEST_URL)",
    )
    ap.add_argument(
        "--gateway-edge-inbox",
        default=str(REPO_ROOT / "edge_app" / "inbox"),
        help="Edge inbox folder for gateway bridge",
    )
    ap.add_argument(
        "--gateway-schema",
        default=str(REPO_ROOT / "processed_water_data.csv"),
        help="Schema CSV for gateway bridge (processed_water_data.csv)",
    )
    args = ap.parse_args()

    if not EDGE_APP.exists():
        print(f"[ERROR] Missing edge app: {EDGE_APP}")
        return 2
    if not CLOUD_APP.exists():
        print(f"[ERROR] Missing cloud analytics app: {CLOUD_APP}")
        return 2
    if not GATEWAY_BRIDGE.exists():
        print(f"[ERROR] Missing gateway bridge: {GATEWAY_BRIDGE}")
        return 2

    print("")
    print("Launching Field Tech Data Validator (hybrid)...")
    print("")
    print(f"- Edge app URL:   http://localhost:{args.edge_port}")
    print(f"- Cloud app URL:  http://localhost:{args.cloud_port}")
    print("")
    print("Press Ctrl+C to stop all processes.")
    print("")

    env = os.environ.copy()
    if args.gateway_ingest_url:
        env["CLOUD_INGEST_URL"] = args.gateway_ingest_url

    procs: list[subprocess.Popen] = []

    try:
        # Gateway bridge (runs continuously; reads edge inbox and syncs when online)
        gateway_cmd = _gateway_cmd() + ["--edge-inbox", args.gateway_edge_inbox, "--schema", args.gateway_schema]
        print(f"[START] Gateway sync: {' '.join(gateway_cmd)}")
        procs.append(subprocess.Popen(gateway_cmd, cwd=str(REPO_ROOT), env=env))

        # Edge Streamlit
        edge_cmd = _streamlit_cmd(EDGE_APP, args.edge_port)
        print(f"[START] Edge Streamlit: {' '.join(edge_cmd)}")
        procs.append(subprocess.Popen(edge_cmd, cwd=str(REPO_ROOT), env=env))

        # Cloud Streamlit
        cloud_cmd = _streamlit_cmd(CLOUD_APP, args.cloud_port)
        print(f"[START] Cloud Streamlit: {' '.join(cloud_cmd)}")
        procs.append(subprocess.Popen(cloud_cmd, cwd=str(REPO_ROOT), env=env))

        # Keep parent alive while children run.
        while True:
            # If any process exits unexpectedly, stop all and return failure.
            for p in procs:
                code = p.poll()
                if code is not None:
                    print(f"[STOP] A process exited early with code {code}. Shutting down the rest...")
                    raise RuntimeError("Child process exited")
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n[CTRL+C] Stopping all processes...")
    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        # Terminate children cleanly
        for p in procs:
            try:
                if p.poll() is None:
                    if os.name == "nt":
                        p.send_signal(signal.CTRL_BREAK_EVENT)  # best-effort on Windows
                        time.sleep(0.2)
                    p.terminate()
            except Exception:
                pass

        # Force kill if needed
        deadline = time.time() + 5
        for p in procs:
            try:
                while p.poll() is None and time.time() < deadline:
                    time.sleep(0.1)
                if p.poll() is None:
                    p.kill()
            except Exception:
                pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

