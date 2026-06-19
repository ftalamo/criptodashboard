"""
main.py — Crypto Trading Scanner
=================================

Uso:
    python main.py                         → portfolio completo (PORTFOLIO en config)
    python main.py SOL                     → una cripto
    python main.py SOL TAO KAITO           → múltiples criptos
    python main.py SOL --compact           → JSON compacto (pegar en dashboard)
    python main.py SOL --intervals 1h 4h 1d

Credenciales:
    Crear archivo .env en la misma carpeta:
        BINANCE_API_KEY=tu_key
        BINANCE_API_SECRET=tu_secret
        USDT_AVAILABLE=127.55       ← opcional, capital disponible
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

from binance.client import Client
from core.get_data import get_signals_for_intervals, get_signals_for_portfolio

# ==============================
# CONFIGURACIÓN
# ==============================

# Portfolio por defecto (sin args)
PORTFOLIO = ["SOLUSDT", "TAOUSDT", "KAITOUSDT", "PEPEUSDT", "DOGEUSDT", "SHIBUSDT"]

# Intervalos por defecto
DEFAULT_INTERVALS = ["15m", "1h", "4h", "12h", "1d"]


# ==============================
# CARGAR .ENV (sin dependencias externas)
# ==============================

def load_env(path=".env") -> dict:
    """Lee .env línea a línea. No requiere python-dotenv."""
    env = {}
    env_file = Path(path)
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# ==============================
# OUTPUT
# ==============================

def pretty_json(data) -> str:
    """Formato legible (tu función original)."""
    return json.dumps(data, indent=4, sort_keys=True, ensure_ascii=False)


def compact_json(data) -> str:
    """Formato mínimo para pegar en el dashboard HTML."""
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def save_json(data, symbol: str, compact: bool = False) -> str:
    """Guarda resultado en output/SYMBOL_DDMMM_HHMM.json"""
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    ts    = datetime.now().strftime("%d%b_%H%M").lower()
    fname = out_dir / f"{symbol.replace('USDT','').lower()}_{ts}.json"
    fname.write_text(
        compact_json(data) if compact else pretty_json(data),
        encoding="utf-8"
    )
    return str(fname)


def print_summary(data: dict | list):
    """Resumen de una línea por símbolo para lectura rápida en terminal."""
    items = data if isinstance(data, list) else [data]
    print("\n┌─────────────────────────────────────────────────────────────┐")
    print(  "│  SYMBOL     PRICE       SIGNAL      BULL  BEAR  RSI_1d    │")
    print(  "├─────────────────────────────────────────────────────────────┤")
    for d in items:
        if "error" in d:
            print(f"│  {d['Symbol']:<10}  ERROR: {d['error'][:36]:<36}│")
            continue
        sym    = d.get("Symbol", "?").replace("USDT", "")
        price  = d.get("Price", 0)
        signal = d.get("signal_global", "?")
        bull   = d.get("bull", 0)
        bear   = d.get("bear", 0)
        rsi_1d = d.get("1d", {}).get("momentum", {}).get("RSI", 0)
        orders = d.get("orders", {})
        entry  = f"  → entry ${orders['entry']:.4f}" if orders.get("entry") else ""
        print(f"│  {sym:<10}  ${price:<10.4f}  {signal:<10}  {bull:<4}  {bear:<4}  {rsi_1d:<6.1f}  │")
        if entry:
            print(f"│  {entry:<59}│")
    print("└─────────────────────────────────────────────────────────────┘\n")


# ==============================
# MAIN
# ==============================

def main():
    # ── Args ──────────────────────────────────────────────────────────────────
    parser = argparse.ArgumentParser(description="Crypto Trading Scanner")
    parser.add_argument(
        "symbols", nargs="*",
        help="Símbolos a analizar (ej: SOL TAO). Sin args → portfolio completo."
    )
    parser.add_argument(
        "--intervals", nargs="+", default=DEFAULT_INTERVALS,
        help=f"Timeframes (default: {' '.join(DEFAULT_INTERVALS)})"
    )
    parser.add_argument(
        "--compact", action="store_true",
        help="Output JSON compacto para pegar en el dashboard"
    )
    parser.add_argument(
        "--no-save", action="store_true",
        help="No guardar archivo JSON"
    )
    parser.add_argument(
        "--usdt", type=float, default=None,
        help="USDT disponible para cálculo de órdenes (override .env)"
    )
    args = parser.parse_args()

    # ── Credenciales ──────────────────────────────────────────────────────────
    env = load_env()

    api_key    = env.get("BINANCE_API_KEY")    or "TU_API_KEY"
    api_secret = env.get("BINANCE_API_SECRET") or "TU_SECRET"
    usdt_avail = args.usdt or float(env.get("USDT_AVAILABLE", 127.55))

    if api_key == "TU_API_KEY":
        print("⚠  Sin credenciales. Crea un archivo .env con BINANCE_API_KEY y BINANCE_API_SECRET.")
        sys.exit(1)

    client = Client(api_key, api_secret)

    # ── Símbolos ──────────────────────────────────────────────────────────────
    if args.symbols:
        # Normalizar: SOL → SOLUSDT
        symbols = [
            s.upper() if s.upper().endswith("USDT") else s.upper() + "USDT"
            for s in args.symbols
        ]
    else:
        symbols = PORTFOLIO

    intervals = args.intervals

    # ── Scan ──────────────────────────────────────────────────────────────────
    print(f"\n🔍  {datetime.now().strftime('%d %b %Y %H:%M')}  |  "
          f"Símbolos: {', '.join(s.replace('USDT','') for s in symbols)}  |  "
          f"Intervalos: {' '.join(intervals)}\n")

    if len(symbols) == 1:
        result = get_signals_for_intervals(symbols[0], intervals, client)
        output = result
    else:
        result = get_signals_for_portfolio(symbols, intervals, client, usdt_avail)
        output = result

    # ── Resumen terminal ──────────────────────────────────────────────────────
    print_summary(output)

    # ── Guardar JSON ──────────────────────────────────────────────────────────
    if not args.no_save:
        label = symbols[0].replace("USDT","") if len(symbols) == 1 else "portfolio"
        saved = save_json(output, label, compact=args.compact)
        print(f"💾  Guardado en: {saved}")

    # ── Print JSON ────────────────────────────────────────────────────────────
    print("\n── JSON ──────────────────────────────────────────────────────")
    if args.compact:
        print(compact_json(output))
    else:
        print(pretty_json(output))
    print("──────────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    main()
