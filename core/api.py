"""
core/api.py — Servidor FastAPI para el dashboard
================================================
Expone el scanner de Binance como API REST local.

Arrancar:
    python run.py
    ó
    python -m uvicorn core.api:app --host 0.0.0.0 --port 8000 --reload

Endpoints:
    GET /health             → estado del servidor y conexión a Binance
    GET /portfolio          → portfolio y configuración activa
    GET /scan               → escanea símbolos y devuelve JSON completo
    GET /config             → configuración cargada (debug)
"""

import os
import time
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from binance.client import Client
from core.get_data import get_signals_for_intervals, get_signals_for_portfolio


# ══════════════════════════════════════════════════════════════════════════════
#  LOADERS
# ══════════════════════════════════════════════════════════════════════════════

def load_env(path: str = ".env") -> dict:
    """
    Lee .env sin dependencias externas.
    Busca el archivo en este orden:
      1. Ruta exacta indicada (si es absoluta)
      2. Relativo al directorio de trabajo actual (donde se corre el script)
      3. Relativo a la raíz del proyecto (carpeta padre de core/)
    """
    result = {}

    candidates = [
        Path(path),                                    # ruta tal como viene
        Path.cwd() / path,                             # desde donde se corre
        Path(__file__).parent.parent / path,           # raíz del proyecto (scanner/)
    ]

    env_file = next((p for p in candidates if p.exists()), None)

    if env_file is None:
        print(f".env no encontrado. Rutas buscadas:\n" +
              "\n".join(f"   {p}" for p in candidates))
        return result

    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip().strip('"').strip("'")

    return result


def load_config(path: str = "scanner.config") -> dict:
    """
    Lee scanner.config — formato clave = valor, comentarios con #.
    Los valores con comas se parsean como listas.
    Se recarga en cada llamada → cambios sin reiniciar el servidor.
    Busca el archivo con la misma lógica que load_env().
    """
    result = {}

    candidates = [
        Path(path),
        Path.cwd() / path,
        Path(__file__).parent.parent / path,   # raíz del proyecto (scanner/)
    ]

    cfg_file = next((p for p in candidates if p.exists()), None)

    if cfg_file is None:
        raise FileNotFoundError(
            f"No se encontró '{path}'.\n"
            f"Rutas buscadas:\n" +
            "\n".join(f"  {p}" for p in candidates) +
            "\nCrea el archivo o copia scanner.config.example."
        )

    for line in cfg_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip()
        # Si tiene comas → lista limpia
        if "," in v:
            result[k] = [item.strip() for item in v.split(",") if item.strip()]
        else:
            result[k] = v
    return result


def get_cfg() -> dict:
    """
    Devuelve la configuración activa, mezclando scanner.config con valores
    de .env para las credenciales.
    Recarga scanner.config en cada llamada → cambios en caliente.
    """
    env = load_env()
    cfg = load_config()

    # Normalizar portfolio: ["SOL","TAO"] → ["SOLUSDT","TAOUSDT"]
    raw_portfolio = cfg.get("PORTFOLIO", [])
    if isinstance(raw_portfolio, str):
        raw_portfolio = [raw_portfolio]
    portfolio = [
        s.upper() + ("" if s.upper().endswith("USDT") else "USDT")
        for s in raw_portfolio
    ]

    # Normalizar intervalos
    def to_list(val):
        if isinstance(val, list): return val
        return [val] if val else []

    intervals_available = to_list(cfg.get("INTERVALS_AVAILABLE", []))
    intervals_default   = to_list(cfg.get("INTERVALS_DEFAULT", []))

    # Validar que default ⊆ available
    intervals_default = [iv for iv in intervals_default if iv in intervals_available]
    if not intervals_default and intervals_available:
        intervals_default = intervals_available[:5]

    return {
        # Credenciales (solo del .env, nunca en .config)
        "api_key":    env.get("BINANCE_API_KEY")    or os.getenv("BINANCE_API_KEY",    ""),
        "api_secret": env.get("BINANCE_API_SECRET") or os.getenv("BINANCE_API_SECRET", ""),
        "usdt":       float(env.get("USDT_AVAILABLE", 127.55)),

        # Del scanner.config
        "portfolio":            portfolio,
        "intervals_available":  intervals_available,
        "intervals_default":    intervals_default,
        "server_host":          cfg.get("SERVER_HOST", "127.0.0.1"),
        "server_port":          int(cfg.get("SERVER_PORT", 8000)),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  APP
# ══════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="Crypto Trading Scanner API",
    version="2.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Cliente Binance (singleton — se recrea si cambian las credenciales) ───────
_client: Client | None = None
_client_key: str = ""

def get_client() -> Client:
    global _client, _client_key
    cfg = get_cfg()
    key = cfg["api_key"]

    if not key or not cfg["api_secret"]:
        raise HTTPException(
            status_code=500,
            detail="Credenciales no configuradas. Revisa tu archivo .env"
        )
    # Recrear si cambiaron las credenciales
    if _client is None or key != _client_key:
        _client     = Client(key, cfg["api_secret"])
        _client_key = key
    return _client


# ══════════════════════════════════════════════════════════════════════════════
#  ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
def health():
    """Estado del servidor y conexión a Binance."""
    try:
        client = get_client()
        client.ping()
        btc = float(client.get_symbol_ticker(symbol="BTCUSDT")["price"])
        cfg = get_cfg()
        return {
            "status":    "ok",
            "binance":   "connected",
            "btc_price": btc,
            "config":    "scanner.config cargado ✓",
            "portfolio": cfg["portfolio"],
            "ts":        datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException as e:
        return {"status": "error", "detail": e.detail}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/config")
def show_config():
    """Configuración activa cargada desde scanner.config (útil para debug)."""
    try:
        cfg = get_cfg()
        # No exponer credenciales
        return {
            "portfolio":           cfg["portfolio"],
            "intervals_available": cfg["intervals_available"],
            "intervals_default":   cfg["intervals_default"],
            "usdt_available":      cfg["usdt"],
            "server_host":         cfg["server_host"],
            "server_port":         cfg["server_port"],
            "config_file":         str(Path("../scanner.config").resolve()),
            "ts":                  datetime.now(timezone.utc).isoformat(),
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/portfolio")
def get_portfolio():
    """Portfolio y configuración activa — el dashboard lo llama al arrancar."""
    try:
        cfg = get_cfg()
        return {
            "symbols":             cfg["portfolio"],
            "intervals_available": cfg["intervals_available"],
            "intervals":           cfg["intervals_default"],
            "usdt":                cfg["usdt"],
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scan")
def scan(
    symbols: str = Query(
        default="",
        description="Símbolos separados por coma: SOL,TAO,KAITO — vacío = portfolio de scanner.config"
    ),
    intervals: str = Query(
        default="",
        description="Intervalos separados por coma: 15m,1h,4h,1d — vacío = default de scanner.config"
    ),
    usdt: float = Query(
        default=None,
        description="USDT disponible para calcular órdenes — vacío = USDT_AVAILABLE de .env"
    ),
):
    """
    Escanea uno o varios símbolos.
    Todos los defaults vienen de scanner.config — sin hardcodeo.
    """
    cfg        = get_cfg()
    client     = get_client()
    usdt_avail = usdt or cfg["usdt"]

    # ── Símbolos ──────────────────────────────────────────────────────────────
    if symbols.strip():
        sym_list = [
            s.strip().upper() + ("" if s.strip().upper().endswith("USDT") else "USDT")
            for s in symbols.split(",") if s.strip()
        ]
    else:
        sym_list = cfg["portfolio"]  # ← viene de scanner.config

    # ── Intervalos ────────────────────────────────────────────────────────────
    if intervals.strip():
        iv_list = [
            iv.strip() for iv in intervals.split(",")
            if iv.strip() in cfg["intervals_available"]
        ]
    else:
        iv_list = cfg["intervals_default"]  # ← viene de scanner.config

    # Fallback de seguridad
    if not iv_list:
        iv_list = cfg["intervals_default"]

    # ── Scan ──────────────────────────────────────────────────────────────────
    t0 = time.time()
    try:
        if len(sym_list) == 1:
            output = get_signals_for_intervals(sym_list[0], iv_list, client)
        else:
            output = get_signals_for_portfolio(sym_list, iv_list, client, usdt_avail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    elapsed = round(time.time() - t0, 2)

    # ── Respuesta ─────────────────────────────────────────────────────────────
    if isinstance(output, list):
        return JSONResponse(content={
            "type":    "portfolio",
            "count":   len(output),
            "elapsed": elapsed,
            "ts":      datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
            "symbols": [d.get("Symbol") for d in output],
            "data":    output,
        })
    else:
        output["_elapsed"] = elapsed
        return JSONResponse(content=output)
