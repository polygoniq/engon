# copyright (c) 2018- polygoniq xyz s.r.o.
# Functionalities to work with geometry nodes modifiers
import bpy
import typing
from . import node_utils_bpy

# Mapping of input.identifier to (input.name, input.value)
NodeGroupInputs = typing.Dict[str, typing.Tuple[str, typing.Any]]


class NodesModifierInput:
    """Mapping of one node group and its inputs"""

    def __init__(self, modifier: bpy.types.NodesModifier) -> None:
        assert modifier.node_group is not None
        self.inputs: NodeGroupInputs = {}
        self.node_group = modifier.node_group
        for input_ in node_utils_bpy.get_node_tree_inputs(modifier.node_group):
            if input_.identifier in modifier:
                self.inputs[input_.identifier] = (input_.name, modifier[input_.identifier])


def get_modifiers_inputs_map(
    modifiers: typing.Iterable[bpy.types.Modifier]
) -> typing.Dict[str, NodesModifierInput]:
    """Returns mapping of geometry nodes modifiers to their respective inputs"""
    ret: typing.Dict[str, NodesModifierInput] = {}
    for mod in modifiers:
        if mod.type != 'NODES':
            continue

        mod = typing.cast(bpy.types.NodesModifier, mod)
        if mod.node_group is None:
            continue

        ret[mod.name] = NodesModifierInput(mod)

    return ret


class NodesModifierInputsNameView:
    """View of Geometry Nodes modifier that allows changing inputs by input name"""

    def __init__(self, mod: bpy.types.Modifier):
        assert mod.type == 'NODES'
        self.mod = mod
        self.name_to_identifier_map = {}
        for input_ in node_utils_bpy.get_node_tree_inputs(mod.node_group):
            # Is the input exposed in the modifier -> modifiers["RG_"]
            if input_.identifier in mod:
                self.name_to_identifier_map[input_.name] = input_.identifier

    def set_input_value(self, input_name: str, value: typing.Any) -> None:
        identifier = self.name_to_identifier_map.get(input_name)
        self.mod[identifier] = value

    def set_obj_input_value(self, input_name: str, obj_name: str) -> None:
        identifier = self.name_to_identifier_map.get(input_name)
        # Object reference has to be set directly from bpy.data.objects
        self.mod[identifier] = bpy.data.objects[obj_name]

    def set_material_input_value(self, input_name: str, mat_name: str) -> None:
        identifier = self.name_to_identifier_map.get(input_name)
        # Materials reference has to be set directly from bpy.data.materials
        self.mod[identifier] = bpy.data.materials[mat_name]

    def set_collection_input_value(self, input_name: str, collection_name: str) -> None:
        identifier = self.name_to_identifier_map.get(input_name)
        # Collections reference has to be set directly from bpy.data.collections
        self.mod[identifier] = bpy.data.collections[collection_name]

    def set_array_input_value(self, input_name: str, value: typing.List[typing.Any]) -> None:
        identifier = self.name_to_identifier_map.get(input_name)
        for i, v in enumerate(value):
            self.mod[identifier][i] = v

    def get_input_value(self, input_name: str) -> typing.Any:
        identifier = self.name_to_identifier_map.get(input_name)
        return self.mod[identifier]

    def __contains__(self, input_name: str) -> bool:
        return input_name in self.name_to_identifier_map


class GeoNodesModifierInputsPanelMixin:
    """Mixin for displaying Geometry Nodes modifier inputs.

    Adds functionally to draw inputs of Geometry Nodes modifiers of active objects
    using a provided template.
    """

    DRAW_ALL = -1

    def draw_active_object_modifiers_node_group_inputs_template(
        self,
        layout: bpy.types.UILayout,
        context: bpy.types.Context,
        inputs: node_utils_bpy.NodeSocketsDrawTemplate,
        draw_modifier_header: bool = False,
        max_occurrences: int = 1
    ) -> None:
        obj = context.active_object
        if obj is None:
            return
        mods = get_geometry_nodes_modifiers_by_node_group(
            obj, inputs.name)
        if len(mods) == 0:
            return
        root_layout = layout
        for i, mod in enumerate(mods):
            if max_occurrences != GeoNodesModifierInputsPanelMixin.DRAW_ALL and i >= max_occurrences:
                break
            if draw_modifier_header:
                layout = self.draw_geonodes_modifier_ui_box(root_layout, mod)
                if not mod.show_expanded:
                    continue
            col = layout.column(align=True)
            inputs.draw_from_geonodes_modifier(col, mods[i])

    def draw_geonodes_modifier_ui_box(
        self,
        layout: bpy.types.UILayout,
        mod: bpy.types.NodesModifier
    ) -> bpy.types.UILayout:
        box = layout.box()
        row = box.row(align=True)
        row.prop(mod, "show_expanded", text="", emboss=False)
        row.prop(mod, "name", text="")
        row.prop(mod, "show_in_editmode", text="")
        row.prop(mod, "show_viewport", text="")
        row.prop(mod, "show_render", text="")
        row.operator("object.modifier_copy", text="", icon='DUPLICATE').modifier = mod.name
        row.operator("object.modifier_remove", text="", icon='X', emboss=False).modifier = mod.name
        return box


def get_geometry_nodes_modifiers_by_node_group(
    obj: bpy.types.Object,
    node_group_name: str
) -> typing.List[bpy.types.NodesModifier]:
    output: typing.List[bpy.types.NodesModifier] = []
    for mod in obj.modifiers:
        if mod.type == 'NODES' and mod.node_group is not None:
            if mod.node_group.name == node_group_name:
                output.append(mod)
    return output
