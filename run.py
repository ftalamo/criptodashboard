"""
run.py — Arranca el servidor del dashboard
==========================================
Uso:
    python run.py              → http://localhost:8000
    python run.py --port 9000  → http://localhost:9000
    python run.py --reload     → recarga automática al editar código
"""
import argparse
import subprocess
import sys
import webbrowser
import time
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port",   type=int,  default=8000)
    parser.add_argument("--host",   type=str,  default="127.0.0.1")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    cmd = [
        sys.executable, "-m", "uvicorn",
        "core.api:app",
        "--host", args.host,
        "--port", str(args.port),
    ]
    if args.reload:
        cmd.append("--reload")

    print(f"\n Ejecutando Servidor en http://{args.host}:{args.port}")
    print(f" Dashboard: abrir dashboard.html en tu navegador")
    print(f"API docs:  http://{args.host}:{args.port}/docs")
    print(f"Pulsa  Ctrl+C para detener\n")

    # Abrir el dashboard automáticamente
    dashboard = Path("dashboard.html").resolve()
    if dashboard.exists():
        time.sleep(1.5)
        webbrowser.open(f"file://{dashboard}")

    subprocess.run(cmd)

if __name__ == "__main__":
    main()
