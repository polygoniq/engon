# copyright (c) 2018- polygoniq xyz s.r.o.
# Functionalities to work with geometry nodes modifiers
import bpy
import typing
import logging
from . import node_utils_bpy

logger = logging.getLogger(f"polygoniq.{__name__}")

# Mapping of input.identifier to (input.name, input.value)
NodeGroupInputs = dict[str, tuple[bpy.types.NodeTreeInterfaceSocket, typing.Any]]


# In Blender 5.2+, the way to access geo nodes modifier inputs changed, so we need to abstract it away
def get_mod_input_keys(mod: bpy.types.NodesModifier) -> list[str]:
    if bpy.app.version >= (5, 2, 0):
        return list(mod.properties.inputs.keys())
    return list(mod.keys())


def has_mod_input(mod: bpy.types.NodesModifier, identifier: str) -> bool:
    if bpy.app.version >= (5, 2, 0):
        return hasattr(mod.properties.inputs, identifier)
    return identifier in mod


def has_mod_input_value_attr(mod: bpy.types.NodesModifier, identifier: str) -> bool:
    if bpy.app.version >= (5, 2, 0):
        input_ = getattr(mod.properties.inputs, identifier)
        return hasattr(input_, "value")
    return True


def get_mod_input_value(mod: bpy.types.NodesModifier, identifier: str) -> typing.Any:
    if not has_mod_input(mod, identifier):
        raise KeyError(f"Modifier {mod.name} doesn't have input with identifier '{identifier}'")
    if not has_mod_input_value_attr(mod, identifier):
        raise ValueError(
            f"Input '{identifier}' of modifier {mod.name} doesn't have a value attribute"
        )
    if bpy.app.version >= (5, 2, 0):
        input_ = getattr(mod.properties.inputs, identifier)
        return input_.value
    return mod[identifier]


def set_mod_input_value(mod: bpy.types.NodesModifier, identifier: str, value: typing.Any) -> None:
    if not has_mod_input(mod, identifier):
        raise KeyError(f"Modifier {mod.name} doesn't have input with identifier '{identifier}'")
    if not has_mod_input_value_attr(mod, identifier):
        raise ValueError(
            f"Input '{identifier}' of modifier {mod.name} doesn't have a value attribute"
        )

    if bpy.app.version >= (5, 2, 0):
        input_ = getattr(mod.properties.inputs, identifier)
        setattr(input_, "value", value)
    else:
        mod[identifier] = value


class NodesModifierInput:
    """Mapping of one node group and its inputs"""

    def __init__(self, modifier: bpy.types.NodesModifier) -> None:
        assert modifier.node_group is not None
        self.inputs: NodeGroupInputs = {}
        self.node_group = modifier.node_group
        self.original_inputs = node_utils_bpy.get_node_tree_inputs_map(modifier.node_group)
        for input_ in self.original_inputs.values():
            if has_mod_input(modifier, input_.identifier) and has_mod_input_value_attr(
                modifier, input_.identifier
            ):
                self.inputs[input_.identifier] = (
                    input_,
                    get_mod_input_value(modifier, input_.identifier),
                )


def get_modifiers_inputs_map(
    modifiers: typing.Iterable[bpy.types.Modifier],
) -> dict[str, NodesModifierInput]:
    """Returns mapping of geometry nodes modifiers to their respective inputs"""
    ret: dict[str, NodesModifierInput] = {}
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

    def __init__(self, mod: bpy.types.NodesModifier) -> None:
        assert mod.type == 'NODES'
        self.mod = mod
        self.name_to_identifier_map = {}
        self.node_tree_inputs = node_utils_bpy.get_node_tree_inputs_map(mod.node_group)
        for input_ in self.node_tree_inputs.values():
            # Is the input exposed in the modifier -> modifiers["RG_"]
            if has_mod_input(mod, input_.identifier) and has_mod_input_value_attr(
                mod, input_.identifier
            ):
                self.name_to_identifier_map[input_.name] = input_.identifier

    def set_input_value(self, input_name: str, value: typing.Any) -> None:
        identifier = self.name_to_identifier_map.get(input_name)
        input_ = self.node_tree_inputs.get(identifier, None)
        # Input cannot be None, this would fail on the identifier already, we expect
        # setting of the inputs to throw errors if the input doesn't exist to not fail
        # silently.
        assert input_ is not None

        socket_type = node_utils_bpy.get_socket_type(input_)
        # bool needs special handling, as through versions it became statically typed
        # boolean from an integer value of 0 or 1
        if socket_type == "NodeSocketBool":
            set_mod_input_value(self.mod, identifier, bool(value))
        else:
            set_mod_input_value(self.mod, identifier, value)

    def set_obj_input_value(self, input_name: str, obj_name: str) -> None:
        identifier = self.name_to_identifier_map.get(input_name)
        # Object reference has to be set directly from bpy.data.objects
        set_mod_input_value(self.mod, identifier, bpy.data.objects[obj_name])

    def set_material_input_value(self, input_name: str, mat_name: str) -> None:
        identifier = self.name_to_identifier_map.get(input_name)
        # Materials reference has to be set directly from bpy.data.materials
        set_mod_input_value(self.mod, identifier, bpy.data.materials[mat_name])

    def set_collection_input_value(self, input_name: str, collection_name: str) -> None:
        identifier = self.name_to_identifier_map.get(input_name)
        # Collections reference has to be set directly from bpy.data.collections
        set_mod_input_value(self.mod, identifier, bpy.data.collections[collection_name])

    def set_array_input_value(self, input_name: str, value: list[typing.Any]) -> None:
        identifier = self.name_to_identifier_map.get(input_name)
        current_value = get_mod_input_value(self.mod, identifier)
        for i, v in enumerate(value):
            current_value[i] = v

    def get_input_value(self, input_name: str) -> typing.Any:
        identifier = self.name_to_identifier_map.get(input_name)
        return get_mod_input_value(self.mod, identifier)

    def __contains__(self, input_name: str) -> bool:
        return input_name in self.name_to_identifier_map


class GeoNodesModifierInputsPanelMixin:
    """Mixin for displaying Geometry Nodes modifier inputs.

    Adds functionally to draw inputs of Geometry Nodes modifiers of active objects
    using a provided template.
    """

    DRAW_ALL = -1

    def draw_object_modifiers_node_group_inputs_template(
        self,
        obj: bpy.types.Object,
        layout: bpy.types.UILayout,
        inputs: node_utils_bpy.NodeSocketsDrawTemplate,
        draw_modifier_header: bool = False,
        max_occurrences: int = 1,
    ) -> None:
        mods = get_geometry_nodes_modifiers_by_node_group(
            obj, inputs.name_prefix, inputs.exact_match
        )
        if len(mods) == 0:
            return
        root_layout = layout
        for i, mod in enumerate(mods):
            if (
                max_occurrences != GeoNodesModifierInputsPanelMixin.DRAW_ALL
                and i >= max_occurrences
            ):
                break
            if draw_modifier_header:
                layout = self.draw_geonodes_modifier_ui_box(root_layout, mod)
                if not mod.show_expanded:
                    continue
            col = layout.column(align=True)
            inputs.draw_from_geonodes_modifier(col, mods[i])

    def draw_active_object_modifiers_node_group_inputs_template(
        self,
        layout: bpy.types.UILayout,
        context: bpy.types.Context,
        inputs: node_utils_bpy.NodeSocketsDrawTemplate,
        draw_modifier_header: bool = False,
        max_occurrences: int = 1,
    ) -> None:
        obj = context.active_object
        if obj is None:
            return
        self.draw_object_modifiers_node_group_inputs_template(
            obj, layout, inputs, draw_modifier_header, max_occurrences
        )

    def draw_show_viewport_and_render(
        self, layout: bpy.types.UILayout, mod: bpy.types.NodesModifier
    ) -> None:
        layout.prop(mod, "show_viewport", text="")
        layout.prop(mod, "show_render", text="")

    def draw_geonodes_modifier_ui_box(
        self, layout: bpy.types.UILayout, mod: bpy.types.NodesModifier
    ) -> bpy.types.UILayout:
        box = layout.box()
        row = box.row(align=True)
        row.prop(mod, "show_expanded", text="", emboss=False)
        row.prop(mod, "name", text="")
        row.prop(mod, "show_in_editmode", text="")
        self.draw_show_viewport_and_render(row, mod)
        row.operator("object.modifier_copy", text="", icon='DUPLICATE').modifier = mod.name
        row.operator("object.modifier_remove", text="", icon='X', emboss=False).modifier = mod.name
        return box


def has_geometry_nodes_modifier_with_node_group(
    obj: bpy.types.Object, node_group_name_prefix: str, exact_match: bool = True
) -> bool:
    return any(
        mod.type == 'NODES'
        and mod.node_group is not None
        and (
            (exact_match and mod.node_group.name == node_group_name_prefix)
            or (not exact_match and mod.node_group.name.startswith(node_group_name_prefix))
        )
        for mod in obj.modifiers
    )


def get_geometry_nodes_modifiers_by_node_group(
    obj: bpy.types.Object, node_group_name_prefix: str, exact_match: bool = True
) -> list[bpy.types.NodesModifier]:
    output: list[bpy.types.NodesModifier] = []
    for mod in obj.modifiers:
        if mod.type == 'NODES' and mod.node_group is not None:
            if (exact_match and mod.node_group.name == node_group_name_prefix) or (
                not exact_match and mod.node_group.name.startswith(node_group_name_prefix)
            ):
                output.append(mod)
    return output


def copy_geometry_nodes_modifier_inputs(
    src_mod: bpy.types.NodesModifier, dst_mod: bpy.types.NodesModifier
) -> bool:
    assert src_mod.node_group is not None
    assert dst_mod.node_group is not None
    src_input_map = node_utils_bpy.get_node_tree_inputs_map(src_mod.node_group)
    dst_input_map = node_utils_bpy.get_node_tree_inputs_map(dst_mod.node_group)
    if len(src_input_map) != len(dst_input_map):
        logger.error(
            f"Different count of modifier inputs {len(src_input_map)} != {len(dst_input_map)}, cannot copy."
        )
        return False

    any_input_incorrect = False
    for src_identifier, src_input in src_input_map.items():
        dst_input = dst_input_map.get(src_identifier)
        if dst_input is None:
            any_input_incorrect = True
            break

        # TODO: Check the type of the input whether it matches. Should we also check the name?
        if node_utils_bpy.get_socket_type(src_input) != node_utils_bpy.get_socket_type(dst_input):
            logger.info(f"Input types don't match: {src_input} != {dst_input}")
            any_input_incorrect = True
            break

    if any_input_incorrect:
        logger.error("Modifier inputs don't match, cannot copy.")
        return False

    # If all inputs match, we can copy the values
    # If we don't materialize the .keys(), blender complaints about the dict changing size during iteration
    for input_ in get_mod_input_keys(src_mod):
        if not has_mod_input_value_attr(src_mod, input_):
            continue
        # setting these utility attributes causes issues with, e.g., the attribute subtype
        # it should be safe to assume they are set correctly in the destination modifier
        if input_.endswith("_use_attribute") or input_.endswith("_attribute_name"):
            continue

        set_mod_input_value(dst_mod, input_, get_mod_input_value(src_mod, input_))

    return True
