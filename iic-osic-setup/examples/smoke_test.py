#!/usr/bin/env python
"""
smoke_test.py — prueba minima de que gLayout funciona en el contenedor.

Genera un NMOS y un PMOS en GF180 y sky130, y escribe sus GDS.
Si esto corre sin error, el entorno esta listo.

Uso (dentro del contenedor, tras correr setup_glayout.sh):
    source setup/glayout_env.sh
    $GLAYOUT_PY examples/smoke_test.py
"""

# 1) activar un PDK generico ANTES de importar glayout (lo requiere el port)
from gdsfactory.generic_tech import get_generic_pdk
get_generic_pdk().activate()

# 2) imports de glayout (rutas del port: todo bajo glayout.flow.*)
from glayout.flow.pdk.gf180_mapped import gf180_mapped_pdk as gf180
from glayout.flow.pdk.sky130_mapped import sky130_mapped_pdk as sky130
from glayout.flow.primitives.fet import nmos, pmos

import os
outdir = os.path.dirname(os.path.abspath(__file__))

cases = [
    ("nmos_gf180",  lambda: nmos(gf180,  width=4, length=0.28)),  # GF180: length min 0.28
    ("pmos_gf180",  lambda: pmos(gf180,  width=4, length=0.28)),
    ("nmos_sky130", lambda: nmos(sky130, width=1, length=0.15)),  # sky130: length min 0.15
]

print("== smoke test gLayout ==")
ok = True
for name, build in cases:
    try:
        comp = build()
        path = os.path.join(outdir, name + ".gds")
        comp.write_gds(path)
        size = os.path.getsize(path)
        assert size > 5000, "GDS demasiado pequeno"
        print(f"  [OK] {name}: {size} bytes")
    except Exception as e:
        ok = False
        print(f"  [FALLA] {name}: {type(e).__name__}: {str(e)[:120]}")

print("== " + ("TODO OK - entorno gLayout funcional" if ok else "HUBO FALLAS - revisar setup") + " ==")
