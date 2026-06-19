# Crypto Trading Scanner

Sistema de análisis técnico para Binance: escanea indicadores multi-timeframe (RSI, ADX, EMA, Bollinger, StochRSI), funding rate y open interest, genera una señal de trading consolidada con entrada/stop/take-profit, y lo muestra en un dashboard web conectado en vivo.

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐      ┌──────────────┐
│   Binance   │ ───▶ │  core/*.py   │ ───▶ │  core/api.py │ ───▶ │ dashboard.html│
│  (klines,   │      │  indicadores │      │  FastAPI     │      │  (browser)   │
│  funding,   │      │  + señal     │      │  servidor    │      │              │
│  OI)        │      │              │      │  local       │      │              │
└─────────────┘      └──────────────┘      └──────────────┘      └──────────────┘
```

---

## Estructura del proyecto

```
scanner/
├── .env                  ← tus credenciales (crear desde .env.example)
├── .env.example           plantilla de credenciales
├── .gitignore              protege .env de subirse a git
├── scanner.config         portfolio, intervalos y puerto del servidor
├── run.py                 arranca el servidor y abre el dashboard
├── main.py                 modo terminal: ejecuta un scan sin servidor
├── dashboard.html          interfaz web conectada en vivo
└── core/
    ├── __init__.py
    ├── api.py             servidor FastAPI — expone /scan, /health, /portfolio, /config
    ├── get_data.py        trae klines de Binance, arma el JSON de indicadores
    ├── indicators.py      cálculo de RSI, ADX, EMA, Bollinger, StochRSI, RVOL
    ├── signal.py          señal por timeframe + scoring global + órdenes sugeridas
    └── clean.py           limpieza de tipos numpy → tipos nativos de Python
```

---

## Instalación

Requiere Python 3.10+.

```bash
cd scanner
pip install fastapi uvicorn python-binance pandas numpy
```

---

## Configuración

### 1. Credenciales — `.env`

```bash
cp .env.example .env
```

Edita `.env` con tus claves de Binance ([crear aquí](https://www.binance.com/es/my/settings/api-management) — usa permisos **solo lectura**, sin trading ni retiros):

```env
BINANCE_API_KEY=tu_api_key_aqui
BINANCE_API_SECRET=tu_api_secret_aqui
USDT_AVAILABLE=127.55
```

### 2. Portfolio e intervalos — `scanner.config`

```ini
PORTFOLIO = SOL, TAO, KAITO, PEPE, DOGE, SHIB
INTERVALS_AVAILABLE = 3m, 5m, 15m, 1h, 4h, 12h, 1d
INTERVALS_DEFAULT = 15m, 1h, 4h, 12h, 1d
SERVER_HOST = 127.0.0.1
SERVER_PORT = 8000
```

Este archivo se recarga automáticamente en cada scan — no hace falta reiniciar el servidor para que tome cambios.

---

## Uso

### Opción A — Dashboard web (recomendado)

```bash
python run.py
```

Esto arranca el servidor en `http://localhost:8000` y abre `dashboard.html` automáticamente en el navegador.

Desde el dashboard puedes:
- Seleccionar/deseleccionar símbolos del portfolio con un click
- Añadir cualquier cripto custom
- Elegir qué timeframes incluir
- Ajustar el USDT disponible para el cálculo de órdenes
- Activar auto-refresh (cada 1/5/10/30 min)
- Descargar el JSON del scan con un botón

### Opción B — Terminal, sin servidor

```bash
python main.py                  # portfolio completo de scanner.config
python main.py SOL               # un solo símbolo
python main.py SOL TAO KAITO     # varios símbolos
python main.py SOL --compact     # JSON compacto, una sola línea
python main.py SOL --intervals 1h 4h 1d
```

El resultado se guarda automáticamente en `output/`.

---

## API — endpoints

Con el servidor corriendo (`python run.py`), documentación interactiva en `http://localhost:8000/docs`.

| Endpoint | Descripción |
|---|---|
| `GET /health` | Estado del servidor, conexión a Binance, precio BTC actual |
| `GET /config` | Configuración activa leída desde `scanner.config` |
| `GET /portfolio` | Portfolio y settings por defecto — el dashboard lo usa al arrancar |
| `GET /scan?symbols=SOL,TAO&intervals=1h,4h,1d&usdt=150` | Ejecuta el scan y devuelve el JSON completo |

---

## Qué calcula el sistema

**Por cada timeframe** (`core/indicators.py`):
- RSI (14), Stochastic RSI (K/D)
- EMA 7 / 25 / 99 y su alineación
- Bandas de Bollinger (20, 2σ) + posición del precio dentro de ellas (`BB_PCT`)
- ADX (14) — fuerza de tendencia
- RVOL — volumen relativo vs promedio de 20 períodos

**A nivel de mercado** (`core/get_data.py`):
- Funding rate (futuros perpetuos)
- Open Interest actual y su variación en la última hora

**Señal consolidada** (`core/signal.py`):
- `generate_signal()` — señal rápida por timeframe individual (BUY / WAIT / NO_TRADE)
- `score_signal()` — motor de puntuación bull/bear que combina todos los timeframes, RSI, ADX, EMAs, Bollinger, RVOL, funding rate y OI en una señal global
- `compute_orders()` — calcula entrada, stop-loss, TP1, TP2, ratio riesgo/beneficio y cuánto USDT deployar

---

## Notas

- El servidor corre **local** (`127.0.0.1`) — tus credenciales nunca salen de tu máquina.
- `.env` está excluido por `.gitignore`; nunca lo subas a un repositorio.
- Funding rate y Open Interest solo existen para símbolos con futuros perpetuos en Binance. Si un símbolo no los tiene, esos campos quedan en `null` sin romper el resto del análisis.
- Este sistema entrega **información y señales técnicas**, no ejecuta órdenes reales. Las decisiones de trading siempre las tomas tú.