import pandas as pd

# ==============================
#  CALCULAR INDICADORES
#  Sin cambios en tu lógica original.
#  Añadido: BB_PCT (posición 0-1 dentro de Bollinger) y BB_MID
# ==============================
def calculate_indicators(df: pd.DataFrame) -> pd.Series:

    # ── EMAs ──────────────────────────────────────────────
    df["EMA7"]  = df["close"].ewm(span=7).mean()
    df["EMA25"] = df["close"].ewm(span=25).mean()
    df["EMA99"] = df["close"].ewm(span=99).mean()

    # ── RSI ───────────────────────────────────────────────
    delta    = df["close"].diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs       = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))

    # ── Stochastic RSI ────────────────────────────────────
    low14  = df["RSI"].rolling(14).min()
    high14 = df["RSI"].rolling(14).max()
    df["StochRSI_K"] = (df["RSI"] - low14) / (high14 - low14 + 1e-10)
    df["StochRSI_D"] = df["StochRSI_K"].rolling(3).mean()

    # ── Bollinger Bands ───────────────────────────────────
    df["BB_MID"]  = df["close"].rolling(20).mean()
    df["BB_STD"]  = df["close"].rolling(20).std()
    df["BB_UP"]   = df["BB_MID"] + 2 * df["BB_STD"]
    df["BB_DOWN"] = df["BB_MID"] - 2 * df["BB_STD"]
    # Posición del precio dentro de las bandas: 0 = fondo, 1 = techo
    bb_range     = df["BB_UP"] - df["BB_DOWN"]
    df["BB_PCT"] = ((df["close"] - df["BB_DOWN"]) / bb_range.replace(0, 1e-10)).clip(0, 1)

    # ── RVOL ──────────────────────────────────────────────
    df["RVOL"] = df["volume"] / df["volume"].rolling(20).mean()

    # ── ADX ───────────────────────────────────────────────
    df["H-L"]  = df["high"] - df["low"]
    df["H-PC"] = abs(df["high"] - df["close"].shift(1))
    df["L-PC"] = abs(df["low"]  - df["close"].shift(1))
    df["TR"]   = df[["H-L", "H-PC", "L-PC"]].max(axis=1)
    df["ATR"]  = df["TR"].rolling(14).mean()

    df["+DM"] = df["high"].diff().clip(lower=0)
    df["-DM"] = (-df["low"].diff()).clip(lower=0)
    df["+DM"] = df["+DM"].where(df["+DM"] > df["-DM"], 0)
    df["-DM"] = df["-DM"].where(df["-DM"] > df["+DM"], 0)

    atr_safe  = df["ATR"].replace(0, 1e-10)
    df["+DI"] = 100 * (df["+DM"].rolling(14).sum() / atr_safe)
    df["-DI"] = 100 * (df["-DM"].rolling(14).sum() / atr_safe)
    di_sum    = (df["+DI"] + df["-DI"]).replace(0, 1e-10)
    df["DX"]  = (abs(df["+DI"] - df["-DI"]) / di_sum) * 100
    df["ADX"] = df["DX"].rolling(14).mean()

    return df.iloc[-1]   # solo la última vela procesada
