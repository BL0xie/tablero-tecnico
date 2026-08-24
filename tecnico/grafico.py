"""Miniaturas en SVG para las listas.

El grafico grande lo dibuja el navegador sobre canvas, para que se le pueda
hacer zoom. Aca solo queda la miniatura de cierre, que es estatica y conviene
resolver de una vez en el servidor.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import calculo as ind

ANCHO = 760
ALTO = 250
MARGEN_IZQ = 6
MARGEN_DER = 62
MARGEN_SUP = 12
MARGEN_INF = 22


def _escala(valor, v_min, v_max, alto_util, margen_sup):
    """Precio -> coordenada Y (el SVG crece hacia abajo)."""
    if v_max <= v_min:
        return margen_sup + alto_util / 2
    return margen_sup + alto_util * (v_max - valor) / (v_max - v_min)


def _fmt_precio(v: float) -> str:
    if v >= 1000:
        return f"{v:,.0f}"
    if v >= 10:
        return f"{v:,.2f}"
    return f"{v:,.3f}"


def sparkline_svg(df: pd.DataFrame, n: int = 40, ancho: int = 104,
                  alto: int = 26) -> str:
    """Miniatura de cierre para la tabla comparativa."""
    serie = df["Close"].tail(n).dropna()
    if len(serie) < 3:
        return ""
    v_min, v_max = float(serie.min()), float(serie.max())
    rango = v_max - v_min or v_max * 0.01
    paso = ancho / (len(serie) - 1)

    puntos = [(i * paso, alto - 2 - (float(v) - v_min) / rango * (alto - 4))
              for i, v in enumerate(serie)]
    linea = " ".join(f"{x:.1f},{y:.1f}" for x, y in puntos)
    area = f"0,{alto} {linea} {ancho},{alto}"
    sube = float(serie.iloc[-1]) >= float(serie.iloc[0])
    clase = "alza" if sube else "baja"
    ux, uy = puntos[-1]

    return (f'<svg viewBox="0 0 {ancho} {alto}" class="spark {clase}" '
            f'aria-hidden="true"><polygon points="{area}" class="spark-area"/>'
            f'<polyline points="{linea}" class="spark-linea"/>'
            f'<circle cx="{ux:.1f}" cy="{uy:.1f}" r="2.1" class="spark-punto"/></svg>')
