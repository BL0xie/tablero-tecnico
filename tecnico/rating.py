"""Veredicto por indicador y resumen agregado.

Reproduce la logica del "Resumen tecnico" que Damian ya mira en Investing.com
y del Technical Rating de TradingView: cada indicador vota COMPRA, VENTA o
NEUTRAL, y el promedio de los votos define el veredicto general.

Escala del promedio (identica a TradingView):
    >=  0.5  COMPRA FUERTE
    >=  0.1  COMPRA
    >  -0.1  NEUTRAL
    >  -0.5  VENTA
    <=      VENTA FUERTE

Ademas de los votos hay `senales_clave()`, que detecta los eventos que
realmente disparan una operacion: cruces de medias, cruces de MACD, salidas
de sobreventa, divergencias y roturas con volumen.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import calculo as ind

COMPRA, VENTA, NEUTRAL = "COMPRA", "VENTA", "NEUTRAL"
_VOTO = {COMPRA: 1, NEUTRAL: 0, VENTA: -1}


@dataclass
class Lectura:
    """El valor de un indicador y su voto."""
    nombre: str
    valor: float
    senal: str
    nota: str = ""


def _ultimos(serie: pd.Series, k: int = 2) -> tuple[float, ...]:
    """Ultimos k valores como floats; NaN si no alcanzan los datos."""
    s = serie.dropna()
    if len(s) < k:
        return tuple([np.nan] * k)
    return tuple(float(v) for v in s.iloc[-k:])


def _cruzo_arriba(a: pd.Series, b: pd.Series, velas: int = 1) -> bool:
    """a cruzo por encima de b en las ultimas `velas` velas."""
    d = (a - b).dropna()
    if len(d) < velas + 1:
        return False
    return bool((d.iloc[-velas - 1:-1] <= 0).any() and d.iloc[-1] > 0)


def _cruzo_abajo(a: pd.Series, b: pd.Series, velas: int = 1) -> bool:
    d = (a - b).dropna()
    if len(d) < velas + 1:
        return False
    return bool((d.iloc[-velas - 1:-1] >= 0).any() and d.iloc[-1] < 0)


# --------------------------------------------------------------------------
# Osciladores
# --------------------------------------------------------------------------
def evaluar_osciladores(df: pd.DataFrame, cfg: dict) -> list[Lectura]:
    p = cfg.get("parametros", {})
    close = df["Close"]
    out: list[Lectura] = []

    # RSI: sobreventa girando al alza compra; sobrecompra girando a la baja vende.
    n = p.get("rsi", 14)
    r = ind.rsi(close, n)
    prev, act = _ultimos(r)
    if np.isfinite(act):
        sup = p.get("rsi_sobrecompra", 70)
        inf = p.get("rsi_sobreventa", 30)
        if act < inf and act > prev:
            s, nota = COMPRA, f"sobreventa (<{inf}) girando al alza"
        elif act > sup and act < prev:
            s, nota = VENTA, f"sobrecompra (>{sup}) girando a la baja"
        elif act < inf:
            s, nota = NEUTRAL, f"sobreventa (<{inf}) pero aun cayendo"
        elif act > sup:
            s, nota = NEUTRAL, f"sobrecompra (>{sup}) pero aun subiendo"
        else:
            s, nota = NEUTRAL, "zona media"
        out.append(Lectura(f"RSI ({n})", act, s, nota))

    # Estocastico
    est = ind.estocastico(df, p.get("estocastico_k", 14), p.get("estocastico_suave", 3),
                          p.get("estocastico_d", 3))
    k, d = est["k"].dropna(), est["d"].dropna()
    if len(k) and len(d):
        kv, dv = float(k.iloc[-1]), float(d.iloc[-1])
        if kv < 20 and dv < 20 and kv > dv:
            s, nota = COMPRA, "sobreventa con %K sobre %D"
        elif kv > 80 and dv > 80 and kv < dv:
            s, nota = VENTA, "sobrecompra con %K bajo %D"
        else:
            s, nota = NEUTRAL, f"%D en {dv:.1f}"
        out.append(Lectura("Estocastico %K", kv, s, nota))

    # CCI
    c = ind.cci(df, p.get("cci", 20))
    prev, act = _ultimos(c)
    if np.isfinite(act):
        if act < -100 and act > prev:
            s, nota = COMPRA, "saliendo de sobreventa"
        elif act > 100 and act < prev:
            s, nota = VENTA, "saliendo de sobrecompra"
        else:
            s, nota = NEUTRAL, ""
        out.append(Lectura(f"CCI ({p.get('cci', 20)})", act, s, nota))

    # ADX: mide fuerza de tendencia; la direccion la dan DI+ / DI-
    a = ind.adx(df, p.get("adx", 14))
    if a["adx"].notna().any():
        adx_v = float(a["adx"].dropna().iloc[-1])
        dip = float(a["di_mas"].dropna().iloc[-1])
        dim = float(a["di_menos"].dropna().iloc[-1])
        umbral = p.get("adx_umbral", 20)
        if adx_v > umbral and dip > dim:
            s, nota = COMPRA, f"tendencia alcista con fuerza (DI+ {dip:.1f} > DI- {dim:.1f})"
        elif adx_v > umbral and dip < dim:
            s, nota = VENTA, f"tendencia bajista con fuerza (DI- {dim:.1f} > DI+ {dip:.1f})"
        else:
            s, nota = NEUTRAL, f"sin tendencia definida (ADX < {umbral})"
        out.append(Lectura(f"ADX ({p.get('adx', 14)})", adx_v, s, nota))

    # Awesome Oscillator: cruce de cero
    ao = ind.awesome_oscillator(df)
    prev, act = _ultimos(ao)
    if np.isfinite(act):
        if act > 0 and prev <= 0:
            s, nota = COMPRA, "cruce alcista del cero"
        elif act < 0 and prev >= 0:
            s, nota = VENTA, "cruce bajista del cero"
        elif act > 0 and act > prev:
            s, nota = COMPRA, "positivo y creciendo"
        elif act < 0 and act < prev:
            s, nota = VENTA, "negativo y cayendo"
        else:
            s, nota = NEUTRAL, ""
        out.append(Lectura("Awesome Oscillator", act, s, nota))

    # Momentum
    m = ind.momentum(close, p.get("momentum", 10))
    prev, act = _ultimos(m)
    if np.isfinite(act):
        s = COMPRA if act > prev else (VENTA if act < prev else NEUTRAL)
        out.append(Lectura(f"Momentum ({p.get('momentum', 10)})", act, s, ""))

    # MACD
    mac = ind.macd(close, p.get("macd_rapida", 12), p.get("macd_lenta", 26),
                   p.get("macd_senal", 9))
    if mac["macd"].notna().any() and mac["signal"].notna().any():
        mv = float(mac["macd"].dropna().iloc[-1])
        sv = float(mac["signal"].dropna().iloc[-1])
        if mv > sv:
            s = COMPRA
            nota = "MACD sobre su señal" + (" (cruce reciente)" if _cruzo_arriba(mac["macd"], mac["signal"], 3) else "")
        elif mv < sv:
            s = VENTA
            nota = "MACD bajo su señal" + (" (cruce reciente)" if _cruzo_abajo(mac["macd"], mac["signal"], 3) else "")
        else:
            s, nota = NEUTRAL, ""
        out.append(Lectura("MACD (12,26,9)", mv, s, nota))

    # Stochastic RSI
    sr = ind.stoch_rsi(close)
    k, d = sr["k"].dropna(), sr["d"].dropna()
    if len(k) and len(d):
        kv, dv = float(k.iloc[-1]), float(d.iloc[-1])
        if kv < 20 and dv < 20 and kv > dv:
            s, nota = COMPRA, "sobreventa girando"
        elif kv > 80 and dv > 80 and kv < dv:
            s, nota = VENTA, "sobrecompra girando"
        else:
            s, nota = NEUTRAL, ""
        out.append(Lectura("Stochastic RSI", kv, s, nota))

    # Williams %R
    w = ind.williams_r(df, p.get("williams", 14))
    prev, act = _ultimos(w)
    if np.isfinite(act):
        if act < -80 and act > prev:
            s, nota = COMPRA, "sobreventa girando"
        elif act > -20 and act < prev:
            s, nota = VENTA, "sobrecompra girando"
        else:
            s, nota = NEUTRAL, ""
        out.append(Lectura("Williams %R", act, s, nota))

    # Bull Bear Power
    bbp = ind.bull_bear_power(df)
    prev, act = _ultimos(bbp)
    if np.isfinite(act):
        if act > 0 and act > prev:
            s = COMPRA
        elif act < 0 and act < prev:
            s = VENTA
        else:
            s = NEUTRAL
        out.append(Lectura("Bull Bear Power", act, s, ""))

    # Ultimate Oscillator
    uo = ind.ultimate_oscillator(df)
    _, act = _ultimos(uo)
    if np.isfinite(act):
        s = COMPRA if act > 70 else (VENTA if act < 30 else NEUTRAL)
        out.append(Lectura("Ultimate Oscillator", act, s, ""))

    # MFI: volumen dentro del bloque de osciladores
    if cfg.get("usar_volumen", True):
        f = ind.mfi(df, p.get("mfi", 14))
        prev, act = _ultimos(f)
        if np.isfinite(act):
            if act < 20 and act > prev:
                s, nota = COMPRA, "dinero entrando desde sobreventa"
            elif act > 80 and act < prev:
                s, nota = VENTA, "dinero saliendo desde sobrecompra"
            else:
                s, nota = NEUTRAL, ""
            out.append(Lectura("Money Flow Index", act, s, nota))

    return out


# --------------------------------------------------------------------------
# Medias moviles
# --------------------------------------------------------------------------
def evaluar_medias(df: pd.DataFrame, cfg: dict) -> list[Lectura]:
    """Precio por encima de la media vota compra; por debajo, venta."""
    p = cfg.get("parametros", {})
    periodos = p.get("medias", [10, 20, 30, 50, 100, 200])
    close = df["Close"]
    precio = float(close.iloc[-1])
    out: list[Lectura] = []

    for n in periodos:
        if len(df) < n:
            continue
        for tipo, fn in (("SMA", ind.sma), ("EMA", ind.ema)):
            serie = fn(close, n)
            if serie.notna().any():
                v = float(serie.dropna().iloc[-1])
                s = COMPRA if precio > v else (VENTA if precio < v else NEUTRAL)
                dist = 100 * (precio - v) / v
                out.append(Lectura(f"{tipo} {n}", v, s, f"precio {dist:+.2f}%"))

    if len(df) >= 20:
        v = ind.vwma(df, 20)
        if v.notna().any():
            val = float(v.dropna().iloc[-1])
            out.append(Lectura("VWMA 20", val,
                               COMPRA if precio > val else VENTA, ""))
    if len(df) >= 9:
        h = ind.hma(close, 9)
        if h.notna().any():
            val = float(h.dropna().iloc[-1])
            out.append(Lectura("Hull MA 9", val,
                               COMPRA if precio > val else VENTA, ""))

    ich = ind.ichimoku(df)
    if ich["kijun"].notna().any():
        kij = float(ich["kijun"].dropna().iloc[-1])
        out.append(Lectura("Ichimoku base", kij,
                           COMPRA if precio > kij else VENTA, ""))
    return out


# --------------------------------------------------------------------------
# Resumen agregado
# --------------------------------------------------------------------------
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


def resumir(lecturas: list[Lectura]) -> dict:
    if not lecturas:
        return {"compra": 0, "venta": 0, "neutral": 0, "promedio": 0.0,
                "veredicto": "SIN DATOS"}
    votos = [_VOTO[l.senal] for l in lecturas]
    prom = float(np.mean(votos))
    return {
        "compra": sum(1 for v in votos if v > 0),
        "venta": sum(1 for v in votos if v < 0),
        "neutral": sum(1 for v in votos if v == 0),
        "promedio": round(prom, 3),
        "veredicto": veredicto(prom),
    }


def resumen_general(osc: list[Lectura], med: list[Lectura],
                    peso_osciladores: float = 0.5, df: pd.DataFrame | None = None,
                    cfg: dict | None = None) -> dict:
    """Combina ambos bloques. El peso permite priorizar tendencia o momentum
    segun el escenario: para corto plazo conviene subir el peso de osciladores.

    Ademas aplica una correccion que el resumen de Investing no hace: si el
    precio esta sobreextendido (RSI extremo, lejos de su media), un "COMPRA
    FUERTE" no significa "compra ahora" sino "ya subio". Se degrada un escalon
    y queda registrado el motivo, asi el veredicto no invita a comprar techos.
    """
    r_osc, r_med = resumir(osc), resumir(med)
    if not osc and not med:
        return {"osciladores": r_osc, "medias": r_med, "promedio": 0.0,
                "veredicto": "SIN DATOS", "ajuste": None}
    if not osc:
        prom = r_med["promedio"]
    elif not med:
        prom = r_osc["promedio"]
    else:
        prom = peso_osciladores * r_osc["promedio"] + (1 - peso_osciladores) * r_med["promedio"]

    ajuste = None
    if df is not None and len(df) > 30:
        p = (cfg or {}).get("parametros", {})
        rsi_v = ind.rsi(df["Close"], p.get("rsi", 14)).dropna()
        ema20 = ind.ema(df["Close"], 20).dropna()
        if len(rsi_v) and len(ema20):
            r = float(rsi_v.iloc[-1])
            dist = float(100 * (df["Close"].iloc[-1] / ema20.iloc[-1] - 1))
            sup = p.get("rsi_sobrecompra", 70)
            inf = p.get("rsi_sobreventa", 30)
            # Sobreextendido al alza: hay compra, pero es tarde para entrar.
            if prom > 0.1 and (r >= sup + 8 or dist >= 12):
                prom = min(prom, 0.3)   # tope en COMPRA, nunca COMPRA FUERTE
                ajuste = (f"sobreextendido: RSI {r:.0f}, precio {dist:+.0f}% sobre la EMA 20. "
                          f"La tendencia es alcista pero entrar ahora es comprar caro")
            # Sobrevendido: hay venta, pero es tarde para vender.
            elif prom < -0.1 and (r <= inf - 5 or dist <= -12):
                prom = max(prom, -0.3)
                ajuste = (f"sobrevendido: RSI {r:.0f}, precio {dist:+.0f}% bajo la EMA 20. "
                          f"La tendencia es bajista pero vender aca suele ser el piso")

    return {"osciladores": r_osc, "medias": r_med,
            "promedio": round(float(prom), 3), "veredicto": veredicto(prom),
            "ajuste": ajuste}


# --------------------------------------------------------------------------
# Senales que disparan operaciones
# --------------------------------------------------------------------------
def _divergencia_rsi(df: pd.DataFrame, n: int = 14, lookback: int = 40,
                     ventana: int = 5) -> str | None:
    """Divergencia entre precio y RSI: el aviso mas util de agotamiento."""
    from .niveles import pivotes_swing

    tramo = df.tail(lookback)
    if len(tramo) < lookback // 2:
        return None
    r = ind.rsi(df["Close"], n).tail(lookback)
    maximos, minimos = pivotes_swing(tramo, ventana)

    if len(minimos) >= 2:
        f1, f2 = minimos.index[-2], minimos.index[-1]
        if minimos.loc[f2] < minimos.loc[f1] and r.loc[f2] > r.loc[f1]:
            return ("alcista", f"el precio hizo un mínimo más bajo el {f2.strftime('%d/%m')} "
                               f"pero el RSI subió ({r.loc[f1]:.0f} → {r.loc[f2]:.0f}): "
                               f"la caída pierde fuerza")
    if len(maximos) >= 2:
        f1, f2 = maximos.index[-2], maximos.index[-1]
        if maximos.loc[f2] > maximos.loc[f1] and r.loc[f2] < r.loc[f1]:
            return ("bajista", f"el precio hizo un máximo más alto el {f2.strftime('%d/%m')} "
                               f"pero el RSI bajó ({r.loc[f1]:.0f} → {r.loc[f2]:.0f}): "
                               f"la subida pierde fuerza")
    return None


def senales_clave(df: pd.DataFrame, cfg: dict) -> list[dict]:
    """Eventos accionables detectados en las ultimas velas."""
    p = cfg.get("parametros", {})
    velas = cfg.get("velas_senal", 3)
    close = df["Close"]
    precio = float(close.iloc[-1])
    out: list[dict] = []

    def agregar(tipo, sesgo, texto, peso=1.0):
        out.append({"tipo": tipo, "sesgo": sesgo, "detalle": texto, "peso": peso})

    # --- Cruces de medias ---
    rapida_n = p.get("cruce_rapida", 20)
    lenta_n = p.get("cruce_lenta", 50)
    if len(df) > lenta_n:
        rapida = ind.ema(close, rapida_n)
        lenta = ind.ema(close, lenta_n)
        if _cruzo_arriba(rapida, lenta, velas):
            agregar("cruce_medias", "alcista",
                    f"EMA {rapida_n} cruzó por encima de EMA {lenta_n}", 1.5)
        elif _cruzo_abajo(rapida, lenta, velas):
            agregar("cruce_medias", "bajista",
                    f"EMA {rapida_n} cruzó por debajo de EMA {lenta_n}", 1.5)

    # Precio recuperando o perdiendo una media clave
    for n in p.get("medias_clave", [20, 50, 200]):
        if len(df) <= n:
            continue
        media = ind.ema(close, n)
        if _cruzo_arriba(close, media, velas):
            agregar("recupera_media", "alcista", f"el precio recuperó la EMA {n}", 1.0)
        elif _cruzo_abajo(close, media, velas):
            agregar("pierde_media", "bajista", f"el precio perdió la EMA {n}", 1.0)

    # --- MACD ---
    mac = ind.macd(close, p.get("macd_rapida", 12), p.get("macd_lenta", 26),
                   p.get("macd_senal", 9))
    if _cruzo_arriba(mac["macd"], mac["signal"], velas):
        agregar("macd", "alcista", "MACD cruzó al alza su línea de señal", 1.3)
    elif _cruzo_abajo(mac["macd"], mac["signal"], velas):
        agregar("macd", "bajista", "MACD cruzó a la baja su línea de señal", 1.3)
    hist = mac["hist"].dropna()
    if len(hist) >= 4:
        ult = hist.iloc[-3:]
        if (ult < 0).all() and ult.is_monotonic_increasing:
            agregar("macd", "alcista", "histograma MACD negativo pero contrayéndose", 0.6)
        elif (ult > 0).all() and ult.is_monotonic_decreasing:
            agregar("macd", "bajista", "histograma MACD positivo pero contrayéndose", 0.6)

    # --- RSI ---
    r = ind.rsi(close, p.get("rsi", 14))
    inf, sup = p.get("rsi_sobreventa", 30), p.get("rsi_sobrecompra", 70)
    rs = r.dropna()
    if len(rs) > velas + 1:
        reciente = rs.iloc[-velas - 1:]
        if (reciente.iloc[:-1] < inf).any() and reciente.iloc[-1] >= inf:
            agregar("rsi", "alcista", f"el RSI salió de sobreventa (cruzó {inf} al alza)", 1.2)
        if (reciente.iloc[:-1] > sup).any() and reciente.iloc[-1] <= sup:
            agregar("rsi", "bajista", f"el RSI salió de sobrecompra (cruzó {sup} a la baja)", 1.2)
        if float(rs.iloc[-1]) < inf:
            agregar("rsi", "alcista", f"RSI en {rs.iloc[-1]:.1f}: zona de sobreventa", 0.8)
        if float(rs.iloc[-1]) > sup:
            agregar("rsi", "bajista", f"RSI en {rs.iloc[-1]:.1f}: zona de sobrecompra", 0.8)

    div = _divergencia_rsi(df, p.get("rsi", 14), p.get("lookback_divergencia", 40),
                           p.get("ventana_swing", 5))
    if div:
        sesgo, texto = div
        agregar("divergencia", sesgo, f"divergencia {sesgo} del RSI: {texto}", 1.6)

    # --- Volumen ---
    if cfg.get("usar_volumen", True) and len(df) >= 20:
        vr = ind.volumen_relativo(df, p.get("volumen_media", 20))
        if vr.notna().any():
            vr_act = float(vr.dropna().iloc[-1])
            umbral = p.get("volumen_alto", 1.5)
            var = float(close.pct_change().iloc[-1] * 100)
            if vr_act >= umbral:
                sesgo = "alcista" if var > 0 else "bajista"
                agregar("volumen", sesgo,
                        f"volumen {vr_act:.1f}x el promedio con vela {var:+.2f}%: "
                        f"movimiento confirmado", 1.2)
            elif vr_act < 0.6:
                agregar("volumen", "neutral",
                        f"volumen {vr_act:.1f}x el promedio: movimiento sin conviccion", 0.5)

        o = ind.obv(df)
        if len(o) > 20:
            obv_tend = float(o.iloc[-1] - o.iloc[-20])
            precio_tend = float(close.iloc[-1] - close.iloc[-20])
            if obv_tend > 0 and precio_tend < 0:
                agregar("volumen", "alcista",
                        "OBV sube mientras el precio baja: acumulación", 1.1)
            elif obv_tend < 0 and precio_tend > 0:
                agregar("volumen", "bajista",
                        "OBV baja mientras el precio sube: distribución", 1.1)

    # --- Volatilidad ---
    if len(df) >= 40:
        bb = ind.bollinger(close, p.get("bollinger", 20), p.get("bollinger_desv", 2.0))
        ancho = bb["ancho"].dropna()
        if len(ancho) >= 40:
            if float(ancho.iloc[-1]) <= float(ancho.tail(40).quantile(0.15)):
                agregar("volatilidad", "neutral",
                        "bandas de Bollinger comprimidas: suele preceder un movimiento fuerte", 0.9)
        pb = bb["pct_b"].dropna()
        if len(pb):
            if float(pb.iloc[-1]) < 0:
                agregar("bollinger", "alcista", "precio por debajo de la banda inferior", 1.0)
            elif float(pb.iloc[-1]) > 1:
                agregar("bollinger", "bajista", "precio por encima de la banda superior", 1.0)

    # --- Rupturas de rango ---
    n_d = p.get("donchian", 20)
    if len(df) > n_d + 1:
        techo = float(df["High"].iloc[-n_d - 1:-1].max())
        piso = float(df["Low"].iloc[-n_d - 1:-1].min())
        if precio > techo:
            agregar("ruptura", "alcista", f"rompió el máximo de {n_d} velas ({techo:.2f})", 1.4)
        elif precio < piso:
            agregar("ruptura", "bajista", f"perdió el mínimo de {n_d} velas ({piso:.2f})", 1.4)

    return out


def sesgo_de_senales(senales: list[dict]) -> tuple[str, float]:
    """Sesgo neto ponderado de las senales clave."""
    alcista = sum(s["peso"] for s in senales if s["sesgo"] == "alcista")
    bajista = sum(s["peso"] for s in senales if s["sesgo"] == "bajista")
    total = alcista + bajista
    if total == 0:
        return "neutral", 0.0
    neto = (alcista - bajista) / total
    if neto > 0.25:
        return "alcista", round(neto, 2)
    if neto < -0.25:
        return "bajista", round(neto, 2)
    return "neutral", round(neto, 2)
