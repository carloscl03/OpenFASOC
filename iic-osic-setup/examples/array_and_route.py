#!/usr/bin/env python
"""
array_and_route.py — ubicar muchas celdas en forma de array y rutearlas.

Patron muy comun: replicas una celda N veces (fila, matriz) y conectas los
puertos por script. Funciona con celdas custom (como aqui) o del PDK.

Uso (dentro del contenedor, tras setup_glayout.sh):
    source setup/glayout_env.sh
    $GLAYOUT_PY examples/array_and_route.py
"""

from gdsfactory.generic_tech import get_generic_pdk
get_generic_pdk().activate()

import gdsfactory as gf
from glayout.flow.pdk.gf180_mapped import gf180_mapped_pdk as gf180
from glayout.flow.routing.straight_route import straight_route

import os
outdir = os.path.dirname(os.path.abspath(__file__))

MET1 = (34, 0)

def celda(nombre):
    c = gf.Component(nombre)
    c.add_polygon([(0, 0), (3, 0), (3, 2), (0, 2)], layer=MET1)
    c.add_port("L", center=(0, 1), width=0.5, orientation=180, layer=MET1, port_type="electrical")
    c.add_port("R", center=(3, 1), width=0.5, orientation=0,   layer=MET1, port_type="electrical")
    return c


def fila(top, n, paso_x=8):
    """N celdas en una fila, conectadas en cadena R[i] -> L[i+1]."""
    refs = []
    for i in range(n):
        r = top << celda(f"cel_{i}")
        r.movex(i * paso_x)
        refs.append(r)
    for i in range(n - 1):
        top << straight_route(gf180, refs[i].ports["R"], refs[i + 1].ports["L"])
    return refs


def matriz(top, filas, cols, paso_x=8, paso_y=6):
    """Matriz filas x cols (sin ruteo entre filas, solo colocacion)."""
    grid = []
    for f in range(filas):
        fila_refs = []
        for c in range(cols):
            r = top << celda(f"m_{f}_{c}")
            r.move((c * paso_x, f * paso_y))
            fila_refs.append(r)
        # rutear cada fila en cadena
        for c in range(cols - 1):
            top << straight_route(gf180, fila_refs[c].ports["R"], fila_refs[c + 1].ports["L"])
        grid.append(fila_refs)
    return grid


if __name__ == "__main__":
    # ejemplo 1: fila de 5
    top1 = gf.Component("fila5")
    fila(top1, 5)
    p1 = os.path.join(outdir, "array_fila.gds")
    top1.write_gds(p1)
    print("fila de 5 celdas ruteadas:", os.path.getsize(p1), "bytes")

    # ejemplo 2: matriz 3x4
    top2 = gf.Component("matriz3x4")
    matriz(top2, filas=3, cols=4)
    p2 = os.path.join(outdir, "array_matriz.gds")
    top2.write_gds(p2)
    print("matriz 3x4 ruteada por filas:", os.path.getsize(p2), "bytes")
