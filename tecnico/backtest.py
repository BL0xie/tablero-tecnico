"""Validacion historica del par stop/objetivo con el metodo de triple barrera.

La pregunta que responde: entrando en este activo, cuantas veces el precio
toco +X% ANTES de tocar -Y%, dentro de un horizonte de N velas.

Se evalua de dos formas:
  - Incondicional: entrando en cualquier vela. Es la linea base, el "azar".
  - Condicional: entrando solo cuando se dio una senal concreta. Si la senal
    no supera a la linea base, no esta aportando nada.

Criterio conservador: si dentro de una misma vela el precio toca las dos
barreras, se cuenta como stop. Sin datos intradiarios no se puede saber cual
llego primero, y suponer lo contrario infla artificialmente los resultados.

Tambien se miden MAE y MFE (cuanto va en contra y cuanto a favor cada
operacion antes de cerrar), que es lo que dice si el stop elegido es
compatible con el ruido normal del activo o si va a saltar de mas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import calculo as ind


def triple_barrera(df: pd.DataFrame, tp_pct: float, sl_pct: float,
                   max_velas: int = 20, direccion: str = "largo",
                   entradas: pd.Series | None = None) -> pd.DataFrame:
    """Simula una operacion abierta al cierre de cada vela marcada.

    entradas: mascara booleana. Si es None se evalua en todas las velas.
    Devuelve una fila por operacion con resultado, retorno, duracion, MAE y MFE.
    """
    close = df["Close"].to_numpy(dtype=float)
    alto = df["High"].to_numpy(dtype=float)
    bajo = df["Low"].to_numpy(dtype=float)
    n = len(df)

    if entradas is None:
        indices = np.arange(n - 1)
    else:
        mask = entradas.reindex(df.index).fillna(False).to_numpy(dtype=bool)
        indices = np.flatnonzero(mask)
        indices = indices[indices < n - 1]

    largo = direccion == "largo"
    tp_r, sl_r = tp_pct / 100, sl_pct / 100
    filas = []

    for i in indices:
        entrada = close[i]
        if not np.isfinite(entrada) or entrada <= 0:
            continue
        if largo:
            nivel_tp = entrada * (1 + tp_r)
            nivel_sl = entrada * (1 - sl_r)
        else:
            nivel_tp = entrada * (1 - tp_r)
            nivel_sl = entrada * (1 + sl_r)

        fin = min(i + max_velas, n - 1)
        resultado, salida, velas = "abierta", close[fin], fin - i
        peor, mejor = 0.0, 0.0

        for j in range(i + 1, fin + 1):
            # Excursion maxima a favor y en contra hasta esta vela.
            if largo:
                mejor = max(mejor, (alto[j] - entrada) / entrada * 100)
                peor = min(peor, (bajo[j] - entrada) / entrada * 100)
                toco_sl = bajo[j] <= nivel_sl
                toco_tp = alto[j] >= nivel_tp
            else:
                mejor = max(mejor, (entrada - bajo[j]) / entrada * 100)
                peor = min(peor, (entrada - alto[j]) / entrada * 100)
                toco_sl = alto[j] >= nivel_sl
                toco_tp = bajo[j] <= nivel_tp

            if toco_sl:  # el stop manda ante el empate dentro de la vela
                resultado, salida, velas = "stop", nivel_sl, j - i
                break
            if toco_tp:
                resultado, salida, velas = "objetivo", nivel_tp, j - i
                break
        else:
            resultado = "vencido"

        retorno = ((salida - entrada) / entrada * 100) if largo else ((entrada - salida) / entrada * 100)
        filas.append({
            "fecha": df.index[i], "entrada": entrada, "salida": salida,
            "resultado": resultado, "retorno_pct": retorno, "velas": velas,
            "mae_pct": peor, "mfe_pct": mejor,
        })

    return pd.DataFrame(filas)


def estadistica(ops: pd.DataFrame) -> dict:
    """Resume un conjunto de operaciones simuladas."""
    if ops.empty:
        return {"operaciones": 0}

    ganadoras = ops[ops["retorno_pct"] > 0]
    perdedoras = ops[ops["retorno_pct"] <= 0]
    n = len(ops)
    tasa_tp = 100 * (ops["resultado"] == "objetivo").sum() / n
    win_rate = 100 * len(ganadoras) / n

    prom_g = float(ganadoras["retorno_pct"].mean()) if len(ganadoras) else 0.0
    prom_p = float(perdedoras["retorno_pct"].mean()) if len(perdedoras) else 0.0
    esperanza = float(ops["retorno_pct"].mean())

    bruto_g = float(ganadoras["retorno_pct"].sum())
    bruto_p = abs(float(perdedoras["retorno_pct"].sum()))

    return {
        "operaciones": n,
        "toco_objetivo_pct": round(tasa_tp, 1),
        "toco_stop_pct": round(100 * (ops["resultado"] == "stop").sum() / n, 1),
        "vencidas_pct": round(100 * (ops["resultado"] == "vencido").sum() / n, 1),
        "win_rate_pct": round(win_rate, 1),
        "retorno_medio_pct": round(esperanza, 2),
        "ganancia_media_pct": round(prom_g, 2),
        "perdida_media_pct": round(prom_p, 2),
        "profit_factor": round(bruto_g / bruto_p, 2) if bruto_p > 0 else float("inf"),
        "velas_promedio": round(float(ops["velas"].mean()), 1),
        # Cuanto va en contra una operacion que despues gana: calibra el stop.
        "mae_medio_ganadoras_pct": round(float(ganadoras["mae_pct"].mean()), 2) if len(ganadoras) else 0.0,
        "mae_p80_ganadoras_pct": round(float(ganadoras["mae_pct"].quantile(0.20)), 2) if len(ganadoras) else 0.0,
        "mfe_medio_perdedoras_pct": round(float(perdedoras["mfe_pct"].mean()), 2) if len(perdedoras) else 0.0,
    }


# --------------------------------------------------------------------------
# Senales historicas vectorizadas, para medir si aportan algo
# --------------------------------------------------------------------------
def mascaras_senales(df: pd.DataFrame, cfg: dict) -> dict[str, pd.Series]:
    """Reconstruye cada senal a lo largo de todo el historial."""
    p = cfg.get("parametros", {})
    close = df["Close"]
    out: dict[str, pd.Series] = {}

    r = ind.rsi(close, p.get("rsi", 14))
    inf = p.get("rsi_sobreventa", 30)
    sup = p.get("rsi_sobrecompra", 70)
    out[f"RSI sale de sobreventa (<{inf})"] = (r.shift(1) < inf) & (r >= inf)
    out[f"RSI en sobreventa (<{inf})"] = r < inf
    out[f"RSI sale de sobrecompra (>{sup})"] = (r.shift(1) > sup) & (r <= sup)

    m = ind.macd(close, p.get("macd_rapida", 12), p.get("macd_lenta", 26),
                 p.get("macd_senal", 9))
    dif = m["macd"] - m["signal"]
    out["MACD cruza al alza"] = (dif.shift(1) <= 0) & (dif > 0)
    out["MACD cruza a la baja"] = (dif.shift(1) >= 0) & (dif < 0)

    rap, len_ = p.get("cruce_rapida", 20), p.get("cruce_lenta", 50)
    d_ema = ind.ema(close, rap) - ind.ema(close, len_)
    out[f"EMA {rap} cruza sobre EMA {len_}"] = (d_ema.shift(1) <= 0) & (d_ema > 0)

    for n in p.get("medias_clave", [20, 50]):
        if len(df) > n:
            d = close - ind.ema(close, n)
            out[f"precio recupera EMA {n}"] = (d.shift(1) <= 0) & (d > 0)

    if len(df) >= 20:
        vr = ind.volumen_relativo(df, p.get("volumen_media", 20))
        alto_vol = vr >= p.get("volumen_alto", 1.5)
        sube = close.pct_change() > 0
        out["vela alcista con volumen alto"] = alto_vol & sube

    bb = ind.bollinger(close, p.get("bollinger", 20), p.get("bollinger_desv", 2.0))
    out["precio bajo la banda inferior"] = close < bb["inf"]

    a = ind.adx(df, p.get("adx", 14))
    out["ADX>25 con DI+ dominante"] = (a["adx"] > 25) & (a["di_mas"] > a["di_menos"])

    # Combinacion tipica de corto plazo: sobreventa + confirmacion + volumen
    if "vela alcista con volumen alto" in out:
        out["RSI sobreventa + MACD al alza"] = out[f"RSI en sobreventa (<{inf})"] & out["MACD cruza al alza"]

    return {k: v.fillna(False) for k, v in out.items()}


def evaluar_todo(df: pd.DataFrame, cfg: dict, tp_pct: float, sl_pct: float,
                 max_velas: int = 20, min_ops: int = 8) -> dict:
    """Linea base + una evaluacion por senal, ordenadas por ventaja sobre la base."""
    base_ops = triple_barrera(df, tp_pct, sl_pct, max_velas)
    base = estadistica(base_ops)

    resultados = []
    for nombre, mask in mascaras_senales(df, cfg).items():
        if int(mask.sum()) < min_ops:
            continue
        ops = triple_barrera(df, tp_pct, sl_pct, max_velas, entradas=mask)
        st = estadistica(ops)
        if st.get("operaciones", 0) < min_ops:
            continue
        st["senal"] = nombre
        st["ventaja_pp"] = round(st["toco_objetivo_pct"] - base.get("toco_objetivo_pct", 0), 1)
        resultados.append(st)

    resultados.sort(key=lambda x: -x["ventaja_pp"])
    return {"base": base, "senales": resultados, "operaciones_base": base_ops,
            "config": {"tp_pct": tp_pct, "sl_pct": sl_pct, "max_velas": max_velas}}


def diagnostico_stop(df: pd.DataFrame, sl_pct: float, tp_pct: float,
                     max_velas: int, intervalo: str = "1d") -> dict:
    """Contrasta el stop elegido con la volatilidad real del activo."""
    atr_serie = ind.atr(df, 14)
    precio = float(df["Close"].iloc[-1])
    atr_v = float(atr_serie.dropna().iloc[-1]) if atr_serie.notna().any() else precio * 0.02
    atr_pct = 100 * atr_v / precio

    # Recorrido tipico del activo en el horizonte de la operacion.
    rango = (df["Close"].rolling(max_velas).max() / df["Close"].rolling(max_velas).min() - 1) * 100
    caida = (df["Close"] / df["Close"].rolling(max_velas).max() - 1) * 100

    return {
        "atr_pct": round(atr_pct, 2),
        "stop_en_atr": round(sl_pct / atr_pct, 2) if atr_pct > 0 else float("inf"),
        "objetivo_en_atr": round(tp_pct / atr_pct, 2) if atr_pct > 0 else float("inf"),
        "rango_tipico_pct": round(float(rango.dropna().median()), 2) if rango.notna().any() else None,
        "caida_tipica_pct": round(float(caida.dropna().quantile(0.25)), 2) if caida.notna().any() else None,
        "volatilidad_anual_pct": round(float(
            df["Close"].pct_change().std() * np.sqrt(
                {"1d": 252, "1wk": 52, "1h": 1638, "60m": 1638}.get(intervalo, 252)) * 100), 1),
    }
