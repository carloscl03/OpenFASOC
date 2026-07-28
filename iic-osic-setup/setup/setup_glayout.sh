#!/bin/bash
# =============================================================================
# setup_glayout.sh
# -----------------------------------------------------------------------------
# Prepara el entorno para usar gLayout (este fork, ya adaptado a gdsfactory 9)
# dentro del contenedor iic-osic-tools. Idempotente.
#
# Este fork YA trae el port aplicado (los shims gf7->gf9 estan commiteados).
# Lo unico que este script hace es:
#   1. instalar deps que faltan en el venv (nltk, prettyprint, cmd2==2.4.3)
#   2. verificar que gLayout genera un NMOS en GF180
#
# Uso: clona este repo DENTRO del contenedor y corre:
#   bash iic-osic-setup/setup/setup_glayout.sh
# =============================================================================
set -e

# getpass.getuser() falla con uid 1000 sin nombre -> definir USER/HOME temprano
export USER="${USER:-foss}" LOGNAME="${LOGNAME:-foss}" HOME="${HOME:-/foss/designs}"

# --- localizar el repo a partir de la ubicacion de este script ---------------
# este script vive en <repo>/iic-osic-setup/setup/  ; el glayout esta en
# <repo>/openfasoc/generators/glayout/
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GL_ROOT="$REPO_ROOT/openfasoc/generators/glayout"
# deps aisladas FUERA del repo (en el home, siempre escribible; el repo puede ser
# read-only segun como se haya obtenido).
EXTRA_DEPS="${GLAYOUT_EXTRA_DEPS:-${HOME:-/foss/designs}/.gl_extra_deps}"
VENV_PY=/foss/tools/klayout_gdsfactory9/bin/python

echo "==> repo:      $REPO_ROOT"
echo "==> glayout:   $GL_ROOT"

echo "==> [1/3] Verificando prerequisitos..."
if [ ! -d "$GL_ROOT/glayout/flow/pdk" ]; then
  echo "ERROR: no encuentro glayout en $GL_ROOT."
  echo "  ¿Clonaste el repo completo? (debe existir openfasoc/generators/glayout/)"
  exit 1
fi
if [ ! -x "$VENV_PY" ]; then
  echo "ERROR: no existe el venv $VENV_PY (klayout_gdsfactory9)."
  echo "  Este setup asume el contenedor iic-osic-tools del Chipathon (gdsfactory 9)."
  exit 1
fi

echo "==> [2/3] Instalando deps faltantes en $EXTRA_DEPS ..."
mkdir -p "$EXTRA_DEPS"
# --upgrade OBLIGATORIO: sin el, --target mezcla versiones (cmd2 queda roto).
"$VENV_PY" -m pip install --target="$EXTRA_DEPS" --upgrade \
  nltk prettyprint prettyprinttree 'cmd2==2.4.3' >/dev/null 2>&1 || \
  "$VENV_PY" -m pip install --target="$EXTRA_DEPS" --upgrade \
    nltk prettyprint prettyprinttree 'cmd2==2.4.3'
# cmd2 puede quedar Frankenstein si habia una version previa: forzar limpio
if ! "$VENV_PY" -c "import sys; sys.path.insert(0,'$EXTRA_DEPS'); import cmd2.ansi" 2>/dev/null; then
  echo "  cmd2.ansi ausente -> reinstalando cmd2 limpio"
  rm -rf "$EXTRA_DEPS"/cmd2 "$EXTRA_DEPS"/cmd2-*.dist-info
  "$VENV_PY" -m pip install --target="$EXTRA_DEPS" --upgrade 'cmd2==2.4.3'
fi
echo "  deps OK"

echo "==> [3/3] Verificando generacion de un NMOS en GF180..."
export USER=foss LOGNAME=foss HOME=/foss/designs
# Cargar el PYTHONPATH del contenedor (donde vive gdstk y el resto del stack).
if [ -z "$PYTHONPATH" ] || ! echo "$PYTHONPATH" | grep -q dist-packages; then
  _BASHRC_PP=$(bash -lc 'echo $PYTHONPATH' 2>/dev/null | tail -1)
  [ -n "$_BASHRC_PP" ] && export PYTHONPATH="$_BASHRC_PP"
fi
export PYTHONPATH="$GL_ROOT:$EXTRA_DEPS:$PYTHONPATH"

_CHECKDIR="$(mktemp -d)"
( cd "$_CHECKDIR" && "$VENV_PY" -c "
from gdsfactory.generic_tech import get_generic_pdk
get_generic_pdk().activate()
from glayout.flow.pdk.gf180_mapped import gf180_mapped_pdk as gf180
from glayout.flow.primitives.fet import nmos
import os
nmos(gf180, width=4, length=0.28).write_gds('_check.gds')
sz = os.path.getsize('_check.gds'); os.remove('_check.gds')
assert sz > 10000, 'GDS demasiado pequeno, algo fallo'
print('  OK - NMOS GF180 generado (%d bytes)' % sz)
" 2>&1 | grep -iE "OK|Error|Traceback|assert" | grep -v "Name conflict" | tail -5 )
rm -rf "$_CHECKDIR"

# escribir el env con las rutas resueltas, para que el usuario solo haga source
cat > "$SCRIPT_DIR/glayout_env.sh" <<ENVEOF
# generado por setup_glayout.sh — hazle source antes de correr scripts de gLayout:
#   source $SCRIPT_DIR/glayout_env.sh
export USER=foss LOGNAME=foss HOME=/foss/designs
export PYTHONPATH="$GL_ROOT:$EXTRA_DEPS:\$PYTHONPATH"
export GLAYOUT_PY=$VENV_PY
echo "[glayout_env] listo. Corre:  \\\$GLAYOUT_PY tu_script.py"
echo "[glayout_env] activa el PDK generico antes de importar glayout:"
echo "    from gdsfactory.generic_tech import get_generic_pdk; get_generic_pdk().activate()"
ENVEOF

echo ""
echo "==> LISTO. Para usar gLayout:"
echo "      source $SCRIPT_DIR/glayout_env.sh"
echo "      \$GLAYOUT_PY iic-osic-setup/examples/smoke_test.py"
echo ""
