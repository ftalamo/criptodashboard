# ==============================
# GENERAR SEÑAL FINAL
# ==============================

# ── Umbrales (ajustables) ─────────────────────────────────────────────────────
RSI_OVERSOLD   = 32
RSI_OVERBOUGHT = 68
ADX_STRONG     = 40
ADX_EXTREME    = 65
RVOL_ACTIVE    = 1.2
RVOL_DEAD      = 0.5


def generate_signal(data: dict) -> str:
    """
    Señal por timeframe — mantiene tu lógica original como primera capa,
    extendida con sobreventa/sobrecompra extrema.

    Retorna: "BUY" | "WAIT" | "NO_TRADE"
    """
    trend    = data["trend"]
    momentum = data["momentum"]
    volumen  = data["volumen"]
    adx      = data["ADX"]
    rsi      = momentum["RSI"]
    sk       = momentum["StochRSI_K"]
    rvol     = volumen["RVOL"]

    # ── Tu lógica original (intacta) ──────────────────────────────────────────
    if (trend["ema_alignment"]
            and rsi > 55
            and sk < 0.40
            and rvol > RVOL_ACTIVE
            and adx > 25):
        return "BUY"

    if sk > 0.80 or rvol < 0.8:
        return "NO_TRADE"

    # ── Extensiones nuevas ────────────────────────────────────────────────────
    # Tendencia bajista extrema — no operar en ningún caso
    if adx > ADX_EXTREME and rsi < 50:
        return "NO_TRADE"

    # Sobreventa con volumen — potencial entrada
    if rsi < RSI_OVERSOLD and rvol > 0.8:
        return "WAIT"

    return "WAIT"


def score_signal(tfs: dict, price: float, deriv: dict) -> dict:
    """
    Motor de scoring multi-timeframe.
    Recibe todos los timeframes procesados, el precio actual y datos de derivados.
    Retorna señal consolidada, puntuación bull/bear y notas explicativas.

    tfs    → { "1h": {...indicators...}, "4h": {...}, ... }
    price  → float precio spot
    deriv  → { "fr": float|None, "fr_t": str|None,
               "oi": float|None, "oi_d": float|None }
    """
    bull, bear = 0, 0
    notes = []

    tf_values = list(tfs.values())

    # ── RSI ───────────────────────────────────────────────────────────────────
    oversold   = sum(1 for t in tf_values if t["momentum"]["RSI"] < RSI_OVERSOLD)
    overbought = sum(1 for t in tf_values if t["momentum"]["RSI"] > RSI_OVERBOUGHT)

    if oversold >= 3:
        bull += 3; notes.append(f"RSI oversold x{oversold}tf")
    elif oversold >= 1:
        bull += 1; notes.append(f"RSI oversold x{oversold}tf")

    if overbought >= 2:
        bear += 3; notes.append(f"RSI overbought x{overbought}tf")

    # RSI trend en timeframes cortos (1h + 15m)
    short_bull = sum(
        1 for k in ["1h", "15m"]
        if tfs.get(k, {}).get("momentum", {}).get("RSI_trend") == "bullish"
    )
    if short_bull == 2:
        bull += 2; notes.append("RSI_trend bullish 1h+15m")

    # ── ADX diario ────────────────────────────────────────────────────────────
    adx_d = tfs.get("1d", {}).get("ADX", 0)

    if adx_d > ADX_EXTREME:
        bear += 3; notes.append(f"ADX_1d extremo ({adx_d:.1f})")
    elif adx_d > ADX_STRONG:
        bear += 1; notes.append(f"ADX_1d fuerte ({adx_d:.1f})")
    else:
        bull += 1; notes.append(f"ADX_1d débil ({adx_d:.1f})")

    # ── EMA alignment ─────────────────────────────────────────────────────────
    ema_bull = sum(1 for t in tf_values if t["trend"]["ema_alignment"] is True)
    ema_bear = sum(1 for t in tf_values if t["trend"]["ema_alignment"] is False)

    if ema_bull >= 3:
        bull += 3; notes.append(f"EMA bull x{ema_bull}tf")
    elif ema_bear >= len(tf_values) - 1:
        bear += 2; notes.append(f"EMA bear x{ema_bear}tf")

    # ── Precio vs EMAs diario ─────────────────────────────────────────────────
    d1_trend = tfs.get("1d", {}).get("trend", {})
    e7, e25, e99 = d1_trend.get("EMA7", price), d1_trend.get("EMA25", price), d1_trend.get("EMA99", price)

    if price < e7 and price < e25 and price < e99:
        bear += 2; notes.append("Px < EMA7/25/99 diario")
    elif price > e7 and price > e25 and price > e99:
        bull += 2; notes.append("Px > EMA7/25/99 diario")

    # ── Bollinger posición (diario) ───────────────────────────────────────────
    bb_pct = tfs.get("1d", {}).get("volatilidad", {}).get("BB_PCT", 0.5)

    if bb_pct < 0.15:
        bull += 2; notes.append(f"BB_pct {bb_pct:.2f} (cerca de banda baja)")
    elif bb_pct > 0.85:
        bear += 2; notes.append(f"BB_pct {bb_pct:.2f} (cerca de banda alta)")

    # ── RVOL (1h) ─────────────────────────────────────────────────────────────
    rvol_1h = tfs.get("1h", {}).get("volumen", {}).get("RVOL", 0)

    if rvol_1h > RVOL_ACTIVE:
        bull += 2; notes.append(f"RVOL_1h {rvol_1h:.2f} activo")
    elif rvol_1h < RVOL_DEAD:
        bear += 1; notes.append(f"RVOL_1h {rvol_1h:.2f} muerto")

    # ── Funding rate ──────────────────────────────────────────────────────────
    fr = deriv.get("fr")
    if fr is not None:
        if fr < -0.03:
            bull += 2; notes.append(f"FR {fr:.4f}% negativo (shorts pagan)")
        elif fr > 0.05:
            bear += 1; notes.append(f"FR {fr:.4f}% alto (longs pagan, riesgo)")

    # ── Open Interest delta ───────────────────────────────────────────────────
    oi_d = deriv.get("oi_d")
    if oi_d is not None:
        if oi_d > 3:
            bull += 1; notes.append(f"OI +{oi_d:.1f}% (posiciones abiertas)")
        elif oi_d < -3:
            bear += 1; notes.append(f"OI {oi_d:.1f}% (posiciones cerrando)")

    # ── Señal consolidada ─────────────────────────────────────────────────────
    total    = bull + bear
    bull_pct = round(bull / total * 100) if total > 0 else 50
    has_vol  = rvol_1h > RVOL_DEAD
    adx_ext  = adx_d > ADX_EXTREME

    if adx_ext and bear > bull:
        signal = "NO_TRADE"
    elif bull_pct >= 65 and oversold >= 1 and has_vol:
        signal = "BUY"
    elif bull_pct >= 52 and oversold >= 1:
        signal = "WAIT"
    elif bear > bull * 1.5:
        signal = "NO_TRADE"
    else:
        signal = "NEUTRAL"

    return {
        "sig":   signal,
        "bull":  bull,
        "bear":  bear,
        "b_pct": bull_pct,
        "notes": notes,
    }


def compute_orders(signal: str, price: float, tfs: dict, usdt_available: float = 127.55) -> dict:
    """
    Calcula entrada, stop-loss, TP1 y TP2 basados en Bollinger diario y EMAs.
    Retorna dict vacío si la señal es NO_TRADE.
    """
    if signal == "NO_TRADE":
        return {}

    d1 = tfs.get("1d", {})
    vol = d1.get("volatilidad", {})
    trend = d1.get("trend", {})

    bb_down = vol.get("BB_DOWN", price * 0.90)
    bb_up   = vol.get("Bollinger_up", price * 1.30)  # clave original del get_data
    ema7    = trend.get("EMA7",  price)
    ema25   = trend.get("EMA25", price * 1.10)

    if signal == "BUY":
        entry  = round(price, 6)
        stop   = round(max(bb_down * 0.96, price * 0.88), 6)
        tp1    = round(price + (price - stop) * 2.0, 6)
        tp2    = round(price + (price - stop) * 3.5, 6)
        deploy = round(min(usdt_available * 0.45, 60), 2)
    else:   # WAIT / NEUTRAL
        entry  = round(min(price * 0.97, (bb_down + price) / 2), 6)
        stop   = round(bb_down * 0.96, 6)
        tp1    = round(ema7  * 1.04, 6)
        tp2    = round(ema25, 6)
        deploy = round(min(usdt_available * 0.35, 45), 2)

    risk_pct = round((entry - stop) / entry * 100, 2) if entry > 0 else 0
    rr       = round((tp1 - entry) / (entry - stop), 2) if (entry - stop) > 0 else 0

    return {
        "entry":   entry,
        "stop":    stop,
        "tp1":     tp1,
        "tp2":     tp2,
        "usdt":    deploy,
        "risk_pct": risk_pct,
        "rr":      rr,
    }
