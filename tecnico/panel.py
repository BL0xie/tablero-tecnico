"""Arma el tablero interactivo que se publica como Artifact.

Es una pagina autocontenida: sin CDN ni librerias, porque el visor bloquea todo
pedido a otro servidor. Los graficos se dibujan en el navegador sobre canvas a
partir de los datos embebidos, no como imagenes ya resueltas: asi se puede hacer
zoom, y 75 activos entran en un peso razonable.

La pagina NO cotiza en vivo. Muestra la foto del momento en que se genero, y por
eso la antiguedad del dato esta siempre a la vista.
"""
from __future__ import annotations

import html as _html
import json
import math
from datetime import datetime, time, timedelta

CLASE_VEREDICTO = {
    "COMPRA FUERTE": "v-cf", "COMPRA": "v-c", "NEUTRAL": "v-n",
    "VENTA": "v-v", "VENTA FUERTE": "v-vf", "SIN DATOS": "v-x",
}
ORDEN_VEREDICTO = {"COMPRA FUERTE": 0, "COMPRA": 1, "NEUTRAL": 2,
                   "VENTA": 3, "VENTA FUERTE": 4, "SIN DATOS": 5}


def e(v) -> str:
    return _html.escape(str(v))


def proxima_corrida(desde: datetime, horario: dict) -> datetime | None:
    """Cuando vuelve a regenerarse el tablero, segun el horario configurado.

    Se calcula aca y no en el navegador porque el horario esta en la hora de
    esta maquina, que no tiene por que coincidir con la de quien mira la pagina.
    Mandando el momento exacto, cada uno lo ve en su propia hora.
    """
    dias = set(horario.get("dias", [0, 1, 2, 3, 4]))
    minutos = sorted(horario.get("minutos", [0]))
    h0 = horario.get("hora_desde", 0)
    h1 = horario.get("hora_hasta", 23)
    if not dias or not minutos:
        return None

    tic = desde.replace(second=0, microsecond=0)
    # Una semana por delante alcanza: si en 7 dias no hay corrida, no hay horario.
    for salto in range(8):
        dia = (tic + timedelta(days=salto)).date()
        if dia.weekday() not in dias:
            continue
        for hora in range(h0, h1 + 1):
            for minuto in minutos:
                cand = datetime.combine(dia, time(hora, minuto))
                if cand > desde:
                    return cand
    return None


def _finito(v):
    """Cambia por null los infinitos y NaN antes de serializar.

    json.dumps escribe float('inf') como Infinity, que es valido en Python pero
    no en JSON: JSON.parse lo rechaza y muere el script entero, dejando la
    pagina en blanco. Aparece, por ejemplo, en profit_factor cuando una senal
    no tuvo ni una operacion perdedora. En el tablero null se muestra como "—".
    """
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, dict):
        return {k: _finito(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_finito(x) for x in v]
    return v


def documento_completo(fragmento: str) -> str:
    """Envuelve el tablero como documento HTML valido e independiente.

    Al publicarlo como Artifact la envoltura la agrega el visor, asi que
    construir() devuelve solo el contenido. Para mandar el archivo suelto hace
    falta el documento entero, si no el navegador lo abre en modo compatibilidad.
    """
    cabeza, _, cuerpo = fragmento.partition("</style>")
    return ('<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f'{cabeza}</style>\n</head>\n<body>{cuerpo}\n</body>\n</html>')


# ==========================================================================
# Estilos
# ==========================================================================
def _estilos() -> str:
    oscuros = """
      --ground:#0E1319; --panel:#151B23; --panel-2:#1C242E; --panel-3:#232C38;
      --linea:#2A3441; --linea-2:#212a35;
      --ink:#E3E9F1; --ink-2:#AFBACA; --muted:#7D8B9E;
      --acento:#6FA8DC; --acento-2:#1B3247;
      --alza:#4FC08A; --alza-2:#14332A; --baja:#E8798D; --baja-2:#3A1F26;
      --warn:#D9AC4A; --warn-2:#332813;
      --sombra:0 1px 3px rgba(0,0,0,.55);
    """
    return f"""
:root {{
  --ground:#EBEEF3; --panel:#FFFFFF; --panel-2:#F4F7FA; --panel-3:#E9EEF4;
  --linea:#D3DBE5; --linea-2:#E6EBF1;
  --ink:#121821; --ink-2:#374252; --muted:#636F80;
  --acento:#2D5F8B; --acento-2:#E2ECF6;
  --alza:#1F7A4D; --alza-2:#E1F1E8; --baja:#A83246; --baja-2:#F8E4E7;
  --warn:#8A6512; --warn-2:#F7EEDA;
  --sombra:0 1px 3px rgba(18,24,33,.07);
  --r:8px;
}}
@media (prefers-color-scheme:dark) {{ :root:not([data-theme="light"]) {{ {oscuros} }} }}
:root[data-theme="dark"] {{ {oscuros} }}

* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--ground); color:var(--ink);
  font-family:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  font-size:14px; line-height:1.5; }}
button {{ font-family:inherit; }}
:focus-visible {{ outline:2px solid var(--acento); outline-offset:1px; }}
.num {{ font-family:"IBM Plex Mono",monospace; font-variant-numeric:tabular-nums; }}
.alza {{ color:var(--alza); }} .baja {{ color:var(--baja); }}

/* ---------------- barra superior ---------------- */
.barra {{ display:flex; flex-wrap:wrap; gap:14px; align-items:center;
  justify-content:space-between; padding:11px 18px; background:var(--panel);
  border-bottom:1px solid var(--linea); position:sticky; top:0; z-index:20; }}
/* En escritorio la fila de marca y reloj se parte: marca a la izquierda, vistas
   en el medio, reloj a la derecha. En movil la fila queda entera y las vistas
   bajan a una segunda linea. */
.barra-fila {{ display:contents; }}
.marca {{ display:flex; align-items:baseline; gap:10px; order:1; }}
.marca h1 {{ font-family:"IBM Plex Serif",Georgia,serif; font-size:1.14rem;
  font-weight:600; margin:0; letter-spacing:-.01em; }}
.marca .sub {{ font-size:.74rem; color:var(--muted); }}
.reloj {{ display:flex; align-items:center; gap:8px; font-size:.75rem; order:3;
  color:var(--muted); }}
.reloj b {{ font-family:"IBM Plex Mono",monospace; color:var(--ink);
  font-weight:500; }}
.latido {{ width:7px; height:7px; border-radius:50%; background:var(--acento);
  flex-shrink:0; }}

.vistas {{ display:flex; gap:3px; padding:3px; background:var(--panel-2); order:2;
  border:1px solid var(--linea); border-radius:var(--r); }}
.vistas button {{ appearance:none; border:none; background:transparent;
  color:var(--muted); font-size:.79rem; font-weight:500; padding:5px 13px;
  border-radius:5px; cursor:pointer; }}
.vistas button[aria-selected="true"] {{ background:var(--panel); color:var(--ink);
  box-shadow:var(--sombra); }}
.contador {{ display:inline-block; min-width:17px; padding:0 5px; margin-left:5px;
  border-radius:9px; background:var(--acento); color:#fff; font-size:.66rem;
  font-weight:600; text-align:center; line-height:16px; }}

/* ---------------- estructura ---------------- */
.tablero {{ display:grid; grid-template-columns:268px 1fr; gap:14px;
  padding:14px 18px 40px; max-width:1560px; margin:0 auto; align-items:start; }}

/* ---------------- panel lateral ---------------- */
.lateral {{ background:var(--panel); border:1px solid var(--linea);
  border-radius:var(--r); box-shadow:var(--sombra); position:sticky; top:64px;
  display:flex; flex-direction:column; max-height:calc(100vh - 80px); }}
.buscador {{ padding:10px; border-bottom:1px solid var(--linea); }}
.buscador input {{ width:100%; padding:7px 10px; border-radius:6px;
  border:1px solid var(--linea); background:var(--panel-2); color:var(--ink);
  font-family:inherit; font-size:.83rem; }}
.buscador input::placeholder {{ color:var(--muted); }}
.filtros {{ display:flex; flex-wrap:wrap; gap:4px; padding:9px 10px;
  border-bottom:1px solid var(--linea); }}
.filtro {{ appearance:none; cursor:pointer; font-size:.71rem; font-weight:500;
  padding:3px 9px; border-radius:99px; background:var(--panel-2);
  border:1px solid var(--linea); color:var(--muted); }}
.filtro[aria-pressed="true"] {{ background:var(--ink); border-color:var(--ink);
  color:var(--panel); }}
/* Solo scroll vertical: con overflow:auto en ambos ejes, Windows dibuja una
   barra horizontal fantasma cada vez que aparece la vertical. */
.lista {{ overflow-y:auto; overflow-x:hidden; flex:1; padding:5px;
  scrollbar-width:thin; scrollbar-color:var(--linea) transparent; }}
.lista::-webkit-scrollbar {{ width:8px; }}
.lista::-webkit-scrollbar-thumb {{ background:var(--linea); border-radius:4px; }}
.item {{ display:grid; grid-template-columns:auto minmax(0,1fr) auto; gap:9px;
  align-items:center; padding:7px 10px 7px 8px; border-radius:6px; cursor:pointer;
  border:1px solid transparent; }}
.item:hover {{ background:var(--panel-2); }}
.item[aria-current="true"] {{ background:var(--acento-2);
  border-color:var(--acento); }}
.item .tk {{ font-family:"IBM Plex Mono",monospace; font-weight:600;
  font-size:.82rem; }}
.item .nm {{ display:block; font-size:.68rem; color:var(--muted);
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; min-width:0; }}
.item .pc {{ text-align:right; font-size:.76rem; display:flex; align-items:center;
  justify-content:flex-end; gap:6px; }}
.item .punto {{ width:7px; height:7px; border-radius:50%; flex-shrink:0; }}
.item .punto.v-cf, .item .punto.v-c {{ background:var(--alza); }}
.item .punto.v-n {{ background:var(--warn); }}
.item .punto.v-v, .item .punto.v-vf {{ background:var(--baja); }}
.item .punto.v-x {{ background:var(--linea); }}
.item .ojo {{ color:var(--warn); font-size:.7rem; margin-left:5px;
  vertical-align:1px; }}
.tilde {{ width:17px; height:17px; border-radius:4px; border:1.5px solid var(--linea);
  display:grid; place-items:center; font-size:.68rem; color:transparent;
  background:var(--panel); flex-shrink:0; }}
.item[data-encartera="1"] .tilde {{ background:var(--acento);
  border-color:var(--acento); color:#fff; }}
.vacio-lista {{ padding:18px 12px; color:var(--muted); font-size:.8rem;
  text-align:center; }}

/* ---------------- area principal ---------------- */
.principal {{ display:flex; flex-direction:column; gap:14px; min-width:0; }}
.tarjeta {{ background:var(--panel); border:1px solid var(--linea);
  border-radius:var(--r); box-shadow:var(--sombra); }}
.tarjeta-cab {{ display:flex; flex-wrap:wrap; gap:12px; align-items:center;
  justify-content:space-between; padding:12px 16px;
  border-bottom:1px solid var(--linea); }}
.tarjeta-cuerpo {{ padding:14px 16px 16px; }}
h2 {{ font-family:"IBM Plex Serif",Georgia,serif; font-size:1rem; font-weight:600;
  margin:0; }}
h3 {{ font-size:.7rem; font-weight:600; text-transform:uppercase;
  letter-spacing:.08em; color:var(--muted); margin:16px 0 7px; }}
h3:first-child {{ margin-top:0; }}

.identidad {{ display:flex; align-items:baseline; gap:11px; flex-wrap:wrap; }}
.identidad .tk {{ font-family:"IBM Plex Mono",monospace; font-size:1.28rem;
  font-weight:600; }}
.identidad .nm {{ font-size:.8rem; color:var(--muted); }}
.identidad .pc {{ font-family:"IBM Plex Mono",monospace; font-size:1.28rem;
  font-weight:500; font-variant-numeric:tabular-nums; }}

.vd {{ display:inline-block; padding:2px 9px; border-radius:99px; font-size:.7rem;
  font-weight:600; white-space:nowrap; border:1px solid transparent; }}
.v-cf {{ background:var(--alza); color:#fff; }}
.v-c {{ background:var(--alza-2); color:var(--alza); border-color:var(--alza); }}
.v-n {{ background:var(--warn-2); color:var(--warn); border-color:var(--warn); }}
.v-v {{ background:var(--baja-2); color:var(--baja); border-color:var(--baja); }}
.v-vf {{ background:var(--baja); color:#fff; }}
.v-x {{ background:var(--panel-2); color:var(--muted); border-color:var(--linea); }}
.viro {{ font-size:.68rem; color:var(--muted); font-style:italic; }}

/* ---------------- grafico ---------------- */
.grafico-cab {{ display:flex; flex-wrap:wrap; gap:10px; align-items:center;
  justify-content:space-between; padding:9px 14px;
  border-bottom:1px solid var(--linea); }}
.pestanas {{ display:flex; gap:3px; padding:3px; background:var(--panel-2);
  border:1px solid var(--linea); border-radius:6px; }}
.pestanas button {{ appearance:none; border:none; background:transparent;
  color:var(--muted); font-size:.77rem; font-weight:500; padding:4px 12px;
  border-radius:4px; cursor:pointer; }}
.pestanas button[aria-selected="true"] {{ background:var(--panel);
  color:var(--ink); box-shadow:var(--sombra); }}
.herramientas {{ display:flex; gap:5px; align-items:center; }}
.herr {{ appearance:none; cursor:pointer; width:27px; height:27px;
  border-radius:5px; border:1px solid var(--linea); background:var(--panel-2);
  color:var(--ink-2); font-size:.85rem; display:grid; place-items:center;
  padding:0; }}
.herr.ancho {{ width:auto; padding:0 10px; font-size:.72rem; }}
.herr:hover {{ border-color:var(--acento); color:var(--acento); }}
.lienzo-caja {{ position:relative; padding:6px 8px 0; }}
canvas {{ display:block; width:100%; touch-action:none; cursor:crosshair; }}
#lienzo {{ height:352px; }}
#lienzoRsi {{ height:78px; }}
.pista {{ font-size:.7rem; color:var(--muted); padding:3px 14px 10px; }}
.lectura {{ position:absolute; top:10px; left:14px; pointer-events:none;
  font-family:"IBM Plex Mono",monospace; font-size:.72rem; line-height:1.45;
  background:var(--panel); border:1px solid var(--linea); border-radius:5px;
  padding:5px 9px; box-shadow:var(--sombra); color:var(--ink-2);
  font-variant-numeric:tabular-nums; z-index:3; }}
.lectura b {{ color:var(--ink); font-weight:600; }}
.lectura .f {{ color:var(--muted); display:block; margin-bottom:2px; }}
.leyenda {{ display:flex; flex-wrap:wrap; gap:13px; font-size:.71rem;
  color:var(--muted); padding:0 14px 10px; }}
.leyenda span {{ display:inline-flex; align-items:center; gap:5px; }}
.trazo {{ width:14px; height:2px; border-radius:1px; }}

/* ---------------- datos ---------------- */
.reja {{ display:grid; gap:11px;
  grid-template-columns:repeat(auto-fit,minmax(148px,1fr)); }}
.celda {{ background:var(--panel-2); border:1px solid var(--linea-2);
  border-radius:6px; padding:9px 11px; }}
.celda .et {{ font-size:.66rem; text-transform:uppercase; letter-spacing:.07em;
  color:var(--muted); display:block; margin-bottom:2px; }}
.celda .vl {{ font-family:"IBM Plex Mono",monospace; font-size:1rem;
  font-weight:500; font-variant-numeric:tabular-nums; }}
.celda .pi {{ font-size:.69rem; color:var(--muted); margin-top:1px; }}

.senales {{ list-style:none; margin:0; padding:0; display:grid; gap:4px; }}
.senales li {{ display:flex; gap:8px; align-items:baseline; font-size:.83rem; }}
.mk {{ font-family:"IBM Plex Mono",monospace; font-weight:700; font-size:.74rem;
  width:12px; flex-shrink:0; }}

table {{ border-collapse:collapse; width:100%; font-size:.82rem; }}
th {{ text-align:left; font-size:.66rem; font-weight:600; text-transform:uppercase;
  letter-spacing:.06em; color:var(--muted); padding:6px 9px;
  border-bottom:1px solid var(--linea); }}
td {{ padding:6px 9px; border-bottom:1px solid var(--linea-2); }}
tr:last-child td {{ border-bottom:none; }}
th.n, td.n {{ text-align:right; font-family:"IBM Plex Mono",monospace;
  font-variant-numeric:tabular-nums; }}
.tabla-caja {{ overflow-x:auto; }}
tr.clicable {{ cursor:pointer; }}
tr.clicable:hover {{ background:var(--panel-2); }}

.barrita {{ display:inline-block; width:44px; height:4px; border-radius:2px;
  background:var(--linea); overflow:hidden; vertical-align:middle; }}
.barrita i {{ display:block; height:100%; background:var(--acento); }}

/* ---------------- escenarios ---------------- */
.esc {{ border:1px solid var(--linea); border-left:3px solid var(--acento);
  border-radius:0 6px 6px 0; padding:11px 14px; margin-bottom:9px;
  background:var(--panel-2); }}
.esc.salida {{ border-left-color:var(--warn); }}
.esc-cab {{ display:flex; flex-wrap:wrap; gap:9px; align-items:baseline;
  justify-content:space-between; margin-bottom:8px; }}
.esc-nm {{ font-weight:600; font-size:.88rem; }}
.esc-datos {{ display:grid; gap:8px;
  grid-template-columns:repeat(auto-fit,minmax(86px,1fr)); margin-bottom:8px; }}
.esc-datos div {{ font-size:.68rem; color:var(--muted); }}
.esc-datos b {{ display:block; font-family:"IBM Plex Mono",monospace;
  font-size:.9rem; font-weight:500; color:var(--ink);
  font-variant-numeric:tabular-nums; }}
.txt {{ font-size:.79rem; color:var(--ink-2); margin:2px 0; }}
.txt b {{ color:var(--ink); }}
.alerta {{ display:flex; gap:7px; background:var(--warn-2);
  border-left:3px solid var(--warn); border-radius:0 5px 5px 0; padding:6px 10px;
  margin-top:6px; font-size:.76rem; color:var(--ink-2); }}
/* ---------------- tendencia de fondo ---------------- */
.fondo {{ border:1px solid var(--linea); border-left:4px solid; border-radius:0 7px 7px 0;
  padding:11px 14px; margin-bottom:13px; background:var(--panel-2); }}
.fondo-alcista {{ border-left-color:var(--alza); }}
.fondo-bajista {{ border-left-color:var(--baja); }}
.fondo-transicion {{ border-left-color:var(--warn); }}
.fondo-cab {{ display:flex; flex-wrap:wrap; gap:9px; align-items:baseline;
  justify-content:space-between; margin-bottom:7px; }}
.fondo-tit {{ font-size:.68rem; text-transform:uppercase; letter-spacing:.07em;
  color:var(--muted); font-weight:600; }}
.fondo-vd {{ font-weight:600; font-size:.92rem; }}
.fondo-alcista .fondo-vd {{ color:var(--alza); }}
.fondo-bajista .fondo-vd {{ color:var(--baja); }}
.fondo-transicion .fondo-vd {{ color:var(--warn); }}
.fondo-datos {{ display:flex; flex-wrap:wrap; gap:4px 16px; font-size:.75rem;
  color:var(--muted); }}
.fondo-datos b {{ font-family:"IBM Plex Mono",monospace; color:var(--ink);
  font-weight:500; font-variant-numeric:tabular-nums; }}
.fondo-txt {{ margin:7px 0 0; font-size:.81rem; color:var(--ink-2); max-width:72ch; }}
.pastilla {{ display:inline-block; padding:2px 9px; border-radius:99px;
  font-size:.69rem; font-weight:600; border:1px solid currentColor; }}
.pastilla.alza {{ background:var(--alza-2); }}
.pastilla.baja {{ background:var(--baja-2); }}
.mfondo {{ font-size:.62rem; margin-left:5px; vertical-align:1px; }}
.mfondo.f-alcista {{ color:var(--alza); }}
.mfondo.f-bajista {{ color:var(--baja); }}
.mfondo.f-transicion {{ color:var(--warn); }}
.filtro.f-alcista {{ color:var(--alza); }}
.filtro.f-bajista {{ color:var(--baja); }}
.filtro.f-alcista[aria-pressed="true"], .filtro.f-bajista[aria-pressed="true"] {{
  color:var(--panel); }}

.cruce {{ border-left:3px solid; border-radius:0 5px 5px 0; padding:8px 12px;
  font-size:.81rem; color:var(--ink-2); margin-bottom:12px; }}
.cruce.ok {{ background:var(--alza-2); border-color:var(--alza); }}
.cruce.ok b {{ color:var(--alza); }}
.cruce.difiere {{ background:var(--warn-2); border-color:var(--warn); }}
.cruce.difiere b {{ color:var(--warn); }}
.aviso-azul {{ background:var(--acento-2); border-left:3px solid var(--acento);
  border-radius:0 5px 5px 0; padding:8px 12px; font-size:.81rem;
  color:var(--ink-2); margin-bottom:12px; }}
.nota {{ font-size:.76rem; color:var(--muted); }}
details {{ margin-top:12px; border:1px solid var(--linea); border-radius:6px; }}
summary {{ cursor:pointer; padding:9px 13px; font-size:.83rem; font-weight:500; }}
details .interior {{ padding:0 13px 12px; font-size:.82rem; color:var(--ink-2); }}
details p {{ margin:0 0 8px; max-width:70ch; }}

.pie {{ padding:20px 18px 34px; max-width:1560px; margin:0 auto;
  color:var(--muted); font-size:.75rem; }}
.pie p {{ max-width:78ch; }}
.pie strong {{ color:var(--ink-2); }}

/* ---------------- cartera ---------------- */
.cartera-vacia {{ text-align:center; padding:44px 20px; color:var(--muted); }}
.cartera-vacia b {{ display:block; color:var(--ink); font-size:1rem;
  margin-bottom:5px; }}

@media (max-width:940px) {{
  .tablero {{ grid-template-columns:1fr; padding:11px; }}
  .lateral {{ position:static; max-height:390px; }}
  #lienzo {{ height:270px; }}
}}
@media (max-width:640px) {{
  /* La barra pasa de tres filas apiladas a dos: titulo y reloj juntos arriba,
     las vistas abajo ocupando todo el ancho. */
  .barra {{ padding:9px 12px; gap:8px; }}
  .barra-fila {{ display:flex; width:100%; align-items:center;
    justify-content:space-between; gap:10px; }}
  .marca {{ flex-direction:column; align-items:flex-start; gap:1px; min-width:0; }}
  .marca h1 {{ font-size:1rem; }}
  .marca .sub {{ font-size:.66rem; }}
  .reloj {{ flex:0 0 auto; font-size:.66rem; text-align:right; }}
  .reloj > span:last-child {{ text-align:right; }}
  .vistas {{ width:100%; }}
  .vistas button {{ flex:1; padding:6px 8px; }}
  /* La tabla de niveles entra en pantalla sin scroll: se oculta la barra de
     fuerza (redundante con el numero) y el origen pasa a ajustarse. */
  .tabla-niveles .col-barra {{ display:none; }}
  .tabla-niveles td.nota {{ white-space:normal; font-size:.68rem; min-width:96px;
    line-height:1.3; }}
  table {{ font-size:.76rem; }}
  th, td {{ padding:5px 5px; }}
  /* Las tablas numericas no entran en 330px sin volverse ilegibles. En vez de
     apretarlas, scrollean dentro de su caja con un degradado en el borde que
     indica que hay mas a la derecha: asi se lee como intencional, no como
     desborde. */
  .tabla-caja {{ position:relative; margin:0 -12px; padding:0 12px;
    -webkit-overflow-scrolling:touch; scrollbar-width:thin; }}
  .tabla-caja::after {{ content:""; position:sticky; display:block; float:right;
    right:0; top:0; width:28px; margin-top:-100%; height:100%; pointer-events:none;
    background:linear-gradient(to right, transparent, var(--panel)); }}
  .tabla-caja table {{ min-width:max-content; }}
  .filtros {{ padding:7px 8px; gap:3px; }}
  .filtro {{ font-size:.67rem; padding:3px 8px; }}
  .tarjeta-cab, .tarjeta-cuerpo {{ padding-left:12px; padding-right:12px; }}
  .identidad .tk, .identidad .pc {{ font-size:1.08rem; }}
  .grafico-cab {{ padding:8px 10px; }}
  .herramientas .herr.ancho {{ padding:0 8px; }}
  .lectura {{ font-size:.66rem; padding:4px 7px; }}
  .esc-datos {{ grid-template-columns:repeat(3,1fr); }}
  .reja {{ grid-template-columns:1fr 1fr; }}
}}
@media (prefers-reduced-motion:reduce) {{
  * {{ animation:none !important; transition:none !important; }}
}}
"""


# ==========================================================================
# Pagina
# ==========================================================================
def construir(resultados: list[dict], cfg: dict, fallos: dict[str, str],
              generado: datetime | None = None, previo: dict | None = None,
              universo: dict | None = None) -> str:
    from . import exportar

    generado = generado or datetime.now()
    previo = previo or {}
    universo = universo or {}
    pcfg = cfg.get("panel", {})
    riesgo = cfg.get("riesgo", {})

    meta = {a["ticker"]: a for a in universo.get("activos", [])}
    grupos = universo.get("grupos", {})

    ordenados = sorted(resultados, key=lambda r: (
        ORDEN_VEREDICTO.get(r["consenso"]["veredicto"], 9),
        -r["consenso"]["promedio"]))

    activos = [exportar.activo(r, cfg, meta.get(r["ticker"], {}), previo)
               for r in ordenados]

    datos = {
        "generado": generado.isoformat(),
        "grupos": grupos,
        "activos": activos,
        "fallos": fallos,
        "riesgo": {"stop": abs(riesgo.get("stop_pct", 7)),
                   "objetivo": abs(riesgo.get("objetivo_pct", 14))},
        "medias": list(cfg.get("parametros", {}).get("medias_pullback", [9, 20])),
    }
    # Momento exacto de la proxima corrida: la pagina lo muestra en la hora de
    # quien mira, que no tiene por que ser la de esta maquina.
    proxima = proxima_corrida(generado, cfg.get("actualizacion", {}))
    datos["proxima"] = proxima.isoformat() if proxima else None

    # allow_nan=False para que una futura porqueria no finita reviente aca, al
    # generar, y no en silencio en la pagina que abre Damian.
    payload = json.dumps(_finito(datos), ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False)
    payload = payload.replace("</", "<\\/")  # no cortar el <script> por accidente

    virados = sum(1 for a in activos if a["cambio"])
    filtros = "".join(
        f'<button class="filtro" data-grupo="{e(k)}" aria-pressed="false">{e(v)}</button>'
        for k, v in grupos.items())

    return f"""<title>Tablero técnico de Damián</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@500;600&display=swap">
<style>{_estilos()}</style>

<header class="barra">
 <div class="barra-fila">
  <div class="marca">
   <h1>Tablero técnico</h1>
   <span class="sub">corto plazo · stop −{datos['riesgo']['stop']:.0f}% /
    objetivo +{datos['riesgo']['objetivo']:.0f}%</span>
  </div>
  <div class="reloj" id="reloj">
   <span class="latido" id="latido"></span>
   <span>datos al <b>{generado.strftime('%d/%m %H:%M')}</b><br>
    <span id="antiguedad"></span></span>
  </div>
 </div>
 <div class="vistas" role="tablist">
  <button data-vista="mercado" role="tab" aria-selected="true">Mercado</button>
  <button data-vista="cartera" role="tab" aria-selected="false">Mi cartera
   <span class="contador" id="cuentaCartera">0</span></button>
 </div>
</header>

<div class="tablero">
 <aside class="lateral">
  <div class="buscador">
   <input type="search" id="buscar" placeholder="Buscar activo o empresa"
    aria-label="Buscar activo">
  </div>
  <div class="filtros">
   <button class="filtro" data-grupo="" aria-pressed="true">Todos</button>
   {filtros}
   <button class="filtro" data-grupo="__cartera" aria-pressed="false">En cartera</button>
   <button class="filtro f-alcista" data-grupo="__sobre200"
    aria-pressed="false" title="Precio sobre la media de 200 y la media subiendo">▲ fondo alcista</button>
   <button class="filtro f-bajista" data-grupo="__bajo200"
    aria-pressed="false" title="Precio bajo la media de 200 y la media bajando">▼ fondo bajista</button>
  </div>
  <div class="lista" id="lista"></div>
 </aside>

 <main class="principal" id="principal"></main>
</div>

<footer class="pie">
 <p><strong>Este tablero no cotiza en vivo.</strong> Muestra la foto del mercado
  al momento indicado arriba y se regenera automáticamente durante la rueda.
  Antes de mandar una orden, confirmá el precio en el homebanking.</p>
 <p>Análisis técnico automatizado sobre datos históricos de Yahoo Finance. No es
  recomendación de inversión: los porcentajes históricos describen lo que ocurrió
  en la muestra analizada, no lo que va a ocurrir. Los CEDEARs se analizan sobre
  el papel original en dólares, así que los niveles hay que convertirlos con el
  ratio correspondiente.</p>
</footer>

<script id="datos" type="application/json">{payload}</script>
<script>{_script()}</script>"""


# ==========================================================================
# Comportamiento
# ==========================================================================
def _script() -> str:
    return r"""
(function () {
'use strict';
var D = JSON.parse(document.getElementById('datos').textContent);
var ACT = D.activos, POR_TK = {};
ACT.forEach(function (a) { POR_TK[a.ticker] = a; });

var CLASE = {'COMPRA FUERTE':'v-cf','COMPRA':'v-c','NEUTRAL':'v-n',
             'VENTA':'v-v','VENTA FUERTE':'v-vf','SIN DATOS':'v-x'};

var est = {
  vista: 'mercado',
  ticker: ACT.length ? ACT[0].ticker : null,
  tf: null,
  grupo: '',
  busca: '',
  cartera: cargarCartera()
};

/* ---------------- persistencia de la cartera ----------------
   Va en la direccion de la pagina (#c=IBIT,AAPL) y ademas en el almacenamiento
   del navegador. La direccion es la que manda: sobrevive a recargar, y permite
   pasarle a otro el link con la cartera ya armada. El almacenamiento es el
   respaldo, porque algunos visores lo tienen bloqueado. */
function cartereDeHash() {
  try {
    var m = (location.hash || '').match(/c=([^&]*)/);
    if (!m || !m[1]) return null;
    return decodeURIComponent(m[1]).split(',').filter(Boolean);
  } catch (x) { return null; }
}
function cargarCartera() {
  var h = cartereDeHash();
  if (h && h.length) return new Set(h);
  try {
    var g = localStorage.getItem('tablero.cartera');
    return new Set(g ? JSON.parse(g) : []);
  } catch (x) { return new Set(); }
}
function guardarCartera() {
  var lista = Array.from(est.cartera);
  try {
    localStorage.setItem('tablero.cartera', JSON.stringify(lista));
  } catch (x) { /* visor sin almacenamiento: queda la direccion */ }
  try {
    var h = lista.length ? '#c=' + encodeURIComponent(lista.join(',')) : '';
    history.replaceState(null, '', location.pathname + location.search + h);
  } catch (x) { /* visor que no deja tocar la direccion: queda el almacenamiento */ }
}

/* ---------------- utilidades ---------------- */
function esc(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function num(v, d) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  return Number(v).toLocaleString('es-AR', {minimumFractionDigits: d === undefined ? 2 : d,
                                            maximumFractionDigits: d === undefined ? 2 : d});
}
function pct(v, d) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  return (v > 0 ? '+' : '') + Number(v).toFixed(d === undefined ? 2 : d) + '%';
}
function claseVar(v) { return v > 0 ? 'alza' : (v < 0 ? 'baja' : ''); }
function tfsDe(a) { return Object.keys(a.tf); }
function tfActual(a) {
  var ts = tfsDe(a);
  return (est.tf && ts.indexOf(est.tf) >= 0) ? est.tf : (ts.indexOf('1d') >= 0 ? '1d' : ts[0]);
}
function cssVar(n) {
  return getComputedStyle(document.documentElement).getPropertyValue(n).trim() || '#888';
}

/* ---------------- panel lateral ---------------- */
function pintarLista() {
  var cont = document.getElementById('lista');
  var q = est.busca.toLowerCase();
  var vistos = ACT.filter(function (a) {
    if (est.grupo === '__cartera') { if (!est.cartera.has(a.ticker)) return false; }
    else if (est.grupo === '__sobre200') { if (!a.fondo || a.fondo.regimen !== 'alcista') return false; }
    else if (est.grupo === '__bajo200') { if (!a.fondo || a.fondo.regimen !== 'bajista') return false; }
    else if (est.grupo && a.grupo !== est.grupo) return false;
    if (!q) return true;
    return a.ticker.toLowerCase().indexOf(q) >= 0 || a.nombre.toLowerCase().indexOf(q) >= 0;
  });

  if (!vistos.length) {
    cont.innerHTML = '<p class="vacio-lista">No hay activos que coincidan.</p>';
    return;
  }
  cont.innerHTML = vistos.map(function (a) {
    var t = a.tf[tfActual(a)] || a.tf[tfsDe(a)[0]];
    var v = t.variaciones['1 vela'];
    // La senal de mas peso como motivo detras del color. Va completa: el CSS la
    // recorta con puntos suspensivos segun el ancho real, en vez de cortarla
    // a ciegas en un numero fijo de letras.
    var motivo = t.senales.length ? t.senales[0].detalle.split(':')[0].split(' (')[0].trim() : a.nombre;
    return '<div class="item" data-tk="' + esc(a.ticker) + '" tabindex="0" role="button"' +
      ' aria-current="' + (a.ticker === est.ticker) + '"' +
      ' data-encartera="' + (est.cartera.has(a.ticker) ? '1' : '0') + '">' +
      '<span class="tilde" data-marcar="' + esc(a.ticker) + '" title="Agregar a mi cartera">✓</span>' +
      '<span><span class="tk">' + esc(a.ticker) + '</span>' +
      (t.ajuste ? '<span class="ojo" title="' + esc(t.ajuste) + '">⚠</span>' : '') +
      (a.fondo ? '<span class="mfondo f-' + a.fondo.regimen + '" title="Media de 200 en diario: ' +
        esc(a.fondo.resumen) + '">' +
        (a.fondo.regimen === 'alcista' ? '▲' : a.fondo.regimen === 'bajista' ? '▼' : '=') +
        '</span>' : '') +
      '<span class="nm" title="' + esc(a.nombre) + ' · ' + esc(motivo) + '">' + esc(motivo) + '</span></span>' +
      '<span class="pc num"><span class="punto ' + CLASE[a.consenso.veredicto] + '"></span>' +
      '<span class="' + claseVar(v) + '">' + pct(v) + '</span></span></div>';
  }).join('');
}

/* ---------------- ficha del activo ---------------- */
function tablaInvesting(t) {
  var inv = t.investing;
  if (!inv || !inv.filas || !inv.filas.length) return '';
  var clase = function (s) {
    if (s === 'COMPRA') return 'alza';
    if (s === 'VENTA') return 'baja';
    return 'nota';
  };
  var fila = function (f) {
    return '<tr><td>' + esc(f.nombre) + '</td>' +
      '<td class="n">' + (f.valor === null ? '—' : num(f.valor, Math.abs(f.valor) >= 10 ? 2 : 4)) + '</td>' +
      '<td class="' + clase(f.senal) + '">' + esc(f.senal.toLowerCase()) + '</td></tr>';
  };
  return '<details><summary>Cómo lee este gráfico Investing.com</summary>' +
    '<div class="interior">' +
    '<p>Investing usa otros indicadores y otras reglas que TradingView, que es el ' +
    'criterio del veredicto principal. Las diferencias de fondo: Investing mira ' +
    'STOCH(9,6), CCI(14), ROC y Highs/Lows, mientras TradingView mira STOCH(14,3,3), ' +
    'CCI(20), Awesome Oscillator y Momentum. Y sobre todo, Investing vota compra con ' +
    'el RSI por encima de 50, mientras TradingView solo lo hace si viene de sobreventa ' +
    'girando al alza. Por eso Investing marca compra bastante más seguido.</p>' +
    '<p class="nota">Lo que está en sobrecompra, sobreventa o marcando volatilidad ' +
    'queda fuera del conteo, igual que en Investing.</p>' +
    '<div class="tabla-caja"><table><thead><tr><th>Indicador</th>' +
    '<th class="n">Valor</th><th>Señal</th></tr></thead><tbody>' +
    inv.filas.map(fila).join('') + '</tbody></table></div>' +
    '<p class="nota">Medias móviles (5, 10, 20, 50, 100 y 200, simple y exponencial): ' +
    inv.medias.compra + ' compra, ' + inv.medias.venta + ' venta. ' +
    'Los valores salen de Yahoo Finance, así que pueden diferir un poco de los que ' +
    'muestra Investing con su propio proveedor.</p>' +
    '</div></details>';
}

function bloqueSenales(t) {
  if (!t.senales.length) return '<p class="nota">Sin señales relevantes en las últimas velas.</p>';
  return '<ul class="senales">' + t.senales.map(function (s) {
    var m = s.sesgo === 'alcista' ? '<span class="mk alza">▲</span>'
          : (s.sesgo === 'bajista' ? '<span class="mk baja">▼</span>' : '<span class="mk">•</span>');
    return '<li>' + m + '<span>' + esc(s.detalle) + '</span></li>';
  }).join('') + '</ul>';
}

function bloqueEscenarios(t, fondo) {
  if (!t.entradas.length) return '<p class="nota">Ningún escenario dentro del rango del perfil.</p>';
  // Una compra contra la tendencia de fondo no está prohibida, pero es otra
  // operación: hay que saber que se está yendo contra la corriente.
  var contra = fondo && fondo.regimen === 'bajista'
    ? '<div class="alerta"><span class="mk">!</span><span>Va contra la tendencia de fondo: ' +
      'el precio está bajo la media de ' + fondo.periodos + ' y la media viene bajando. ' +
      'Los rebotes acá suelen durar poco.</span></div>'
    : '';
  return t.entradas.map(function (x) {
    var alertas = (x.avisos || []).map(function (a) {
      return '<div class="alerta"><span class="mk">!</span><span>' + esc(a) + '</span></div>';
    }).join('');
    var cuerpo;
    if (x.direccion === 'salida') {
      cuerpo = '<div class="esc-datos"><div>Quiebre<b>' + num(x.min, t.dec) + '</b></div>' +
        '<div>Soporte<b>' + num(x.max, t.dec) + '</b></div></div>' +
        (x.nota ? '<p class="txt">' + esc(x.nota) + '</p>' : '');
    } else {
      cuerpo = '<div class="esc-datos">' +
        '<div>Zona de entrada<b>' + num(x.min, t.dec) + ' – ' + num(x.max, t.dec) + '</b></div>' +
        '<div>Stop<b class="baja">' + num(x.stop, t.dec) + '</b></div>' +
        '<div>Objetivo<b class="alza">' + num(x.objetivo, t.dec) + '</b></div>' +
        '<div>Riesgo<b>' + num(x.riesgo, 1) + '%</b></div>' +
        '<div>Beneficio<b>+' + num(x.beneficio, 1) + '%</b></div>' +
        '<div>R:R<b>' + num(x.rr, 2) + '</b></div></div>';
    }
    return '<div class="esc' + (x.direccion === 'salida' ? ' salida' : '') + '">' +
      '<div class="esc-cab"><span class="esc-nm">' + esc(x.escenario) + '</span>' +
      '<span class="nota">confluencia <span class="barrita"><i style="width:' +
      x.confianza + '%"></i></span> ' + Math.round(x.confianza) + '</span></div>' +
      cuerpo +
      '<p class="txt"><b>Se activa:</b> ' + esc(x.disparador) + '</p>' +
      '<p class="txt"><b>Se cae:</b> ' + esc(x.invalidacion) + '</p>' + alertas +
      (x.direccion === 'largo' ? contra : '') + '</div>';
  }).join('');
}

function bloqueNiveles(t) {
  var filas = t.zonas.slice().sort(function (a, b) { return b.precio - a.precio; })
    .map(function (z) {
      var dist = 100 * (z.precio - t.precio) / t.precio;
      return '<tr><td class="' + (z.tipo === 'soporte' ? 'alza' : 'baja') + '">' +
        (z.tipo === 'soporte' ? 'S' : 'R') + '</td>' +
        '<td class="n">' + num(z.precio, t.dec) + '</td>' +
        '<td class="n">' + pct(dist) + '</td>' +
        '<td class="n">' + Math.round(z.fuerza) + '</td>' +
        '<td class="col-barra"><span class="barrita"><i style="width:' + z.fuerza + '%"></i></span></td>' +
        '<td class="nota">' + esc(z.origen) + '</td></tr>';
    }).join('');
  return '<div class="tabla-caja"><table class="tabla-niveles"><thead><tr><th></th><th class="n">Precio</th>' +
    '<th class="n">Dist.</th><th class="n">Fuerza</th><th class="col-barra"></th><th>Origen</th>' +
    '</tr></thead><tbody>' + filas + '</tbody></table></div>';
}

function bloqueBacktest(t) {
  if (!t.backtest) return '';
  var b = t.backtest, base = b.base, c = b.config, dg = b.diagnostico;
  var filas = '<tr><td><b>Entrando en cualquier vela</b></td><td class="n">' +
    base.operaciones + '</td><td class="n">' + num(base.toco_objetivo_pct, 1) + '%</td>' +
    '<td class="n">' + num(base.toco_stop_pct, 1) + '%</td><td class="n">' +
    num(base.profit_factor, 2) + '</td><td class="n">—</td></tr>';
  filas += b.senales.map(function (s) {
    return '<tr><td>' + esc(s.senal) + '</td><td class="n">' + s.operaciones + '</td>' +
      '<td class="n">' + num(s.toco_objetivo_pct, 1) + '%</td>' +
      '<td class="n">' + num(s.toco_stop_pct, 1) + '%</td>' +
      '<td class="n">' + num(s.profit_factor, 2) + '</td>' +
      '<td class="n ' + (s.ventaja_pp > 0 ? 'alza' : 'baja') + '">' +
      (s.ventaja_pp > 0 ? '+' : '') + num(s.ventaja_pp, 1) + '</td></tr>';
  }).join('');
  return '<details><summary>Qué pasó históricamente con este stop y este objetivo</summary>' +
    '<div class="interior"><p>Sobre ' + base.operaciones + ' entradas simuladas: cuántas veces ' +
    'el precio llegó a <b>+' + c.tp_pct + '%</b> antes de caer <b>−' + c.sl_pct + '%</b>, ' +
    'dentro de ' + c.max_velas + ' velas. Si una señal no le gana a la línea de base, no aporta.</p>' +
    '<div class="tabla-caja"><table><thead><tr><th>Caso</th><th class="n">Casos</th>' +
    '<th class="n">Llegó</th><th class="n">Saltó stop</th><th class="n">P.Factor</th>' +
    '<th class="n">vs base</th></tr></thead><tbody>' + filas + '</tbody></table></div>' +
    '<p class="nota">El stop equivale a ' + num(dg.stop_en_atr, 1) + ' ATR y el objetivo a ' +
    num(dg.objetivo_en_atr, 1) + ' ATR. Volatilidad anualizada ' +
    num(dg.volatilidad_anual_pct, 1) + '%. De las que terminaron ganando, el 80% nunca fue ' +
    'más de ' + num(Math.abs(base.mae_p80_ganadoras_pct), 1) + '% en contra.</p></div></details>';
}

function pintarFicha() {
  var a = POR_TK[est.ticker];
  var cont = document.getElementById('principal');
  if (!a) { cont.innerHTML = ''; return; }
  var tf = tfActual(a), t = a.tf[tf];
  var v = t.variaciones['1 vela'];
  var enCartera = est.cartera.has(a.ticker);

  var pestanas = tfsDe(a).map(function (k) {
    return '<button data-tf="' + k + '" role="tab" aria-selected="' + (k === tf) + '">' + k + '</button>';
  }).join('');

  var avisoTf = a.errores.length
    ? '<p class="nota">Sin datos de ' + esc(a.errores.join(', ')) + ' para este activo.</p>' : '';
  var avisoAlin = a.consenso.temporalidades_alineadas || Object.keys(a.consenso.detalle).length < 2
    ? '' : '<div class="aviso-azul">Las temporalidades no coinciden entre sí: la señal es más ' +
          'débil de lo que sugiere el veredicto.</div>';
  var avisoAjuste = t.ajuste
    ? '<div class="aviso-azul"><b>Veredicto moderado.</b> ' + esc(t.ajuste) + '.</div>' : '';

  // Segunda lectura con el criterio de Investing.com. Cuando los dos criterios
  // coinciden la señal es mas solida; cuando difieren, conviene verlo.
  var inv = t.investing;
  var bloqueInv = inv
    ? '<div class="celda"><span class="et">Resumen técnico · Investing</span>' +
      '<span class="vd ' + CLASE[inv.veredicto] + '">' + esc(inv.veredicto) + '</span>' +
      '<div class="pi">osciladores ' + inv.osciladores.compra + '↑ ' +
       inv.osciladores.venta + '↓ · medias ' + inv.medias.compra + '↑ ' +
       inv.medias.venta + '↓' +
       (inv.osciladores.sin_voto ? ' · ' + inv.osciladores.sin_voto + ' sin voto' : '') +
      '</div></div>'
    : '';
  // Tendencia de fondo: la media de 200 en diario. Se muestra en todas las
  // temporalidades porque es el marco, no una lectura del momento.
  var f = a.fondo;
  var bloqueFondo = '';
  if (f) {
    var etiqueta = {alcista: 'Alcista', bajista: 'Bajista', transicion: 'En transición'}[f.regimen];
    var claseF = {alcista: 'fondo-alcista', bajista: 'fondo-bajista', transicion: 'fondo-transicion'}[f.regimen];
    var cruce = f.cruce_medias
      ? '<span class="pastilla ' + (f.cruce_medias === 'dorado' ? 'alza' : 'baja') + '">cruce ' +
        (f.cruce_medias === 'dorado' ? 'dorado' : 'de la muerte') +
        (f.velas_desde_cruce !== null && f.velas_desde_cruce !== undefined
          ? ' hace ' + f.velas_desde_cruce + (f.velas_desde_cruce === 1 ? ' rueda' : ' ruedas') : '') +
        '</span>' : '';
    bloqueFondo =
      '<div class="fondo ' + claseF + '">' +
       '<div class="fondo-cab">' +
        '<span class="fondo-tit">Tendencia de fondo · media de ' + f.periodos + ' en diario</span>' +
        '<span class="fondo-vd">' + etiqueta + '</span>' +
       '</div>' +
       '<div class="fondo-datos">' +
        '<span>media <b>' + num(f.media, f.media >= 1000 ? 0 : 2) + '</b></span>' +
        '<span>precio <b class="' + (f.encima ? 'alza' : 'baja') + '">' + pct(f.distancia_pct, 1) + '</b></span>' +
        '<span>la media viene <b>' + esc(f.pendiente) + '</b> (' + pct(f.pendiente_pct, 1) + ' en 20)</span>' +
        '<span>' + (f.encima ? 'encima' : 'debajo') + ' hace <b>' + f.velas_del_lado + '</b> ruedas</span>' +
       '</div>' +
       (cruce ? '<div style="margin-top:6px">' + cruce + '</div>' : '') +
       '<p class="fondo-txt">' + esc(f.texto) + '</p>' +
      '</div>';
  }

  var avisoCruce = inv
    ? (inv.coincide
        ? '<div class="cruce ok"><b>Los dos criterios coinciden</b> en ' +
          esc(inv.veredicto.toLowerCase().replace(" fuerte", "")) +
          '. Dos lecturas independientes apuntando al mismo lado: la señal es más sólida.</div>'
        : '<div class="cruce difiere"><b>Los criterios no coinciden:</b> el nuestro dice ' +
          esc(t.resumen.veredicto.toLowerCase()) + ' y el de Investing, ' +
          esc(inv.veredicto.toLowerCase()) +
          '. Cuando pasa esto conviene no forzar la entrada y esperar que se alineen.</div>')
    : '';

  // La aptitud del par stop/objetivo va arriba, no enterrada: es lo que dice
  // si tiene sentido operar este activo con estos numeros.
  var apt = t.backtest && t.backtest.aptitud;
  var claseApt = {buena:'alza', aceptable:'', neutra:'', mala:'baja', sin_datos:''};
  var bloqueApt = apt
    ? '<div class="celda"><span class="et">Stop −' + D.riesgo.stop + '% / objetivo +' + D.riesgo.objetivo +
      '% en este activo</span><span class="vl ' + (claseApt[apt.nivel] || '') + '" style="font-size:.84rem;font-family:inherit;font-weight:600">' +
      (apt.nivel === 'buena' ? 'Funciona bien' : apt.nivel === 'aceptable' ? 'Funciona, justo' :
       apt.nivel === 'neutra' ? 'Empata' : apt.nivel === 'mala' ? 'Pierde históricamente' : 'Sin datos') +
      '</span><div class="pi">' + esc(apt.texto) + (apt.aviso_stop ? ' · ' + esc(apt.aviso_stop) : '') + '</div></div>'
    : '';

  cont.innerHTML =
   '<section class="tarjeta">' +
    '<div class="tarjeta-cab">' +
     '<div class="identidad"><span class="tk">' + esc(a.ticker) + '</span>' +
      '<span class="nm">' + esc(a.nombre) + '</span>' +
      '<span class="pc">' + num(t.precio, t.dec) + '</span>' +
      '<span class="pc ' + claseVar(v) + '" style="font-size:.92rem">' + pct(v) + '</span></div>' +
     '<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">' +
      (a.cambio ? '<span class="viro">venía de ' + esc(a.cambio) + '</span>' : '') +
      '<span class="vd ' + CLASE[a.consenso.veredicto] + '">' + esc(a.consenso.veredicto) + '</span>' +
      '<button class="herr ancho" id="btnCartera">' +
        (enCartera ? '✓ En mi cartera' : '+ Agregar a mi cartera') + '</button>' +
     '</div>' +
    '</div>' +

    '<div class="grafico-cab">' +
     '<div class="pestanas" role="tablist" id="tabsTf">' + pestanas + '</div>' +
     '<div class="herramientas">' +
      '<button class="herr" data-zoom="-1" title="Alejar" aria-label="Alejar">−</button>' +
      '<button class="herr" data-zoom="1" title="Acercar" aria-label="Acercar">+</button>' +
      '<button class="herr" data-alto="-1" title="Comprimir vertical" aria-label="Comprimir vertical">↕−</button>' +
      '<button class="herr" data-alto="1" title="Estirar vertical" aria-label="Estirar vertical">↕+</button>' +
      '<button class="herr ancho" data-reset="1" title="Volver a la vista completa">Ajustar</button>' +
     '</div>' +
    '</div>' +
    '<div class="lienzo-caja"><canvas id="lienzo"></canvas>' +
     '<div class="lectura" id="lectura" hidden></div></div>' +
    '<div class="lienzo-caja"><canvas id="lienzoRsi"></canvas></div>' +
    '<div class="leyenda">' +
     '<span><i class="trazo" style="background:var(--acento)"></i>EMA ' + D.medias[0] + '</span>' +
     '<span><i class="trazo" style="background:var(--warn)"></i>EMA ' + D.medias[D.medias.length-1] + '</span>' +
     '<span><i class="trazo" style="background:var(--alza)"></i>soporte</span>' +
     '<span><i class="trazo" style="background:var(--baja)"></i>resistencia</span>' +
     '<span><i class="trazo" style="background:var(--acento);opacity:.4"></i>zona de entrada</span>' +
    '</div>' +
    '<p class="pista">Rueda del mouse para acercar · arrastrar para desplazar · ' +
     'doble clic para volver a la vista completa</p>' +
   '</section>' +

   '<section class="tarjeta"><div class="tarjeta-cuerpo">' +
    bloqueFondo + avisoCruce + avisoAjuste + avisoAlin + avisoTf +
    '<div class="reja">' +
     '<div class="celda"><span class="et">Resumen técnico · TradingView</span>' +
      '<span class="vd ' + CLASE[t.resumen.veredicto] + '">' + esc(t.resumen.veredicto) + '</span>' +
      '<div class="pi">osciladores ' + t.resumen.osciladores.compra + '↑ ' +
       t.resumen.osciladores.venta + '↓ · medias ' + t.resumen.medias.compra + '↑ ' +
       t.resumen.medias.venta + '↓</div></div>' +
     bloqueInv +
     bloqueApt +
     '<div class="celda"><span class="et">Volatilidad (ATR)</span>' +
      '<span class="vl">' + num(t.atr_pct, 2) + '%</span>' +
      '<div class="pi">' + num(t.atr, t.dec) + ' por vela</div></div>' +
     '<div class="celda"><span class="et">Volumen</span>' +
      '<span class="vl">' + (t.vol_rel ? num(t.vol_rel, 1) + '×' : '—') + '</span>' +
      '<div class="pi">contra el promedio de 20</div></div>' +
     '<div class="celda"><span class="et">Último dato</span>' +
      '<span class="vl" style="font-size:.83rem">' + esc(t.fecha) + '</span>' +
      '<div class="pi">' + t.velas_total + ' velas analizadas</div></div>' +
    '</div>' +
    tablaInvesting(t) +
    '<h3>Señales activas</h3>' + bloqueSenales(t) +
    '<h3>Escenarios</h3>' + bloqueEscenarios(t, a.fondo) +
    '<h3>Soportes y resistencias</h3>' + bloqueNiveles(t) +
    bloqueBacktest(t) +
   '</div></section>';

  vista = null;   // el grafico se re-encuadra al cambiar de activo o temporalidad
  dibujar();
}

/* ---------------- cartera ---------------- */
function pintarCartera() {
  var cont = document.getElementById('principal');
  var lista = ACT.filter(function (a) { return est.cartera.has(a.ticker); });

  if (!lista.length) {
    cont.innerHTML = '<section class="tarjeta"><div class="cartera-vacia">' +
      '<b>Todavía no armaste tu cartera</b>' +
      'Marcá el casillero de los activos que tenés, en la lista de la izquierda, ' +
      'y acá vas a ver el análisis consolidado de todos juntos.</div></section>';
    return;
  }

  var cuenta = {}, suma = 0;
  lista.forEach(function (a) {
    var v = a.consenso.veredicto;
    cuenta[v] = (cuenta[v] || 0) + 1;
    suma += a.consenso.promedio;
  });
  var prom = suma / lista.length;
  var veredicto = prom >= 0.5 ? 'COMPRA FUERTE' : (prom >= 0.1 ? 'COMPRA' :
                  (prom > -0.1 ? 'NEUTRAL' : (prom > -0.5 ? 'VENTA' : 'VENTA FUERTE')));

  var alcistas = (cuenta['COMPRA FUERTE'] || 0) + (cuenta['COMPRA'] || 0);
  var bajistas = (cuenta['VENTA FUERTE'] || 0) + (cuenta['VENTA'] || 0);

  // Lo que pide atencion hoy: posiciones sobreextendidas (candidatas a tomar
  // ganancia) y activos donde el par stop/objetivo pierde historicamente.
  var extendidos = lista.filter(function (a) {
    var t = a.tf[tfActual(a)] || a.tf[tfsDe(a)[0]]; return !!t.ajuste;
  });
  var parMalo = lista.filter(function (a) {
    var t = a.tf[tfActual(a)] || a.tf[tfsDe(a)[0]];
    return t.backtest && t.backtest.aptitud && t.backtest.aptitud.nivel === 'mala';
  });
  var atencion = '';
  if (extendidos.length) {
    atencion += '<div class="aviso-azul"><b>Sobreextendidos:</b> ' +
      extendidos.map(function (a) { return esc(a.ticker); }).join(', ') +
      '. Vienen de subir o bajar fuerte; si ya estás adentro, es momento de revisar ' +
      'stops y tomas parciales, no de agregar.</div>';
  }
  if (parMalo.length) {
    atencion += '<div class="alerta"><span class="mk">!</span><span><b>El par −' +
      D.riesgo.stop + '% / +' + D.riesgo.objetivo + '% pierde históricamente en:</b> ' +
      parMalo.map(function (a) { return esc(a.ticker); }).join(', ') +
      '. Para estos conviene otro stop u objetivo; mirá el detalle de cada uno.</span></div>';
  }

  // Grupos representados: una cartera de un solo rubro se mueve toda junta.
  var porGrupo = {};
  lista.forEach(function (a) { porGrupo[a.grupo] = (porGrupo[a.grupo] || 0) + 1; });
  var gs = Object.keys(porGrupo).sort(function (x, y) { return porGrupo[y] - porGrupo[x]; });
  var mayor = porGrupo[gs[0]] / lista.length;
  var concentracion = gs.length === 1
    ? 'Toda la cartera está en ' + (D.grupos[gs[0]] || gs[0]).toLowerCase() +
      ': se va a mover casi en bloque.'
    : (mayor >= 0.6
        ? Math.round(mayor * 100) + '% de la cartera está en ' +
          (D.grupos[gs[0]] || gs[0]).toLowerCase() + '.'
        : 'Repartida entre ' + gs.length + ' rubros.');

  var oportunidades = [];
  lista.forEach(function (a) {
    var t = a.tf[tfActual(a)] || a.tf[tfsDe(a)[0]];
    (t.entradas || []).forEach(function (x) {
      if (x.direccion !== 'largo' || !x.rr) return;
      oportunidades.push({tk: a.ticker, nm: a.nombre, x: x, t: t,
                          dist: 100 * ((x.min + x.max) / 2 - t.precio) / t.precio});
    });
  });
  oportunidades.sort(function (p, q) { return q.x.confianza - p.x.confianza; });

  var filasOp = oportunidades.slice(0, 8).map(function (o) {
    return '<tr class="clicable" data-tk="' + esc(o.tk) + '">' +
      '<td><b class="num">' + esc(o.tk) + '</b></td>' +
      '<td>' + esc(o.x.escenario) + '</td>' +
      '<td class="n">' + num(o.x.min, o.t.dec) + ' – ' + num(o.x.max, o.t.dec) + '</td>' +
      '<td class="n">' + pct(o.dist, 1) + '</td>' +
      '<td class="n">' + num(o.x.rr, 2) + '</td>' +
      '<td class="n">' + Math.round(o.x.confianza) + '</td></tr>';
  }).join('');

  var filasPos = lista.slice().sort(function (p, q) {
    return q.consenso.promedio - p.consenso.promedio;
  }).map(function (a) {
    var t = a.tf[tfActual(a)] || a.tf[tfsDe(a)[0]];
    var v = t.variaciones['1 vela'];
    return '<tr class="clicable" data-tk="' + esc(a.ticker) + '">' +
      '<td><b class="num">' + esc(a.ticker) + '</b><br><span class="nota">' +
        esc(a.nombre) + '</span></td>' +
      '<td class="n">' + num(t.precio, t.dec) + '</td>' +
      '<td class="n ' + claseVar(v) + '">' + pct(v) + '</td>' +
      '<td><span class="vd ' + CLASE[a.consenso.veredicto] + '">' +
        esc(a.consenso.veredicto) + '</span>' +
        (a.cambio ? ' <span class="viro">venía de ' + esc(a.cambio) + '</span>' : '') + '</td>' +
      '<td class="n">' + num(t.atr_pct, 1) + '%</td>' +
      '<td><button class="herr ancho" data-quitar="' + esc(a.ticker) + '">Quitar</button></td></tr>';
  }).join('');

  cont.innerHTML =
   '<section class="tarjeta">' +
    '<div class="tarjeta-cab"><h2>Consolidado de tu cartera</h2>' +
     '<span class="vd ' + CLASE[veredicto] + '">' + veredicto + '</span></div>' +
    '<div class="tarjeta-cuerpo">' +
     '<div class="reja">' +
      '<div class="celda"><span class="et">Activos</span><span class="vl">' +
       lista.length + '</span><div class="pi">' + esc(concentracion) + '</div></div>' +
      '<div class="celda"><span class="et">A favor</span><span class="vl alza">' +
       alcistas + '</span><div class="pi">en compra o compra fuerte</div></div>' +
      '<div class="celda"><span class="et">En contra</span><span class="vl baja">' +
       bajistas + '</span><div class="pi">en venta o venta fuerte</div></div>' +
      '<div class="celda"><span class="et">Score promedio</span><span class="vl">' +
       (prom >= 0 ? '+' : '') + prom.toFixed(2) + '</span>' +
       '<div class="pi">de −1 a +1</div></div>' +
     '</div>' +
     '<p class="nota" style="margin-top:11px">El consolidado pesa todos los activos ' +
      'por igual: es el estado técnico del conjunto, no el rendimiento de tu plata.</p>' +
     (atencion ? '<div style="margin-top:12px">' + atencion + '</div>' : '') +
    '</div>' +
   '</section>' +

   (filasOp ? '<section class="tarjeta"><div class="tarjeta-cab">' +
     '<h2>Mejores oportunidades de tu cartera</h2></div><div class="tarjeta-cuerpo">' +
     '<div class="tabla-caja"><table><thead><tr><th>Activo</th><th>Escenario</th>' +
     '<th class="n">Zona</th><th class="n">Distancia</th><th class="n">R:R</th>' +
     '<th class="n">Confl.</th></tr></thead><tbody>' + filasOp + '</tbody></table></div>' +
     '<p class="nota">Ordenadas por confluencia. Tocá una fila para ver el gráfico.</p>' +
     '</div></section>' : '') +

   '<section class="tarjeta"><div class="tarjeta-cab"><h2>Posiciones</h2></div>' +
    '<div class="tarjeta-cuerpo"><div class="tabla-caja"><table><thead><tr>' +
    '<th>Activo</th><th class="n">Precio</th><th class="n">Día</th><th>Veredicto</th>' +
    '<th class="n">ATR</th><th></th></tr></thead><tbody>' + filasPos +
    '</tbody></table></div></div></section>';
}

/* ==================== GRAFICO ==================== */
var vista = null;   // {desde, hasta, escalaY} — null = encuadre automatico
var cursor = null;  // {x, y} en pixeles del lienzo, null = fuera del grafico
var geo = null;     // geometria del ultimo dibujo, para traducir el cursor a datos

function datosGrafico() {
  var a = POR_TK[est.ticker];
  if (!a) return null;
  return a.tf[tfActual(a)];
}

function encuadre(t) {
  var n = t.velas.c.length;
  if (!vista) vista = {desde: Math.max(0, n - 90), hasta: n, escalaY: 1};
  vista.desde = Math.max(0, Math.min(vista.desde, n - 8));
  vista.hasta = Math.min(n, Math.max(vista.hasta, vista.desde + 8));
  return vista;
}

function prepararLienzo(cv) {
  var dpr = window.devicePixelRatio || 1;
  var w = cv.clientWidth, h = cv.clientHeight;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
  }
  var ctx = cv.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return {ctx: ctx, w: w, h: h};
}

function dibujar() {
  var t = datosGrafico();
  var cv = document.getElementById('lienzo');
  if (!t || !cv) return;
  var v = encuadre(t);
  var L = prepararLienzo(cv), ctx = L.ctx, W = L.w, H = L.h;
  var mDer = 62, mSup = 8, mInf = 18, ancho = W - mDer - 4;

  var C = {
    linea: cssVar('--linea-2'), eje: cssVar('--muted'),
    alza: cssVar('--alza'), baja: cssVar('--baja'),
    acento: cssVar('--acento'), warn: cssVar('--warn'), ink: cssVar('--ink')
  };

  var i0 = Math.floor(v.desde), i1 = Math.ceil(v.hasta);
  var hi = -Infinity, lo = Infinity;
  for (var i = i0; i < i1; i++) {
    if (t.velas.h[i] > hi) hi = t.velas.h[i];
    if (t.velas.l[i] < lo) lo = t.velas.l[i];
  }
  Object.keys(t.medias).forEach(function (k) {
    for (var i = i0; i < i1; i++) {
      var m = t.medias[k][i];
      if (m !== null) { if (m > hi) hi = m; if (m < lo) lo = m; }
    }
  });
  // Los niveles cercanos entran en el encuadre: si quedan afuera no se ven.
  t.zonas.forEach(function (z) {
    if (z.precio < hi * 1.05 && z.precio > lo * 0.95) {
      if (z.precio > hi) hi = z.precio;
      if (z.precio < lo) lo = z.precio;
    }
  });
  if (!isFinite(hi) || !isFinite(lo) || hi <= lo) return;

  var centro = (hi + lo) / 2, medio = (hi - lo) / 2 / v.escalaY;
  hi = centro + medio * 1.06; lo = centro - medio * 1.06;

  var n = i1 - i0, paso = ancho / n;
  function X(i) { return 4 + (i - i0 + 0.5) * paso; }
  function Y(p) { return mSup + (H - mSup - mInf) * (hi - p) / (hi - lo); }

  ctx.font = '9px "IBM Plex Mono", monospace';
  ctx.textBaseline = 'middle';

  for (var g = 0; g <= 4; g++) {
    var pr = lo + (hi - lo) * g / 4, y = Y(pr);
    ctx.strokeStyle = C.linea; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(4, y); ctx.lineTo(4 + ancho, y); ctx.stroke();
    ctx.fillStyle = C.eje; ctx.textAlign = 'left';
    ctx.fillText(fmtPrecio(pr, t.dec), 4 + ancho + 6, y);
  }

  var mejor = null;
  for (var k = 0; k < t.entradas.length; k++) {
    if (t.entradas[k].direccion === 'largo') { mejor = t.entradas[k]; break; }
  }
  if (mejor && mejor.min !== null) {
    var yA = Y(Math.max(mejor.min, mejor.max)), yB = Y(Math.min(mejor.min, mejor.max));
    ctx.fillStyle = C.acento; ctx.globalAlpha = 0.13;
    ctx.fillRect(4, yA, ancho, Math.max(yB - yA, 2));
    ctx.globalAlpha = 1;
  }

  t.zonas.slice(0, 6).forEach(function (z) {
    var y = Y(z.precio);
    if (y < mSup || y > H - mInf) return;
    ctx.strokeStyle = z.tipo === 'soporte' ? C.alza : C.baja;
    ctx.lineWidth = 0.7 + (z.fuerza / 100) * 1.1;
    ctx.setLineDash([5, 3]); ctx.globalAlpha = 0.8;
    ctx.beginPath(); ctx.moveTo(4, y); ctx.lineTo(4 + ancho, y); ctx.stroke();
    ctx.setLineDash([]); ctx.globalAlpha = 1;
    ctx.fillStyle = z.tipo === 'soporte' ? C.alza : C.baja;
    ctx.textAlign = 'left';
    ctx.fillText(fmtPrecio(z.precio, t.dec), 4 + ancho + 6, y);
  });

  var cuerpo = Math.max(Math.min(paso * 0.62, 11), 1);
  for (var i = i0; i < i1; i++) {
    var o = t.velas.o[i], c = t.velas.c[i], x = X(i);
    var sube = c >= o, col = sube ? C.alza : C.baja;
    ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(Math.round(x) + 0.5, Y(t.velas.h[i]));
    ctx.lineTo(Math.round(x) + 0.5, Y(t.velas.l[i]));
    ctx.stroke();
    var yo = Y(o), yc = Y(c);
    ctx.fillRect(x - cuerpo / 2, Math.min(yo, yc), cuerpo, Math.max(Math.abs(yc - yo), 1));
  }

  var colores = [C.acento, C.warn];
  Object.keys(t.medias).forEach(function (k, idx) {
    ctx.strokeStyle = colores[idx % colores.length];
    ctx.lineWidth = 1.4;
    if (idx === 1) ctx.setLineDash([4, 2.5]);
    ctx.beginPath();
    var arranco = false;
    for (var i = i0; i < i1; i++) {
      var m = t.medias[k][i];
      if (m === null) continue;
      if (!arranco) { ctx.moveTo(X(i), Y(m)); arranco = true; }
      else ctx.lineTo(X(i), Y(m));
    }
    ctx.stroke(); ctx.setLineDash([]);
  });

  ctx.fillStyle = C.eje; ctx.textAlign = 'center';
  [i0, Math.floor((i0 + i1) / 2), i1 - 1].forEach(function (i) {
    if (i < 0 || i >= t.velas.t.length) return;
    var f = new Date(t.velas.t[i] * 1000);
    var et = ('0' + f.getDate()).slice(-2) + '/' + ('0' + (f.getMonth() + 1)).slice(-2);
    ctx.fillText(et, X(i), H - 7);
  });

  // Linea del ultimo precio, para leer de un vistazo donde esta hoy.
  var ult = t.velas.c[i1 - 1];
  if (ult !== null && ult !== undefined) {
    var yU = Y(ult);
    if (yU >= mSup && yU <= H - mInf) {
      ctx.strokeStyle = C.ink; ctx.globalAlpha = 0.5; ctx.setLineDash([2, 3]); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(4, yU); ctx.lineTo(4 + ancho, yU); ctx.stroke();
      ctx.setLineDash([]); ctx.globalAlpha = 1;
      ctx.fillStyle = C.ink; ctx.fillRect(4 + ancho + 2, yU - 7, mDer - 4, 14);
      ctx.fillStyle = cssVar('--panel'); ctx.textAlign = 'left';
      ctx.fillText(fmtPrecio(ult, t.dec), 4 + ancho + 6, yU);
    }
  }

  geo = {i0: i0, i1: i1, paso: paso, X: X, Y: Y, hi: hi, lo: lo,
         mSup: mSup, mInf: mInf, H: H, ancho: ancho, t: t};
  dibujarCrosshair();
  dibujarRsi(t, i0, i1, paso, X);
}

function dibujarCrosshair() {
  var caja = document.getElementById('lectura');
  if (!geo || !cursor || !caja) { if (caja) caja.hidden = true; return; }
  var g = geo, t = g.t;
  var i = Math.floor(g.i0 + (cursor.x - 4) / g.paso);
  if (i < g.i0 || i >= g.i1 || cursor.x > 4 + g.ancho) { caja.hidden = true; return; }

  var cv = document.getElementById('lienzo');
  var ctx = cv.getContext('2d');
  var x = g.X(i);
  var precioY = g.hi - (cursor.y - g.mSup) / (g.H - g.mSup - g.mInf) * (g.hi - g.lo);

  ctx.save();
  ctx.strokeStyle = cssVar('--muted'); ctx.globalAlpha = 0.6;
  ctx.setLineDash([3, 3]); ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(x, g.mSup); ctx.lineTo(x, g.H - g.mInf); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(4, cursor.y); ctx.lineTo(4 + g.ancho, cursor.y); ctx.stroke();
  ctx.restore();

  // Precio bajo el cursor, en el eje.
  ctx.fillStyle = cssVar('--muted'); ctx.fillRect(4 + g.ancho + 2, cursor.y - 7, 58, 14);
  ctx.fillStyle = cssVar('--panel'); ctx.font = '9px "IBM Plex Mono", monospace';
  ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
  ctx.fillText(fmtPrecio(precioY, t.dec), 4 + g.ancho + 6, cursor.y);

  var o = t.velas.o[i], h = t.velas.h[i], l = t.velas.l[i], c = t.velas.c[i];
  var f = new Date(t.velas.t[i] * 1000);
  var fecha = ('0' + f.getDate()).slice(-2) + '/' + ('0' + (f.getMonth() + 1)).slice(-2) +
    (t.velas.t.length && (t.velas.t[1] - t.velas.t[0]) < 86400
      ? ' ' + ('0' + f.getHours()).slice(-2) + ':' + ('0' + f.getMinutes()).slice(-2) : '');
  var var1 = o ? 100 * (c - o) / o : 0;
  var rsi = t.rsi[i];
  caja.innerHTML = '<span class="f">' + esc(fecha) + '</span>' +
    'A <b>' + fmtPrecio(o, t.dec) + '</b> · M <b>' + fmtPrecio(h, t.dec) + '</b><br>' +
    'm <b>' + fmtPrecio(l, t.dec) + '</b> · C <b class="' + claseVar(var1) + '">' +
    fmtPrecio(c, t.dec) + '</b> <span class="' + claseVar(var1) + '">' + pct(var1) + '</span>' +
    (rsi !== null && rsi !== undefined ? '<br>RSI <b>' + Number(rsi).toFixed(0) + '</b>' : '') +
    ' · Vol <b>' + abreviar(t.velas.v[i]) + '</b>';
  caja.hidden = false;
  // La caja se corre al otro lado cuando el cursor esta en la mitad izquierda.
  caja.style.left = cursor.x < cv.clientWidth / 2 ? 'auto' : '14px';
  caja.style.right = cursor.x < cv.clientWidth / 2 ? (62 + 14) + 'px' : 'auto';
}

function abreviar(v) {
  if (v === null || v === undefined) return '—';
  if (v >= 1e9) return (v / 1e9).toFixed(1) + 'B';
  if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M';
  if (v >= 1e3) return (v / 1e3).toFixed(0) + 'K';
  return String(v);
}

function fmtPrecio(p, dec) {
  return Number(p).toLocaleString('es-AR',
    {minimumFractionDigits: Math.min(dec, 2), maximumFractionDigits: Math.min(dec, 2)});
}

function dibujarRsi(t, i0, i1, paso, X) {
  var cv = document.getElementById('lienzoRsi');
  if (!cv || !t.rsi) return;
  var L = prepararLienzo(cv), ctx = L.ctx, W = L.w, H = L.h;
  var mDer = 62, ancho = W - mDer - 4;
  var C = {linea: cssVar('--linea-2'), eje: cssVar('--muted'),
           acento: cssVar('--acento'), alza: cssVar('--alza'), baja: cssVar('--baja')};

  function Y(v) { return 6 + (H - 18) * (100 - v) / 100; }
  ctx.font = '9px "IBM Plex Mono", monospace';
  ctx.textBaseline = 'middle';

  [30, 70].forEach(function (nivel) {
    ctx.strokeStyle = nivel === 70 ? C.baja : C.alza;
    ctx.globalAlpha = 0.45; ctx.setLineDash([4, 3]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(4, Y(nivel)); ctx.lineTo(4 + ancho, Y(nivel)); ctx.stroke();
    ctx.setLineDash([]); ctx.globalAlpha = 1;
    ctx.fillStyle = C.eje; ctx.textAlign = 'left';
    ctx.fillText(String(nivel), 4 + ancho + 6, Y(nivel));
  });

  ctx.strokeStyle = C.acento; ctx.lineWidth = 1.3; ctx.beginPath();
  var arranco = false;
  for (var i = i0; i < i1; i++) {
    var r = t.rsi[i];
    if (r === null || r === undefined) continue;
    if (!arranco) { ctx.moveTo(X(i), Y(r)); arranco = true; }
    else ctx.lineTo(X(i), Y(r));
  }
  ctx.stroke();
  ctx.fillStyle = C.eje; ctx.textAlign = 'left';
  ctx.fillText('RSI', 6, 11);
}

/* ---------------- interaccion del grafico ---------------- */
function zoomX(factor, anclaRel) {
  var t = datosGrafico(); if (!t) return;
  var v = encuadre(t), rango = v.hasta - v.desde;
  var nuevo = Math.max(8, Math.min(t.velas.c.length, rango / factor));
  var ancla = v.desde + rango * (anclaRel === undefined ? 0.5 : anclaRel);
  v.desde = ancla - nuevo * (anclaRel === undefined ? 0.5 : anclaRel);
  v.hasta = v.desde + nuevo;
  if (v.desde < 0) { v.hasta -= v.desde; v.desde = 0; }
  if (v.hasta > t.velas.c.length) {
    v.desde -= (v.hasta - t.velas.c.length); v.hasta = t.velas.c.length;
    if (v.desde < 0) v.desde = 0;
  }
  dibujar();
}
function zoomY(factor) {
  var t = datosGrafico(); if (!t) return;
  var v = encuadre(t);
  v.escalaY = Math.max(0.25, Math.min(6, v.escalaY * factor));
  dibujar();
}
function desplazar(velas) {
  var t = datosGrafico(); if (!t) return;
  var v = encuadre(t), n = t.velas.c.length, rango = v.hasta - v.desde;
  v.desde = Math.max(0, Math.min(n - rango, v.desde + velas));
  v.hasta = v.desde + rango;
  dibujar();
}

function conectarLienzo() {
  var cv = document.getElementById('lienzo');
  if (!cv || cv.dataset.listo) return;
  cv.dataset.listo = '1';

  cv.addEventListener('wheel', function (ev) {
    ev.preventDefault();
    var r = cv.getBoundingClientRect();
    var rel = Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width));
    if (ev.shiftKey) zoomY(ev.deltaY < 0 ? 1.15 : 1 / 1.15);
    else zoomX(ev.deltaY < 0 ? 1.15 : 1 / 1.15, rel);
  }, {passive: false});

  var arrastre = null;
  cv.addEventListener('pointerdown', function (ev) {
    var t = datosGrafico(); if (!t) return;
    var v = encuadre(t);
    arrastre = {x: ev.clientX, desde: v.desde, rango: v.hasta - v.desde};
    cv.setPointerCapture(ev.pointerId);
    cv.style.cursor = 'grabbing';
  });
  cv.addEventListener('pointermove', function (ev) {
    var r = cv.getBoundingClientRect();
    cursor = {x: ev.clientX - r.left, y: ev.clientY - r.top};
    if (!arrastre) { dibujar(); return; }
    var t = datosGrafico(); if (!t) return;
    var v = encuadre(t), n = t.velas.c.length;
    var porPixel = arrastre.rango / cv.clientWidth;
    var d = arrastre.desde - (ev.clientX - arrastre.x) * porPixel;
    v.desde = Math.max(0, Math.min(n - arrastre.rango, d));
    v.hasta = v.desde + arrastre.rango;
    dibujar();
  });
  ['pointerup', 'pointercancel'].forEach(function (t) {
    cv.addEventListener(t, function () { arrastre = null; cv.style.cursor = 'crosshair'; });
  });
  cv.addEventListener('pointerleave', function () {
    arrastre = null; cursor = null; cv.style.cursor = 'crosshair'; dibujar();
  });
  cv.addEventListener('dblclick', function () { vista = null; dibujar(); });
}

/* ---------------- eventos ---------------- */
function alternarCartera(tk) {
  if (est.cartera.has(tk)) est.cartera.delete(tk); else est.cartera.add(tk);
  guardarCartera();
  document.getElementById('cuentaCartera').textContent = est.cartera.size;

  // Se actualiza solo el renglon tocado: repintar la lista entera haria saltar
  // el scroll justo cuando esta eligiendo varios seguidos.
  var it = document.querySelector('.item[data-tk="' + tk + '"]');
  if (it) it.dataset.encartera = est.cartera.has(tk) ? '1' : '0';
  if (est.grupo === '__cartera') pintarLista();   // salvo que cambie que se muestra

  if (est.vista === 'cartera') pintarCartera();
  else {
    var btn = document.getElementById('btnCartera');
    if (btn && est.ticker === tk) {
      btn.textContent = est.cartera.has(tk) ? '✓ En mi cartera' : '+ Agregar a mi cartera';
    }
  }
}

function elegir(tk) {
  est.ticker = tk;
  est.vista = 'mercado';
  document.querySelectorAll('.vistas button').forEach(function (b) {
    b.setAttribute('aria-selected', String(b.dataset.vista === 'mercado'));
  });
  pintarLista(); pintarFicha(); conectarLienzo();
}

document.getElementById('lista').addEventListener('click', function (ev) {
  var marca = ev.target.closest('[data-marcar]');
  if (marca) { ev.stopPropagation(); alternarCartera(marca.dataset.marcar); return; }
  var it = ev.target.closest('.item');
  if (it) elegir(it.dataset.tk);
});
document.getElementById('lista').addEventListener('keydown', function (ev) {
  if (ev.key !== 'Enter' && ev.key !== ' ') return;
  var it = ev.target.closest('.item');
  if (it) { ev.preventDefault(); elegir(it.dataset.tk); }
});

document.getElementById('buscar').addEventListener('input', function (ev) {
  est.busca = ev.target.value; pintarLista();
});

document.querySelectorAll('.filtro').forEach(function (b) {
  b.addEventListener('click', function () {
    est.grupo = b.dataset.grupo;
    document.querySelectorAll('.filtro').forEach(function (o) {
      o.setAttribute('aria-pressed', String(o === b));
    });
    pintarLista();
  });
});

document.querySelectorAll('.vistas button').forEach(function (b) {
  b.addEventListener('click', function () {
    est.vista = b.dataset.vista;
    document.querySelectorAll('.vistas button').forEach(function (o) {
      o.setAttribute('aria-selected', String(o === b));
    });
    if (est.vista === 'cartera') pintarCartera();
    else { pintarFicha(); conectarLienzo(); }
  });
});

document.getElementById('principal').addEventListener('click', function (ev) {
  var tab = ev.target.closest('[data-tf]');
  if (tab) { est.tf = tab.dataset.tf; pintarFicha(); conectarLienzo(); pintarLista(); return; }
  var z = ev.target.closest('[data-zoom]');
  if (z) { zoomX(Number(z.dataset.zoom) > 0 ? 1.35 : 1 / 1.35); return; }
  var al = ev.target.closest('[data-alto]');
  if (al) { zoomY(Number(al.dataset.alto) > 0 ? 1.3 : 1 / 1.3); return; }
  if (ev.target.closest('[data-reset]')) { vista = null; dibujar(); return; }
  if (ev.target.closest('#btnCartera')) { alternarCartera(est.ticker); return; }
  var q = ev.target.closest('[data-quitar]');
  if (q) { alternarCartera(q.dataset.quitar); return; }
  var fila = ev.target.closest('tr.clicable');
  if (fila && fila.dataset.tk) elegir(fila.dataset.tk);
});

window.addEventListener('resize', function () {
  if (est.vista === 'mercado') dibujar();
});
if (window.matchMedia) {
  var mq = window.matchMedia('(prefers-color-scheme: dark)');
  if (mq.addEventListener) mq.addEventListener('change', function () { dibujar(); });
}

/* ---------------- antiguedad del dato ----------------
   El punto de color no adorna: dice si el tablero esta al dia, si esta pausado
   porque no toca actualizar, o si deberia haberse actualizado y no pasó. Un
   dato viejo sin explicacion se lee como que algo se rompio. */
(function () {
  var sello = document.getElementById('antiguedad');
  var latido = document.getElementById('latido');
  var gen = new Date(D.generado);
  var prox = D.proxima ? new Date(D.proxima) : null;

  function cuando(fecha) {
    var hoy = new Date();
    var dias = ['domingo','lunes','martes','miércoles','jueves','viernes','sábado'];
    var hhmm = ('0'+fecha.getHours()).slice(-2) + ':' + ('0'+fecha.getMinutes()).slice(-2);
    var difDias = Math.round((fecha.setHours(0,0,0,0) - hoy.setHours(0,0,0,0)) / 86400000);
    fecha = new Date(D.proxima);           // setHours de arriba muta la fecha
    if (difDias === 0) return 'hoy ' + hhmm;
    if (difDias === 1) return 'mañana ' + hhmm;
    return dias[fecha.getDay()] + ' ' + hhmm;
  }

  function antiguedad(min) {
    if (min < 2) return 'recién actualizado';
    if (min < 60) return 'hace ' + min + ' min';
    if (min < 48 * 60) {
      var h = Math.floor(min / 60);
      return 'hace ' + h + (h === 1 ? ' hora' : ' horas');
    }
    return 'hace ' + Math.floor(min / 1440) + ' días';
  }

  function refrescar() {
    var min = Math.floor((Date.now() - gen.getTime()) / 60000);
    if (isNaN(min) || min < 0) return;
    var txt = antiguedad(min);
    var color = 'var(--acento)';

    if (min > 40) {
      if (prox && prox.getTime() > Date.now()) {
        // Pausado a proposito: fuera del horario de actualizacion.
        txt += ' · vuelve ' + cuando(new Date(D.proxima));
        color = 'var(--warn)';
      } else {
        // Deberia haber corrido: la PC apagada, la aplicacion cerrada o un fallo.
        txt += ' · debería haberse actualizado';
        color = 'var(--baja)';
      }
    }
    sello.textContent = txt;
    if (latido) latido.style.background = color;
  }
  refrescar(); setInterval(refrescar, 60000);
})();

/* ---------------- arranque ---------------- */
document.getElementById('cuentaCartera').textContent = est.cartera.size;
pintarLista();
pintarFicha();
conectarLienzo();
// Las fuentes cambian el ancho del lienzo al cargar: se redibuja cuando estan listas.
if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { dibujar(); });
})();
"""
