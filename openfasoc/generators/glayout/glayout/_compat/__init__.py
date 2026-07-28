"""
Compatibility shims for gdsfactory 7→9 migration of glayout.

Provides drop-in replacements for APIs that were removed/renamed in gdsfactory 9.
Each shim emulates the gdsfactory 7 behavior expected by glayout's cell factories.
"""
import gdsfactory as gf


# =============================================================================
# transformed() shim
# =============================================================================
# Strong-ref cache: prevent garbage collection of Components passed through transformed()
_TRANSFORMED_KEEPALIVE = []


def transformed(ref):
    """Emulates gdsfactory 7's transformed(ref) → Component (with ports preserved).

    In gdsfactory 7 this baked transformation into a fresh Component.
    In gdsfactory 9, kfactory cells are aggressive with GC.
    
    Pragmatic approach: if input is Component, return it as-is (transformation
    is already in place). If input is Reference, create a wrapping Component
    that keeps the underlying alive.
    """
    if isinstance(ref, gf.Component):
        # Ya es Component; conservar referencia fuerte para evitar GC
        _TRANSFORMED_KEEPALIVE.append(ref)
        return ref
    # Reference (DInstance) → crear wrapper que mantenga underlying alive
    new = gf.Component()
    transferred_ports = []
    _TRANSFORMED_KEEPALIVE.append(new)

    if False:  # nunca llega
        pass
    elif hasattr(ref, 'cell'):
        # kfactory DInstance: el Component está en ref.cell
        underlying = ref.cell
        try:
            new_inst = new.add_ref(underlying)
            # Aplicar la transformación de la ref original
            if hasattr(ref, 'dcplx_trans'):
                new_inst.dcplx_trans = ref.dcplx_trans
            elif hasattr(ref, 'trans'):
                new_inst.trans = ref.trans
            # Copiar ports del Component subyacente
            for p in underlying.ports:
                transferred_ports.append(p)
        except Exception:
            pass
    else:
        new.add_ref(ref)

    # NO hacemos flatten porque destruye el cell subyacente y rompe is_locked.
    # En gf 7 transformed flattenaba; en gf 9 dejamos el ref como está
    # (semánticamente: el bbox/visual es igual; la diferencia es jerarquía interna).

    # Re-añadir los ports al new Component
    for p in transferred_ports:
        try:
            new.add_port(
                name=p.name,
                center=p.center if hasattr(p, 'center') else (p.dcenter[0], p.dcenter[1]),
                width=p.width if hasattr(p, 'width') else p.dwidth,
                orientation=p.orientation,
                layer=p.layer,
                port_type=getattr(p, 'port_type', 'electrical'),
            )
        except Exception:
            pass

    return new


# =============================================================================
# Polygon shim — emula gdsfactory 7 Polygon.
# El código glayout usa .points, .layer, .center, .xmin/xmax/ymin/ymax,
# .bounding_box(). Component.add(lista_de_polygons) los añade.
# =============================================================================
class Polygon:
    """Polygon shim emulating gdsfactory 7 Polygon API used by sky130_add_npc."""

    def __init__(self, points=None, layer=None, **kwargs):
        # Acepta keyword 'points=' o positional
        if points is None and 'points' in kwargs:
            points = kwargs['points']
        self.points = [(float(p[0]), float(p[1])) for p in points]
        self.layer = layer

    @property
    def xmin(self):
        return min(p[0] for p in self.points)

    @property
    def xmax(self):
        return max(p[0] for p in self.points)

    @property
    def ymin(self):
        return min(p[1] for p in self.points)

    @property
    def ymax(self):
        return max(p[1] for p in self.points)

    @property
    def center(self):
        return ((self.xmin + self.xmax) / 2, (self.ymin + self.ymax) / 2)

    def bounding_box(self):
        return ((self.xmin, self.ymin), (self.xmax, self.ymax))

    def __repr__(self):
        return f'Polygon(layer={self.layer}, n_points={len(self.points)})'


# Component.add patch: support lists of Polygon shims AND Component instances.
# gf 7: add(Component) created an instance automatically.
# gf 9: add() expects DInstance (from add_ref). We detect Component and redirect.
def _patch_component_add():
    _orig_add = gf.Component.add

    def _add_with_polygon_support(self, instances):
        if not isinstance(instances, (list, tuple)):
            instances = [instances]
        for item in instances:
            if isinstance(item, Polygon):
                self.add_polygon(item.points, layer=item.layer)
            elif isinstance(item, gf.Component):
                # gf 7 compat: add(Component) -> add_ref(Component)
                self.add_ref(item)
            else:
                _orig_add(self, item)

    gf.Component.add = _add_with_polygon_support

_patch_component_add()


# =============================================================================
# rectangular_ring shim — gdsfactory 9 no lo trae como component
# =============================================================================
def rectangular_ring(enclosed_size, width, layer, centered=True):
    """Emulates gdsfactory 7's rectangular_ring component.

    Creates a hollow rectangle (frame) of given enclosed inner size and wall width.
    """
    from gdsfactory.components import rectangle
    inner_w, inner_h = enclosed_size
    outer_w = inner_w + 2 * width
    outer_h = inner_h + 2 * width

    outer = rectangle(size=(outer_w, outer_h), layer=layer, centered=centered)
    inner_comp = gf.Component()
    inner_comp.add_ref(rectangle(size=(inner_w, inner_h), layer=layer, centered=centered))

    ring = gf.boolean(outer, inner_comp, operation='not', layer=layer)
    return ring


# =============================================================================
# LayerMap conversion + cache
# =============================================================================
_LAYER_DICT_CACHE = {}


def dict_to_layermap(name: str, layers: dict[str, tuple[int, int]]):
    """Convierte un dict {name: (gds_layer, datatype)} a un LayerMap dinámico.

    Guarda el dict original en cache para que MappedPDK.layers_dict pueda usarlo.
    """
    from gdsfactory.technology import LayerMap
    lm = LayerMap(name, names=list(layers.items()))
    _LAYER_DICT_CACHE[name] = layers
    _LAYER_DICT_CACHE[id(lm)] = layers
    return lm


def get_layer_dict_for(layermap):
    """Devuelve el dict original del LayerMap si fue creado con dict_to_layermap."""
    if id(layermap) in _LAYER_DICT_CACHE:
        return _LAYER_DICT_CACHE[id(layermap)]
    # Fallback: reconstruir
    return {m.name: (m.layer, m.datatype) for m in layermap}


# =============================================================================
# route_quad / route_sharp shims (gf 7 → 9: signature changed to require Component)
# =============================================================================
def route_quad(*args, **kwargs):
    """Wrap gf 9 route_quad: gf 7 returned Component; gf 9 modifies in-place."""
    from gdsfactory.routing.route_quad import route_quad as _orig
    if args and isinstance(args[0], gf.Component):
        return _orig(*args, **kwargs)
    temp = gf.Component()
    _orig(temp, *args, **kwargs)
    return temp


def route_sharp(*args, **kwargs):
    """Wrap gf 9 route_sharp similar to route_quad."""
    from gdsfactory.routing.route_sharp import route_sharp as _orig
    if args and isinstance(args[0], gf.Component):
        return _orig(*args, **kwargs)
    temp = gf.Component()
    _orig(temp, *args, **kwargs)
    return temp



# =============================================================================
# clear_cache_noop - para importar en archivos que hacen
# 'from gdsfactory import clear_cache' (el patch de __init__.py no alcanza esos namespaces)
# =============================================================================
def clear_cache_noop(*args, **kwargs):
    return None
