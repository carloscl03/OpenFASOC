#!/usr/bin/env python
"""
folder_project.py — organizar un proyecto en carpetas SIN que se rompan los links.

Problema (gdsfactory 9 / kfactory): si escribes un GDS que INSTANCIA otras celdas,
guarda referencias VIVAS al cache global. Si el cache se limpia, colisionan nombres,
o cierras la sesion, esos links apuntan a celdas destruidas -> "se rompe la logica".

Solucion: guardar cada bloque APLANADO (flatten sobre una copia). Un GDS aplanado
es AUTONOMO: contiene toda su geometria, no depende de nada en memoria. Lo puedes
archivar, compartir, re-importar en otra sesion y ensamblar sin que se rompa.

Regla practica:
    - bloque que vas a guardar/compartir/archivar  -> flatten (autonomo)
    - trabajo en vivo dentro de un mismo script     -> referencias normales (<<)

Uso (dentro del contenedor, tras setup_glayout.sh):
    source setup/glayout_env.sh
    $GLAYOUT_PY examples/folder_project.py
"""

from gdsfactory.generic_tech import get_generic_pdk
get_generic_pdk().activate()

import gdsfactory as gf
from glayout.flow.pdk.gf180_mapped import gf180_mapped_pdk as gf180
from glayout.flow.primitives.fet import nmos, pmos

import os
base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proyecto_demo")
os.makedirs(os.path.join(base, "bloques"), exist_ok=True)
os.makedirs(os.path.join(base, "top"), exist_ok=True)


def guardar_plano(comp, path):
    """Guarda un componente APLANADO (autonomo, sin links vivos)."""
    c = comp.copy()      # copia: no tocar la celda cacheada
    c.flatten()          # quemar geometria
    c.write_gds(path)
    return os.path.getsize(path)


if __name__ == "__main__":
    # === 1) generar bloques y guardarlos aplanados en su carpeta ===
    s1 = guardar_plano(nmos(gf180, width=4, length=0.28),
                       os.path.join(base, "bloques", "nmos.gds"))
    s2 = guardar_plano(pmos(gf180, width=4, length=0.28),
                       os.path.join(base, "bloques", "pmos.gds"))
    print(f"bloques guardados: nmos={s1}b  pmos={s2}b")

    # === 2) re-importar desde disco (simula otra sesion / otro dia) ===
    # Aqui NO hay ninguna celda 'viva' del paso anterior: se lee del GDS.
    imp_nmos = gf.import_gds(os.path.join(base, "bloques", "nmos.gds"))
    imp_pmos = gf.import_gds(os.path.join(base, "bloques", "pmos.gds"))
    print("re-import desde disco OK")

    # === 3) ensamblar un top a partir de los importados ===
    top = gf.Component("top_desde_disco")
    r1 = top << imp_nmos
    r2 = top << imp_pmos
    r2.movex(20)
    top_path = os.path.join(base, "top", "top.gds")
    top.write_gds(top_path)
    print("top ensamblado desde disco:", os.path.getsize(top_path), "bytes")
    print("estructura:")
    print("  proyecto_demo/bloques/{nmos,pmos}.gds  (autonomos)")
    print("  proyecto_demo/top/top.gds              (ensamblado)")
