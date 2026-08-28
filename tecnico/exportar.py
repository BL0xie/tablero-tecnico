"""Convierte el analisis a una estructura compacta lista para embeber en la pagina.

El tablero dibuja los graficos en el navegador, no en Python, para que se pueda
hacer zoom y para que el peso no se dispare con 75 activos. Eso obliga a mandar
las velas como datos, y con esa cantidad de activos el tamano importa: por eso
las series van como arrays paralelos (no como lista de objetos, que repetiria
el nombre de cada campo en cada vela) y los precios van redondeados a la
precision que el activo realmente necesita.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _decimales(precio: float) -> int:
    """Cuantos decimales tiene sentido conservar para este precio."""
    if precio >= 1000:
        return 1
    if precio >= 10:
        return 2
    if precio >= 1:
        return 3
    return 5


def _serie(valores, dec: int) -> list:
    return [None if not np.isfinite(v) else round(float(v), dec) for v in valores]


def velas(df: pd.DataFrame, n: int, dec: int) -> dict:
    """Arrays paralelos de tiempo y OHLCV."""
    d = df.tail(n)
    return {
        "t": [int(ts.timestamp()) for ts in d.index],
        "o": _serie(d["Open"], dec),
        "h": _serie(d["High"], dec),
        "l": _serie(d["Low"], dec),
        "c": _serie(d["Close"], dec),
        "v": [int(x) if np.isfinite(x) else 0 for x in d["Volume"]],
    }


def _entrada(x, dec: int) -> dict:
    def r(v):
        return None if v is None or not np.isfinite(v) else round(float(v), dec)
    return {
        "escenario": x.escenario, "direccion": x.direccion,
        "min": r(x.zona_min), "max": r(x.zona_max),
        "stop": r(x.stop), "objetivo": r(x.objetivo),
        "riesgo": r(x.riesgo_pct), "beneficio": r(x.beneficio_pct),
        "rr": None if not np.isfinite(x.rr) else round(x.rr, 2),
        "confianza": x.confianza,
        "disparador": x.disparador, "invalidacion": x.invalidacion,
        "avisos": list(x.avisos),
        "nota": str(x.detalle.get("nota", "")) or None,
    }


def temporalidad(r: dict, velas_grafico: int, medias: tuple[int, ...]) -> dict:
    """Todo lo que la pagina necesita de una temporalidad de un activo."""
    from . import calculo as ind

    dec = _decimales(r["precio"])
    df = r["df"]
    d = df.tail(velas_grafico)

    series_media = {}
    for p in medias:
        if len(df) > p:
            series_media[str(p)] = _serie(ind.ema(df["Close"], p).tail(velas_grafico), dec)

    rsi = ind.rsi(df["Close"], 14).tail(velas_grafico)

    return {
        "precio": round(r["precio"], dec),
        "fecha": r["fecha_dato"][:16],
        "velas_total": r["velas"],
        "atr": r["atr"], "atr_pct": r["atr_pct"],
        "vol_rel": r.get("volumen_relativo"),
        "variaciones": r["variaciones_pct"],
        "resumen": r["resumen"],
        "ajuste": r["resumen"].get("ajuste"),
        "investing": _investing(r, dec),
        "sesgo": list(r["sesgo"]),
        "senales": [{"sesgo": s["sesgo"], "detalle": s["detalle"], "peso": s["peso"]}
                    for s in sorted(r["senales"], key=lambda x: -x["peso"])[:8]],
        "zonas": [{"precio": round(z.precio, dec), "tipo": z.tipo,
                   "fuerza": z.fuerza, "origen": z.origen, "toques": z.toques}
                  for z in sorted(r["zonas"], key=lambda z: -z.fuerza)[:12]],
        "entradas": [_entrada(x, dec) for x in r["entradas"][:5]],
        "velas": velas(df, velas_grafico, dec),
        "medias": series_media,
        "rsi": _serie(rsi, 1),
        "backtest": _backtest(r),
        "dec": dec,
    }


def _investing(r: dict, dec: int) -> dict | None:
    """La lectura con el criterio de Investing, y si coincide con la nuestra.

    Lo util no es el veredicto ajeno por si solo, sino el cruce: dos criterios
    distintos apuntando al mismo lado es mejor señal que uno solo.
    """
    inv = r.get("investing")
    if not inv:
        return None

    propio = r["resumen"]["veredicto"]
    ajeno = inv["veredicto"]
    # Se compara el bando, no el matiz: COMPRA y COMPRA FUERTE son lo mismo
    # a la hora de decidir si comprar.
    bando = lambda v: v.replace(" FUERTE", "")
    coinciden = bando(propio) == bando(ajeno)

    def num(v):
        if v is None or not np.isfinite(v):
            return None
        return round(float(v), 2 if abs(v) >= 10 else 4)

    return {
        "veredicto": ajeno,
        "promedio": inv["promedio"],
        "coincide": coinciden,
        "osciladores": inv["osciladores"],
        "medias": inv["medias"],
        "filas": [{"nombre": f["nombre"], "valor": num(f["valor"]), "senal": f["senal"]}
                  for f in inv["filas_osciladores"]],
        "filas_medias": [{"nombre": f["nombre"], "valor": num(f["valor"]),
                          "senal": f["senal"]}
                         for f in inv["filas_medias"]],
    }


def _aptitud(base: dict, diag: dict) -> dict:
    """Resume en una frase si el par stop/objetivo le sienta bien a este activo.

    Es lo mas util del backtest y estaba enterrado en una tabla plegada. Un
    profit factor menor a 1 significa que, historicamente, entrar con estos
    numeros en este activo perdio plata aun entrando en cualquier vela.
    """
    pf = base.get("profit_factor")
    tp = base.get("toco_objetivo_pct") or 0
    sl = base.get("toco_stop_pct") or 0
    stop_atr = (diag or {}).get("stop_en_atr")

    if pf is None:
        return {"nivel": "sin_datos", "texto": "sin historial suficiente"}

    # Con un objetivo del doble que el stop, el punto de equilibrio es ganar una
    # de cada tres. El profit factor solo no alcanza: un activo puede tener PF
    # 1.1 acertando el 22% de las veces, y eso en la practica es saltar el stop
    # tres de cada cuatro operaciones. Se miran las dos cosas.
    ratio = sl / tp if tp > 0 else 99
    if pf >= 1.5 and tp >= 38 and ratio <= 1.4:
        nivel = "buena"
        texto = f"funciona bien acá: llegó al objetivo el {tp:.0f}% de las veces contra {sl:.0f}% de stops"
    elif pf >= 1.15 and tp >= 30 and ratio <= 1.8:
        nivel = "aceptable"
        texto = f"funciona, con margen justo: {tp:.0f}% llega al objetivo, {sl:.0f}% salta el stop"
    elif pf >= 0.95:
        nivel = "neutra"
        texto = (f"apenas empata: salta el stop {sl:.0f}% de las veces y llega al objetivo {tp:.0f}%. "
                 f"Las ganadoras compensan, pero se sufre mucho en el medio")
    else:
        nivel = "mala"
        texto = (f"pierde históricamente en este activo: saltó el stop el {sl:.0f}% de las veces "
                 f"y llegó al objetivo solo el {tp:.0f}%. Conviene otro stop u objetivo")

    aviso_stop = None
    if stop_atr is not None and stop_atr < 1.5:
        aviso_stop = f"el stop equivale a {stop_atr:.1f} ATR: queda dentro del ruido normal del activo"
    elif stop_atr is not None and stop_atr > 4:
        aviso_stop = f"el stop equivale a {stop_atr:.1f} ATR: demasiado holgado para este activo, se puede ajustar"
    return {"nivel": nivel, "texto": texto, "pf": pf, "aviso_stop": aviso_stop}


def _backtest(r: dict) -> dict | None:
    bt = r.get("backtest")
    if not bt or not bt["base"].get("operaciones"):
        return None
    base = bt["base"]
    diag = r.get("diagnostico_stop", {})
    return {
        "aptitud": _aptitud(base, diag),
        "config": bt["config"],
        "base": {k: base.get(k) for k in
                 ("operaciones", "toco_objetivo_pct", "toco_stop_pct",
                  "retorno_medio_pct", "profit_factor", "mae_p80_ganadoras_pct")},
        "senales": [{k: s.get(k) for k in
                     ("senal", "operaciones", "toco_objetivo_pct", "toco_stop_pct",
                      "profit_factor", "ventaja_pp")}
                    for s in bt["senales"][:5]],
        "diagnostico": {k: diag.get(k) for k in
                        ("stop_en_atr", "objetivo_en_atr", "volatilidad_anual_pct")},
    }


def activo(res: dict, cfg: dict, meta: dict, previo: dict) -> dict:
    """Un activo completo: el consenso y cada temporalidad."""
    pcfg = cfg.get("panel", {})
    velas_g = pcfg.get("velas_grafico", 120)
    medias = tuple(cfg.get("parametros", {}).get("medias_pullback", [9, 20]))

    ticker = res["ticker"]
    antes = (previo or {}).get(ticker, {}).get("veredicto")
    ahora = res["consenso"]["veredicto"]

    return {
        "ticker": ticker,
        "nombre": meta.get("nombre", ticker),
        "grupo": meta.get("grupo", "otro"),
        "consenso": res["consenso"],
        "fondo": res.get("tendencia_fondo"),
        "cambio": antes if antes and antes != ahora else None,
        "errores": list(res["errores"]),
        "tf": {tf: temporalidad(r, velas_g, medias)
               for tf, r in res["temporalidades"].items()},
    }
