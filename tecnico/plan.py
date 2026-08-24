"""Armado del plan operativo: entradas, stop, objetivo y tamano de posicion.

Toma el mapa de niveles y las senales, y las convierte en escenarios concretos:

  REBOTE      comprar contra un soporte cercano
  RUPTURA     comprar la superacion de una resistencia, con volumen
  RETROCESO   comprar el pullback a una media en tendencia alcista
  CAIDA       que pasa si pierde el soporte: donde se frena y donde re-comprar

El stop y el objetivo salen de la configuracion del escenario (por ejemplo
-7% / +14%), pero se cruzan siempre contra la estructura real del grafico y
contra el ATR: un stop que queda dentro del ruido normal del activo se marca
como riesgoso aunque el porcentaje sea el pedido.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import calculo as ind
from .niveles import Zona


@dataclass
class Entrada:
    escenario: str
    direccion: str                  # "largo" | "corto"
    zona_min: float
    zona_max: float
    stop: float
    objetivo: float
    riesgo_pct: float
    beneficio_pct: float
    rr: float
    confianza: float                # 0-100, heuristica de confluencia
    disparador: str
    invalidacion: str
    avisos: list[str] = field(default_factory=list)
    detalle: dict = field(default_factory=dict)

    @property
    def precio_ref(self) -> float:
        return (self.zona_min + self.zona_max) / 2


def _rr(entrada: float, stop: float, objetivo: float) -> tuple[float, float, float]:
    riesgo = abs(entrada - stop) / entrada * 100
    beneficio = abs(objetivo - entrada) / entrada * 100
    return riesgo, beneficio, (beneficio / riesgo if riesgo > 0 else 0.0)


def _calcular_stop(entrada: float, direccion: str, cfg: dict, atr_v: float,
                   zona: Zona | None) -> tuple[float, list[str]]:
    """Devuelve el stop y los avisos si el porcentaje pedido no encaja con el grafico."""
    riesgo = cfg.get("riesgo", {})
    modo = riesgo.get("modo_stop", "porcentaje")
    pct = abs(riesgo.get("stop_pct", 7.0)) / 100
    mult_atr = riesgo.get("stop_atr", 2.0)
    avisos: list[str] = []
    signo = -1 if direccion == "largo" else 1

    stop_pct = entrada * (1 + signo * pct)
    stop_atr = entrada + signo * atr_v * mult_atr

    # Stop de estructura: por fuera del extremo real de la zona, no del centro,
    # para que no lo levante la mecha que formo el soporte.
    colchon = atr_v * riesgo.get("colchon_estructura_atr", 0.35)
    if zona is not None:
        rango = zona.detalle.get("rango")
        extremo = zona.precio
        if rango:
            extremo = rango[0] if direccion == "largo" else rango[1]
        stop_estructura = (extremo - colchon if direccion == "largo" else extremo + colchon)
    else:
        stop_estructura = stop_pct

    opciones = {"porcentaje": stop_pct, "atr": stop_atr, "estructura": stop_estructura}
    stop = opciones.get(modo, stop_pct)

    if modo == "combinado":
        # El mas lejano de los tres: prioriza no ser barrido por ruido.
        stop = min(opciones.values()) if direccion == "largo" else max(opciones.values())

    # Control de coherencia: el stop no deberia caer dentro del ruido normal.
    minimo_atr = riesgo.get("min_stop_atr", 1.2)
    distancia_atr = abs(entrada - stop) / atr_v if atr_v > 0 else np.inf

    if distancia_atr < minimo_atr:
        if modo == "porcentaje":
            # El porcentaje lo eligio quien configuro el perfil: se respeta,
            # pero se avisa que es ajustado para la volatilidad del activo.
            avisos.append(
                f"el stop queda a {distancia_atr:.1f} ATR de la entrada: por debajo de "
                f"{minimo_atr} ATR hay alta chance de que lo barra el ruido normal del "
                f"activo (ATR actual {atr_v:.2f} = {100 * atr_v / entrada:.1f}%)")
        else:
            # Los modos calculados si se corrigen: un stop dentro del ruido no
            # es un stop, es una salida garantizada.
            stop = entrada + signo * atr_v * minimo_atr
            avisos.append(
                f"el stop calculado quedaba a {distancia_atr:.1f} ATR (dentro del ruido "
                f"del activo) y se alejo hasta {minimo_atr} ATR: {stop:.2f}, "
                f"{abs(100 * (stop - entrada) / entrada):.2f}% de riesgo")
    if zona is not None and direccion == "largo" and stop > zona.precio:
        avisos.append(
            f"el stop ({stop:.2f}) queda por ENCIMA del soporte de referencia "
            f"({zona.precio:.2f}): salta antes de que la zona se ponga a prueba")
    return float(stop), avisos


def _calcular_objetivo(entrada: float, stop: float, direccion: str, cfg: dict,
                       resistencias: list[Zona], atr_v: float) -> tuple[float, list[str]]:
    riesgo = cfg.get("riesgo", {})
    modo = riesgo.get("modo_objetivo", "porcentaje")
    pct = abs(riesgo.get("objetivo_pct", 14.0)) / 100
    signo = 1 if direccion == "largo" else -1
    avisos: list[str] = []

    objetivo_pct = entrada * (1 + signo * pct)
    objetivo_rr = entrada + signo * abs(entrada - stop) * riesgo.get("objetivo_rr", 2.0)

    delante = [z for z in resistencias
               if (z.precio > entrada if direccion == "largo" else z.precio < entrada)]
    delante.sort(key=lambda z: abs(z.precio - entrada))

    # Con objetivo por nivel hay que saltear las resistencias demasiado cercanas:
    # la primera que aparece puede estar a un 1% y dejar una relacion absurda
    # frente a un stop del 12%. Se busca la primera que respete el R:R minimo.
    rr_min = riesgo.get("rr_minimo", 1.5)
    riesgo_abs = abs(entrada - stop)
    objetivo_nivel = None
    for z in delante:
        if riesgo_abs > 0 and abs(z.precio - entrada) / riesgo_abs >= rr_min:
            objetivo_nivel = z.precio
            break
    if objetivo_nivel is None and modo == "nivel":
        objetivo_nivel = objetivo_rr
        if delante:
            avisos.append(
                f"ninguna resistencia del gráfico llega al R:R minimo de {rr_min} "
                f"(la más cercana esta en {delante[0].precio:.2f}): el objetivo se "
                f"calculó por R:R en su lugar")

    objetivo = {"porcentaje": objetivo_pct, "rr": objetivo_rr,
                "nivel": objetivo_nivel if objetivo_nivel is not None else objetivo_pct
                }.get(modo, objetivo_pct)

    # Si hay una resistencia fuerte antes del objetivo, conviene saberlo.
    estorbo = [z for z in delante
               if (z.precio < objetivo if direccion == "largo" else z.precio > objetivo)
               and z.fuerza >= riesgo.get("fuerza_estorbo", 60)]
    if estorbo:
        z = estorbo[0]
        avisos.append(
            f"hay {z.tipo} fuerte en {z.precio:.2f} ({z.fuerza:.0f}/100) antes del objetivo "
            f"{objetivo:.2f}: considerar toma parcial ahí")
    return float(objetivo), avisos


def _confianza(base: float, zona: Zona | None, sesgo_valor: float,
               direccion: str, alineado_tendencia: bool, rr: float,
               rr_minimo: float = 1.5) -> float:
    """Score heuristico de confluencia. No es una probabilidad estadistica:
    para eso esta el modulo backtest, que mide frecuencias historicas reales."""
    score = base
    if zona is not None:
        score += zona.fuerza * 0.25
    favor = sesgo_valor if direccion == "largo" else -sesgo_valor
    score += favor * 15
    if alineado_tendencia:
        score += 10
    score += min(rr, 4) * 3

    # Una zona puede tener toda la confluencia del mundo: si la relacion
    # riesgo/beneficio no cierra, la operacion no vale la pena igual.
    if rr_minimo > 0 and 0 < rr < rr_minimo:
        score *= max(0.35, rr / rr_minimo)
    return round(float(np.clip(score, 0, 100)), 1)


def construir(df: pd.DataFrame, zonas: list[Zona], senales: list[dict],
              sesgo: tuple[str, float], cfg: dict) -> list[Entrada]:
    """Genera los escenarios operables para el perfil de configuracion dado."""
    p = cfg.get("parametros", {})
    riesgo = cfg.get("riesgo", {})
    precio = float(df["Close"].iloc[-1])
    atr_v = float(ind.atr(df, p.get("atr", 14)).dropna().iloc[-1]) if len(df) > 20 else precio * 0.02
    if not np.isfinite(atr_v) or atr_v <= 0:
        atr_v = precio * 0.02

    soportes = sorted([z for z in zonas if z.tipo == "soporte"],
                      key=lambda z: -z.precio)
    resistencias = sorted([z for z in zonas if z.tipo == "resistencia"],
                          key=lambda z: z.precio)

    _, sesgo_valor = sesgo
    ema_larga = ind.ema(df["Close"], p.get("tendencia", 50))
    alcista = bool(ema_larga.notna().any() and precio > float(ema_larga.dropna().iloc[-1]))

    max_dist = riesgo.get("max_distancia_entrada_pct", 12.0)
    rr_min = riesgo.get("rr_minimo", 1.5)
    ancho_zona = atr_v * riesgo.get("ancho_zona_atr", 0.4)
    entradas: list[Entrada] = []

    # ---------------- REBOTE en soportes ----------------
    for z in soportes[:riesgo.get("max_soportes", 3)]:
        dist = 100 * (precio - z.precio) / precio
        if dist > max_dist:
            continue
        centro = z.precio
        stop, av_s = _calcular_stop(centro, "largo", cfg, atr_v, z)
        objetivo, av_o = _calcular_objetivo(centro, stop, "largo", cfg, resistencias, atr_v)
        r_pct, b_pct, rr = _rr(centro, stop, objetivo)
        if rr < rr_min:
            av_s.append(f"relación riesgo/beneficio {rr:.2f} por debajo del minimo "
                        f"{rr_min} del perfil")
        entradas.append(Entrada(
            escenario="REBOTE en soporte", direccion="largo",
            zona_min=centro - ancho_zona, zona_max=centro + ancho_zona,
            stop=stop, objetivo=objetivo,
            riesgo_pct=round(r_pct, 2), beneficio_pct=round(b_pct, 2), rr=round(rr, 2),
            confianza=_confianza(35, z, sesgo_valor, "largo", alcista, rr, rr_min),
            disparador=(f"que el precio llegue a la zona y deje vela de rechazo "
                        f"(martillo o cierre por encima de {centro:.2f}) "
                        f"con volumen sobre el promedio"),
            invalidacion=f"cierre por debajo de {stop:.2f}",
            avisos=av_s + av_o,
            detalle={"zona": z.origen, "fuerza_zona": z.fuerza,
                     "distancia_pct": round(-dist, 2), "toques": z.toques},
        ))

    # ---------------- RUPTURA de resistencia ----------------
    for z in resistencias[:riesgo.get("max_resistencias", 2)]:
        dist = 100 * (z.precio - precio) / precio
        if dist > max_dist:
            continue
        gatillo = z.precio + atr_v * riesgo.get("confirmacion_ruptura_atr", 0.25)
        soporte_bajo = [s for s in soportes if s.precio < gatillo]
        stop, av_s = _calcular_stop(gatillo, "largo", cfg, atr_v,
                                    soporte_bajo[0] if soporte_bajo else None)
        resto = [r for r in resistencias if r.precio > z.precio]
        objetivo, av_o = _calcular_objetivo(gatillo, stop, "largo", cfg, resto, atr_v)
        r_pct, b_pct, rr = _rr(gatillo, stop, objetivo)
        if rr < rr_min:
            av_s.append(f"relación riesgo/beneficio {rr:.2f} por debajo del minimo {rr_min}")
        entradas.append(Entrada(
            escenario="RUPTURA de resistencia", direccion="largo",
            zona_min=gatillo, zona_max=gatillo + ancho_zona,
            stop=stop, objetivo=objetivo,
            riesgo_pct=round(r_pct, 2), beneficio_pct=round(b_pct, 2), rr=round(rr, 2),
            confianza=_confianza(30, z, sesgo_valor, "largo", alcista, rr, rr_min),
            disparador=(f"cierre por encima de {gatillo:.2f} con volumen de al menos "
                        f"{p.get('volumen_alto', 1.5)}x el promedio; sin volumen suele ser "
                        f"ruptura falsa"),
            invalidacion=f"volver a cerrar por debajo de {z.precio:.2f}",
            avisos=av_s + av_o,
            detalle={"zona": z.origen, "fuerza_zona": z.fuerza,
                     "distancia_pct": round(dist, 2)},
        ))

    # ---------------- RETROCESO a media en tendencia ----------------
    if alcista:
        for n in p.get("medias_pullback", [20, 50]):
            if len(df) <= n:
                continue
            media = ind.ema(df["Close"], n)
            if not media.notna().any():
                continue
            valor = float(media.dropna().iloc[-1])
            if valor >= precio:
                continue  # la media ya esta por encima: no es pullback
            dist = 100 * (precio - valor) / precio
            if dist > max_dist:
                continue
            zona_ref = Zona(valor, "soporte", 55.0, f"EMA {n}")
            stop, av_s = _calcular_stop(valor, "largo", cfg, atr_v, zona_ref)
            objetivo, av_o = _calcular_objetivo(valor, stop, "largo", cfg, resistencias, atr_v)
            r_pct, b_pct, rr = _rr(valor, stop, objetivo)
            entradas.append(Entrada(
                escenario=f"RETROCESO a EMA {n}", direccion="largo",
                zona_min=valor - ancho_zona, zona_max=valor + ancho_zona,
                stop=stop, objetivo=objetivo,
                riesgo_pct=round(r_pct, 2), beneficio_pct=round(b_pct, 2), rr=round(rr, 2),
                confianza=_confianza(38, zona_ref, sesgo_valor, "largo", True, rr, rr_min),
                disparador=f"que el precio busque la EMA {n} ({valor:.2f}) y la respete "
                           f"con cierre por encima",
                invalidacion=f"cierre por debajo de {stop:.2f}",
                avisos=av_s + av_o,
                detalle={"distancia_pct": round(-dist, 2)},
            ))

    # ---------------- CAIDA: que pasa si pierde el soporte ----------------
    if soportes:
        primero = soportes[0]
        quiebre = primero.precio - atr_v * riesgo.get("confirmacion_ruptura_atr", 0.25)
        siguientes = [s for s in soportes if s.precio < quiebre]
        destino = siguientes[0] if siguientes else None
        caida_pct = (100 * (destino.precio - quiebre) / quiebre) if destino else None

        if riesgo.get("permitir_cortos", False) and destino:
            stop_c, av_c = _calcular_stop(quiebre, "corto", cfg, atr_v, primero)
            objetivo_c, av_o = _calcular_objetivo(quiebre, stop_c, "corto", cfg, soportes, atr_v)
            r_pct, b_pct, rr = _rr(quiebre, stop_c, objetivo_c)
            entradas.append(Entrada(
                escenario="CAIDA: quiebre de soporte", direccion="corto",
                zona_min=quiebre - ancho_zona, zona_max=quiebre,
                stop=stop_c, objetivo=objetivo_c,
                riesgo_pct=round(r_pct, 2), beneficio_pct=round(b_pct, 2), rr=round(rr, 2),
                confianza=_confianza(28, primero, sesgo_valor, "corto", not alcista, rr, rr_min),
                disparador=f"cierre por debajo de {quiebre:.2f} con volumen",
                invalidacion=f"recuperar {primero.precio:.2f}",
                avisos=av_c + av_o,
                detalle={"zona": primero.origen},
            ))
        else:
            # Sin cortos operables, la caida se informa como gestion y re-entrada.
            texto_destino = (f"próximo soporte real en {destino.precio:.2f} "
                             f"({caida_pct:+.1f}% desde el quiebre, fuerza {destino.fuerza:.0f}/100)"
                             if destino else "no hay soporte claro por debajo en el historial cargado")
            entradas.append(Entrada(
                escenario="CAIDA: perdida de soporte (gestion)", direccion="salida",
                zona_min=quiebre, zona_max=primero.precio,
                stop=float("nan"),
                objetivo=destino.precio if destino else float("nan"),
                riesgo_pct=float("nan"), beneficio_pct=float("nan"), rr=float("nan"),
                confianza=_confianza(30, primero, -sesgo_valor, "largo", not alcista, 1.0),
                disparador=f"cierre por debajo de {quiebre:.2f}",
                invalidacion=f"recuperar {primero.precio:.2f} con volumen",
                avisos=[],
                detalle={"nota": f"Si pierde {primero.precio:.2f}, {texto_destino}. "
                                 f"Es el nivel para reducir o esperar más abajo, no para promediar."},
            ))

    entradas = _fusionar_solapadas(entradas, atr_v)
    entradas = _marcar_contexto(entradas, df, cfg)
    entradas.sort(key=lambda e: -e.confianza)
    return entradas


def _fusionar_solapadas(entradas: list[Entrada], atr_v: float) -> list[Entrada]:
    """Junta los escenarios largos cuyas zonas de entrada se pisan.

    "Rebote en el soporte de 41.30" y "retroceso a la EMA 20 en 41.45" son la
    misma operacion contada dos veces. Dejarlas separadas infla la lista y hace
    parecer que hay mas oportunidades de las que hay. Se queda el de mayor
    confianza y hereda el origen del otro como confirmacion extra.
    """
    largos = [e for e in entradas if e.direccion == "largo"]
    otros = [e for e in entradas if e.direccion != "largo"]
    largos.sort(key=lambda e: -e.confianza)

    fusionados: list[Entrada] = []
    for e in largos:
        for f in fusionados:
            # Solapan si sus zonas comparten precio, con medio ATR de margen.
            if e.zona_min <= f.zona_max + atr_v * 0.5 and f.zona_min <= e.zona_max + atr_v * 0.5:
                f.detalle.setdefault("confluencia_extra", []).append(e.escenario)
                # Dos fuentes distintas apuntando a la misma zona suman algo.
                f.confianza = round(min(100.0, f.confianza + 4), 1)
                break
        else:
            fusionados.append(e)

    for f in fusionados:
        extra = f.detalle.get("confluencia_extra")
        if extra:
            f.detalle["confluencia_extra"] = extra
            nombres = ", ".join(dict.fromkeys(x.split(":")[0].lower() for x in extra))
            f.disparador = f"{f.disparador}. Coincide con: {nombres}."
    return fusionados + otros


def _marcar_contexto(entradas: list[Entrada], df: pd.DataFrame, cfg: dict) -> list[Entrada]:
    """Baja la confianza y avisa cuando el momento no acompaña al escenario.

    Un rebote en soporte es buena idea; un rebote en soporte cuando el precio
    viene de subir 25% en cinco ruedas con RSI en 85 es perseguir el precio.
    El escenario sigue siendo valido como nivel, pero no como entrada de hoy.
    """
    p = cfg.get("parametros", {})
    rsi = ind.rsi(df["Close"], p.get("rsi", 14)).dropna()
    if rsi.empty:
        return entradas
    rsi_v = float(rsi.iloc[-1])
    sobrecompra = p.get("rsi_sobrecompra", 70)
    extremo = sobrecompra + 8

    close = df["Close"]
    tramo5 = float(100 * (close.iloc[-1] / close.iloc[-6] - 1)) if len(close) > 6 else 0.0

    for e in entradas:
        if e.direccion != "largo":
            continue
        if rsi_v >= extremo:
            e.confianza = round(e.confianza * 0.7, 1)
            e.avisos.insert(0,
                f"RSI en {rsi_v:.0f}: el activo está sobreextendido. Los niveles valen, "
                f"pero entrar hoy es comprar en el techo; mejor esperar el retroceso a la zona")
        elif tramo5 >= 15:
            e.confianza = round(e.confianza * 0.85, 1)
            e.avisos.insert(0,
                f"subió {tramo5:.0f}% en cinco velas: el movimiento ya corrió bastante, "
                f"conviene esperar que vuelva a la zona en vez de perseguirlo")
    return entradas


def tamano_posicion(entrada: Entrada, cfg: dict) -> dict | None:
    """Cuantos nominales comprar para arriesgar el % de capital definido en el perfil."""
    riesgo = cfg.get("riesgo", {})
    capital = riesgo.get("capital")
    riesgo_op = riesgo.get("riesgo_por_operacion_pct")
    if not capital or not riesgo_op or not np.isfinite(entrada.riesgo_pct) or entrada.riesgo_pct <= 0:
        return None

    monto_riesgo = capital * riesgo_op / 100
    precio = entrada.precio_ref
    perdida_unidad = abs(precio - entrada.stop)
    if perdida_unidad <= 0:
        return None

    unidades = monto_riesgo / perdida_unidad
    invertido = unidades * precio
    tope = riesgo.get("max_posicion_pct")
    aviso = None
    if tope and invertido > capital * tope / 100:
        invertido = capital * tope / 100
        unidades = invertido / precio
        monto_riesgo = unidades * perdida_unidad
        aviso = f"posicion recortada al tope de {tope}% del capital"

    return {
        "unidades": round(unidades, 4),
        "invertido": round(invertido, 2),
        "pct_capital": round(100 * invertido / capital, 2),
        "riesgo_dinero": round(monto_riesgo, 2),
        "ganancia_objetivo": round(unidades * abs(entrada.objetivo - precio), 2)
        if np.isfinite(entrada.objetivo) else None,
        "aviso": aviso,
    }
