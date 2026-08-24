"""Orquestador: toma un perfil de configuracion y produce el analisis completo.

Un perfil es un YAML en config/. Define que temporalidades mirar, con que
parametros, y con que reglas de riesgo. Cambiar de escenario = cambiar de
perfil, sin tocar una linea de codigo.

Los perfiles pueden heredar de otro con `extiende: <nombre>`, asi el escenario
de corto plazo solo declara lo que lo diferencia del base.
"""
from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import backtest, calculo as ind, datos, niveles, plan, rating

RAIZ = Path(__file__).resolve().parent.parent
DIR_CONFIG = RAIZ / "config"


# --------------------------------------------------------------------------
# Perfiles
# --------------------------------------------------------------------------
def _fusionar(base: dict, encima: dict) -> dict:
    """Merge recursivo: lo del hijo pisa lo del padre, clave por clave."""
    out = copy.deepcopy(base)
    for k, v in encima.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _fusionar(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def cargar_perfil(nombre: str, _vistos: set | None = None) -> dict:
    """Carga un perfil resolviendo la cadena de herencia."""
    _vistos = _vistos or set()
    if nombre in _vistos:
        raise ValueError(f"herencia circular de perfiles en '{nombre}'")
    _vistos.add(nombre)

    ruta = Path(nombre)
    if not ruta.exists():
        ruta = DIR_CONFIG / f"{nombre}.yaml"
    if not ruta.exists():
        disponibles = sorted(p.stem for p in DIR_CONFIG.glob("*.yaml"))
        raise FileNotFoundError(
            f"no encontre el perfil '{nombre}'. Disponibles: {', '.join(disponibles)}")

    cfg = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    padre = cfg.pop("extiende", None)
    if padre:
        cfg = _fusionar(cargar_perfil(padre, _vistos), cfg)
    cfg.setdefault("nombre", ruta.stem)
    return cfg


def perfiles_disponibles() -> list[str]:
    return sorted(p.stem for p in DIR_CONFIG.glob("*.yaml"))


# --------------------------------------------------------------------------
# Analisis de un ticker en una temporalidad
# --------------------------------------------------------------------------
def analizar_temporalidad(ticker: str, intervalo: str, cfg: dict,
                          csv: str | None = None, usar_cache: bool = True) -> dict:
    df = datos.obtener(ticker, intervalo, csv=csv, usar_cache=usar_cache)
    minimo = cfg.get("min_velas", 60)
    if len(df) < minimo:
        raise datos.ErrorDatos(
            f"{ticker} {intervalo}: solo {len(df)} velas, hacen falta {minimo} "
            f"para que los indicadores largos tengan sentido")

    p = cfg.get("parametros", {})
    close = df["Close"]
    precio = float(close.iloc[-1])

    osc = rating.evaluar_osciladores(df, cfg)
    med = rating.evaluar_medias(df, cfg)
    resumen = rating.resumen_general(osc, med, cfg.get("peso_osciladores", 0.5),
                                     df=df, cfg=cfg)

    senales = rating.senales_clave(df, cfg)
    sesgo = rating.sesgo_de_senales(senales)

    zonas = niveles.mapa_de_niveles(df, cfg.get("niveles", {}))
    entradas = plan.construir(df, zonas, senales, sesgo, cfg)
    for e in entradas:
        e.detalle["posicion"] = plan.tamano_posicion(e, cfg)

    # Contexto de precio y volatilidad
    atr_serie = ind.atr(df, p.get("atr", 14))
    atr_v = float(atr_serie.dropna().iloc[-1]) if atr_serie.notna().any() else np.nan
    variaciones = {}
    for etiqueta, n in (("1 vela", 1), ("5 velas", 5), ("20 velas", 20), ("60 velas", 60)):
        if len(close) > n:
            variaciones[etiqueta] = round(float(100 * (close.iloc[-1] / close.iloc[-1 - n] - 1)), 2)

    resultado = {
        "ticker": ticker,
        "intervalo": intervalo,
        "precio": precio,
        "fecha_dato": str(df.index[-1]),
        "velas": len(df),
        "variaciones_pct": variaciones,
        "atr": round(atr_v, 4) if np.isfinite(atr_v) else None,
        "atr_pct": round(100 * atr_v / precio, 2) if np.isfinite(atr_v) else None,
        "volumen_relativo": None,
        "osciladores": osc,
        "medias": med,
        "resumen": resumen,
        "senales": senales,
        "sesgo": sesgo,
        "zonas": zonas,
        "entradas": entradas,
        "df": df,
    }

    if len(df) >= 20:
        vr = ind.volumen_relativo(df, p.get("volumen_media", 20))
        if vr.notna().any():
            resultado["volumen_relativo"] = round(float(vr.dropna().iloc[-1]), 2)

    # Validacion historica del par stop/objetivo
    if cfg.get("backtest", {}).get("activo", True):
        r = cfg.get("riesgo", {})
        bcfg = cfg.get("backtest", {})
        tp = abs(r.get("objetivo_pct", 14.0))
        sl = abs(r.get("stop_pct", 7.0))
        horizonte = bcfg.get("max_velas", 20)
        try:
            resultado["backtest"] = backtest.evaluar_todo(
                df, cfg, tp, sl, horizonte, bcfg.get("min_operaciones", 8))
            resultado["diagnostico_stop"] = backtest.diagnostico_stop(
                df, sl, tp, horizonte, intervalo)
        except Exception as e:
            resultado["backtest_error"] = str(e)

    return resultado


def analizar(ticker: str, cfg: dict, csv: str | None = None,
             usar_cache: bool = True) -> dict:
    """Corre el perfil completo sobre un ticker, en todas sus temporalidades."""
    temporalidades = cfg.get("temporalidades", ["1d"])
    por_tf: dict[str, dict] = {}
    errores: dict[str, str] = {}

    for tf in temporalidades:
        try:
            por_tf[tf] = analizar_temporalidad(ticker, tf, cfg, csv, usar_cache)
        except Exception as e:
            errores[tf] = str(e)

    if not por_tf:
        raise datos.ErrorDatos(
            f"{ticker}: ninguna temporalidad pudo analizarse ({errores})")

    return {
        "ticker": ticker,
        "perfil": cfg.get("nombre", "sin nombre"),
        "generado": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "temporalidades": por_tf,
        "errores": errores,
        "consenso": _consenso(por_tf, cfg),
        "config": cfg,
    }


def _consenso(por_tf: dict[str, dict], cfg: dict) -> dict:
    """Combina las temporalidades. Las mas largas pesan mas: marcan el contexto."""
    pesos_cfg = cfg.get("pesos_temporalidad", {})
    orden = {"1m": 1, "5m": 2, "15m": 3, "30m": 4, "60m": 5, "1h": 5,
             "1d": 6, "1wk": 7, "1mo": 8}

    total_peso = 0.0
    acumulado = 0.0
    detalle = {}
    for tf, r in por_tf.items():
        peso = float(pesos_cfg.get(tf, orden.get(tf, 5)))
        prom = r["resumen"]["promedio"]
        acumulado += prom * peso
        total_peso += peso
        detalle[tf] = {"veredicto": r["resumen"]["veredicto"], "promedio": prom,
                       "peso": peso, "sesgo_senales": r["sesgo"][0]}

    prom = acumulado / total_peso if total_peso else 0.0
    veredictos = [r["resumen"]["veredicto"] for r in por_tf.values()]
    alineadas = len(set(v.replace(" FUERTE", "") for v in veredictos)) == 1

    return {
        "promedio": round(prom, 3),
        "veredicto": rating.veredicto(prom),
        "temporalidades_alineadas": alineadas,
        "detalle": detalle,
    }


def analizar_lista(tickers: list[str], cfg: dict, usar_cache: bool = True,
                   al_terminar=None) -> tuple[list[dict], dict[str, str]]:
    """Corre el perfil sobre varios tickers. Un ticker que falla no corta el lote."""
    resultados, fallos = [], {}
    for t in tickers:
        try:
            r = analizar(t, cfg, usar_cache=usar_cache)
            resultados.append(r)
            if al_terminar:
                al_terminar(t, r, None)
        except Exception as e:
            fallos[t] = str(e)
            if al_terminar:
                al_terminar(t, None, e)
    return resultados, fallos
