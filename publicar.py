"""Genera el tablero HTML que despues se publica como Artifact.

    python publicar.py                 # todos los activos del perfil panel
    python publicar.py --perfil panel  # equivalente
    python publicar.py IBIT AAPL       # solo estos, ignorando la lista del perfil

Escribe siempre en el mismo archivo (salidas/tablero.html) para que al
republicarlo mantenga la misma direccion y el link que ya tiene Damian siga
funcionando.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

from tecnico import analisis, panel

RAIZ = Path(__file__).resolve().parent
SALIDA = RAIZ / "salidas" / "tablero.html"
UNIVERSO = RAIZ / "config" / "universo.yaml"
ESTADO = RAIZ / "salidas" / "estado.json"


def _leer_universo() -> dict:
    """Los activos que ofrece el tablero, con su nombre y grupo."""
    import yaml
    try:
        return yaml.safe_load(UNIVERSO.read_text(encoding="utf-8")) or {}
    except Exception as ex:
        print(f"No pude leer {UNIVERSO.name}: {ex}")
        return {}


def _leer_estado() -> dict:
    """Veredictos de la corrida anterior, para saber que cambio."""
    import json
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _guardar_estado(resultados: list[dict]) -> None:
    import json
    datos = {r["ticker"]: {"veredicto": r["consenso"]["veredicto"],
                           "score": r["consenso"]["promedio"],
                           "precio": next(iter(r["temporalidades"].values()))["precio"]}
             for r in resultados}
    try:
        ESTADO.parent.mkdir(parents=True, exist_ok=True)
        ESTADO.write_text(json.dumps(datos, indent=1), encoding="utf-8")
    except Exception:
        pass


def _cambios(resultados: list[dict], previo: dict) -> list[str]:
    """Que activos cambiaron de veredicto desde la ultima corrida.

    Es lo unico que hace falta mirar cuando el tablero se actualiza solo: si
    nada cambio de bando, no hay nada nuevo que decidir.
    """
    salida = []
    for r in resultados:
        antes = previo.get(r["ticker"])
        if not antes:
            continue
        ahora = r["consenso"]["veredicto"]
        if antes["veredicto"] != ahora:
            salida.append(f"{r['ticker']}: {antes['veredicto']} -> {ahora}")
    return salida


def desplegar(html_completo: str) -> str:
    """Sube el tablero a GitHub Pages, siempre con un solo commit.

    La pagina se actualiza cada 15 minutos y pesa varios MB: con commits
    normales el repositorio engordaria cerca de un giga por mes. Por eso la
    rama `pagina` vive en un worktree aparte (.despliegue/) y cada corrida
    REEMPLAZA su unico commit (amend + push forzado) en vez de apilar otro.
    El historial de esa rama no importa: es un destino de publicacion, no
    codigo. El codigo va por `main` con historial normal.
    """
    import subprocess

    wt = RAIZ / ".despliegue"

    def git(*args_git, cwd=RAIZ):
        r = subprocess.run(["git", *args_git], cwd=cwd, capture_output=True,
                           text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args_git)}: {r.stderr.strip()[:200]}")
        return r.stdout.strip()

    if not (wt / ".git").exists():
        # Primer uso en esta copia del repo: enganchar el worktree a la rama.
        git("fetch", "origin", "pagina")
        try:
            git("worktree", "add", str(wt), "pagina")
        except RuntimeError:
            git("worktree", "add", "-B", "pagina", str(wt), "origin/pagina")

    (wt / "index.html").write_text(html_completo, encoding="utf-8")
    # .nojekyll evita que GitHub intente procesar la pagina como sitio Jekyll.
    (wt / ".nojekyll").write_text("", encoding="utf-8")

    git("add", "-A", cwd=wt)
    git("commit", "--amend", "-m", "Tablero tecnico (se reemplaza en cada corrida)",
        cwd=wt)
    git("push", "--force", "origin", "pagina", cwd=wt)
    return "https://bl0xie.github.io/tablero-tecnico/"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Genera el tablero tecnico compartible.")
    ap.add_argument("tickers", nargs="*", help="activos a incluir (default: los del perfil)")
    ap.add_argument("-p", "--perfil", default="panel", help="perfil a usar (default: panel)")
    ap.add_argument("-o", "--salida", default=str(SALIDA), help="archivo HTML a escribir")
    ap.add_argument("--sin-cache", action="store_true", help="forzar descarga de datos")
    ap.add_argument("--archivo", action="store_true",
                    help="ademas, escribir una copia autonoma para mandar por mail "
                         "o WhatsApp (salidas/tablero-para-compartir.html)")
    ap.add_argument("--desplegar", action="store_true",
                    help="subir el tablero a GitHub Pages (bl0xie.github.io/tablero-tecnico)")
    args = ap.parse_args(argv)

    cfg = analisis.cargar_perfil(args.perfil)
    universo = _leer_universo()
    # La lista de activos sale del universo; el perfil solo aporta los parametros.
    del_universo = [a["ticker"] for a in universo.get("activos", [])]
    tickers = args.tickers or del_universo or cfg.get("tickers") or ["IBIT"]

    print(f"Perfil {cfg.get('nombre')}: {len(tickers)} activos, "
          f"temporalidades {', '.join(cfg.get('temporalidades', []))}")

    previo = _leer_estado()
    inicio = time.time()
    resultados, fallos = [], {}
    for i, ticker in enumerate(tickers, 1):
        ticker = ticker.strip().upper()
        t0 = time.time()
        try:
            res = analisis.analizar(ticker, cfg, usar_cache=not args.sin_cache)
            resultados.append(res)
            faltantes = f"  (sin {', '.join(res['errores'])})" if res["errores"] else ""
            print(f"  [{i}/{len(tickers)}] {ticker:<9} "
                  f"{res['consenso']['veredicto']:<14} {time.time() - t0:5.1f}s{faltantes}")
        except Exception as ex:
            fallos[ticker] = str(ex)
            print(f"  [{i}/{len(tickers)}] {ticker:<9} FALLO: {str(ex)[:70]}")

    if not resultados:
        print("Ningun activo pudo analizarse. No se escribio el tablero.")
        return 1

    html = panel.construir(resultados, cfg, fallos, datetime.now(), previo, universo)
    destino = Path(args.salida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html, encoding="utf-8")

    if args.archivo:
        suelto = destino.parent / "tablero-para-compartir.html"
        suelto.write_text(panel.documento_completo(html), encoding="utf-8")
        print(f"Copia para compartir: {suelto}")

    if args.desplegar:
        try:
            direccion = desplegar(panel.documento_completo(html))
            print(f"Desplegado en: {direccion}")
        except Exception as ex:
            # El tablero local quedo bien igual; el despliegue se reintenta en
            # la proxima corrida. Se avisa para que no falle en silencio.
            print(f"DESPLIEGUE FALLIDO: {ex}")

    print(f"\nTablero: {destino}")
    print(f"{len(resultados)} activos en {time.time() - inicio:.0f}s "
          f"· {len(html) / 1024:.0f} KB")
    if fallos:
        print(f"Fallaron: {', '.join(fallos)}")

    cambios = _cambios(resultados, previo)
    if cambios:
        print("CAMBIOS DE VEREDICTO:")
        for c in cambios:
            print(f"  {c}")
    elif previo:
        print("CAMBIOS DE VEREDICTO: ninguno")
    _guardar_estado(resultados)
    return 0


if __name__ == "__main__":
    sys.exit(main())
