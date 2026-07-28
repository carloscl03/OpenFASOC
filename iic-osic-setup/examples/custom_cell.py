#!/usr/bin/env python
"""
custom_cell.py — definir TUS PROPIAS celdas (sin depender de las del PDK).

Util cuando quieres optimizar geometria a mano en vez de usar las primitivas
predisenadas del PDK. Mientras tu celda tenga PUERTOS, gLayout la trata igual
que cualquier celda del PDK: se instancia, se coloca y se rutea.

Uso (dentro del contenedor, tras setup_glayout.sh):
    source setup/glayout_env.sh
    $GLAYOUT_PY examples/custom_cell.py
"""

from gdsfactory.generic_tech import get_generic_pdk
get_generic_pdk().activate()

import gdsfactory as gf
import os
outdir = os.path.dirname(os.path.abspath(__file__))

# Capas GF180 (layer, datatype) — ajusta a las que uses.
MET1 = (34, 0)
POLY = (30, 0)

def mi_celda(nombre="mi_celda", w=3.0, h=2.0):
    """Una celda custom: un trozo de metal con dos puertos (izq/der).

    La geometria la defines tu (add_polygon). Los puertos son el contrato que
    permite rutear: center = donde esta el pin, orientation = hacia donde mira.
    """
    c = gf.Component(nombre)
    c.add_polygon([(0, 0), (w, 0), (w, h), (0, h)], layer=MET1)

    # puertos = puntos de conexion. SIN esto no se puede rutear.
    c.add_port("L", center=(0, h/2),  width=0.5, orientation=180,
               layer=MET1, port_type="electrical")
    c.add_port("R", center=(w, h/2),  width=0.5, orientation=0,
               layer=MET1, port_type="electrical")
    return c


if __name__ == "__main__":
    cell = mi_celda()
    print("celda custom con puertos:", [p.name for p in cell.ports])
    path = os.path.join(outdir, "mi_celda.gds")
    cell.write_gds(path)
    print("GDS escrito:", os.path.getsize(path), "bytes ->", path)

    # NOTA: puedes mezclar libremente celdas custom con celdas del PDK:
    #   from glayout.flow.primitives.fet import nmos
    #   top << mi_celda()
    #   top << nmos(gf180, width=4, length=0.28)
    #   top << straight_route(gf180, custom.ports["R"], fet.ports["..._drain_W"])
