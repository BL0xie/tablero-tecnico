"""Deteccion de soportes, resistencias y niveles operables.

De aca salen las zonas concretas de entrada: donde rebota (soporte) y donde
cae o frena (resistencia). Combina cuatro fuentes independientes:

  1. Pivotes de swing agrupados en zonas por cercania (los toques historicos).
  2. Puntos pivote clasicos y de Fibonacci del ultimo periodo cerrado.
  3. Retrocesos de Fibonacci del ultimo tramo relevante.
  4. Niveles dinamicos: medias moviles, bandas de Bollinger y canal de Donchian.

Cada zona lleva una fuerza de 0 a 100 que pondera cuantas veces se respeto,
que tan reciente es y cuanto volumen se opero ahi.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import calculo as ind


@dataclass
class Zona:
    """Un nivel de precio operable."""
    precio: float
    tipo: str                      # "soporte" | "resistencia"
    fuerza: float                  # 0-100
    origen: str                    # de donde salio
    toques: int = 0
    detalle: dict = field(default_factory=dict)

    def distancia_pct(self, precio_actual: float) -> float:
        return 100 * (self.precio - precio_actual) / precio_actual


# --------------------------------------------------------------------------
# 1. Pivotes de swing agrupados en zonas
# --------------------------------------------------------------------------
def pivotes_swing(df: pd.DataFrame, ventana: int = 5) -> tuple[pd.Series, pd.Series]:
    """Maximos y minimos que dominan `ventana` velas a cada lado."""
    alto, bajo = df["High"], df["Low"]
    es_max = alto == alto.rolling(2 * ventana + 1, center=True, min_periods=1).max()
    es_min = bajo == bajo.rolling(2 * ventana + 1, center=True, min_periods=1).min()
    return alto.where(es_max).dropna(), bajo.where(es_min).dropna()


def zonas_por_toques(df: pd.DataFrame, ventana: int = 5, tolerancia_atr: float = 0.5,
                     max_zonas: int = 6) -> list[Zona]:
    """Agrupa pivotes cercanos entre si: varios toques al mismo precio = zona fuerte."""
    if len(df) < 3 * ventana:
        return []

    maximos, minimos = pivotes_swing(df, ventana)
    atr_actual = ind.atr(df, 14).iloc[-1]
    if not np.isfinite(atr_actual) or atr_actual <= 0:
        atr_actual = df["Close"].iloc[-1] * 0.01
    tolerancia = atr_actual * tolerancia_atr

    precio = float(df["Close"].iloc[-1])
    n = len(df)
    zonas: list[Zona] = []

    for serie, tipo in ((minimos, "soporte"), (maximos, "resistencia")):
        if serie.empty:
            continue
        puntos = sorted(zip(serie.to_numpy(), serie.index), key=lambda x: x[0])
        grupo: list = [puntos[0]]

        for p in puntos[1:] + [(np.inf, None)]:
            if p[0] - grupo[-1][0] <= tolerancia:
                grupo.append(p)
                continue

            valores = np.array([g[0] for g in grupo])
            fechas = [g[1] for g in grupo]
            centro = float(valores.mean())

            # Recencia: 0 si el ultimo toque fue al principio de la serie, 1 si fue hoy.
            posiciones = [df.index.get_loc(f) for f in fechas]
            recencia = max(posiciones) / max(n - 1, 1)

            # Volumen relativo operado en las velas de los toques.
            vol_medio = df["Volume"].mean()
            vol_zona = df["Volume"].iloc[posiciones].mean() if vol_medio > 0 else 0
            factor_vol = min(vol_zona / vol_medio, 2.0) if vol_medio > 0 else 1.0

            fuerza = min(100.0, (
                min(len(grupo), 5) * 14        # hasta 70 pts por cantidad de toques
                + recencia * 20                # hasta 20 pts por ser reciente
                + factor_vol * 5               # hasta 10 pts por volumen
            ))

            zonas.append(Zona(
                precio=centro, tipo=tipo, fuerza=round(fuerza, 1),
                origen=f"{len(grupo)} toque histórico" if len(grupo) == 1
                       else f"{len(grupo)} toques históricos",
                toques=len(grupo),
                detalle={"ultimo_toque": str(max(fechas).date()),
                         "rango": (round(float(valores.min()), 4),
                                   round(float(valores.max()), 4))},
            ))
            if p[1] is not None:
                grupo = [p]

    # Nos quedamos con las zonas mas fuertes de cada lado del precio actual.
    abajo = sorted([z for z in zonas if z.precio < precio],
                   key=lambda z: (-z.fuerza, precio - z.precio))[:max_zonas]
    arriba = sorted([z for z in zonas if z.precio > precio],
                    key=lambda z: (-z.fuerza, z.precio - precio))[:max_zonas]
    return abajo + arriba


# --------------------------------------------------------------------------
# 2. Puntos pivote (los que muestra Investing.com)
# --------------------------------------------------------------------------
def puntos_pivote(alto: float, bajo: float, cierre: float,
                  metodo: str = "clasico") -> dict[str, float]:
    """Pivotes del ultimo periodo cerrado. Metodos: clasico | fibonacci | camarilla."""
    rango = alto - bajo
    pp = (alto + bajo + cierre) / 3

    if metodo == "fibonacci":
        return {"S3": pp - rango, "S2": pp - 0.618 * rango, "S1": pp - 0.382 * rango,
                "PP": pp,
                "R1": pp + 0.382 * rango, "R2": pp + 0.618 * rango, "R3": pp + rango}
    if metodo == "camarilla":
        return {"S3": cierre - rango * 1.1 / 4, "S2": cierre - rango * 1.1 / 6,
                "S1": cierre - rango * 1.1 / 12, "PP": pp,
                "R1": cierre + rango * 1.1 / 12, "R2": cierre + rango * 1.1 / 6,
                "R3": cierre + rango * 1.1 / 4}

    r1, s1 = 2 * pp - bajo, 2 * pp - alto
    return {"S3": bajo - 2 * (alto - pp), "S2": pp - rango, "S1": s1, "PP": pp,
            "R1": r1, "R2": pp + rango, "R3": alto + 2 * (pp - bajo)}


def zonas_pivote(df: pd.DataFrame, metodo: str = "clasico",
                 agrupar: str | None = None) -> list[Zona]:
    """Pivotes del ultimo periodo. `agrupar` en 'W' o 'ME' los calcula semanal/mensual."""
    if agrupar:
        g = df.resample(agrupar).agg({"High": "max", "Low": "min", "Close": "last"})
        g = g.dropna()
        if len(g) < 2:
            return []
        fila = g.iloc[-2]  # ultimo periodo YA cerrado
    else:
        if len(df) < 2:
            return []
        fila = df.iloc[-2]

    niveles = puntos_pivote(float(fila["High"]), float(fila["Low"]),
                            float(fila["Close"]), metodo)
    precio = float(df["Close"].iloc[-1])
    etiqueta = {"W": "semanal", "ME": "mensual"}.get(agrupar or "", "diario")
    nombre_metodo = {"clasico": "clásico"}.get(metodo, metodo)

    salida = []
    for nombre, valor in niveles.items():
        if not np.isfinite(valor):
            continue
        salida.append(Zona(
            precio=float(valor),
            tipo="soporte" if valor < precio else "resistencia",
            fuerza=55.0 if nombre == "PP" else (45.0 if nombre in ("S1", "R1") else 35.0),
            origen=f"pivote {nombre_metodo} {etiqueta} {nombre}",
            detalle={"nivel": nombre},
        ))
    return salida


# --------------------------------------------------------------------------
# 3. Retrocesos de Fibonacci
# --------------------------------------------------------------------------
def zonas_fibonacci(df: pd.DataFrame, lookback: int = 120) -> list[Zona]:
    """Retrocesos del ultimo tramo relevante dentro de las ultimas `lookback` velas."""
    tramo = df.tail(lookback)
    if len(tramo) < 20:
        return []

    maximo = float(tramo["High"].max())
    minimo = float(tramo["Low"].min())
    rango = maximo - minimo
    if rango <= 0:
        return []

    pos_max = tramo["High"].idxmax()
    pos_min = tramo["Low"].idxmin()
    alcista = pos_min < pos_max  # el tramo subio: los retrocesos son soportes

    precio = float(df["Close"].iloc[-1])
    salida = []
    for ratio in (0.236, 0.382, 0.5, 0.618, 0.786):
        valor = maximo - rango * ratio if alcista else minimo + rango * ratio
        salida.append(Zona(
            precio=valor,
            tipo="soporte" if valor < precio else "resistencia",
            fuerza=60.0 if ratio in (0.5, 0.618) else 40.0,
            origen=f"Fibonacci {ratio:.1%} del tramo {'alcista' if alcista else 'bajista'}",
            detalle={"ratio": ratio, "maximo": round(maximo, 4), "minimo": round(minimo, 4)},
        ))
    return salida


# --------------------------------------------------------------------------
# 4. Niveles dinamicos
# --------------------------------------------------------------------------
def zonas_dinamicas(df: pd.DataFrame, medias: tuple[int, ...] = (20, 50, 200),
                    n_bollinger: int = 20, desv_bollinger: float = 2.0,
                    n_donchian: int = 20) -> list[Zona]:
    """Medias moviles, bandas de Bollinger y canal de Donchian como soporte/resistencia."""
    precio = float(df["Close"].iloc[-1])
    salida = []

    for n in medias:
        if len(df) < n:
            continue
        valor = ind.ema(df["Close"], n).iloc[-1]
        if not np.isfinite(valor):
            continue
        # Las medias largas pesan mas como soporte estructural.
        fuerza = 45.0 + min(n / 200, 1.0) * 25
        salida.append(Zona(
            precio=float(valor),
            tipo="soporte" if valor < precio else "resistencia",
            fuerza=round(fuerza, 1), origen=f"EMA {n}",
            detalle={"periodos": n},
        ))

    if len(df) >= n_bollinger:
        bb = ind.bollinger(df["Close"], n_bollinger, desv_bollinger).iloc[-1]
        for clave, nombre in (("inf", "banda inferior"), ("sup", "banda superior")):
            valor = bb[clave]
            if np.isfinite(valor):
                salida.append(Zona(
                    precio=float(valor),
                    tipo="soporte" if valor < precio else "resistencia",
                    fuerza=50.0, origen=f"Bollinger {nombre} ({n_bollinger},{desv_bollinger})",
                ))

    if len(df) >= n_donchian:
        techo = float(df["High"].tail(n_donchian).max())
        piso = float(df["Low"].tail(n_donchian).min())
        salida.append(Zona(precio=piso, tipo="soporte", fuerza=55.0,
                           origen=f"mínimo de {n_donchian} velas"))
        salida.append(Zona(precio=techo, tipo="resistencia", fuerza=55.0,
                           origen=f"máximo de {n_donchian} velas"))
    return salida


# --------------------------------------------------------------------------
# Consolidacion
# --------------------------------------------------------------------------
_FAMILIAS = (
    ("toque", "toques"), ("pivote", "pivotes"), ("Fibonacci", "fibonacci"),
    ("EMA", "medias"), ("Bollinger", "bollinger"),
    ("máximo de", "rango"), ("mínimo de", "rango"),
)


def _familia(origen: str) -> str:
    """A que metodo pertenece un nivel. Dos niveles de la misma familia no son
    confirmacion independiente: los pivotes S1, PP y R1 salen todos de la misma
    formula, asi que si caen juntos no valen como tres confirmaciones."""
    for clave, nombre in _FAMILIAS:
        if clave in origen:
            return nombre
    return "otro"


def _saturar(total: float, k: float = 75.0) -> float:
    """Lleva la fuerza acumulada a una escala 0-100 con rendimientos decrecientes.

    Sumar linealmente hace que toda zona con tres o cuatro confirmaciones quede
    clavada en 100, y una escala donde todo vale 100 no distingue nada. Esta
    curva deja casi intactos los valores bajos y comprime los altos, asi que las
    zonas realmente excepcionales se separan del resto en vez de empatar arriba.
    """
    return round(float(100 * (1 - np.exp(-max(total, 0.0) / k))), 1)


def _resumir_origen(zonas: list[Zona]) -> str:
    """Descripcion compacta: agrupa por familia en vez de encadenar duplicados."""
    por_familia: dict[str, list[Zona]] = {}
    for z in zonas:
        por_familia.setdefault(_familia(z.origen), []).append(z)

    partes = []
    for familia, grupo in por_familia.items():
        if familia == "toques":
            total = sum(g.toques for g in grupo)
            partes.append(f"{total} toques históricos")
        elif len(grupo) == 1:
            partes.append(grupo[0].origen)
        else:
            partes.append(f"{grupo[0].origen} (+{len(grupo) - 1} del mismo tipo)")
    return " + ".join(partes)


def mapa_de_niveles(df: pd.DataFrame, cfg: dict | None = None) -> list[Zona]:
    """Junta las cuatro fuentes y fusiona los niveles que caen casi en el mismo precio.

    Una zona confirmada por metodos DISTINTOS (por ejemplo el 61.8% de Fibonacci
    que coincide con la EMA 50) es mucho mas confiable que una sola, asi que la
    fuerza se suma con rendimientos decrecientes. La confluencia se cuenta una
    sola vez por familia de indicador, para no inflar zonas donde lo unico que
    pasa es que varios niveles del mismo calculo quedaron pegados.
    """
    cfg = cfg or {}
    zonas: list[Zona] = []
    zonas += zonas_por_toques(df, cfg.get("ventana_swing", 5),
                              cfg.get("tolerancia_atr", 0.5))
    zonas += zonas_pivote(df, cfg.get("metodo_pivote", "clasico"))
    if cfg.get("pivotes_semanales", True):
        zonas += zonas_pivote(df, cfg.get("metodo_pivote", "clasico"), agrupar="W")
    zonas += zonas_fibonacci(df, cfg.get("lookback_fibo", 120))
    zonas += zonas_dinamicas(df, tuple(cfg.get("medias_soporte", (20, 50, 200))),
                             cfg.get("n_bollinger", 20), cfg.get("desv_bollinger", 2.0),
                             cfg.get("n_donchian", 20))

    zonas = [z for z in zonas if np.isfinite(z.precio) and z.precio > 0]
    if not zonas:
        return []

    atr_actual = ind.atr(df, 14).iloc[-1]
    precio = float(df["Close"].iloc[-1])
    if not np.isfinite(atr_actual) or atr_actual <= 0:
        atr_actual = precio * 0.01
    tolerancia = atr_actual * cfg.get("fusion_atr", 0.35)

    zonas.sort(key=lambda z: z.precio)
    fusionadas: list[Zona] = []
    grupo = [zonas[0]]

    for z in zonas[1:] + [Zona(np.inf, "resistencia", 0, "")]:
        if z.precio - grupo[-1].precio <= tolerancia:
            grupo.append(z)
            continue

        if len(grupo) == 1:
            fusionadas.append(grupo[0])
        else:
            pesos = np.array([g.fuerza for g in grupo], dtype=float)
            precios = np.array([g.precio for g in grupo], dtype=float)
            centro = float(np.average(precios, weights=pesos)) if pesos.sum() else float(precios.mean())

            # Una sola contribucion por familia: la mas fuerte de cada una.
            mejor_por_familia: dict[str, float] = {}
            for g in grupo:
                fam = _familia(g.origen)
                mejor_por_familia[fam] = max(mejor_por_familia.get(fam, 0.0), g.fuerza)
            ordenadas = sorted(mejor_por_familia.values(), reverse=True)
            fuerza = ordenadas[0] + sum(ordenadas[1:]) * 0.35

            fusionadas.append(Zona(
                precio=centro,
                tipo="soporte" if centro < precio else "resistencia",
                fuerza=fuerza,   # se normaliza al final, junto con las zonas simples
                origen=_resumir_origen(grupo),
                toques=sum(g.toques for g in grupo),
                detalle={"confluencia": len(mejor_por_familia),
                         "familias": sorted(mejor_por_familia)},
            ))
        if np.isfinite(z.precio):
            grupo = [z]

    # La misma escala para todas: simples y fusionadas quedan comparables.
    for z in fusionadas:
        z.tipo = "soporte" if z.precio < precio else "resistencia"
        z.fuerza = _saturar(z.fuerza, cfg.get("saturacion_fuerza", 75.0))
    return sorted(fusionadas, key=lambda z: z.precio)


def cercanas(zonas: list[Zona], precio: float, tipo: str, n: int = 3,
             max_distancia_pct: float | None = None) -> list[Zona]:
    """Las `n` zonas del tipo pedido mas cercanas al precio actual."""
    cand = [z for z in zonas if z.tipo == tipo]
    if max_distancia_pct is not None:
        cand = [z for z in cand if abs(z.distancia_pct(precio)) <= max_distancia_pct]
    cand.sort(key=lambda z: abs(z.precio - precio))
    return cand[:n]
