# glayout-iic-osic-fix

Hacer que **gLayout** funcione dentro del contenedor **iic-osic-tools**
(el de gdsfactory 9, usado en el Chipathon) — y un set de ejemplos para trabajar
con celdas propias, arrays y proyectos organizados en carpetas.

> **El problema que resuelve**: gLayout upstream está congelado a `gdsfactory 7`,
> pero el contenedor trae `gdsfactory 9`, que lo rompe. Existe un "port" que lo
> adapta pero venía desactualizado y fallaba. Este repo trae un script que lo
> **repara automáticamente** + ejemplos genéricos para empezar a diseñar.

---

## TL;DR

**Clona este repo DENTRO de tu contenedor iic-osic-tools** y corre el setup:

```bash
# (dentro del contenedor, p.ej. en /foss/designs)
git clone https://github.com/carloscl03/OpenFASOC.git
cd OpenFASOC

# 1) preparar el entorno (una vez, idempotente)
bash iic-osic-setup/setup/setup_glayout.sh

# 2) probar que quedó bien
source iic-osic-setup/setup/glayout_env.sh
$GLAYOUT_PY iic-osic-setup/examples/smoke_test.py
```

Si el smoke test imprime `TODO OK - entorno gLayout funcional`, ya puedes diseñar.

> El port (los shims que adaptan gLayout a gdsfactory 9) **ya viene aplicado en
> este fork** — no hay que parchear nada. El setup solo instala deps que faltan y
> verifica que todo genera.

---

## ⚠️ El síntoma más común (y su cura)

> **"error en las dimensiones de los transistores / son muy chicos"**, aunque
> estén dentro de lo que permite el PDK y en xschem funcionen bien.

**NO es un problema de tus dimensiones.** Es gLayout upstream (gdsfactory 7)
corriendo sobre el contenedor (gdsfactory 9): las reglas de tamaño (`grules`) no
se leen y todo parece ilegal. **Usa este fork** (que trae el port) + el setup.

---

## Requisitos

1. Contenedor **iic-osic-tools** del Chipathon corriendo (trae el venv
   `klayout_gdsfactory9` con gdsfactory 9.20.6, y los PDKs sky130 / gf180mcuD).
2. Haber clonado **este fork completo** dentro del contenedor (el port vive en
   `openfasoc/generators/glayout/`, ya adaptado).

Nada más que instalar a mano: el setup se encarga de las deps.

---

## Qué hace el setup

`setup_glayout.sh` es **idempotente** (se puede correr varias veces):

1. Instala las deps que faltan en el venv (`nltk`, `prettyprint`,
   `prettyprinttree`, `cmd2==2.4.3`) en `.gl_extra_deps/` dentro del repo. No toca
   el entorno base del contenedor.
2. Genera `glayout_env.sh` con las rutas ya resueltas.
3. Verifica generando un NMOS en GF180.

## Qué trae ya aplicado el fork (el "port")

El trabajo pesado está **commiteado en el fork**, no lo hace el setup. Son los
shims que adaptan gLayout (escrito para gdsfactory 7) a gdsfactory 9:

| Cambio | Por qué |
|---|---|
| `mappedpdk.py`: `__init__` que preserva `grules/glayers/grid_size` | pydantic 2 los descartaba → `'MappedPDK' object has no attribute 'grules'` |
| `gf180_mapped.py`: `gds_write_settings`/`cell_decorator_settings` comentados | removidos en gdsfactory 9 |
| `gf180_mapped.py`: `LAYER` envuelto con `dict_to_layermap` | gf9 exige `LayerEnum`, no un dict crudo |
| `_compat/` + monkey-patches en `glayout/__init__.py` | refactor gdsfactory 7→9 (kfactory, pydantic 1→2, bbox, flatten, ports…) |

Basado en el port original de OpenFASOC a gdsfactory 9; aquí re-validado y
completado para GF180.

---

## Cómo se usa el entorno (`glayout_env.sh`)

Haz `source setup/glayout_env.sh` antes de correr cualquier script. Define:

- **`$GLAYOUT_PY`** = el intérprete correcto
  (`/foss/tools/klayout_gdsfactory9/bin/python`, venv gdsfactory 9.20.6).
  **NO** uses el `python3` base del contenedor.
- **`USER` / `HOME`** para que `getpass.getuser()` no falle (uid 1000 sin nombre).
- **`PYTHONPATH`** con el port + deps extra, **añadido** (no reemplazado; si lo
  reemplazas pierdes `gdstk` y el resto del stack).

Reglas: **no corras desde `/tmp`** (hay un `bisect.py` que tapa el stdlib), y
**activa un PDK genérico ANTES de importar glayout**:
```python
from gdsfactory.generic_tech import get_generic_pdk
get_generic_pdk().activate()
```

---

## Ejemplos (en `examples/`)

Todos validados en el contenedor. Corre cualquiera con:
```bash
source setup/glayout_env.sh
$GLAYOUT_PY examples/<archivo>.py
```

### `smoke_test.py` — verificar la instalación
Genera NMOS/PMOS en GF180 y sky130. Si corre, el entorno está listo.

### `custom_cell.py` — TUS PROPIAS celdas (sin depender del PDK)
Define una celda con geometría a mano + puertos. Útil para **optimizar layout tú
mismo** en vez de usar las primitivas preddiseñadas del PDK. La clave: mientras
tu celda tenga **puertos**, gLayout la trata igual que una del PDK.

```python
c = gf.Component("mi_celda")
c.add_polygon([(0,0),(w,0),(w,h),(0,h)], layer=(34,0))     # tu geometría
c.add_port("L", center=(0,h/2), width=0.5, orientation=180,
           layer=(34,0), port_type="electrical")            # tu puerto
```

### `array_and_route.py` — muchas celdas en array + ruteo
Replica una celda N veces (fila o matriz) y conecta los puertos por script.

```python
refs = [top << celda(f"c_{i}") for i in range(N)]
for i, r in enumerate(refs):
    r.movex(i * paso)
for i in range(N-1):                                          # cadena
    top << straight_route(pdk, refs[i].ports["R"], refs[i+1].ports["L"])
```
Incluye fila (1D) y matriz (2D). Funciona con celdas custom o del PDK.

### `import_and_route.py` — insertar un GDS hecho a mano en KLayout
Importa un GDS externo, le defines puertos, y lo ruteas mezclado con celdas del
PDK. **El único paso manual es marcar los puertos** (coords sacadas de KLayout).

```python
dibujo = gf.import_gds("mi_dibujo.gds")
dibujo.add_port("salida", center=(4,1), width=0.5, orientation=0,
                layer=(34,0), port_type="electrical")
top << straight_route(pdk, dibujo.ports["salida"], fet.ports["..._drain_W"])
```
Truco: si al dibujar pones **labels de texto** sobre los pines, `import_gds`
puede convertirlos en puertos automáticamente.

### `folder_project.py` — organizar un proyecto en carpetas sin romper links
Guarda cada bloque **aplanado** (autónomo) en su carpeta, y ensambla el top
re-importando desde disco.

```python
def guardar_plano(comp, path):
    c = comp.copy(); c.flatten(); c.write_gds(path)   # sin links vivos
```
Estructura resultante:
```
proyecto_demo/
├── bloques/{nmos,pmos}.gds   (autónomos)
└── top/top.gds               (ensamblado desde disco)
```

---

## Conceptos clave (para entender los ejemplos)

- **Component** = la celda. Todo es un Component; se anidan (`top << bloque`).
- **Puertos** = puntos de conexión con nombre. **El ruteo conecta puertos, no
  coordenadas.** Sin puertos no puedes rutear una celda.
- **Placement** = los `.move()/.movex()/.movey()`. Es tu diseño, tú decides dónde.
- **Ruteo** = `straight_route` / `L_route` / `c_route`. Conectan dos puertos.
- **flatten vs referencias**:
  - referencias (`<<`): eficiente, para trabajo en vivo dentro de un script.
  - flatten (`.copy().flatten()`): autónomo, para **guardar/compartir/archivar**
    sin que se rompan los links del cache (el problema clásico de gdsfactory 9).

---

## Estructura del repo

```
glayout-iic-osic-fix/
├── README.md
├── setup/
│   ├── setup_glayout.sh    repara el port (idempotente, se auto-verifica)
│   └── glayout_env.sh      exporta el entorno (source antes de correr)
└── examples/
    ├── smoke_test.py        verificar instalación
    ├── custom_cell.py       tus propias celdas con puertos
    ├── array_and_route.py   arrays (fila/matriz) + ruteo
    ├── import_and_route.py  importar GDS externo + rutearlo
    └── folder_project.py    organización en carpetas (flatten)
```

---

## Verificación DRC

Este repo deja gLayout **funcional**, pero un GDS que "genera sin error" **no
está garantizado DRC-clean**. Para verificar en GF180:

```bash
klayout -b -r $PDK_ROOT/gf180mcuD/libs.tech/klayout/drc/gf180mcu.drc \
  -rd input=tu_layout.gds -rd report=drc.lyrdb
```

gLayout no garantiza DRC limpio (*"la calidad del layout = la calidad del
programador"*). Verificar es un paso aparte.

---

## Notas de compatibilidad

- Probado contra el port en branch `py312-gdsfactory9-port` y el venv
  `klayout_gdsfactory9` (gdsfactory **9.20.6**). El python **base** del contenedor
  (gdsfactory 9.40.1) NO se usa: el port fue validado contra el venv.
- Si en el futuro el contenedor sube de versión y algo se rompe, los fixes de
  `setup_glayout.sh` son **el mapa** de qué APIs usa gLayout — re-aplicarlos sobre
  la nueva API es el camino.
- Warnings al correr que son **normales** (no errores): `DeprecationWarning` de
  `generic_tech`, y `Name conflict in kfactory.kcell` (celdas Unnamed
  auto-renombradas). No afectan el GDS.
