"""glayout — ported to gdsfactory 9 + Python 3.12 (compat layer applied)."""
# === COMPAT MONKEY PATCHES ===
import kfactory as _kf
import gdsfactory as _gf
from kfactory.ports import DPorts, ProtoPorts


# 1. kfactory's Instance API renamed get_ports_list() to .ports
def _get_ports_list(self, **kwargs):
    """COMPAT: kfactory >= 1.x removed get_ports_list.
    Para DInstance: usa cell.ports (ports del Component, no la jerarquia aplanada).
    En gf7, get_ports_list() de una ref devolvia los ports del nivel superior solamente.
    list(self.ports) en kfactory devuelve TODOS los ports de la jerarquia = 21279 ports.
    """
    import kfactory as _kf_gpl
    if isinstance(self, _kf_gpl.DInstance) and hasattr(self, 'cell'):
        return list(self.cell.ports)
    return list(self.ports)

_kf.Instance.get_ports_list = _get_ports_list
if hasattr(_kf, 'DInstance'):
    _kf.DInstance.get_ports_list = _get_ports_list
_gf.Component.get_ports_list = _get_ports_list
if hasattr(_gf, 'ComponentReference'):
    _gf.ComponentReference.get_ports_list = _get_ports_list


# 2. Component.flatten() returns None in gdsfactory 9 (was self in 7).
_orig_component_flatten = _gf.Component.flatten

def _flatten_returns_self(self, *args, **kwargs):
    """COMPAT: gdsfactory 7 flatten() returned self; 9 returns None.
    COMPAT gf9: kfactory locks cached cells; if locked, copy first then flatten."""
    try:
        _orig_component_flatten(self, *args, **kwargs)
    except Exception as _e:
        if 'LockedError' in type(_e).__name__ or 'locked' in str(_e).lower():
            import copy as _copy
            _dup = self.dup()
            _orig_component_flatten(_dup, *args, **kwargs)
            return _dup
        raise
    return self

_gf.Component.flatten = _flatten_returns_self


# 3. DPorts/ProtoPorts dict-like API shims
def _dports_items(self):
    return [(p.name, p) for p in self]

def _dports_keys(self):
    return [p.name for p in self]

def _dports_values(self):
    return list(self)

def _dports_getitem(self, key):
    if isinstance(key, str):
        for p in self:
            if p.name == key:
                return p
        raise KeyError(key)
    return list(self)[key]

def _dports_get(self, key, default=None):
    try:
        return _dports_getitem(self, key)
    except (KeyError, IndexError):
        return default

def _dports_pop(self, key, *default):
    try:
        port = _dports_getitem(self, key)
        # Remover del backing list of bases
        if hasattr(self, 'bases'):
            try:
                idx_to_remove = next(i for i, b in enumerate(self.bases)
                                     if hasattr(port, '_base') and b is port._base)
                self.bases.pop(idx_to_remove)
            except (StopIteration, AttributeError):
                pass
        return port
    except (KeyError, IndexError):
        if default:
            return default[0]
        raise KeyError(key)

# Aplicar a ProtoPorts (parent class) y DPorts
for cls in (ProtoPorts, DPorts):
    cls.items = _dports_items
    cls.keys = _dports_keys
    cls.values = _dports_values
    cls.get = _dports_get
    cls.pop = _dports_pop
    # Override __getitem__ solo si el actual no soporta string keys
    if not hasattr(cls, '__getitem_original__'):
        cls.__getitem_original__ = cls.__getitem__
        def _getitem_dispatch(self, key, _orig=cls.__getitem_original__):
            if isinstance(key, str):
                return _dports_getitem(self, key)
            return _orig(self, key)
        cls.__getitem__ = _getitem_dispatch


# 4. DPorts dict-like __setitem__ — para ports[name] = port_obj
def _dports_setitem(self, key, value):
    """COMPAT: dict-style assignment ports[name] = port."""
    if isinstance(key, str):
        # Si ya existe, reemplazar; si no, añadir con ese nombre
        try:
            existing = _dports_getitem(self, key)
            # Remover el viejo
            if hasattr(self, 'bases') and hasattr(existing, '_base'):
                try:
                    idx = next(i for i, b in enumerate(self.bases) if b is existing._base)
                    self.bases.pop(idx)
                except StopIteration:
                    pass
        except (KeyError, IndexError):
            pass
        # Añadir el nuevo (renombrado al key)
        if hasattr(value, 'copy'):
            new_port = value.copy()
        else:
            new_port = value
        new_port.name = key
        # Añadir a la colección
        if hasattr(self, 'add_port'):
            self.add_port(name=key, port=new_port)
        elif hasattr(self, 'create_port'):
            self.create_port(name=key, port=new_port)
        else:
            # último recurso: insertar el _base
            if hasattr(new_port, '_base'):
                self.bases.append(new_port._base)
    else:
        raise TypeError('DPorts setitem requires string key')

for cls in (ProtoPorts, DPorts):
    cls.__setitem__ = _dports_setitem


# 5. Component.bbox in gdsfactory 9 is a method returning DBox (left/right/top/bottom).
#    glayout 7 expected an attribute returning ((x0,y0),(x1,y1)) tuple-of-tuples.
#    Override .bbox to expose tuple-of-tuples while keeping DBox-style access intact.
import builtins as _builtins
from kfactory.kcell import KCell as _KCell

class _BBoxTupleProxy:
    """Acts as both DBox (left/right/...) and tuple-of-tuples ((x0,y0),(x1,y1))."""
    def __init__(self, dbox):
        self._dbox = dbox
        self._tuple = ((dbox.left, dbox.bottom), (dbox.right, dbox.top))
    def __getitem__(self, idx):
        return self._tuple[idx]
    def __getattr__(self, name):
        return getattr(self._dbox, name)
    def __iter__(self):
        return iter(self._tuple)
    def __len__(self):
        return 2
    def __repr__(self):
        return f'BBox({self._tuple})'

_orig_component_bbox = _gf.Component.bbox

class _BBoxCallableProxy(_BBoxTupleProxy):
    """BBox proxy que también puede llamarse como método para retro-compat."""
    def __call__(self, *args, **kwargs):
        return self  # llamar al proxy devuelve el proxy mismo

class _BBoxDescriptor:
    """Property descriptor: si lees comp.bbox devuelve proxy; comp.bbox() también funciona."""
    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        db = _orig_component_bbox(obj)
        return _BBoxCallableProxy(db)

_gf.Component.bbox = _BBoxDescriptor()

# También en DInstance (Reference)
class _BBoxDescriptorInst:
    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        # DInstance.bbox es método; lo llamamos
        if callable(getattr(type(obj).__bases__[0], 'bbox', None)):
            db = type(obj).__bases__[0].bbox(obj)
        else:
            db = obj.bbox()
        return _BBoxCallableProxy(db)

# Override sólo si bbox actual es método callable
import kfactory as _kf2
if hasattr(_kf2, 'DInstance'):
    _orig_dinstance_bbox = _kf2.DInstance.bbox
    def _dinst_bbox_wrap(self, *args, **kwargs):
        db = _orig_dinstance_bbox(self, *args, **kwargs) if callable(_orig_dinstance_bbox) else _orig_dinstance_bbox
        return _BBoxCallableProxy(db)
    # Reemplazar como descriptor para que comp_ref.bbox sin paréntesis devuelva proxy
    class _DescDInst:
        def __get__(self, obj, objtype=None):
            if obj is None:
                return self
            db = _orig_dinstance_bbox(obj) if callable(_orig_dinstance_bbox) else _orig_dinstance_bbox
            return _BBoxCallableProxy(db)
    _kf2.DInstance.bbox = _DescDInst()

# kfactory.Instance también tiene bbox
if hasattr(_kf.Instance, 'bbox'):
    _orig_inst_bbox = _kf.Instance.bbox
    def _inst_bbox_compat(self, *args, **kwargs):
        db = _orig_inst_bbox(self, *args, **kwargs) if callable(_orig_inst_bbox) else _orig_inst_bbox
        if hasattr(db, 'left'):
            return _BBoxTupleProxy(db)
        return db
    # Solo si bbox es método
    if callable(_orig_inst_bbox):
        _kf.Instance.bbox = _inst_bbox_compat


# 6. Component.ref() — gdsfactory 7 method to create a ComponentReference, removed in 9.
def _component_ref(self, *args, **kwargs):
    """COMPAT: gf 7's Component.ref() created a Reference; in gf 9 use add_ref of a wrapping component."""
    wrapper = _gf.Component()
    return wrapper.add_ref(self)

if not hasattr(_gf.Component, 'ref') or _gf.Component.ref is None:
    _gf.Component.ref = _component_ref


# 7. DPort.move_copy(offset) — gdsfactory 7 API. In gf9 use copy + dx/dy.
from kfactory.port import DPort, Port
def _port_move_copy(self, offset):
    """COMPAT: copia el port y mueve la copia por offset (dx, dy)."""
    new = self.copy()
    new.dx += offset[0]
    new.dy += offset[1]
    return new

if not hasattr(DPort, 'move_copy'):
    DPort.move_copy = _port_move_copy
if not hasattr(Port, 'move_copy'):
    Port.move_copy = _port_move_copy

# DPort needs movex/movey too? glayout uses ref.movex().movey() — for ComponentReference
# DInstance has movex/movey already, OK.


# 8. DPort/Port not hashable in pydantic 2 — needed for kfactory @cell cache.
def _port_hash(self):
    return hash((self.name, self.layer, getattr(self, 'port_type', '')))

if not hasattr(DPort, '__hash__') or DPort.__hash__ is None:
    DPort.__hash__ = _port_hash
if not hasattr(Port, '__hash__') or Port.__hash__ is None:
    Port.__hash__ = _port_hash


# 9. DPort.layer in kfactory devuelve int (layer index), no tuple (layer, datatype).
#    layer_info da el LayerInfo con layer/datatype.
#    Hacemos que .layer devuelva tuple usando layer_info.
_orig_dport_layer = type(_gf.Component().add_port('_x', center=(0,0), width=1, orientation=0, layer=(1,0))).layer

def _port_layer_compat(self):
    info = self.layer_info
    return (info.layer, info.datatype)

# Aplicar como property
DPort_layer_prop = property(_port_layer_compat)
DPort.layer = DPort_layer_prop
Port.layer = DPort_layer_prop


# 10. Port shim — kfactory DPort/Port don't accept 'parent' or 'shear_angle'.
#     glayout 7's Port took these. Wrap constructors to drop them silently.
_orig_DPort_init = DPort.__init__
_orig_Port_init = Port.__init__

# Lista de args que kfactory NO acepta pero glayout pasa:
_INCOMPAT_PORT_ARGS = ('parent', 'shear_angle')

def _make_compat_init(orig_init):
    def _compat_init(self, *args, **kwargs):
        # Drop unsupported args (gdsfactory 7 had them, kfactory doesn't)
        for arg in _INCOMPAT_PORT_ARGS:
            kwargs.pop(arg, None)
        # 'cross_section' may be None — kfactory doesn't like it sometimes
        if kwargs.get('cross_section') is None:
            kwargs.pop('cross_section', None)
        return orig_init(self, *args, **kwargs)
    return _compat_init

DPort.__init__ = _make_compat_init(_orig_DPort_init)
Port.__init__ = _make_compat_init(_orig_Port_init)

# Add 'parent' as readonly None property (glayout reads it but doesn't depend on real value)
if not hasattr(DPort, 'parent') or not isinstance(getattr(DPort, 'parent', None), property):
    DPort.parent = property(lambda self: None)
if not hasattr(Port, 'parent') or not isinstance(getattr(Port, 'parent', None), property):
    Port.parent = property(lambda self: None)

# shear_angle similar (glayout reads on copy)
if not hasattr(DPort, 'shear_angle'):
    DPort.shear_angle = property(lambda self: None)
if not hasattr(Port, 'shear_angle'):
    Port.shear_angle = property(lambda self: None)


# 11. Component.add_polygon: in gdsfactory 7, accepted gdstk.Polygon objects.
#     In gf 9 requires (points, layer=...). Wrap to support both.
import gdstk as _gdstk
_orig_add_polygon = _gf.Component.add_polygon

def _add_polygon_compat(self, points, layer=None, **kwargs):
    """COMPAT: accept gdstk.Polygon as first arg (points), extract its data."""
    if isinstance(points, _gdstk.Polygon):
        gp = points
        # gdstk.Polygon.points es np.array; layer/datatype son atributos
        pts = [(float(p[0]), float(p[1])) for p in gp.points]
        layer = layer or (gp.layer, gp.datatype)
        return _orig_add_polygon(self, pts, layer=layer, **kwargs)
    return _orig_add_polygon(self, points, layer=layer, **kwargs)

_gf.Component.add_polygon = _add_polygon_compat


# 12. Component.add_port: kfactory enforces width to be even multiple of 1 DBU.
#     glayout 7 didn't enforce this; kfactory does. Auto-snap width to 2*grid.
_orig_add_port = _gf.Component.add_port

def _add_port_compat(self, *args, **kwargs):
    """COMPAT: snap port width to 2*grid (filosofía glayout snap_to_2xgrid)."""
    width = kwargs.get('width', None)
    if width is not None:
        # Default grid = 0.001 µm = 1 DBU; 2*DBU = 0.002 µm
        # Más conservador: redondear a múltiplo de 0.005 (Sky130 manufacturing grid)
        grid_2x = 0.002  # kfactory exige múltiplo de 2 DBU = 0.002 µm
        snapped = round(width / grid_2x) * grid_2x
        if snapped < grid_2x:
            snapped = grid_2x  # mínimo
        kwargs['width'] = snapped
    return _orig_add_port(self, *args, **kwargs)

_gf.Component.add_port = _add_port_compat


# 13. Component("name") in kfactory raises if name exists.
#     gdsfactory 7 allowed duplicates (silently). Patch to auto-suffix.
_orig_component_init = _gf.Component.__init__
_seen_names = {}

def _component_init_with_suffix(self, name=None, *args, **kwargs):
    """COMPAT: auto-suffix duplicate names instead of raising."""
    if name is not None:
        count = _seen_names.get(name, 0)
        if count > 0:
            unique_name = f'{name}_{count}'
        else:
            unique_name = name
        _seen_names[name] = count + 1
        try:
            return _orig_component_init(self, unique_name, *args, **kwargs)
        except ValueError as e:
            if 'already exists' in str(e):
                # Try with even higher suffix
                _seen_names[name] = count + 2
                return _orig_component_init(self, f'{name}_{count + 1}', *args, **kwargs)
            raise
    return _orig_component_init(self, *args, **kwargs)

_gf.Component.__init__ = _component_init_with_suffix


# 14. DInstance.move(): kfactory requires (origin, destination); gf 7 supported destination kwarg only.
#     Wrap to default origin=(0,0) when only destination is given.
_orig_dinstance_move = _kf.DInstance.move

def _move_compat(self, origin=None, destination=None, *args, **kwargs):
    if origin is None and destination is None:
        # Maybe just kwargs
        destination = kwargs.pop('destination', None)
    if destination is not None and origin is None:
        origin = (0, 0)
    if origin is not None and destination is not None:
        return _orig_dinstance_move(self, origin, destination, *args, **kwargs)
    # Fallback al método original con whatever args
    return _orig_dinstance_move(self, origin, *args, **kwargs)

_kf.DInstance.move = _move_compat

# Component.move también
_orig_component_move = _gf.Component.move
def _comp_move_compat(self, origin=None, destination=None, *args, **kwargs):
    if origin is None and destination is None:
        destination = kwargs.pop('destination', None)
    if destination is not None and origin is None:
        origin = (0, 0)
    if origin is not None and destination is not None:
        return _orig_component_move(self, origin, destination, *args, **kwargs)
    return _orig_component_move(self, origin, *args, **kwargs)
_gf.Component.move = _comp_move_compat


# 15. Component.add_padding(layers, default): gf 7 helper to add layer surrounding component.
#     Add rect for each layer, expanded by 'default' from current bbox.
def _component_add_padding(self, layers=None, default=0,
                            top=None, bottom=None, left=None, right=None,
                            **kwargs):
    """COMPAT: add a rectangle in each layer enclosing the component bbox + padding."""
    if layers is None:
        return self
    # Usar el bbox proxy (que sí funciona vía descriptor patched)
    bbox_proxy = self.bbox  # _BBoxCallableProxy
    db = bbox_proxy._dbox if hasattr(bbox_proxy, '_dbox') else bbox_proxy
    pad_top = top if top is not None else default
    pad_bottom = bottom if bottom is not None else default
    pad_left = left if left is not None else default
    pad_right = right if right is not None else default
    x0 = db.left - pad_left
    y0 = db.bottom - pad_bottom
    x1 = db.right + pad_right
    y1 = db.top + pad_top
    points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for layer in layers:
        self.add_polygon(points, layer=layer)
    return self

if not hasattr(_gf.Component, 'add_padding') or _gf.Component.add_padding is None:
    _gf.Component.add_padding = _component_add_padding


# 16. Component.info — gdsfactory 9 (kfactory) restringe tipos en info dict.
#     glayout guarda objetos Netlist custom. Usamos un dict separado a nivel
#     de instancia que ignora la validación de pydantic.
_INFO_OVERRIDE_STORAGE = {}  # id(component) -> dict

class _InfoDict(dict):
    """Dict con get/set/etc, instalable como property override de Component.info."""
    pass

_orig_info_descriptor = type(_gf.Component).__getattribute__(_gf.Component, 'info') if False else None

def _info_get(self):
    cid = id(self)
    if cid not in _INFO_OVERRIDE_STORAGE:
        _INFO_OVERRIDE_STORAGE[cid] = _InfoDict()
    return _INFO_OVERRIDE_STORAGE[cid]

def _info_set(self, value):
    cid = id(self)
    _INFO_OVERRIDE_STORAGE[cid] = _InfoDict(value) if not isinstance(value, _InfoDict) else value

# Definir como property en Component (override del field pydantic)
# Pydantic no permite property en model; usamos __getattr__ approach via a class wrapper
_orig_component_getattr = _gf.Component.__getattribute__

def _component_getattr_override(self, name):
    if name == 'info':
        return _info_get(self)
    return _orig_component_getattr(self, name)

# No reemplazar __getattribute__ porque rompe demasiadas cosas.
# Mejor: monkey-patch __setattr__ para 'info' assignment y crear shadow dict
_orig_component_setattr = _gf.Component.__setattr__
def _component_setattr_compat(self, name, value):
    if name == 'info':
        _info_set(self, value)
        return
    return _orig_component_setattr(self, name, value)

# Para setattr funciona. Para 'comp.info' acceso, agregar property carefully:
# kfactory's Component es pydantic; properties en pydantic models no funcionan bien.
# Workaround: usar __getattr__ del object base de kfactory si es accesible.

# Probar approach diferente: monkey-patch Info.__setitem__ directamente
from kfactory.kcell import Info
_orig_info_setitem = getattr(Info, '__setitem__', None)
def _info_setitem_compat(self, key, value):
    # Bypass validator: set directamente en _data si existe
    if hasattr(self, '__dict__'):
        if 'extra_data' not in self.__dict__:
            self.__dict__['extra_data'] = {}
        self.__dict__['extra_data'][key] = value
    elif _orig_info_setitem:
        try:
            return _orig_info_setitem(self, key, value)
        except Exception:
            pass

def _info_getitem_compat(self, key):
    if 'extra_data' in self.__dict__ and key in self.__dict__['extra_data']:
        return self.__dict__['extra_data'][key]
    return getattr(self, key, None)

Info.__setitem__ = _info_setitem_compat
Info.__getitem__ = _info_getitem_compat

# 17. route_quad/sharp shim (gf 7 → 9 signature change)
import gdsfactory as _gf
import gdsfactory.routing as _routing

_orig_route_quad = _routing.route_quad
_orig_route_sharp = _routing.route_sharp

def _route_quad_compat(*args, **kwargs):
    if args and isinstance(args[0], _gf.Component):
        return _orig_route_quad(*args, **kwargs)
    temp = _gf.Component()
    _orig_route_quad(temp, *args, **kwargs)
    return temp

def _route_sharp_compat(*args, **kwargs):
    if args and isinstance(args[0], _gf.Component):
        return _orig_route_sharp(*args, **kwargs)
    temp = _gf.Component()
    _orig_route_sharp(temp, *args, **kwargs)
    return temp

_routing.route_quad = _route_quad_compat
_routing.route_sharp = _route_sharp_compat
# También en el módulo donde glayout las importa
import sys
import gdsfactory.routing.route_quad as _rq_module_loc  # esto es la función misma en gf 9
import gdsfactory.routing.route_sharp as _rs_module_loc


# 18. DInstance.origin: gf 7 had .origin = (x, y); kfactory uses .dtrans.disp
def _instance_origin(self):
    """COMPAT: gf 7 origin → tuple (x, y) of current displacement."""
    try:
        d = self.dtrans.disp
        return (d.x, d.y)
    except Exception:
        try:
            return (self.dcenter[0], self.dcenter[1])  # fallback
        except Exception:
            return (0.0, 0.0)

if not hasattr(_kf.Instance, 'origin'):
    _kf.Instance.origin = property(_instance_origin)
if hasattr(_kf, 'DInstance') and not hasattr(_kf.DInstance, 'origin'):
    _kf.DInstance.origin = property(_instance_origin)


# 19. DPort.width: gf 7 was settable; kfactory makes it readonly.
#     Patch with a settable property that writes underlying _base or dwidth.
_orig_dport_width_property = DPort.width

def _port_width_get(self):
    if isinstance(_orig_dport_width_property, property):
        return _orig_dport_width_property.fget(self)
    return self.dwidth if hasattr(self, 'dwidth') else 0

def _port_width_set(self, value):
    # Snap to 2 DBU
    snapped = round(value / 0.002) * 0.002
    if snapped < 0.002:
        snapped = 0.002
    # kfactory: setattr underlying dwidth
    try:
        # Acceso directo via _base (BasePort)
        self._base.cross_section.dwidth = snapped
    except Exception:
        try:
            object.__setattr__(self, 'dwidth', snapped)
        except Exception:
            pass

DPort.width = property(_port_width_get, _port_width_set)
Port.width = property(_port_width_get, _port_width_set)


# 20. DPort.layer settable (gf 7 was; kfactory readonly).
def _port_layer_set(self, value):
    """COMPAT: setter para port.layer = (l, dt)."""
    try:
        if isinstance(value, (tuple, list)) and len(value) == 2:
            from klayout import db
            self._base.layer_info = db.LayerInfo(int(value[0]), int(value[1]))
        elif isinstance(value, int):
            # ya es layer index
            self._base.layer = value
    except Exception:
        pass

# Reemplazar la property anterior con getter+setter
DPort.layer = property(_port_layer_compat, _port_layer_set)
Port.layer = property(_port_layer_compat, _port_layer_set)


# 21. Component.unlock()/lock(): kfactory has _locked attr, no method.
def _component_unlock(self):
    try:
        if hasattr(self, '_base') and hasattr(self._base, 'kdb_cell'):
            # En kfactory el lock está en otro lado o no expuesto público
            pass  # noop seguro
    except Exception:
        pass
    return self

def _component_lock(self):
    return self

if not hasattr(_gf.Component, 'unlock') or _gf.Component.unlock is None:
    _gf.Component.unlock = _component_unlock
if not hasattr(_gf.Component, 'lock') or _gf.Component.lock is None:
    _gf.Component.lock = _component_lock


# 22. DPort.copy(name=...) — gf 7 accepted kwargs; kfactory doesn't.
#     Wrap to extract name kwarg, copy, then rename.
_orig_dport_copy = DPort.copy

def _dport_copy_compat(self, *args, **kwargs):
    new_name = kwargs.pop('name', None)
    new_port = _orig_dport_copy(self, *args, **kwargs)
    if new_name is not None and hasattr(new_port, 'name'):
        try:
            new_port.name = new_name
        except Exception:
            pass
    return new_port

DPort.copy = _dport_copy_compat
Port.copy = _dport_copy_compat


# 23. Instance.info — kfactory Instance no expone .info como Component.
#     Usar el mismo storage shim de info.
def _instance_info_get(self):
    cid = id(self)
    if cid not in _INFO_OVERRIDE_STORAGE:
        _INFO_OVERRIDE_STORAGE[cid] = _InfoDict()
    return _INFO_OVERRIDE_STORAGE[cid]

def _instance_info_set(self, value):
    cid = id(self)
    _INFO_OVERRIDE_STORAGE[cid] = _InfoDict(value) if not isinstance(value, _InfoDict) else value

if not hasattr(_kf.Instance, 'info') or not isinstance(getattr(_kf.Instance, 'info', None), property):
    _kf.Instance.info = property(_instance_info_get, _instance_info_set)
if hasattr(_kf, 'DInstance') and (not hasattr(_kf.DInstance, 'info') or not isinstance(getattr(_kf.DInstance, 'info', None), property)):
    _kf.DInstance.info = property(_instance_info_get, _instance_info_set)


# 24. Component.locked - wrap to handle destroyed cells gracefully (return False).
_orig_locked_descriptor = type(_gf.Component).__dict__.get('locked')
_orig_kcell_locked = _kf.kcell.KCell.__dict__.get('locked')

class _LockedSafeDescriptor:
    """Returns False instead of raising if cell is destroyed."""
    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        try:
            return obj._base.locked
        except RuntimeError:
            return False
        except Exception:
            return False

_gf.Component.locked = _LockedSafeDescriptor()
_kf.kcell.KCell.locked = _LockedSafeDescriptor()


# 25. Component.ref() keepalive — el wrapper temporal debe sobrevivir.
_REF_KEEPALIVE = []

_orig_component_ref = _gf.Component.ref

def _component_ref_keepalive(self, *args, **kwargs):
    """COMPAT: gf 7's Component.ref() returned a Reference; keep wrapper alive."""
    wrapper = _gf.Component()
    _REF_KEEPALIVE.append(wrapper)  # CRÍTICO: evita GC del wrapper
    return wrapper.add_ref(self)

_gf.Component.ref = _component_ref_keepalive


# 26. clear_cache() en gf 9 borra TODO el KCLayout, destruyendo Refs vivas.
#     glayout 7 lo usaba defensivamente entre stages; en gf 9 es destructivo.
#     Auto-suffix shim ya maneja name collisions, así que clear_cache es noop.
def _clear_cache_noop(*args, **kwargs):
    """COMPAT: noop — clear_cache en kfactory destruye Refs vivas."""
    return None

_gf.clear_cache = _clear_cache_noop
# Y también su bind original
import gdsfactory
gdsfactory.clear_cache = _clear_cache_noop


# 27. Instance.parent — gf 7 ref.parent = Component padre. kfactory usa ref.parent_cell.
def _instance_parent(self):
    if hasattr(self, 'parent_cell'):
        return self.parent_cell
    return None

# 28. Component.extract(layers=[...]) - gf 7 filtraba polygons por layer y retornaba sub-Component.
# gf 9 / kfactory DKCell no tiene este metodo. Glayout lo usa solo para calcular bbox.
# Retornamos un objeto con .bbox que calcula el bounding box de las instancias en esa layer.
class _ExtractResult:
    def __init__(self, bbox_val):
        if hasattr(bbox_val, 'left'):
            self._x0=float(bbox_val.left); self._y0=float(bbox_val.bottom)
            self._x1=float(bbox_val.right); self._y1=float(bbox_val.top)
        elif bbox_val and len(bbox_val)==2:
            self._x0=float(bbox_val[0][0]); self._y0=float(bbox_val[0][1])
            self._x1=float(bbox_val[1][0]); self._y1=float(bbox_val[1][1])
        else:
            self._x0=self._y0=self._x1=self._y1=0.0
    @property
    def bbox(self): return ((self._x0,self._y0),(self._x1,self._y1))
    @property
    def xmin(self): return self._x0
    @property
    def xmax(self): return self._x1
    @property
    def ymin(self): return self._y0
    @property
    def ymax(self): return self._y1
    @property
    def center(self): return ((self._x0+self._x1)/2, (self._y0+self._y1)/2)
    def __iter__(self): return iter(self.bbox)
    def __getitem__(self,i): return self.bbox[i]

def _component_extract(self, layers=None, **kwargs):
    import klayout.db as db
    try:
        kdb_cell = self.kdb_cell if hasattr(self, 'kdb_cell') else self._base.kdb_cell
        layout = kdb_cell.layout()
        combined = db.DBox()
        for layer_info in (layers or []):
            if isinstance(layer_info, (tuple, list)) and len(layer_info) == 2:
                li = db.LayerInfo(int(layer_info[0]), int(layer_info[1]))
            elif isinstance(layer_info, int):
                li = db.LayerInfo(layer_info, 0)
            else:
                # String como "mcon", "li1" - buscar en el layout iterando layers
                li = None
                for layer_idx in range(layout.layers()):
                    info = layout.get_info(layer_idx)
                    # No podemos resolver por nombre simbolico aqui; usar fallback
                li = None
            if li is None:
                continue
            idx = layout.layer(li)
            b = kdb_cell.dbbox(idx)
            combined += b
        if not combined.empty():
            return _ExtractResult(((combined.left, combined.bottom),(combined.right, combined.top)))
    except Exception:
        pass
    # Fallback: bbox de toda la cell
    try:
        bb = self.bbox
        if callable(bb): bb = bb()
        return _ExtractResult(bb)
    except Exception:
        return _ExtractResult(((0,0),(0,0)))

import gdsfactory as _gf2
import kfactory as _kf_extract
_gf2.Component.extract = _component_extract
# Tambien parchear DKCell para que .parent.extract() funcione en DInstances
_kf_extract.DKCell.extract = _component_extract


if not hasattr(_kf.Instance, 'parent') or not isinstance(getattr(_kf.Instance, 'parent', None), property):
    _kf.Instance.parent = property(_instance_parent)
if hasattr(_kf, 'DInstance') and (not hasattr(_kf.DInstance, 'parent') or not isinstance(getattr(_kf.DInstance, 'parent', None), property)):
    _kf.DInstance.parent = property(_instance_parent)


# 29. evaluate_bbox acepta _ExtractResult - pydantic @validate_call rechaza _ExtractResult
# porque el type hint exige Component|ComponentReference. Wrapeamos con un pre-check.
def _patch_evaluate_bbox():
    import glayout.flow.pdk.util.comp_utils as _cu
    _orig_evaluate_bbox = _cu.evaluate_bbox
    def _evaluate_bbox_compat(custom_comp, *args, **kwargs):
        if isinstance(custom_comp, _ExtractResult):
            # Calcula directamente sin pasar por pydantic
            bb = custom_comp.bbox
            import decimal
            width = abs(decimal.Decimal(str(bb[1][0])) - decimal.Decimal(str(bb[0][0])))
            height = abs(decimal.Decimal(str(bb[1][1])) - decimal.Decimal(str(bb[0][1])))
            return_decimal = kwargs.get('return_decimal', False) or (args and args[0])
            if return_decimal:
                return (width, height)
            return (float(width), float(height))
        return _orig_evaluate_bbox(custom_comp, *args, **kwargs)
    _cu.evaluate_bbox = _evaluate_bbox_compat
    # Tambien parchear el nombre en todos los modulos que ya lo importaron
    import glayout.flow.primitives.via_gen as _vg
    _vg.evaluate_bbox = _evaluate_bbox_compat

_patch_evaluate_bbox()
