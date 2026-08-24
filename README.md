# Indicadores — análisis técnico automatizado por escenarios

Corre el mismo análisis técnico que se hace a mano en Investing.com o TradingView,
pero automatizado y **parametrizado por escenario**: cada configuración vive en un
archivo YAML, así que probar "corto plazo con stop del 7%" contra "swing con stop
por estructura" es cambiar una palabra en el comando, no rehacer el análisis.

Sobre cada activo produce:

- **Resumen técnico** con la misma metodología de Investing/TradingView: cada
  indicador vota compra/venta/neutral y el promedio da el veredicto.
- **Soportes y resistencias** con una fuerza de 0 a 100, detectados por cuatro
  métodos independientes (toques históricos, puntos pivote, Fibonacci y niveles
  dinámicos).
- **Escenarios operables**: zona de entrada, stop, objetivo, relación R:R,
  qué tiene que pasar para activarlos y qué los invalida.
- **Validación histórica**: cuántas veces, en el historial real del activo, el
  precio llegó al objetivo antes de tocar el stop.

---

## Instalación

```bash
pip install -r requirements.txt
```

## Uso

```bash
python analizar.py IBIT
```

El escenario de corto plazo (stop −7% / objetivo +14%) es el que corre por defecto.

### Ejemplos

```bash
python analizar.py IBIT --perfil corto_plazo --detalle
```

```bash
python analizar.py IBIT BTC-USD AAPL --perfil swing
```

```bash
python analizar.py IBIT --stop 5 --objetivo 10 --capital 500000
```

```bash
python analizar.py GGAL.BA --perfil largo_plazo --abrir
```

```bash
python analizar.py --listar
```

### Opciones

| Opción | Qué hace |
|---|---|
| `-p, --perfil` | Escenario a usar (default `corto_plazo`) |
| `-t, --temporalidad` | Pisa las temporalidades del perfil: `-t 1d 1wk` |
| `--stop` / `--objetivo` | Pisa el stop y el objetivo, en % |
| `--capital` / `--riesgo` | Calcula cuántos nominales comprar |
| `-d, --detalle` | Muestra el valor de cada indicador |
| `--html` / `--excel` / `--todo` | Genera los informes en `salidas/` |
| `--abrir` | Abre el informe HTML al terminar |
| `--csv` | Usa un CSV propio en vez de descargar |
| `--sin-cache` | Fuerza la descarga aunque el caché esté fresco |

---

## El tablero compartible

`publicar.py` genera un tablero con los 76 activos de `config/universo.yaml`, que
se publica como página privada y se comparte por link. Damián no instala nada:
abre el link y lo ve.

```bash
python publicar.py
```

Escribe `salidas/tablero.html` (~3,4 MB, 76 activos en unos 2 minutos). La página
es autocontenida: sin librerías ni CDN, porque la política de seguridad del visor
bloquea los pedidos a servidores externos.

### Qué tiene el tablero

- **Buscador y filtros** por CEDEARs, acciones argentinas, cripto e índices.
- **Gráfico con zoom**: rueda del mouse para acercar, arrastrar para desplazar,
  `Shift` + rueda para estirar la escala vertical, doble clic para volver a la
  vista completa. También hay botones para todo eso.
- **Tres temporalidades** por activo: diario, 4 horas y 1 hora, cada una con su
  análisis completo.
- **Mi cartera**: se marcan los activos que se tienen y el tablero consolida el
  análisis del conjunto — cuántos a favor, cuántos en contra, score promedio,
  concentración por rubro y las mejores oportunidades entre los elegidos.

La cartera se guarda en la dirección de la página (`#c=IBIT,AAPL,...`) y, como
respaldo, en el navegador. Eso permite pasarle a alguien un link con la cartera
ya armada. Si el visor bloquea las dos cosas, la selección dura mientras no se
recargue la página.

### Por qué el gráfico se dibuja en el navegador

Las velas viajan como datos y el gráfico se dibuja sobre canvas, en vez de mandar
una imagen ya resuelta. Es lo que permite hacer zoom, y además pesa menos: con 76
activos y tres temporalidades cada uno, mandar imágenes hechas era inviable.
Cuántas velas viajan lo define `velas_grafico` en `config/panel.yaml`, y es lo que
marca hasta dónde se puede alejar el zoom.

**Link publicado:** https://claude.ai/code/artifact/f25ff54e-9f53-459c-800d-25794d4a14bc

Para actualizarlo hay que republicar **con esa misma URL**; si se publica sin
indicarla se crea una página nueva y el link que ya tiene Damián queda viejo.

### Actualización automática

Hay una tarea programada (`tablero-tecnico-damian`) que corre `publicar.py` y
republica el tablero **cada 15 minutos de 7:04 a 16:49, hora de esta PC**, de
lunes a viernes. Cubre desde antes de la apertura hasta después del cierre.

Los 15 minutos no son arbitrarios: cada corrida tarda unos 2 minutos en analizar
los 76 activos, más el tiempo de republicar. Bajarlo más solaparía corridas sin
ganar nada, porque las velas de 1 hora y diarias no cambian en ese lapso.

Dos cosas que conviene tener presentes:

- **La PC está configurada en UTC−5**, no en hora argentina. El cron usa la hora
  local de la máquina, así que esos horarios son 9:47 y 17:47 en Argentina. Si se
  cambia la zona horaria de Windows, hay que reajustar la tarea.
- **La tarea corre mientras la aplicación está abierta.** Si estaba cerrada a la
  hora prevista, se ejecuta la próxima vez que se abra.

Cada corrida compara contra `salidas/estado.json` e informa qué activos cambiaron
de veredicto desde la vez anterior, que es lo único que hace falta mirar cuando el
tablero se actualiza solo.

### Lo que el tablero no hace

**No cotiza en vivo.** Muestra la foto del mercado del momento en que se generó,
con la antigüedad del dato siempre visible arriba. Una página publicada no puede
pedirle precios a Yahoo: el visor bloquea todo pedido de red a otro servidor, así
que la única forma de refrescar es volver a generarla y republicarla.

Para ver la vela formándose minuto a minuto, como en TradingView, hace falta un
programa corriendo en la máquina de quien mira — deja de ser un link y pasa a ser
una instalación.

## Los escenarios

Cada perfil es un archivo en `config/`. Heredan de `base.yaml`, así que solo
declaran lo que cambian.

| Perfil | Horizonte | Stop | Objetivo | Temporalidades |
|---|---|---|---|---|
| `corto_plazo` | días a semanas | −7% fijo | +14% fijo | 1d + 60m |
| `swing` | 2 a 8 semanas | el más holgado entre %, ATR y estructura | próxima resistencia real | 1d + 1wk |
| `intradiario` | horas | 1,5 ATR | R:R 2:1 | 15m + 60m |
| `largo_plazo` | meses | estructura | próxima resistencia real | 1d + 1wk + 1mo |

### Crear un escenario nuevo

Copiar cualquier perfil y cambiar lo necesario. Por ejemplo, `config/agresivo.yaml`:

```yaml
extiende: corto_plazo
nombre: agresivo
descripcion: Corto plazo con stop mas corto y objetivo mas ambicioso.

riesgo:
  stop_pct: 5.0
  objetivo_pct: 20.0
  rr_minimo: 3.0
```

```bash
python analizar.py IBIT -p agresivo
```

No hay nada más que hacer: el archivo aparece solo en `--listar`.

---

## Qué mira exactamente

**Osciladores** — RSI, estocástico, CCI, ADX con DI+/DI−, Awesome Oscillator,
Momentum, MACD, Stochastic RSI, Williams %R, Bull Bear Power, Ultimate
Oscillator y Money Flow Index.

**Medias móviles** — SMA y EMA de 10, 20, 30, 50, 100 y 200 períodos, más VWMA,
Hull MA e Ichimoku.

**Señales accionables** — cruces de medias y de MACD, salidas de sobreventa y
sobrecompra, divergencias RSI-precio, confirmación por volumen y OBV,
compresión de bandas de Bollinger y rupturas de rango.

**Niveles** — pivotes de swing agrupados por cercanía, puntos pivote (clásico,
Fibonacci o Camarilla, diarios y semanales), retrocesos de Fibonacci, medias
móviles, bandas de Bollinger y canal de Donchian.

Los niveles que caen casi en el mismo precio se fusionan, y la confluencia se
cuenta **una sola vez por método**: que S1, PP y R1 queden pegados no son tres
confirmaciones, es un solo cálculo. Que el 61,8% de Fibonacci coincida con la
EMA 200 y con cinco toques históricos, sí.

---

## La validación histórica

Es la parte que separa este análisis de una opinión. Para cada entrada simulada
en el historial del activo, mide si el precio llegó al objetivo **antes** de
tocar el stop, dentro del horizonte configurado. Compara dos cosas:

- **La base**: entrando en cualquier vela, al azar.
- **Cada señal**: entrando solo cuando esa señal se disparó.

Si una señal no le gana a la base, no está aportando nada y conviene saberlo
antes de operarla, no después.

Criterio conservador: si dentro de una misma vela el precio toca las dos
barreras, se cuenta como stop. Sin datos intradiarios no se puede saber cuál
llegó primero, y suponer lo contrario infla los resultados.

También reporta el **MAE**: cuánto fue en contra una operación que después ganó.
Si el 80% de las ganadoras nunca cayó más de 4,3%, un stop del 7% está holgado;
uno del 3% habría barrido la mayoría de las operaciones buenas.

---

## Datos

Yahoo Finance vía `yfinance`, sin API key. Cubre:

- ETF y acciones de USA: `IBIT`, `AAPL`, `SPY`
- Acciones y CEDEARs locales: `GGAL.BA`, `YPFD.BA`, `AAPL.BA`
- Cripto spot: `BTC-USD`, `ETH-USD`

Los datos quedan cacheados en `cache/` (entre 2 minutos y 4 horas según la
temporalidad) para no re-descargar en cada corrida.

**Límites del intradiario en Yahoo**: velas de 1m solo 7 días hacia atrás,
de 5m a 30m hasta 60 días, de 60m hasta 2 años. Por eso el backtest del perfil
`intradiario` corre sobre una muestra chica: sirve para el día, no para sacar
conclusiones de fondo.

Si preferís tus propios datos (export del broker o de TradingView):

```bash
python analizar.py IBIT --csv mis_datos.csv
```

Reconoce encabezados en inglés y en español, y números en formato local
(`1.234,56`, volumen tipo `12,5M`).

---

## Estructura

```
analizar.py           CLI de analisis individual
publicar.py           genera el tablero compartible
config/               un archivo por escenario
  panel.yaml          parámetros del tablero
  universo.yaml       los 76 activos que ofrece
  base.yaml           valores por defecto, heredan todos
  corto_plazo.yaml    -7% / +14%
  swing.yaml
  intradiario.yaml
  largo_plazo.yaml
tecnico/
  datos.py            descarga, caché, lectura de CSV
  calculo.py          los indicadores, en pandas puro
  niveles.py          soportes y resistencias
  rating.py           veredicto por indicador y señales
  plan.py             entradas, stop, objetivo, tamaño de posición
  backtest.py         validación por triple barrera
  reporte.py          consola, HTML y Excel
  grafico.py          miniaturas en SVG
  exportar.py         empaqueta el análisis para el navegador
  panel.py            el tablero interactivo
salidas/              informes generados
```

Sin TA-Lib ni compiladores: todo es `pandas` y `numpy`.

---

## Advertencia

Análisis técnico automatizado sobre datos históricos. **No es recomendación de
inversión.** Los porcentajes de la validación histórica describen lo que ocurrió
en la muestra analizada, no lo que va a ocurrir. La "confianza" de cada escenario
es una heurística de confluencia entre indicadores, no una probabilidad
estadística.
