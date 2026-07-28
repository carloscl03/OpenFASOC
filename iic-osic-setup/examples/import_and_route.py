#!/usr/bin/env python
"""
import_and_route.py — como insertar un GDS hecho a mano (KLayout) y rutearlo
por script, mezclado con celdas del PDK.

El unico paso manual es DEFINIR LOS PUERTOS del GDS importado (sus puntos de
conexion). Una vez con puertos, gLayout lo trata igual que sus propias celdas.

Uso (dentro del contenedor, tras correr setup_glayout.sh):
    source setup/glayout_env.sh
    $GLAYOUT_PY examples/import_and_route.py
"""

from gdsfactory.generic_tech import get_generic_pdk
get_generic_pdk().activate()

import gdsfactory as gf
from glayout.flow.pdk.sky130_mapped import sky130_mapped_pdk as sky130
from glayout.flow.primitives.fet import nmos
from glayout.flow.routing.straight_route import straight_route

import os
outdir = os.path.dirname(os.path.abspath(__file__))

# --- PASO 1: simular "un bloque dibujado a mano" ---------------------------
# En un caso real seria: dibujo = gf.import_gds("mi_dibujo.gds")
# Aqui lo fabricamos con un rectangulo de metal para que el ejemplo sea autonomo.
dibujo = gf.Component("dibujo_manual")
dibujo.add_polygon([(0, 0), (4, 0), (4, 2), (0, 2)], layer=(68, 20))  # met1 sky130

# --- PASO 2: definirle un PUERTO (el paso manual clave) --------------------
# center = coordenada del pin (la sacas mirando tu dibujo en KLayout).
# port_type="electrical" para diseno analogico.
dibujo.add_port("salida", center=(4, 1), width=0.5, orientation=0,
                layer=(68, 20), port_type="electrical")
print("dibujo con puerto:", [p.name for p in dibujo.ports])

# --- PASO 3: una celda del PDK (ya trae puertos con nombre) ----------------
transistor = nmos(sky130, width=1, length=0.15)
drain = [p.name for p in transistor.ports if "drain" in p.name][0]
print("nmos del PDK, puerto usado:", drain)

# --- PASO 4: instanciar ambos en un top y colocarlos -----------------------
top = gf.Component("top_mixto")
ref_dibujo = top << dibujo
ref_fet = top << transistor
ref_fet.movex(15)  # separarlos

# --- PASO 5: rutear el puerto del dibujo con el del PDK ---------------------
top << straight_route(sky130, ref_dibujo.ports["salida"], ref_fet.ports[drain])
print("ruteo dibujo <-> PDK: OK")

path = os.path.join(outdir, "top_mixto.gds")
top.write_gds(path)
print(f"GDS escrito: {os.path.getsize(path)} bytes ->", path)

# TRUCO: si al dibujar en KLayout pones labels de texto sobre los pines
# (en una capa de labels), gf.import_gds puede convertirlos en puertos
# automaticamente y te ahorras anotar coordenadas a mano.
