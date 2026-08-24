"""Salida del analisis: consola, HTML con grafico y Excel.

La consola es para mirar rapido antes de operar. El HTML es el informe
completo con el grafico y los niveles dibujados. El Excel es para que Damian
siga trabajando los numeros a mano si quiere.
"""
from __future__ import annotations

import html as _html
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import calculo as ind

RAIZ = Path(__file__).resolve().parent.parent
SALIDAS = RAIZ / "salidas"

COLOR = {
    "COMPRA FUERTE": "bold green", "COMPRA": "green", "NEUTRAL": "yellow",
    "VENTA": "red", "VENTA FUERTE": "bold red", "SIN DATOS": "dim",
    "alcista": "green", "bajista": "red", "neutral": "yellow",
}
HEX = {
    "COMPRA FUERTE": "#0a7d3f", "COMPRA": "#2e9e5b", "NEUTRAL": "#b08900",
    "VENTA": "#d1495b", "VENTA FUERTE": "#a4133c", "SIN DATOS": "#888",
}


def _consola_unicode() -> bool:
    """La consola de Windows suele venir en cp1252 y no puede imprimir flechas."""
    return "utf" in (getattr(sys.stdout, "encoding", "") or "").lower()


# Simbolos con alternativa ASCII, para que la salida no dependa del codepage.
if _consola_unicode():
    SIM = {"sube": "▲", "baja": "▼", "igual": "●", "aviso": "⚠",
           "aqui": "→", "raya": "─", "guion": "–"}
else:
    SIM = {"sube": "^", "baja": "v", "igual": "*", "aviso": "!",
           "aqui": ">", "raya": "-", "guion": "-"}


def _fmt(v, dec=2, vacio="-"):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return vacio
    return f"{v:,.{dec}f}"


# ==========================================================================
# CONSOLA
# ==========================================================================
def a_consola(res: dict, consola: Console | None = None, detalle: bool = False) -> None:
    c = consola or Console()
    cfg = res["config"]
    cons = res["consenso"]

    c.print()
    c.rule(f"[bold]{res['ticker']}[/bold]  ·  perfil: {res['perfil']}  ·  {res['generado']}")

    # ---- consenso ----
    linea = Text()
    linea.append("VEREDICTO GENERAL: ", style="bold")
    linea.append(cons["veredicto"], style=COLOR.get(cons["veredicto"], "white"))
    linea.append(f"   (score {cons['promedio']:+.2f} de -1 a +1)")
    if not cons["temporalidades_alineadas"] and len(cons["detalle"]) > 1:
        linea.append("\nLas temporalidades NO estan alineadas: senal mas debil.",
                     style="yellow")
    c.print(Panel(linea, border_style=COLOR.get(cons["veredicto"], "white")))

    for tf, r in res["temporalidades"].items():
        _temporalidad_consola(c, tf, r, cfg, detalle)

    if res["errores"]:
        for tf, e in res["errores"].items():
            c.print(f"[yellow]No se pudo analizar {tf}: {e}[/yellow]")

    c.print("\n[dim]Analisis tecnico automatizado sobre datos historicos. "
            "No es recomendacion de inversion: el rendimiento pasado no garantiza "
            "resultados futuros.[/dim]\n")


def _temporalidad_consola(c: Console, tf: str, r: dict, cfg: dict, detalle: bool) -> None:
    resumen = r["resumen"]
    c.print()
    raya = SIM["raya"] * 2
    c.print(f"[bold cyan]{raya} {tf} {raya}[/bold cyan]  precio [bold]{_fmt(r['precio'])}[/bold]"
            f"   ATR {_fmt(r['atr'])} ({_fmt(r['atr_pct'])}%)"
            f"   dato: {r['fecha_dato'][:16]}   velas: {r['velas']}")

    if r["variaciones_pct"]:
        var = "   ".join(f"{k}: {v:+.2f}%" for k, v in r["variaciones_pct"].items())
        c.print(f"  [dim]variacion  {var}[/dim]")
    if r.get("volumen_relativo"):
        c.print(f"  [dim]volumen: {r['volumen_relativo']}x el promedio de "
                f"{cfg.get('parametros', {}).get('volumen_media', 20)} velas[/dim]")

    # ---- resumen tecnico estilo Investing ----
    t = Table(box=None, pad_edge=False, show_header=True, header_style="dim")
    t.add_column("bloque"); t.add_column("compra", justify="right")
    t.add_column("neutral", justify="right"); t.add_column("venta", justify="right")
    t.add_column("veredicto")
    for nombre, blq in (("Osciladores", resumen["osciladores"]), ("Medias moviles", resumen["medias"])):
        t.add_row(nombre, f"[green]{blq['compra']}[/green]", str(blq["neutral"]),
                  f"[red]{blq['venta']}[/red]",
                  Text(blq["veredicto"], style=COLOR.get(blq["veredicto"], "white")))
    t.add_row("[bold]RESUMEN[/bold]", "", "", "",
              Text(resumen["veredicto"], style=COLOR.get(resumen["veredicto"], "white")))
    c.print(t)

    if detalle:
        _detalle_indicadores(c, r)

    # ---- senales ----
    if r["senales"]:
        sesgo, valor = r["sesgo"]
        c.print(f"\n  [bold]Senales activas[/bold]  "
                f"(sesgo neto: [{COLOR.get(sesgo)}]{sesgo}[/{COLOR.get(sesgo)}] {valor:+.2f})")
        for s in sorted(r["senales"], key=lambda x: -x["peso"]):
            marca = {"alcista": f"[green]{SIM['sube']}[/green]",
                     "bajista": f"[red]{SIM['baja']}[/red]"}.get(
                s["sesgo"], f"[yellow]{SIM['igual']}[/yellow]")
            c.print(f"    {marca} {s['detalle']}")
    else:
        c.print("\n  [dim]Sin senales relevantes en las ultimas velas.[/dim]")

    # ---- niveles ----
    _niveles_consola(c, r)

    # ---- plan ----
    _plan_consola(c, r, cfg)

    # ---- backtest ----
    if "backtest" in r:
        _backtest_consola(c, r, cfg)


def _detalle_indicadores(c: Console, r: dict) -> None:
    for titulo, lecturas in (("Osciladores", r["osciladores"]), ("Medias moviles", r["medias"])):
        t = Table(title=f"  {titulo}", box=None, title_justify="left",
                  title_style="bold", pad_edge=False)
        t.add_column("indicador"); t.add_column("valor", justify="right")
        t.add_column("senal"); t.add_column("nota", style="dim")
        for l in lecturas:
            t.add_row(l.nombre, _fmt(l.valor, 2),
                      Text(l.senal, style=COLOR.get(l.senal.title(), "white")
                           if l.senal == "NEUTRAL" else ("green" if l.senal == "COMPRA" else "red")),
                      l.nota)
        c.print(t)


def _niveles_consola(c: Console, r: dict) -> None:
    precio = r["precio"]
    zonas = r["zonas"]
    if not zonas:
        return
    resis = sorted([z for z in zonas if z.tipo == "resistencia"], key=lambda z: z.precio)[:4]
    sopor = sorted([z for z in zonas if z.tipo == "soporte"], key=lambda z: -z.precio)[:4]

    c.print("\n  [bold]Niveles[/bold]  [dim](fuerza 0-100: cuantas fuentes y toques confirman la zona)[/dim]")
    t = Table(box=None, pad_edge=False, header_style="dim")
    t.add_column(" "); t.add_column("precio", justify="right")
    t.add_column("dist.", justify="right"); t.add_column("fuerza", justify="right")
    t.add_column("origen", style="dim", max_width=52)

    for z in reversed(resis):
        t.add_row("[red]R[/red]", _fmt(z.precio), f"{z.distancia_pct(precio):+.2f}%",
                  f"{z.fuerza:.0f}", z.origen)
    t.add_row(f"[bold]{SIM['aqui']}[/bold]", f"[bold]{_fmt(precio)}[/bold]",
              "[bold]precio[/bold]", "", "")
    for z in sopor:
        t.add_row("[green]S[/green]", _fmt(z.precio), f"{z.distancia_pct(precio):+.2f}%",
                  f"{z.fuerza:.0f}", z.origen)
    c.print(t)


def _plan_consola(c: Console, r: dict, cfg: dict) -> None:
    entradas = r["entradas"]
    if not entradas:
        c.print("\n  [dim]Sin escenarios de entrada dentro del rango de distancia del perfil.[/dim]")
        return

    c.print("\n  [bold]Escenarios operables[/bold]")
    for e in entradas:
        estilo = "green" if e.direccion == "largo" else ("red" if e.direccion == "corto" else "yellow")
        cab = Text()
        cab.append(f"{e.escenario}", style=f"bold {estilo}")
        cab.append(f"   confianza {e.confianza:.0f}/100")

        cuerpo = Text()
        if e.direccion == "salida":
            cuerpo.append(f"  Nivel de quiebre: {_fmt(e.zona_min)}  "
                          f"(soporte en {_fmt(e.zona_max)})\n")
            cuerpo.append(f"  {e.detalle.get('nota', '')}\n", style="dim")
        else:
            cuerpo.append(f"  Zona de entrada: {_fmt(e.zona_min)} {SIM['guion']} {_fmt(e.zona_max)}"
                          f"   ({100 * (e.precio_ref - r['precio']) / r['precio']:+.2f}% del precio actual)\n")
            cuerpo.append(f"  Stop: {_fmt(e.stop)}  ({e.riesgo_pct:.2f}% de riesgo)"
                          f"   Objetivo: {_fmt(e.objetivo)}  (+{e.beneficio_pct:.2f}%)"
                          f"   R:R = {e.rr:.2f}\n")
            pos = e.detalle.get("posicion")
            if pos:
                cuerpo.append(f"  Posicion: {pos['unidades']:,.2f} nominales "
                              f"({_fmt(pos['invertido'])} = {pos['pct_capital']:.1f}% del capital), "
                              f"riesgo {_fmt(pos['riesgo_dinero'])}\n", style="cyan")
        cuerpo.append(f"  Disparador: {e.disparador}\n", style="dim")
        cuerpo.append(f"  Se invalida si: {e.invalidacion}", style="dim")
        for a in e.avisos:
            cuerpo.append(f"\n  {SIM['aviso']} {a}", style="yellow")

        c.print(Panel(cuerpo, title=cab, title_align="left", border_style=estilo,
                      padding=(0, 1)))


def _backtest_consola(c: Console, r: dict, cfg: dict) -> None:
    bt = r["backtest"]
    base = bt["base"]
    if not base.get("operaciones"):
        return
    conf = bt["config"]
    diag = r.get("diagnostico_stop", {})

    c.print(f"\n  [bold]Validacion historica[/bold]  [dim](+{conf['tp_pct']:.0f}% antes de "
            f"-{conf['sl_pct']:.0f}%, dentro de {conf['max_velas']} velas, "
            f"sobre {base['operaciones']} entradas simuladas)[/dim]")

    t = Table(box=None, pad_edge=False, header_style="dim")
    t.add_column("caso", max_width=38); t.add_column("n", justify="right")
    t.add_column("llego al +%", justify="right"); t.add_column("salto el stop", justify="right")
    t.add_column("retorno medio", justify="right"); t.add_column("PF", justify="right")
    t.add_column("vs base", justify="right")

    t.add_row("[bold]entrando en cualquier vela (base)[/bold]", str(base["operaciones"]),
              f"{base['toco_objetivo_pct']:.1f}%", f"{base['toco_stop_pct']:.1f}%",
              f"{base['retorno_medio_pct']:+.2f}%", f"{base['profit_factor']:.2f}",
              SIM["guion"])

    for s in bt["senales"][:6]:
        color = "green" if s["ventaja_pp"] > 0 else "red"
        t.add_row(s["senal"], str(s["operaciones"]), f"{s['toco_objetivo_pct']:.1f}%",
                  f"{s['toco_stop_pct']:.1f}%", f"{s['retorno_medio_pct']:+.2f}%",
                  f"{s['profit_factor']:.2f}",
                  f"[{color}]{s['ventaja_pp']:+.1f} pp[/{color}]")
    c.print(t)

    if diag:
        c.print(f"  [dim]El stop de {conf['sl_pct']:.0f}% equivale a {diag.get('stop_en_atr', 0):.1f} ATR "
                f"y el objetivo de {conf['tp_pct']:.0f}% a {diag.get('objetivo_en_atr', 0):.1f} ATR. "
                f"Volatilidad anualizada: {diag.get('volatilidad_anual_pct')}%.[/dim]")
        mae = base.get("mae_p80_ganadoras_pct")
        if mae:
            c.print(f"  [dim]De las operaciones que terminaron ganando, el 80% nunca cayo mas de "
                    f"{abs(mae):.1f}% en contra: es la referencia para saber si el stop de "
                    f"{conf['sl_pct']:.0f}% esta holgado o justo.[/dim]")


# ==========================================================================
# EXCEL
# ==========================================================================
def a_excel(res: dict, ruta: Path | str | None = None) -> Path:
    SALIDAS.mkdir(exist_ok=True)
    ruta = Path(ruta) if ruta else SALIDAS / f"{res['ticker']}_{res['perfil']}.xlsx"

    with pd.ExcelWriter(ruta, engine="openpyxl") as xls:
        filas = [{"campo": "Ticker", "valor": res["ticker"]},
                 {"campo": "Perfil", "valor": res["perfil"]},
                 {"campo": "Generado", "valor": res["generado"]},
                 {"campo": "Veredicto general", "valor": res["consenso"]["veredicto"]},
                 {"campo": "Score (-1 a +1)", "valor": res["consenso"]["promedio"]}]
        for tf, d in res["consenso"]["detalle"].items():
            filas.append({"campo": f"Veredicto {tf}", "valor": d["veredicto"]})
        pd.DataFrame(filas).to_excel(xls, sheet_name="Resumen", index=False)

        for tf, r in res["temporalidades"].items():
            suf = tf.replace(" ", "")

            ind_filas = [{"bloque": b, "indicador": l.nombre, "valor": l.valor,
                          "senal": l.senal, "nota": l.nota}
                         for b, lst in (("Oscilador", r["osciladores"]),
                                        ("Media movil", r["medias"])) for l in lst]
            pd.DataFrame(ind_filas).to_excel(xls, sheet_name=f"Indicadores {suf}"[:31], index=False)

            pd.DataFrame([{
                "tipo": z.tipo, "precio": round(z.precio, 4),
                "distancia_%": round(z.distancia_pct(r["precio"]), 2),
                "fuerza": z.fuerza, "toques": z.toques, "origen": z.origen,
            } for z in sorted(r["zonas"], key=lambda z: -z.precio)]
            ).to_excel(xls, sheet_name=f"Niveles {suf}"[:31], index=False)

            pd.DataFrame([{
                "escenario": e.escenario, "direccion": e.direccion,
                "zona_min": round(e.zona_min, 4), "zona_max": round(e.zona_max, 4),
                "stop": round(e.stop, 4) if np.isfinite(e.stop) else None,
                "objetivo": round(e.objetivo, 4) if np.isfinite(e.objetivo) else None,
                "riesgo_%": e.riesgo_pct, "beneficio_%": e.beneficio_pct, "R:R": e.rr,
                "confianza": e.confianza, "disparador": e.disparador,
                "invalidacion": e.invalidacion, "avisos": " | ".join(e.avisos),
            } for e in r["entradas"]]).to_excel(xls, sheet_name=f"Plan {suf}"[:31], index=False)

            if r["senales"]:
                pd.DataFrame(r["senales"]).to_excel(xls, sheet_name=f"Senales {suf}"[:31], index=False)

            if "backtest" in r and r["backtest"]["base"].get("operaciones"):
                bt = r["backtest"]
                base = dict(bt["base"]); base["senal"] = "BASE (cualquier vela)"
                pd.DataFrame([base] + bt["senales"]).to_excel(
                    xls, sheet_name=f"Backtest {suf}"[:31], index=False)
    return ruta


# ==========================================================================
# HTML
# ==========================================================================
def _grafico(r: dict, cfg: dict) -> str:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    n = cfg.get("salida", {}).get("grafico_velas", 180)
    df = r["df"].tail(n)
    p = cfg.get("parametros", {})

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        row_heights=[0.62, 0.19, 0.19], vertical_spacing=0.03,
                        subplot_titles=("", "Volumen", "RSI / MACD"))

    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        name="precio", increasing_line_color="#2e9e5b", decreasing_line_color="#d1495b",
    ), row=1, col=1)

    for periodo, color in zip(p.get("medias_pullback", [20, 50]) + [200], ("#f4a261", "#4361ee", "#7209b7")):
        if len(r["df"]) > periodo:
            serie = ind.ema(r["df"]["Close"], periodo).tail(n)
            fig.add_trace(go.Scatter(x=serie.index, y=serie, name=f"EMA {periodo}",
                                     line=dict(width=1.3, color=color)), row=1, col=1)

    # Niveles: solo los mas fuertes, para no tapar el grafico.
    for z in sorted(r["zonas"], key=lambda z: -z.fuerza)[:8]:
        color = "#2e9e5b" if z.tipo == "soporte" else "#d1495b"
        fig.add_hline(y=z.precio, line=dict(color=color, width=1, dash="dot"),
                      opacity=0.55, row=1, col=1,
                      annotation_text=f"{z.precio:,.2f} · {z.fuerza:.0f}",
                      annotation_position="right",
                      annotation_font=dict(size=9, color=color))

    # Zonas de entrada
    for e in r["entradas"][:3]:
        if e.direccion == "salida" or not np.isfinite(e.stop):
            continue
        fig.add_hrect(y0=e.zona_min, y1=e.zona_max, fillcolor="#4361ee", opacity=0.13,
                      line_width=0, row=1, col=1)

    colores = ["#2e9e5b" if c >= o else "#d1495b"
               for c, o in zip(df["Close"], df["Open"])]
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="volumen",
                         marker_color=colores, opacity=0.6), row=2, col=1)

    rsi = ind.rsi(r["df"]["Close"], p.get("rsi", 14)).tail(n)
    fig.add_trace(go.Scatter(x=rsi.index, y=rsi, name="RSI", line=dict(color="#7209b7", width=1.3)),
                  row=3, col=1)
    fig.add_hline(y=p.get("rsi_sobrecompra", 70), line=dict(color="#d1495b", width=1, dash="dash"),
                  opacity=0.5, row=3, col=1)
    fig.add_hline(y=p.get("rsi_sobreventa", 30), line=dict(color="#2e9e5b", width=1, dash="dash"),
                  opacity=0.5, row=3, col=1)

    fig.update_layout(
        template="plotly_white", height=760, margin=dict(l=50, r=90, t=30, b=30),
        xaxis_rangeslider_visible=False, showlegend=True,
        legend=dict(orientation="h", y=1.06, x=0),
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=11),
    )
    fig.update_yaxes(title_text="", row=1, col=1)
    return fig.to_html(full_html=False, include_plotlyjs="cdn",
                       config={"displayModeBar": False})


def a_html(res: dict, ruta: Path | str | None = None) -> Path:
    SALIDAS.mkdir(exist_ok=True)
    ruta = Path(ruta) if ruta else SALIDAS / f"{res['ticker']}_{res['perfil']}.html"
    cfg = res["config"]
    cons = res["consenso"]
    e = _html.escape

    partes = [f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(res['ticker'])} · {e(res['perfil'])}</title>
<style>
 :root {{ --tinta:#1a1a1a; --suave:#666; --linea:#e5e5e5; --fondo:#fafafa; }}
 * {{ box-sizing:border-box; }}
 body {{ font-family:system-ui,-apple-system,'Segoe UI',sans-serif; margin:0;
        background:var(--fondo); color:var(--tinta); line-height:1.55; }}
 .wrap {{ max-width:1180px; margin:0 auto; padding:28px 20px 60px; }}
 header {{ border-bottom:2px solid var(--tinta); padding-bottom:14px; margin-bottom:24px; }}
 h1 {{ margin:0 0 4px; font-size:1.9rem; letter-spacing:-.02em; }}
 h2 {{ font-size:1.15rem; margin:34px 0 12px; padding-bottom:6px;
       border-bottom:1px solid var(--linea); }}
 h3 {{ font-size:.95rem; margin:22px 0 8px; color:var(--suave);
       text-transform:uppercase; letter-spacing:.06em; }}
 .meta {{ color:var(--suave); font-size:.88rem; }}
 .veredicto {{ display:inline-block; padding:9px 18px; border-radius:7px;
               color:#fff; font-weight:700; font-size:1.05rem; }}
 .card {{ background:#fff; border:1px solid var(--linea); border-radius:9px;
          padding:16px 18px; margin:12px 0; }}
 table {{ border-collapse:collapse; width:100%; font-size:.88rem; margin:8px 0; }}
 th {{ text-align:left; font-weight:600; color:var(--suave); font-size:.75rem;
       text-transform:uppercase; letter-spacing:.05em;
       border-bottom:1px solid var(--linea); padding:7px 9px; }}
 td {{ padding:7px 9px; border-bottom:1px solid #f2f2f2; }}
 td.num, th.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
 .compra {{ color:#0a7d3f; font-weight:600; }} .venta {{ color:#a4133c; font-weight:600; }}
 .neutral {{ color:#b08900; }}
 .aviso {{ background:#fff8e1; border-left:3px solid #f0a500; padding:9px 13px;
           margin:8px 0; font-size:.86rem; border-radius:0 5px 5px 0; }}
 .pill {{ display:inline-block; padding:2px 9px; border-radius:11px; font-size:.75rem;
          background:#eee; margin-right:6px; }}
 .fuerza {{ display:inline-block; height:6px; border-radius:3px; background:#4361ee;
            vertical-align:middle; }}
 .tabla-wrap {{ overflow-x:auto; }}
 footer {{ margin-top:44px; padding-top:16px; border-top:1px solid var(--linea);
           color:var(--suave); font-size:.8rem; }}
</style></head><body><div class="wrap">
<header>
 <h1>{e(res['ticker'])}</h1>
 <div class="meta">Perfil <strong>{e(res['perfil'])}</strong> · {e(cfg.get('descripcion', ''))}
  · generado {e(res['generado'])}</div>
</header>
<div class="card">
 <span class="veredicto" style="background:{HEX.get(cons['veredicto'], '#666')}">
  {e(cons['veredicto'])}</span>
 <span class="meta" style="margin-left:12px">score {cons['promedio']:+.2f} (de -1 a +1)</span>
 {'' if cons['temporalidades_alineadas'] or len(cons['detalle']) < 2
   else '<div class="aviso">Las temporalidades no coinciden entre si: la senal es mas debil de lo que sugiere el veredicto.</div>'}
</div>"""]

    for tf, r in res["temporalidades"].items():
        partes.append(_html_temporalidad(tf, r, cfg, e))

    partes.append(f"""
<footer>Analisis tecnico automatizado sobre datos historicos de Yahoo Finance.
No constituye recomendacion de inversion. El rendimiento pasado no garantiza
resultados futuros. Los porcentajes historicos describen lo que ocurrio en la
muestra analizada, no lo que va a ocurrir.</footer>
</div></body></html>""")

    ruta.write_text("".join(partes), encoding="utf-8")
    return ruta


def _html_temporalidad(tf: str, r: dict, cfg: dict, e) -> str:
    resumen = r["resumen"]
    precio = r["precio"]
    out = [f"""<h2>Temporalidad {e(tf)}</h2>
<div class="card">
 <span class="pill">precio {precio:,.2f}</span>
 <span class="pill">ATR {r['atr']:,.2f} ({r['atr_pct']}%)</span>
 <span class="pill">{r['velas']} velas</span>
 <span class="pill">dato {e(r['fecha_dato'][:16])}</span>
 {' '.join(f'<span class="pill">{e(k)} {v:+.2f}%</span>' for k, v in r['variaciones_pct'].items())}
</div>"""]

    # Resumen tecnico
    filas = "".join(
        f"<tr><td>{nombre}</td><td class='num compra'>{b['compra']}</td>"
        f"<td class='num neutral'>{b['neutral']}</td><td class='num venta'>{b['venta']}</td>"
        f"<td style='color:{HEX.get(b['veredicto'], '#666')};font-weight:600'>{b['veredicto']}</td></tr>"
        for nombre, b in (("Osciladores", resumen["osciladores"]),
                          ("Medias moviles", resumen["medias"])))
    out.append(f"""<h3>Resumen tecnico</h3><div class="tabla-wrap"><table>
<tr><th>bloque</th><th class="num">compra</th><th class="num">neutral</th>
<th class="num">venta</th><th>veredicto</th></tr>{filas}
<tr><td><strong>RESUMEN</strong></td><td colspan="3"></td>
<td style="color:{HEX.get(resumen['veredicto'], '#666')};font-weight:700">
{resumen['veredicto']}</td></tr></table></div>""")

    # Grafico
    try:
        out.append(f'<div class="card">{_grafico(r, cfg)}</div>')
    except Exception as ex:
        out.append(f'<div class="aviso">No se pudo dibujar el grafico: {e(str(ex))}</div>')

    # Senales
    if r["senales"]:
        sesgo, valor = r["sesgo"]
        items = "".join(
            f"<li><span class='{'compra' if s['sesgo'] == 'alcista' else ('venta' if s['sesgo'] == 'bajista' else 'neutral')}'>"
            f"{'▲' if s['sesgo'] == 'alcista' else ('▼' if s['sesgo'] == 'bajista' else '●')}</span> "
            f"{e(s['detalle'])}</li>"
            for s in sorted(r["senales"], key=lambda x: -x["peso"]))
        out.append(f"""<h3>Senales activas · sesgo {e(sesgo)} ({valor:+.2f})</h3>
<div class="card"><ul style="margin:0;padding-left:18px">{items}</ul></div>""")

    # Niveles
    if r["zonas"]:
        filas = []
        for z in sorted(r["zonas"], key=lambda z: -z.precio):
            dist = z.distancia_pct(precio)
            clase = "venta" if z.tipo == "resistencia" else "compra"
            filas.append(
                f"<tr><td class='{clase}'>{'R' if z.tipo == 'resistencia' else 'S'}</td>"
                f"<td class='num'>{z.precio:,.2f}</td><td class='num'>{dist:+.2f}%</td>"
                f"<td class='num'>{z.fuerza:.0f}</td>"
                f"<td><span class='fuerza' style='width:{z.fuerza * 0.9:.0f}px'></span></td>"
                f"<td class='meta'>{e(z.origen)}</td></tr>")
        out.append(f"""<h3>Soportes y resistencias</h3><div class="tabla-wrap"><table>
<tr><th></th><th class="num">precio</th><th class="num">distancia</th>
<th class="num">fuerza</th><th></th><th>origen</th></tr>{''.join(filas)}</table></div>""")

    # Plan
    if r["entradas"]:
        out.append("<h3>Escenarios operables</h3>")
        for ent in r["entradas"]:
            avisos = "".join(f'<div class="aviso">{e(a)}</div>' for a in ent.avisos)
            if ent.direccion == "salida":
                cuerpo = (f"<div><strong>Quiebre en {ent.zona_min:,.2f}</strong> "
                          f"(soporte {ent.zona_max:,.2f})</div>"
                          f"<div class='meta'>{e(str(ent.detalle.get('nota', '')))}</div>")
            else:
                pos = ent.detalle.get("posicion")
                cuerpo = (
                    f"<table>"
                    f"<tr><th>zona de entrada</th><th class='num'>stop</th>"
                    f"<th class='num'>objetivo</th><th class='num'>riesgo</th>"
                    f"<th class='num'>beneficio</th><th class='num'>R:R</th></tr>"
                    f"<tr><td>{ent.zona_min:,.2f} – {ent.zona_max:,.2f}</td>"
                    f"<td class='num venta'>{ent.stop:,.2f}</td>"
                    f"<td class='num compra'>{ent.objetivo:,.2f}</td>"
                    f"<td class='num'>{ent.riesgo_pct:.2f}%</td>"
                    f"<td class='num'>+{ent.beneficio_pct:.2f}%</td>"
                    f"<td class='num'><strong>{ent.rr:.2f}</strong></td></tr></table>")
                if pos:
                    cuerpo += (f"<div class='meta'>Posicion sugerida: {pos['unidades']:,.2f} "
                               f"nominales · {pos['invertido']:,.2f} ({pos['pct_capital']:.1f}% "
                               f"del capital) · riesgo {pos['riesgo_dinero']:,.2f}</div>")
            out.append(f"""<div class="card">
 <div><strong>{e(ent.escenario)}</strong>
  <span class="pill">confianza {ent.confianza:.0f}/100</span></div>
 {cuerpo}
 <div class="meta"><strong>Disparador:</strong> {e(ent.disparador)}</div>
 <div class="meta"><strong>Se invalida si:</strong> {e(ent.invalidacion)}</div>
 {avisos}</div>""")

    # Backtest
    if "backtest" in r and r["backtest"]["base"].get("operaciones"):
        bt = r["backtest"]
        base = bt["base"]
        c = bt["config"]
        filas = [f"<tr><td><strong>entrando en cualquier vela (base)</strong></td>"
                 f"<td class='num'>{base['operaciones']}</td>"
                 f"<td class='num'>{base['toco_objetivo_pct']:.1f}%</td>"
                 f"<td class='num'>{base['toco_stop_pct']:.1f}%</td>"
                 f"<td class='num'>{base['retorno_medio_pct']:+.2f}%</td>"
                 f"<td class='num'>{base['profit_factor']:.2f}</td><td class='num'>—</td></tr>"]
        for s in bt["senales"][:8]:
            clase = "compra" if s["ventaja_pp"] > 0 else "venta"
            filas.append(f"<tr><td>{e(s['senal'])}</td><td class='num'>{s['operaciones']}</td>"
                         f"<td class='num'>{s['toco_objetivo_pct']:.1f}%</td>"
                         f"<td class='num'>{s['toco_stop_pct']:.1f}%</td>"
                         f"<td class='num'>{s['retorno_medio_pct']:+.2f}%</td>"
                         f"<td class='num'>{s['profit_factor']:.2f}</td>"
                         f"<td class='num {clase}'>{s['ventaja_pp']:+.1f} pp</td></tr>")
        diag = r.get("diagnostico_stop", {})
        out.append(f"""<h3>Validacion historica</h3>
<div class="card">
<p class="meta">De cada entrada simulada, cuantas veces el precio llego a
<strong>+{c['tp_pct']:.0f}%</strong> antes de caer <strong>-{c['sl_pct']:.0f}%</strong>,
dentro de {c['max_velas']} velas. Si una senal no le gana a la fila base, no esta aportando.</p>
<div class="tabla-wrap"><table>
<tr><th>caso</th><th class="num">n</th><th class="num">llego al objetivo</th>
<th class="num">salto el stop</th><th class="num">retorno medio</th>
<th class="num">profit factor</th><th class="num">vs base</th></tr>
{''.join(filas)}</table></div>
<p class="meta">El stop de {c['sl_pct']:.0f}% equivale a {diag.get('stop_en_atr', 0):.1f} ATR y el
objetivo a {diag.get('objetivo_en_atr', 0):.1f} ATR. Volatilidad anualizada
{diag.get('volatilidad_anual_pct')}%. De las operaciones que terminaron ganando, el 80%
nunca fue mas de {abs(base.get('mae_p80_ganadoras_pct', 0)):.1f}% en contra.</p>
</div>""")

    return "".join(out)


# ==========================================================================
# Comparativa de varios tickers
# ==========================================================================
def tabla_lote(resultados: list[dict], consola: Console | None = None) -> None:
    c = consola or Console()
    t = Table(title="Comparativa", header_style="bold")
    t.add_column("ticker"); t.add_column("precio", justify="right")
    t.add_column("veredicto"); t.add_column("score", justify="right")
    t.add_column("sesgo senales"); t.add_column("mejor escenario", max_width=30)
    t.add_column("R:R", justify="right"); t.add_column("conf.", justify="right")

    for r in sorted(resultados, key=lambda x: -x["consenso"]["promedio"]):
        principal = next(iter(r["temporalidades"].values()))
        mejor = next((e for e in principal["entradas"] if e.direccion != "salida"), None)
        ver = r["consenso"]["veredicto"]
        t.add_row(
            r["ticker"], _fmt(principal["precio"]),
            Text(ver, style=COLOR.get(ver, "white")),
            f"{r['consenso']['promedio']:+.2f}",
            Text(principal["sesgo"][0], style=COLOR.get(principal["sesgo"][0], "white")),
            mejor.escenario if mejor else SIM["guion"],
            f"{mejor.rr:.2f}" if mejor else SIM["guion"],
            f"{mejor.confianza:.0f}" if mejor else SIM["guion"])
    c.print(t)
