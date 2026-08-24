"""Descarga y normalizacion de datos OHLCV.

Fuente por defecto: Yahoo Finance (yfinance), sin API key.
Cubre acciones y ETF de USA (IBIT, AAPL...), CEDEAR y acciones locales con
sufijo .BA (GGAL.BA, YPFD.BA...) y cripto spot (BTC-USD, ETH-USD...).

Tambien puede leer CSV exportados del broker: ver cargar_csv().
Los datos quedan cacheados en cache/ para no re-descargar en cada corrida.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
CACHE = RAIZ / "cache"

COLUMNAS = ["Open", "High", "Low", "Close", "Volume"]

# Cuanto historial pedir para cada temporalidad. Yahoo limita el intradiario:
# 1m solo 7 dias, el resto de intradiario hasta 60 dias.
# Cuidado al tocar estos valores: Yahoo devuelve una respuesta VACIA (no un
# error) cuando el periodo excede lo permitido para el intervalo. Por eso van
# los periodos con nombre, que son los que la API acepta sin ambiguedad:
# 60m con "2y" trae 2 anios de velas horarias, pero con "719d" no trae nada.
HISTORIAL = {
    "1m": "7d", "2m": "60d", "5m": "60d", "15m": "60d", "30m": "60d",
    "60m": "2y", "1h": "2y", "1d": "5y", "1wk": "10y", "1mo": "max",
}

# Cuantos minutos vale el cache segun temporalidad.
VIDA_CACHE = {"1m": 2, "5m": 5, "15m": 10, "30m": 15, "60m": 30, "1h": 30,
              "1d": 60, "1wk": 240, "1mo": 720}

# Velas por año, para anualizar volatilidad y metricas.
VELAS_ANIO = {"1m": 98280, "5m": 19656, "15m": 6552, "30m": 3276,
              "60m": 1638, "1h": 1638, "1d": 252, "1wk": 52, "1mo": 12}


class ErrorDatos(Exception):
    """No se pudieron obtener datos utilizables para un ticker."""


def _ruta_cache(ticker: str, intervalo: str) -> Path:
    limpio = ticker.replace("/", "_").replace("\\", "_").replace("=", "_")
    return CACHE / f"{limpio}__{intervalo}.parquet"


def _normalizar(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Deja el DataFrame con columnas OHLCV limpias, indice temporal y sin huecos."""
    if df is None or df.empty:
        raise ErrorDatos(f"{ticker}: la fuente no devolvio datos")

    # yfinance devuelve MultiIndex cuando se piden varios tickers.
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(1, axis=1)

    df = df.rename(columns={c: str(c).strip().title() for c in df.columns})
    faltan = [c for c in COLUMNAS if c not in df.columns]
    if faltan:
        raise ErrorDatos(f"{ticker}: faltan columnas {faltan}")

    df = df[COLUMNAS].copy()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df["Volume"] = df["Volume"].fillna(0.0)

    # Velas invalidas (High < Low, precios <= 0) contaminan todos los indicadores.
    df = df[(df["High"] >= df["Low"]) & (df["Close"] > 0)]
    if df.empty:
        raise ErrorDatos(f"{ticker}: no quedaron velas validas tras la limpieza")
    return df


# Yahoo no sirve velas de 2h ni de 4h: se arman agrupando las de 1h.
DERIVADOS = {"2h": ("60m", "2h"), "3h": ("60m", "3h"), "4h": ("60m", "4h")}


def _agrupar(df: pd.DataFrame, regla: str) -> pd.DataFrame:
    """Reconstruye velas mas largas a partir de las horarias.

    Se agrupa con las velas alineadas al comienzo de cada bloque y se descartan
    los intervalos vacios, que en acciones son casi todos: fuera del horario de
    rueda no hay operaciones y una vela sin datos deformaria los indicadores.
    """
    agrupado = df.resample(regla, label="left", closed="left").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum",
    })
    return agrupado.dropna(subset=["Open", "High", "Low", "Close"])


def descargar(ticker: str, intervalo: str = "1d", periodo: str | None = None,
              usar_cache: bool = True) -> pd.DataFrame:
    """Devuelve OHLCV de un ticker. Usa cache si esta fresco."""
    import yfinance as yf

    intervalo = intervalo.lower()
    if intervalo in DERIVADOS:
        base, regla = DERIVADOS[intervalo]
        horarias = descargar(ticker, base, periodo, usar_cache)
        derivado = _agrupar(horarias, regla)
        if derivado.empty:
            raise ErrorDatos(f"{ticker}: no se pudieron armar velas de {intervalo}")
        return derivado

    periodo = periodo or HISTORIAL.get(intervalo, "2y")
    ruta = _ruta_cache(ticker, intervalo)

    if usar_cache and ruta.exists():
        edad_min = (time.time() - ruta.stat().st_mtime) / 60
        if edad_min < VIDA_CACHE.get(intervalo, 60):
            try:
                return _normalizar(pd.read_parquet(ruta), ticker)
            except Exception:
                pass  # cache corrupto: se re-descarga

    try:
        crudo = yf.Ticker(ticker).history(period=periodo, interval=intervalo,
                                          auto_adjust=False)
    except Exception as e:
        # Si la descarga falla pero hay cache viejo, es mejor eso que nada.
        if ruta.exists():
            return _normalizar(pd.read_parquet(ruta), ticker)
        raise ErrorDatos(f"{ticker}: fallo la descarga ({e})") from e

    df = _normalizar(crudo, ticker)
    try:
        CACHE.mkdir(exist_ok=True)
        df.to_parquet(ruta)
    except Exception:
        pass  # sin cache tambien funciona
    return df


def cargar_csv(ruta: str | Path, ticker: str = "CSV") -> pd.DataFrame:
    """Lee un CSV exportado del broker o de TradingView.

    Detecta la columna de fecha entre los nombres habituales y acepta tanto
    encabezados en ingles como en espanol.
    """
    df = pd.read_csv(ruta)
    equivalencias = {
        "fecha": "Date", "date": "Date", "time": "Date", "datetime": "Date",
        "apertura": "Open", "open": "Open", "maximo": "High", "high": "High",
        "minimo": "Low", "low": "Low", "cierre": "Close", "close": "Close",
        "ultimo": "Close", "adj close": "Close",
        "volumen": "Volume", "volume": "Volume", "vol.": "Volume",
    }
    df = df.rename(columns={c: equivalencias.get(str(c).strip().lower(), c)
                            for c in df.columns})
    if "Date" not in df.columns:
        raise ErrorDatos(f"{ruta}: no encontre columna de fecha")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", format="mixed")
    df = df.dropna(subset=["Date"]).set_index("Date")

    # Los exports en formato local traen "1.234,56" y volumen tipo "12,5M".
    for col in COLUMNAS:
        if col in df.columns and df[col].dtype == object:
            df[col] = _a_numero(df[col])
    return _normalizar(df, ticker)


def _a_numero(serie: pd.Series) -> pd.Series:
    s = (serie.astype(str)
         .str.replace(r"[^\d,.\-KMB]", "", regex=True)
         .str.replace(".", "", regex=False)
         .str.replace(",", ".", regex=False))
    mult = pd.Series(1.0, index=s.index)
    mult = mult.mask(s.str.endswith("K"), 1e3)
    mult = mult.mask(s.str.endswith("M"), 1e6)
    mult = mult.mask(s.str.endswith("B"), 1e9)
    return pd.to_numeric(s.str.rstrip("KMB"), errors="coerce") * mult


def obtener(ticker: str, intervalo: str = "1d", csv: str | None = None,
            usar_cache: bool = True) -> pd.DataFrame:
    """Punto de entrada unico: CSV si se indica, si no descarga."""
    if csv:
        return cargar_csv(csv, ticker)
    return descargar(ticker, intervalo, usar_cache=usar_cache)


def velas_por_anio(intervalo: str) -> int:
    return VELAS_ANIO.get(intervalo.lower(), 252)
