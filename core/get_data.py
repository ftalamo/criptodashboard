import time
import pandas as pd
from datetime import datetime, timezone

from .clean import clean_numpy
from .signal import generate_signal, score_signal, compute_orders
from .indicators import calculate_indicators

# ==============================
# CONSTANTES
# ==============================
KLINES_LIMIT = 200   # velas por request


# ==============================
# DERIVADOS: Funding Rate + Open Interest
# Solo disponibles para símbolos con futuros perpetuos en Binance.
# Usa el cliente Futures (python-binance: Client con futures=True o client.futures_*)
# ==============================

def get_derivatives(client, symbol: str) -> dict:
    """
    Obtiene funding rate y open interest desde Binance Futures.
    Retorna dict con fr, fr_t, oi, oi_d (o None si el símbolo no tiene futuros).
    """
    result = {"fr": None, "fr_t": None, "oi": None, "oi_d": None}

    try:
        fr_data = client.futures_funding_rate(symbol=symbol, limit=2)
        if fr_data:
            fr = float(fr_data[-1]["fundingRate"])
            result["fr"]   = round(fr * 100, 4)          # en %
            result["fr_t"] = "long" if fr > 0 else "short"
    except Exception:
        pass

    try:
        oi_data = client.futures_open_interest(symbol=symbol)
        result["oi"] = round(float(oi_data["openInterest"]), 2)
    except Exception:
        pass

    try:
        # OI histórico (última hora) para calcular delta
        oi_hist = client.futures_open_interest_hist(
            symbol=symbol, period="1h", limit=2
        )
        if oi_hist and len(oi_hist) >= 2:
            oi_now  = float(oi_hist[-1]["sumOpenInterest"])
            oi_prev = float(oi_hist[-2]["sumOpenInterest"])
            if oi_prev > 0:
                result["oi_d"] = round((oi_now - oi_prev) / oi_prev * 100, 2)
    except Exception:
        pass

    return result


# ==============================
# UN SOLO SÍMBOLO — lógica original refactorizada
# ==============================

def get_signals_for_intervals(symbol: str, intervals: list, client) -> dict:
    """
    Mantiene compatibilidad con tu main.py original.
    Añade: funding rate, open interest, score global y órdenes sugeridas.
    """
    results = {}

    # ── Precio spot (una sola llamada, fuera del loop) ────────────────────────
    price = float(client.get_symbol_ticker(symbol=symbol)["price"])

    # ── Ticker 24h ────────────────────────────────────────────────────────────
    try:
        ticker      = client.get_ticker(symbol=symbol)
        price_24h   = round(float(ticker.get("priceChangePercent", 0)), 2)
        volume_24h  = round(float(ticker.get("quoteVolume", 0)), 2)
    except Exception:
        price_24h, volume_24h = None, None

    # ── Derivados (futuros perpetuos) ─────────────────────────────────────────
    deriv = get_derivatives(client, symbol)

    # ── Indicadores por timeframe ─────────────────────────────────────────────
    tfs_data = {}   # guarda los dicts de indicadores para el scoring global

    for interval in intervals:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=KLINES_LIMIT)

        df = pd.DataFrame(klines, columns=[
            "time", "open", "high", "low", "close", "volume",
            "close_time", "qav", "trades", "taker_base", "taker_quote", "ignore"
        ])
        df = df.astype({
            "open": float, "high": float, "low": float,
            "close": float, "volume": float
        })

        last = calculate_indicators(df)

        indicators = {
            "trend": {
                "ema_alignment": bool(last["EMA7"] > last["EMA25"] > last["EMA99"]),
                "EMA7":  round(float(last["EMA7"]),  6),
                "EMA25": round(float(last["EMA25"]), 6),
                "EMA99": round(float(last["EMA99"]), 6),
            },
            "momentum": {
                "RSI":       round(float(last["RSI"]), 4),
                "RSI_trend": "bullish" if last["RSI"] > 50 else "bearish",
                "StochRSI_K": round(float(last["StochRSI_K"]), 4),
                "StochRSI_D": round(float(last["StochRSI_D"]), 4),
            },
            "volumen": {
                "RVOL":          round(float(last["RVOL"]), 4),
                "alta_actividad": bool(last["RVOL"] > 1.2),
            },
            "volatilidad": {
                "Bollinger_up":   round(float(last["BB_UP"]),   6),
                "Bollinger_down": round(float(last["BB_DOWN"]), 6),
                "BB_MID":         round(float(last["BB_MID"]),  6),
                "BB_PCT":         round(float(last["BB_PCT"]),  4),  # nuevo
            },
            "ADX": round(float(last["ADX"]), 4),
        }

        indicators = clean_numpy(indicators)
        indicators["signal"] = generate_signal(indicators)   # señal por TF (tu lógica)

        tfs_data[interval] = indicators
        results[interval]  = indicators

        time.sleep(0.08)   # respetar rate limit

    # ── Score global multi-timeframe ──────────────────────────────────────────
    global_score = score_signal(tfs_data, price, deriv)
    orders       = compute_orders(global_score["sig"], price, tfs_data)

    # ── Metadata y resultado final ─────────────────────────────────────────────
    results["Symbol"]    = symbol
    results["Price"]     = price
    results["price_24h"] = price_24h
    results["vol_24h"]   = volume_24h
    results["ts"]        = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")

    # Derivados
    results["fr"]    = deriv["fr"]
    results["fr_t"]  = deriv["fr_t"]
    results["oi"]    = deriv["oi"]
    results["oi_d"]  = deriv["oi_d"]

    # Señal consolidada
    results["signal_global"] = global_score["sig"]
    results["bull"]          = global_score["bull"]
    results["bear"]          = global_score["bear"]
    results["bull_pct"]      = global_score["b_pct"]
    results["signal_notes"]  = global_score["notes"]

    # Órdenes sugeridas
    results["orders"] = orders

    return results


# ==============================
# PORTFOLIO DE X SÍMBOLOS
# ==============================

def get_signals_for_portfolio(symbols: list, intervals: list, client,
                               usdt_available: float = 127.55) -> list:
    """
    Analiza un portfolio de múltiples criptos.
    Retorna lista de dicts, uno por símbolo, listos para el dashboard.

    symbols         → ["SOLUSDT", "TAOUSDT", "KAITOUSDT"]
    intervals       → ["15m", "1h", "4h", "1d"]
    usdt_available  → capital disponible para calcular órdenes
    """
    results = []

    for symbol in symbols:
        print(f"  → {symbol}...", end=" ", flush=True)
        try:
            data = get_signals_for_intervals(symbol, intervals, client)
            # Recalcular órdenes con USDT disponible real
            tfs_only = {k: v for k, v in data.items() if k in intervals}
            orders   = compute_orders(data["signal_global"], data["Price"],
                                      tfs_only, usdt_available)
            data["orders"] = orders
            results.append(data)
            print(f"{data['signal_global']} | RSI_1d="
                  f"{data.get('1d', {}).get('momentum', {}).get('RSI', '?'):.1f}")
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({"Symbol": symbol, "error": str(e)})

        time.sleep(0.2)

    return results
