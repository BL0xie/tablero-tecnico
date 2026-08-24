"""Calculo de indicadores tecnicos sobre OHLCV.

Todo en pandas/numpy puro: sin TA-Lib ni compiladores.
Cada funcion recibe Series/DataFrame y devuelve Series/DataFrame alineado al indice.
El suavizado de Wilder (RSI, ATR, ADX) usa ewm(alpha=1/n, adjust=False), que es
la definicion original y coincide con lo que muestran TradingView e Investing.com.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------
# Medias moviles
# --------------------------------------------------------------------------
def sma(serie: pd.Series, n: int) -> pd.Series:
    return serie.rolling(n, min_periods=n).mean()


def ema(serie: pd.Series, n: int) -> pd.Series:
    return serie.ewm(span=n, adjust=False, min_periods=n).mean()


def wma(serie: pd.Series, n: int) -> pd.Series:
    pesos = np.arange(1, n + 1, dtype=float)
    return serie.rolling(n, min_periods=n).apply(
        lambda x: np.dot(x, pesos) / pesos.sum(), raw=True
    )


def hma(serie: pd.Series, n: int) -> pd.Series:
    """Hull Moving Average: rapida y con poco retraso."""
    mitad = max(int(n / 2), 1)
    raiz = max(int(np.sqrt(n)), 1)
    return wma(2 * wma(serie, mitad) - wma(serie, n), raiz)


def vwma(df: pd.DataFrame, n: int) -> pd.Series:
    """Media ponderada por volumen."""
    pv = (df["Close"] * df["Volume"]).rolling(n, min_periods=n).sum()
    v = df["Volume"].rolling(n, min_periods=n).sum()
    return pv / v.replace(0, np.nan)


def _wilder(serie: pd.Series, n: int) -> pd.Series:
    return serie.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


# --------------------------------------------------------------------------
# Momentum / osciladores
# --------------------------------------------------------------------------
def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    ganancia = delta.clip(lower=0)
    perdida = -delta.clip(upper=0)
    avg_g = _wilder(ganancia, n)
    avg_p = _wilder(perdida, n)
    rs = avg_g / avg_p.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    # Sin perdidas en la ventana el RSI vale 100 por definicion.
    return out.where(avg_p != 0, 100.0)


def macd(close: pd.Series, rapida: int = 12, lenta: int = 26, senal: int = 9) -> pd.DataFrame:
    linea = ema(close, rapida) - ema(close, lenta)
    sig = linea.ewm(span=senal, adjust=False, min_periods=senal).mean()
    return pd.DataFrame({"macd": linea, "signal": sig, "hist": linea - sig})


def estocastico(df: pd.DataFrame, n: int = 14, suave_k: int = 3, suave_d: int = 3) -> pd.DataFrame:
    bajo = df["Low"].rolling(n, min_periods=n).min()
    alto = df["High"].rolling(n, min_periods=n).max()
    rango = (alto - bajo).replace(0, np.nan)
    k_crudo = 100 * (df["Close"] - bajo) / rango
    k = k_crudo.rolling(suave_k, min_periods=suave_k).mean()
    d = k.rolling(suave_d, min_periods=suave_d).mean()
    return pd.DataFrame({"k": k, "d": d})


def stoch_rsi(close: pd.Series, n_rsi: int = 14, n_stoch: int = 14,
              suave_k: int = 3, suave_d: int = 3) -> pd.DataFrame:
    r = rsi(close, n_rsi)
    bajo = r.rolling(n_stoch, min_periods=n_stoch).min()
    alto = r.rolling(n_stoch, min_periods=n_stoch).max()
    rango = (alto - bajo).replace(0, np.nan)
    k = (100 * (r - bajo) / rango).rolling(suave_k, min_periods=suave_k).mean()
    d = k.rolling(suave_d, min_periods=suave_d).mean()
    return pd.DataFrame({"k": k, "d": d})


def cci(df: pd.DataFrame, n: int = 20) -> pd.Series:
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    media = tp.rolling(n, min_periods=n).mean()
    desv = tp.rolling(n, min_periods=n).apply(
        lambda x: np.abs(x - x.mean()).mean(), raw=True
    )
    return (tp - media) / (0.015 * desv.replace(0, np.nan))


def williams_r(df: pd.DataFrame, n: int = 14) -> pd.Series:
    alto = df["High"].rolling(n, min_periods=n).max()
    bajo = df["Low"].rolling(n, min_periods=n).min()
    rango = (alto - bajo).replace(0, np.nan)
    return -100 * (alto - df["Close"]) / rango


def momentum(close: pd.Series, n: int = 10) -> pd.Series:
    return close.diff(n)


def roc(close: pd.Series, n: int = 12) -> pd.Series:
    return 100 * close.pct_change(n)


def awesome_oscillator(df: pd.DataFrame, rapida: int = 5, lenta: int = 34) -> pd.Series:
    mediana = (df["High"] + df["Low"]) / 2
    return sma(mediana, rapida) - sma(mediana, lenta)


def ultimate_oscillator(df: pd.DataFrame, c: int = 7, m: int = 14, l: int = 28) -> pd.Series:
    prev = df["Close"].shift(1)
    minimo = pd.concat([df["Low"], prev], axis=1).min(axis=1)
    maximo = pd.concat([df["High"], prev], axis=1).max(axis=1)
    bp = df["Close"] - minimo
    tr = (maximo - minimo).replace(0, np.nan)
    a = bp.rolling(c, min_periods=c).sum() / tr.rolling(c, min_periods=c).sum()
    b = bp.rolling(m, min_periods=m).sum() / tr.rolling(m, min_periods=m).sum()
    d = bp.rolling(l, min_periods=l).sum() / tr.rolling(l, min_periods=l).sum()
    return 100 * (4 * a + 2 * b + d) / 7


def bull_bear_power(df: pd.DataFrame, n: int = 13) -> pd.Series:
    e = ema(df["Close"], n)
    return (df["High"] - e) + (df["Low"] - e)


# --------------------------------------------------------------------------
# Tendencia / volatilidad
# --------------------------------------------------------------------------
def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["Close"].shift(1)
    return pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev).abs(),
        (df["Low"] - prev).abs(),
    ], axis=1).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return _wilder(true_range(df), n)


def adx(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    up = df["High"].diff()
    down = -df["Low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    tr_s = _wilder(true_range(df), n).replace(0, np.nan)
    plus_di = 100 * _wilder(plus_dm, n) / tr_s
    minus_di = 100 * _wilder(minus_dm, n) / tr_s
    suma = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / suma
    return pd.DataFrame({"adx": _wilder(dx, n), "di_mas": plus_di, "di_menos": minus_di})


def bollinger(close: pd.Series, n: int = 20, desv: float = 2.0) -> pd.DataFrame:
    media = sma(close, n)
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    sup = media + desv * sd
    inf = media - desv * sd
    ancho = (sup - inf) / media.replace(0, np.nan)
    # %B: 0 = banda inferior, 1 = banda superior
    pct_b = (close - inf) / (sup - inf).replace(0, np.nan)
    return pd.DataFrame({"media": media, "sup": sup, "inf": inf,
                         "ancho": ancho, "pct_b": pct_b})


def ichimoku(df: pd.DataFrame, conv: int = 9, base: int = 26, span_b: int = 52) -> pd.DataFrame:
    def linea(n):
        return (df["High"].rolling(n, min_periods=n).max() +
                df["Low"].rolling(n, min_periods=n).min()) / 2
    tenkan = linea(conv)
    kijun = linea(base)
    return pd.DataFrame({
        "tenkan": tenkan,
        "kijun": kijun,
        "span_a": ((tenkan + kijun) / 2).shift(base),
        "span_b": linea(span_b).shift(base),
    })


def psar(df: pd.DataFrame, af_paso: float = 0.02, af_max: float = 0.2) -> pd.Series:
    """Parabolic SAR: sirve como stop dinamico de seguimiento."""
    alto, bajo = df["High"].to_numpy(), df["Low"].to_numpy()
    n = len(df)
    out = np.full(n, np.nan)
    if n < 3:
        return pd.Series(out, index=df.index)
    alcista = True
    sar = bajo[0]
    ep = alto[0]
    af = af_paso
    for i in range(1, n):
        sar = sar + af * (ep - sar)
        if alcista:
            sar = min(sar, bajo[i - 1], bajo[max(i - 2, 0)])
            if bajo[i] < sar:
                alcista, sar, ep, af = False, ep, bajo[i], af_paso
            elif alto[i] > ep:
                ep, af = alto[i], min(af + af_paso, af_max)
        else:
            sar = max(sar, alto[i - 1], alto[max(i - 2, 0)])
            if alto[i] > sar:
                alcista, sar, ep, af = True, ep, alto[i], af_paso
            elif bajo[i] < ep:
                ep, af = bajo[i], min(af + af_paso, af_max)
        out[i] = sar
    return pd.Series(out, index=df.index)


# --------------------------------------------------------------------------
# Volumen
# --------------------------------------------------------------------------
def obv(df: pd.DataFrame) -> pd.Series:
    signo = np.sign(df["Close"].diff().fillna(0.0))
    return (signo * df["Volume"]).cumsum()


def volumen_relativo(df: pd.DataFrame, n: int = 20) -> pd.Series:
    """Volumen actual / volumen medio. Por encima de 1.5 el movimiento viene confirmado."""
    media = df["Volume"].rolling(n, min_periods=n).mean()
    return df["Volume"] / media.replace(0, np.nan)


def mfi(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Money Flow Index: el RSI ponderado por volumen."""
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    flujo = tp * df["Volume"]
    dif = tp.diff()
    pos = flujo.where(dif > 0, 0.0).rolling(n, min_periods=n).sum()
    neg = flujo.where(dif < 0, 0.0).rolling(n, min_periods=n).sum()
    return 100 - (100 / (1 + pos / neg.replace(0, np.nan)))


def vwap_sesion(df: pd.DataFrame) -> pd.Series:
    """VWAP acumulado por dia. Solo tiene sentido en intradiario."""
    if not isinstance(df.index, pd.DatetimeIndex):
        return pd.Series(np.nan, index=df.index)
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    dias = df.index.normalize()
    pv = (tp * df["Volume"]).groupby(dias).cumsum()
    vv = df["Volume"].groupby(dias).cumsum().replace(0, np.nan)
    return pv / vv
