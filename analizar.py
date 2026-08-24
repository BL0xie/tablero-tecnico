"""Analisis tecnico automatizado por escenarios.

Ejemplos:
    python analizar.py IBIT
    python analizar.py IBIT --perfil corto_plazo --detalle
    python analizar.py IBIT BTC-USD AAPL --perfil swing
    python analizar.py IBIT --stop 5 --objetivo 10 --capital 500000
    python analizar.py GGAL.BA --perfil largo_plazo --abrir
    python analizar.py --listar
"""
from __future__ import annotations

import argparse
import logging
import sys
import warnings
import webbrowser
from pathlib import Path

warnings.filterwarnings("ignore")

# La consola de Windows suele venir en cp1252 y hace explotar cualquier simbolo
# que no sea ASCII. Con esto la salida nunca corta el analisis por un caracter.
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# yfinance avisa por stderr cada vez que una temporalidad no esta disponible;
# esos casos ya se reportan de forma ordenada al final del analisis.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

from rich.console import Console

from tecnico import analisis, reporte

console = Console(legacy_windows=False) if sys.platform == "win32" else Console()


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="analizar.py",
        description="Analisis tecnico automatizado con perfiles configurables.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("tickers", nargs="*",
                   help="uno o varios tickers (IBIT, BTC-USD, AAPL, GGAL.BA...)")
    p.add_argument("-p", "--perfil", default="corto_plazo",
                   help="perfil de config a usar (default: corto_plazo)")
    p.add_argument("-t", "--temporalidad", nargs="+", metavar="TF",
                   help="pisa las temporalidades del perfil (ej: -t 1d 1wk)")
    p.add_argument("--stop", type=float, metavar="PCT",
                   help="pisa el stop del perfil, en %%")
    p.add_argument("--objetivo", type=float, metavar="PCT",
                   help="pisa el objetivo del perfil, en %%")
    p.add_argument("--capital", type=float,
                   help="capital disponible, para calcular el tamano de posicion")
    p.add_argument("--riesgo", type=float, metavar="PCT",
                   help="%% del capital a arriesgar por operacion (default: el del perfil)")
    p.add_argument("--csv", help="usar un CSV propio en vez de descargar")
    p.add_argument("-d", "--detalle", action="store_true",
                   help="mostrar el valor de cada indicador")
    p.add_argument("--html", action="store_true", help="generar informe HTML")
    p.add_argument("--excel", action="store_true", help="generar planilla Excel")
    p.add_argument("--todo", action="store_true", help="generar HTML y Excel")
    p.add_argument("--abrir", action="store_true",
                   help="abrir el informe HTML en el navegador al terminar")
    p.add_argument("--sin-cache", action="store_true",
                   help="forzar la descarga aunque haya cache fresco")
    p.add_argument("--listar", action="store_true",
                   help="listar los perfiles disponibles y salir")
    return p


def aplicar_overrides(cfg: dict, args) -> dict:
    """Las opciones de linea de comando pisan lo que dice el perfil."""
    if args.temporalidad:
        cfg["temporalidades"] = args.temporalidad
    riesgo = cfg.setdefault("riesgo", {})
    if args.stop is not None:
        riesgo["stop_pct"] = abs(args.stop)
        riesgo["modo_stop"] = "porcentaje"
    if args.objetivo is not None:
        riesgo["objetivo_pct"] = abs(args.objetivo)
        riesgo["modo_objetivo"] = "porcentaje"
    if args.capital is not None:
        riesgo["capital"] = args.capital
    if args.riesgo is not None:
        riesgo["riesgo_por_operacion_pct"] = args.riesgo
    return cfg


def main(argv=None) -> int:
    args = construir_parser().parse_args(argv)

    if args.listar:
        console.print("\n[bold]Perfiles disponibles[/bold]\n")
        for nombre in analisis.perfiles_disponibles():
            try:
                cfg = analisis.cargar_perfil(nombre)
                r = cfg.get("riesgo", {})
                console.print(f"  [cyan]{nombre:<14}[/cyan] {cfg.get('descripcion', '')}")
                console.print(f"  {'':<14} [dim]temporalidades: "
                              f"{', '.join(cfg.get('temporalidades', []))} · "
                              f"stop {r.get('stop_pct')}% ({r.get('modo_stop')}) · "
                              f"objetivo {r.get('objetivo_pct')}% ({r.get('modo_objetivo')})[/dim]")
            except Exception as e:
                console.print(f"  [red]{nombre}: {e}[/red]")
        console.print()
        return 0

    if not args.tickers:
        console.print("[red]Falta indicar al menos un ticker.[/red] "
                      "Ejemplo: [cyan]python analizar.py IBIT[/cyan]\n"
                      "Ver perfiles: [cyan]python analizar.py --listar[/cyan]")
        return 2

    try:
        cfg = analisis.cargar_perfil(args.perfil)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]{e}[/red]")
        return 2
    cfg = aplicar_overrides(cfg, args)

    quiere_html = args.html or args.todo or args.abrir
    quiere_excel = args.excel or args.todo
    resultados, fallos, generados = [], {}, []

    for ticker in args.tickers:
        ticker = ticker.strip().upper()
        with console.status(f"Analizando {ticker}..."):
            try:
                res = analisis.analizar(ticker, cfg, csv=args.csv,
                                        usar_cache=not args.sin_cache)
            except Exception as e:
                fallos[ticker] = str(e)
                continue
        resultados.append(res)
        reporte.a_consola(res, console, detalle=args.detalle)

        if quiere_html:
            try:
                ruta = reporte.a_html(res)
                generados.append(ruta)
                console.print(f"  [dim]informe HTML:[/dim] {ruta}")
            except Exception as e:
                console.print(f"  [yellow]no se pudo generar el HTML: {e}[/yellow]")
        if quiere_excel:
            try:
                ruta = reporte.a_excel(res)
                console.print(f"  [dim]planilla Excel:[/dim] {ruta}")
            except Exception as e:
                console.print(f"  [yellow]no se pudo generar el Excel: {e}[/yellow]")

    if len(resultados) > 1:
        console.print()
        reporte.tabla_lote(resultados, console)

    for ticker, err in fallos.items():
        console.print(f"[red]{ticker}: {err}[/red]")

    if args.abrir and generados:
        webbrowser.open(Path(generados[0]).resolve().as_uri())

    return 0 if resultados else 1


if __name__ == "__main__":
    sys.exit(main())
