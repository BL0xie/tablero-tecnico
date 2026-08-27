"""Criterio de Investing.com, para contrastar contra el nuestro.

El resumen tecnico de Investing.com y el de TradingView NO son la misma cosa,
aunque se parezcan en la pantalla. Nuestro motor principal (rating.py) replica
el de TradingView. Este modulo replica el de Investing.com, para poder mirar
los dos y ver donde coinciden.

Diferencias verificadas contra investing.com (AAPL diario, 27/08/2026):

  INDICADORES        Investing usa STOCH(9,6), CCI(14), ATR(14), Highs/Lows(14)
                     y ROC. TradingView usa STOCH(14,3,3), CCI(20), Awesome
                     Oscillator y Momentum(10). Solo comparten siete.

  MEDIAS             Investing: 5, 10, 20, 50, 100 y 200, simple y exponencial
                     (12 filas). TradingView: 10, 20, 30, 50, 100 y 200 mas
                     Ichimoku, VWMA y Hull (15 filas).

  REGLA DEL RSI      Investing vota COMPRA con el RSI por encima de 50.
                     TradingView solo vota COMPRA si viene de sobreventa y esta
                     girando al alza; el resto del tiempo vota NEUTRAL. Esta
                     sola diferencia ya separa los dos veredictos casi siempre.

  SOBRECOMPRA        En Investing, un indicador en sobrecompra o sobreventa
                     queda FUERA del conteo: no vota ni a favor ni en contra.
                     En AAPL se vieron 9 compras, 0 ventas y 0 neutrales sobre
                     12 filas, porque tres estaban en sobrecompra o marcando
                     volatilidad. TradingView los cuenta como neutrales.

  ATR                No vota: informa "mas volatilidad" o "menos volatilidad".
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import calculo as ind

COMPRA, VENTA, NEUTRAL = "COMPRA", "VENTA", "NEUTRAL"
SOBRECOMPRA, SOBREVENTA = "SOBRECOMPRA", "SOBREVENTA"
VOLATIL, TRANQUILO = "MÁS VOLÁTIL", "MENOS VOLÁTIL"

# Solo estas tres cuentan para el resumen. Las etiquetas de sobrecompra,
# sobreventa y volatilidad se muestran pero quedan fuera del conteo, igual
# que en Investing.
_VOTO = {COMPRA: 1, NEUTRAL: 0, VENTA: -1}


@dataclass
class Fila:
    """Una fila de la tabla, tal como la muestra Investing."""
    nombre: str
    valor: float
    senal: str

    @property
    def vota(self) -> bool:
        return self.senal in _VOTO


def _ult(serie: pd.Series) -> float:
    s = serie.dropna()
    return float(s.iloc[-1]) if len(s) else np.nan


def _sobre_medio(valor: float, alto: float, bajo: float,
                 medio: float = 50.0) -> str:
    """Regla de Investing para los osciladores acotados de 0 a 100.

    Fuera de las bandas el indicador queda en sobrecompra o sobreventa y no
    vota. Dentro, decide por el punto medio: por encima compra, por debajo
    vende. Esto es lo que hace que Investing marque compra mucho mas seguido
    que TradingView.
    """
    if not np.isfinite(valor):
        return NEUTRAL
    if valor >= alto:
        return SOBRECOMPRA
    if valor <= bajo:
        return SOBREVENTA
    if valor > medio:
        return COMPRA
    if valor < medio:
        return VENTA
    return NEUTRAL


def highs_lows(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Distancia del cierre al centro del rango de las ultimas n velas.

    Investing no publica la formula de su "Highs/Lows(14)". Esta version
    reproduce el orden de magnitud y el signo de los valores observados
    (AAPL a 314.89 daba 2.0133), pero es una aproximacion: tomarla como tal
    si alguna vez el numero no coincide al decimal.
    """
    alto = df["High"].rolling(n, min_periods=n).max()
    bajo = df["Low"].rolling(n, min_periods=n).min()
    return df["Close"] - (alto + bajo) / 2


def osciladores(df: pd.DataFrame) -> list[Fila]:
    """Las doce filas de "Technical Indicators", con los periodos de Investing."""
    close = df["Close"]
    out: list[Fila] = []

    # RSI(14): por encima de 50 compra. Es la diferencia mas grande con el
    # criterio de TradingView, que aca votaria neutral.
    r = _ult(ind.rsi(close, 14))
    out.append(Fila("RSI(14)", r, _sobre_medio(r, 70, 30)))

    # STOCH(9,6): %K de 9 velas, %D como media de 6. Investing muestra el %K.
    est = ind.estocastico(df, n=9, suave_k=1, suave_d=6)
    k = _ult(est["k"])
    out.append(Fila("STOCH(9,6)", k, _sobre_medio(k, 80, 20)))

    sr = _ult(ind.stoch_rsi(close, n_rsi=14, n_stoch=14, suave_k=3, suave_d=3)["k"])
    out.append(Fila("STOCHRSI(14)", sr, _sobre_medio(sr, 80, 20)))

    # MACD(12,26): Investing muestra la diferencia entre la linea y su senal.
    mac = ind.macd(close, 12, 26, 9)
    linea, senal = _ult(mac["macd"]), _ult(mac["signal"])
    dif = linea - senal if np.isfinite(linea) and np.isfinite(senal) else np.nan
    out.append(Fila("MACD(12,26)", dif,
                    COMPRA if dif > 0 else (VENTA if dif < 0 else NEUTRAL)))

    # ADX(14): la fuerza la da el ADX, la direccion el par DI+/DI-.
    a = ind.adx(df, 14)
    adx_v, dip, dim = _ult(a["adx"]), _ult(a["di_mas"]), _ult(a["di_menos"])
    if not np.isfinite(adx_v) or adx_v < 20:
        s_adx = NEUTRAL
    else:
        s_adx = COMPRA if dip > dim else VENTA
    out.append(Fila("ADX(14)", adx_v, s_adx))

    # Williams %R: misma logica, en escala de -100 a 0.
    w = _ult(ind.williams_r(df, 14))
    out.append(Fila("Williams %R", w, _sobre_medio(w, -20, -80, medio=-50)))

    # CCI(14): no esta acotado; fuera de +-100 marca direccion, adentro neutral.
    c = _ult(ind.cci(df, 14))
    if not np.isfinite(c):
        s_cci = NEUTRAL
    else:
        s_cci = COMPRA if c > 100 else (VENTA if c < -100 else NEUTRAL)
    out.append(Fila("CCI(14)", c, s_cci))

    # ATR(14): no vota. Compara la volatilidad de hoy con su propio promedio.
    atr_serie = ind.atr(df, 14)
    atr_v = _ult(atr_serie)
    promedio = _ult(atr_serie.rolling(100, min_periods=20).mean())
    if np.isfinite(atr_v) and np.isfinite(promedio):
        s_atr = VOLATIL if atr_v > promedio else TRANQUILO
    else:
        s_atr = TRANQUILO
    out.append(Fila("ATR(14)", atr_v, s_atr))

    hl = _ult(highs_lows(df, 14))
    out.append(Fila("Highs/Lows(14)", hl,
                    COMPRA if hl > 0 else (VENTA if hl < 0 else NEUTRAL)))

    uo = _ult(ind.ultimate_oscillator(df))
    out.append(Fila("Ultimate Oscillator", uo, _sobre_medio(uo, 70, 30)))

    roc = _ult(ind.roc(close, 12))
    out.append(Fila("ROC", roc,
                    COMPRA if roc > 0 else (VENTA if roc < 0 else NEUTRAL)))

    bbp = _ult(ind.bull_bear_power(df, 13))
    out.append(Fila("Bull/Bear Power(13)", bbp,
                    COMPRA if bbp > 0 else (VENTA if bbp < 0 else NEUTRAL)))

    return out


PERIODOS_MEDIAS = (5, 10, 20, 50, 100, 200)


def medias(df: pd.DataFrame) -> list[Fila]:
    """Las doce filas de "Moving Averages": seis periodos, simple y exponencial.

    La regla es la misma que en TradingView y no admite matices: el precio por
    encima de la media compra, por debajo vende.
    """
    close = df["Close"]
    precio = float(close.iloc[-1])
    out: list[Fila] = []
    for n in PERIODOS_MEDIAS:
        if len(df) <= n:
            continue
        for etiqueta, fn in (("Simple", ind.sma), ("Exponencial", ind.ema)):
            v = _ult(fn(close, n))
            if not np.isfinite(v):
                continue
            out.append(Fila(f"MA{n} {etiqueta}", v,
                            COMPRA if precio > v else VENTA))
    return out


def _resumir(filas: list[Fila]) -> dict:
    votantes = [f for f in filas if f.vota]
    compra = sum(1 for f in votantes if f.senal == COMPRA)
    venta = sum(1 for f in votantes if f.senal == VENTA)
    neutral = sum(1 for f in votantes if f.senal == NEUTRAL)
    # Las etiquetas de sobrecompra, sobreventa y volatilidad no entran al conteo.
    aparte = len(filas) - len(votantes)
    prom = float(np.mean([_VOTO[f.senal] for f in votantes])) if votantes else 0.0
    return {"compra": compra, "venta": venta, "neutral": neutral,
            "sin_voto": aparte, "promedio": round(prom, 3),
            "veredicto": veredicto(prom)}


def veredicto(promedio: float) -> str:
    if promedio >= 0.5:
        return "COMPRA FUERTE"
    if promedio >= 0.1:
        return "COMPRA"
    if promedio > -0.1:
        return "NEUTRAL"
    if promedio > -0.5:
        return "VENTA"
    return "VENTA FUERTE"


def evaluar(df: pd.DataFrame) -> dict:
    """Resumen tecnico completo segun el criterio de Investing.com."""
    osc = osciladores(df)
    med = medias(df)
    r_osc, r_med = _resumir(osc), _resumir(med)

    votantes = [f for f in osc + med if f.vota]
    prom = float(np.mean([_VOTO[f.senal] for f in votantes])) if votantes else 0.0

    return {
        "osciladores": r_osc,
        "medias": r_med,
        "promedio": round(prom, 3),
        "veredicto": veredicto(prom),
        "filas_osciladores": [{"nombre": f.nombre, "valor": f.valor, "senal": f.senal}
                              for f in osc],
        "filas_medias": [{"nombre": f.nombre, "valor": f.valor, "senal": f.senal}
                         for f in med],
    }
