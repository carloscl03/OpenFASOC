from gdsfactory import Component
from pydantic import validate_call


@validate_call(config={"arbitrary_types_allowed": True})
def component_snap_to_grid(comp: Component) -> Component:
	"""snaps all polygons and ports in component to grid
	comp = the component to snap to grid
	NOTE this function will flatten the component
	"""
	#return comp.flatten()
	# flatten the component then copy (snaps polygons and ports to grid)
	name = comp.name
	comp = comp.flatten().copy()
	comp.name = name
	return comp


