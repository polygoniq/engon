# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import typing
import itertools
import collections
import dataclasses

from . import utils_bpy


def get_node_tree_inputs_map(
    node_tree: bpy.types.NodeTree,
) -> dict[str, bpy.types.NodeTreeInterfaceSocket]:
    """Returns map of {identifier: input} of given 'node_tree'"""
    return {
        item.identifier: item
        for item in node_tree.interface.items_tree
        if item.item_type == 'SOCKET' and item.in_out == 'INPUT'
    }


def get_node_tree_interface_input_items(
    node_tree: bpy.types.NodeTree,
) -> list[bpy.types.NodeTreeInterfaceItem]:
    """Returns list of inputs and panels of given 'node_tree'"""
    return [
        item
        for item in node_tree.interface.items_tree
        if (isinstance(item, bpy.types.NodeTreeInterfaceSocket) and item.in_out == 'INPUT')
        or (isinstance(item, bpy.types.NodeTreeInterfacePanel))
    ]


def get_node_tree_outputs_by_name(
    node_tree: bpy.types.NodeTree, name: str
) -> list[bpy.types.NodeTreeInterfaceSocket]:
    """Returns a list of output sockets of 'name' from the given 'node_tree'"""
    return [
        item
        for item in node_tree.interface.items_tree
        if item.item_type == 'SOCKET' and item.in_out == 'OUTPUT' and item.name == name
    ]


def get_socket_type(
    socket: bpy.types.NodeTreeInterfaceSocket | bpy.types.NodeSocket,
) -> str:
    socket_type = (
        socket.bl_socket_idname
        if isinstance(socket, bpy.types.NodeTreeInterfaceSocket)
        else socket.type
    )
    key = socket_type.upper()
    MAP = {
        'STRING': 'NodeSocketString',
        'BOOLEAN': 'NodeSocketBool',
        'MATERIAL': 'NodeSocketMaterial',
        'VECTOR': 'NodeSocketVector',
        'INT': 'NodeSocketInt',
        'GEOMETRY': 'NodeSocketGeometry',
        'COLLECTION': 'NodeSocketCollection',
        'TEXTURE': 'NodeSocketTexture',
        'VALUE': 'NodeSocketFloat',
        'RGBA': 'NodeSocketColor',
        'OBJECT': 'NodeSocketObject',
        'IMAGE': 'NodeSocketImage',
        'ROTATION': 'NodeSocketRotation',
    }

    new_value = MAP.get(key, None)
    assert new_value is None
    return socket_type


def node_socket_type_to_node_socket_data_type(socket_type: str) -> str:
    """Converts `Node Socket Type` enum items (used by `NodeSocket.type`) to `Node Socket Data Type`
    enum items (used by `NodeCompositorFileOutputItems.new()` in Blender 5.0+).
    """
    if socket_type == 'CUSTOM':
        raise ValueError("Cannot convert 'CUSTOM' socket type to data type")
    if socket_type == 'VALUE':
        return 'FLOAT'
    return socket_type


def find_nodes_in_tree(
    node_tree: bpy.types.NodeTree | None,
    filter_: typing.Callable[[bpy.types.Node], bool] | None = None,
    local_only: bool = False,
) -> set[bpy.types.Node]:
    """Returns a set of nodes from a given node tree that comply with the filter"""
    ret = set()
    if node_tree is None:
        return ret
    for node in node_tree.nodes:
        if getattr(node, "node_tree", None) is not None:
            if node.node_tree.library is None or not local_only:
                ret.update(find_nodes_in_tree(node.node_tree, filter_, local_only))

        if filter_ is not None and not filter_(node):
            continue

        ret.add(node)

    return ret


def get_top_level_material_nodes_with_name(
    obj: bpy.types.Object,
    node_names: set[str],
) -> typing.Iterable[bpy.types.Node]:
    """Searches for top level nodes or node groups = not nodes nested in other node groups.

    Raise exception if 'obj' is instanced collection. If linked object links materials from another
    blend then Blender API doesn't allow us easily access these materials. We would be able only
    to access materials that are local inside blend of linked object. This could be confusing
    behavior of this function, so this function doesn't search for any nodes in linked objects.
    """
    assert obj.instance_collection != 'COLLECTION'

    for material_slot in obj.material_slots:
        if material_slot.material is None:
            continue
        if material_slot.material.node_tree is None:
            continue  # material is not using nodes or the node_tree is invalid
        for node in material_slot.material.node_tree.nodes:
            if node.type == 'GROUP':
                if utils_bpy.remove_object_duplicate_suffix(node.node_tree.name) in node_names:
                    yield node
            else:
                if utils_bpy.remove_object_duplicate_suffix(node.name) in node_names:
                    yield node


def find_nodes_by_bl_idname(
    nodes: typing.Iterable[bpy.types.Node], bl_idname: str, recursive: bool = False
) -> typing.Iterable[bpy.types.Node]:
    for node in nodes:
        if node.bl_idname == bl_idname:
            yield node
        if recursive and node.node_tree is not None:
            yield from find_nodes_by_bl_idname(node.node_tree.nodes, bl_idname)


def find_nodes_by_name(
    node_tree: bpy.types.NodeTree, name_prefix: str, exact_match: bool = True
) -> set[bpy.types.Node]:
    """Returns set of nodes from 'node_tree' which name without duplicate suffix is 'name'"""
    nodes = find_nodes_in_tree(
        node_tree,
        lambda x: (exact_match and utils_bpy.remove_object_duplicate_suffix(x.name) == name_prefix)
        or (
            not exact_match
            and utils_bpy.remove_object_duplicate_suffix(x.name).startswith(name_prefix)
        ),
    )
    return nodes


def find_nodegroups_by_name(
    node_tree: bpy.types.NodeTree | None,
    name_prefix: str,
    use_node_tree_name: bool = True,
    exact_match: bool = True,
) -> set[bpy.types.NodeGroup]:
    """Returns set of node groups from 'node_tree' which name without duplicate suffix is 'name'

    Nodegroups have node.label, node.name and node.node_tree.name, if node.label is empty,
    Blender UI, displays node_tree.name in nodegroup header. That's why node.name is often not
    renamed to anything reasonable. So most of the times we want to search nodegroups by
    node_tree.name. If use_node_tree_name is True and the nodegroup has no node_tree, it is skipped.
    """

    def nodegroup_filter(node: bpy.types.Node) -> bool:
        if node.type != 'GROUP':
            return False
        if use_node_tree_name and node.node_tree is None:
            return False

        name_for_comparing = utils_bpy.remove_object_duplicate_suffix(
            node.node_tree.name if use_node_tree_name else node.name
        )
        return (exact_match and name_for_comparing == name_prefix) or (
            not exact_match and name_for_comparing.startswith(name_prefix)
        )

    nodes = find_nodes_in_tree(node_tree, nodegroup_filter)
    return nodes


def find_incoming_nodes(node: bpy.types.Node) -> set[bpy.types.Node]:
    """Finds and returns all nodes connecting to 'node'"""
    ret: set[bpy.types.Node] = set()
    for input_ in node.inputs:
        for link in input_.links:
            ret.add(link.from_node)

    return ret


def find_link_connected_to(
    links: typing.Iterable[bpy.types.NodeLink],
    to_node: bpy.types.Node,
    to_socket_name: str,
    skip_reroutes: bool = False,
) -> bpy.types.NodeLink | None:
    """Find the link connected to given target node (to_node) to given socket name (to_socket_name)

    There can be at most 1 such link. In Blender it is not allowed to connect more than one link
    to a socket. It is allowed to connect multiple links *from* one socket, but not *to* one socket.
    """

    ret: list[bpy.types.NodeLink] = []
    for link in links:
        if to_node != link.to_node:
            continue
        if to_socket_name != link.to_socket.name:
            continue

        if skip_reroutes and isinstance(link.from_node, bpy.types.NodeReroute):
            return find_link_connected_to(
                links, link.from_node, link.from_node.inputs[0].name, skip_reroutes
            )

        ret.append(link)

    if len(ret) > 1:
        raise RuntimeError(
            "Found multiple nodes connected to given node and socket. This is not valid!"
        )
    elif len(ret) == 0:
        return None
    return ret[0]


def find_links_connected_from(
    links: typing.Iterable[bpy.types.NodeLink],
    from_node: bpy.types.Node,
    from_socket_name: str | None = None,
) -> typing.Iterable[bpy.types.NodeLink]:
    """Find links connected from the given node (from_node) with an option for links only from a given socket name (from_socket_name)

    There can be any number of such links.
    """
    for link in links:
        if from_node != link.from_node:
            continue
        if from_socket_name is not None and from_socket_name != link.from_socket.name:
            continue

        yield link


def is_node_socket_connected_to(
    links: typing.Iterable[bpy.types.NodeLink],
    from_node: bpy.types.Node,
    from_socket_name: str,
    to_nodes: list[bpy.types.Node],
    to_socket_name: str | None,
    recursive: bool = True,
) -> bool:
    for link in find_links_connected_from(links, from_node, from_socket_name):
        if link.to_node in to_nodes and (
            to_socket_name is None or to_socket_name == link.to_socket.name
        ):
            return True
        if not recursive:
            continue
        for recursive_link in find_links_connected_from(links, link.to_node):
            if is_node_socket_connected_to(
                links,
                link.to_node,
                recursive_link.from_socket.name,
                to_nodes,
                to_socket_name,
                True,
            ):
                return True

    return False


def get_node_input_socket(node: bpy.types.Node, socket_name: str) -> bpy.types.NodeSocket | None:
    ret = None
    for input_ in node.inputs:
        if input_.name != socket_name:
            continue
        if ret is not None:
            raise RuntimeError("Multiple matches!")
        ret = input_

    return ret


def get_node_output_socket(node: bpy.types.Node, socket_name: str) -> bpy.types.NodeSocket | None:
    ret = None
    for output in node.outputs:
        if output.name != socket_name:
            continue
        if ret is not None:
            raise RuntimeError("Multiple matches!")
        ret = output

    return ret


def find_nodegroup_users(
    nodegroup_name: str,
) -> typing.Iterable[tuple[bpy.types.Object, typing.Iterable[bpy.types.Object]]]:
    """Returns iterable of (obj, user_objs) that use nodegroup with name 'nodegroup_name'

    In case of instanced object this checks the instanced collection and the nested
    objects in order to find the mesh object that can be potentional user of 'nodegroup_name'.
    In this case this returns the original instanced object and list of non-empty objects that are
    instanced.

    In case of editable objects this returns the object itself and list with the object in it.
    """

    def find_origin_objects(instancer_obj: bpy.types.Object) -> typing.Iterable[bpy.types.Object]:
        if instancer_obj.type != 'EMPTY':
            return [instancer_obj]

        objects = {instancer_obj}
        while len(objects) > 0:
            obj = objects.pop()
            if (
                obj.type == 'EMPTY'
                and obj.instance_type == 'COLLECTION'
                and obj.instance_collection is not None
            ):
                objects.update(obj.instance_collection.all_objects)
            else:
                yield obj

    # Firstly gather all the materials that use the nodegroup with given name
    materials_using_nodegroup = set()
    for material in bpy.data.materials:
        if material.node_tree is None:
            continue

        nodes = find_nodes_in_tree(
            material.node_tree,
            lambda x: isinstance(x, bpy.types.ShaderNodeGroup)
            and x.node_tree is not None
            and x.node_tree.name == nodegroup_name,
        )

        if len(nodes) > 0:
            materials_using_nodegroup.add(material)

    if len(materials_using_nodegroup) == 0:
        return []

    # Go through all objects and yield ones that have one of the found materials
    for obj in bpy.data.objects:
        # We skip objects with library here as they will be gathered by 'find_origin_objects'
        if obj.library is not None:
            continue

        # In case of instanced collection we find the actual instanced objects and gather all
        # used materials.
        if (
            obj.type == 'EMPTY'
            and obj.instance_type == 'COLLECTION'
            and obj.instance_collection is not None
        ):
            instance_materials = set()
            instanced_objs = set(itertools.chain(find_origin_objects(obj)))
            for instanced_obj in instanced_objs:
                instance_materials.update(
                    {
                        slot.material
                        for slot in instanced_obj.material_slots
                        if slot.material is not None
                    }
                )

            if len(instance_materials.intersection(materials_using_nodegroup)) > 0:
                yield obj, instanced_objs

        else:
            if not hasattr(obj, "material_slots"):
                continue

            obj_materials = {
                slot.material for slot in obj.material_slots if slot.material is not None
            }

            if len(obj_materials & materials_using_nodegroup) > 0:
                yield obj, [obj]


def get_channel_nodes_map(
    node_tree: bpy.types.NodeTree,
) -> collections.defaultdict[str, list[bpy.types.ShaderNodeTexImage]]:
    """Returns all image nodes from given nodegroup mapping to filepath"""
    image_nodes = find_nodes_in_tree(
        node_tree, lambda x: isinstance(x, bpy.types.ShaderNodeTexImage)
    )

    channel_nodes_map: collections.defaultdict[str, list[bpy.types.ShaderNodeTexImage]] = (
        collections.defaultdict(list)
    )

    for node in image_nodes:
        name_wo_suffix = utils_bpy.remove_object_duplicate_suffix(node.name)
        split = name_wo_suffix.rsplit("_", 1)
        if len(split) == 2:
            # channel name = {"mq_Diffuse", "mq_Normal", "mq_Height", ...}
            channel_name, _ = split
        else:
            # fallback channel name to display the information about texture node anyways
            channel_name = "unknown"

        channel_nodes_map[channel_name].append(node)

        for list_ in channel_nodes_map.values():
            list_.sort(key=lambda x: x.name)

    return channel_nodes_map


def filter_node_socket_name(
    socket: bpy.types.NodeSocket | bpy.types.NodeTreeInterfaceSocket,
    *names: str,
    case_sensitive: bool = False,
) -> bool:
    socket_name = socket.name if case_sensitive else socket.name.lower()
    names = names if case_sensitive else map(lambda x: x.lower(), names)
    for name in names:
        if name in socket_name:
            return True
    return False


@dataclasses.dataclass
class NodeSocketsDrawTemplate:
    """Template for drawing node sockets from a nodegroup in a material or geonodes modifier.

    The 'filter_' and 'socket_names_drawn_first' are optional and they are mutually exclusive if provided.
    If 'socket_names_drawn_first' is not None, their relative inputs are drawn first if they exist
    and 'filter_' is applied to the rest.
    """

    name_prefix: str
    filter_: typing.Callable[[bpy.types.NodeSocket | bpy.types.NodeTreeInterfaceSocket], bool] = (
        lambda _: True
    )
    socket_names_drawn_first: list[str] | None = None
    exact_match: bool = True

    def draw_from_material(
        self,
        mat: bpy.types.Material,
        layout: bpy.types.UILayout,
        draw_max_first_occurrences: int = 1,
    ) -> None:
        if draw_max_first_occurrences < 1:
            return
        nodegroups = list(
            itertools.chain(
                find_nodes_by_name(mat.node_tree, self.name_prefix, exact_match=self.exact_match),
                find_nodegroups_by_name(
                    mat.node_tree, self.name_prefix, exact_match=self.exact_match
                ),
            )
        )

        if len(nodegroups) == 0:
            layout.label(text=f"No '{self.name_prefix}' nodegroup found", icon='INFO')
            return

        for i, group in enumerate(nodegroups):
            if i >= draw_max_first_occurrences:
                break

            inputs = list(filter(is_drawable_node_input, group.inputs))
            self._draw_template(
                inputs,
                layout,
                lambda input_, layout: layout.row().prop(input_, "default_value", text=input_.name),
            )

    def draw_from_geonodes_modifier(
        self,
        layout: bpy.types.UILayout,
        mod: bpy.types.NodesModifier,
    ) -> None:
        assert mod.type == 'NODES'
        if self.exact_match and mod.node_group.name != self.name_prefix:
            layout.label(text=f"No '{self.name_prefix}' nodegroup found", icon='INFO')
            return
        elif not self.exact_match and not mod.node_group.name.startswith(self.name_prefix):
            layout.label(text=f"No nodegroup starting with '{self.name_prefix}' found", icon='INFO')
            return

        inputs = list(
            filter(
                is_drawable_node_interface_item, get_node_tree_interface_input_items(mod.node_group)
            )
        )
        self._draw_template(
            inputs,
            layout,
            lambda input_, layout: draw_modifier_input_socket(layout, mod, input_),
            lambda panel, layout: draw_modifier_input_panel(layout, mod, panel),
        )

    def _draw_template(
        self,
        inputs: list[bpy.types.NodeTreeInterfaceItem] | list[bpy.types.NodeSocket],
        layout: bpy.types.UILayout,
        draw_socket_function: typing.Callable[
            [bpy.types.NodeTreeInterfaceSocket | bpy.types.NodeSocket, bpy.types.UILayout], None
        ],
        draw_panel_function: (
            typing.Callable[
                [bpy.types.NodeTreeInterfacePanel, bpy.types.UILayout], bpy.types.UILayout
            ]
            | None
        ) = None,
    ) -> None:
        """Draws the template into given layout using provided draw functions.

        In congruence with bpy, nested panels are not supported.
        All inputs after a panel are drawn into the panel, unless new panel is encountered.
        """
        master_layout = layout
        current_layout = master_layout
        already_drawn = set()
        if self.socket_names_drawn_first is not None:
            socket_name_to_input_map = {
                input_.name.lower(): input_  # type: ignore
                for input_ in inputs
                if isinstance(input_, (bpy.types.NodeTreeInterfaceSocket, bpy.types.NodeSocket))
            }
            for name in self.socket_names_drawn_first:
                input_ = socket_name_to_input_map.get(name.lower(), None)
                if input_ is None:
                    continue
                already_drawn.add(input_)
                draw_socket_function(input_, current_layout)

        for input_ in inputs:
            if (
                input_ not in already_drawn
                and isinstance(input_, (bpy.types.NodeTreeInterfaceSocket, bpy.types.NodeSocket))
                and self.filter_(input_)
            ):
                # if panel is closed, layout can be None
                if current_layout is not None:
                    draw_socket_function(input_, current_layout)
            elif isinstance(input_, bpy.types.NodeTreeInterfacePanel):
                assert (
                    draw_panel_function is not None
                ), "draw_panel_function must be provided to draw this modifier panel"
                current_layout = draw_panel_function(input_, master_layout)


def is_drawable_node_input(input_: bpy.types.NodeSocket) -> bool:
    return (
        hasattr(input_, "default_value")
        and input_.enabled
        and not input_.hide_value
        and not input_.is_linked
    )


def is_drawable_node_interface_item(input_: bpy.types.NodeTreeInterfaceItem) -> bool:
    if isinstance(input_, bpy.types.NodeTreeInterfaceSocket):
        return get_socket_type(input_) != 'NodeSocketGeometry' and not input_.hide_value
    if isinstance(input_, bpy.types.NodeTreeInterfacePanel):
        return True
    return False


def draw_node_inputs_filtered(
    layout: bpy.types.UILayout,
    node: bpy.types.Node,
    filter_: typing.Callable[[bpy.types.NodeSocket], bool] = lambda _: True,
) -> None:
    for input_ in node.inputs:
        if not is_drawable_node_input(input_):
            continue

        if filter_(input_):
            layout.row().prop(input_, "default_value", text=input_.name)


def draw_modifier_input_socket(
    layout: bpy.types.UILayout,
    mod: bpy.types.NodesModifier,
    input_: bpy.types.NodeTreeInterfaceSocket,
):
    if get_socket_type(input_) == 'NodeSocketObject':
        layout.row().prop_search(
            mod,
            f"[\"{input_.identifier}\"]",
            bpy.data,
            "objects",
            text=input_.name,
            icon='OBJECT_DATA',
        )
    elif get_socket_type(input_) == 'NodeSocketMaterial':
        layout.row().prop_search(
            mod,
            f"[\"{input_.identifier}\"]",
            bpy.data,
            "materials",
            text=input_.name,
            icon='MATERIAL_DATA',
        )
    elif get_socket_type(input_) == 'NodeSocketCollection':
        layout.row().prop_search(
            mod,
            f"[\"{input_.identifier}\"]",
            bpy.data,
            "collections",
            text=input_.name,
            icon='OUTLINER_COLLECTION',
        )
    else:
        layout.row().prop(mod, f"[\"{input_.identifier}\"]", text=input_.name)


def draw_modifier_input_panel(
    layout: bpy.types.UILayout,
    mod: bpy.types.NodesModifier,
    interface_panel: bpy.types.NodeTreeInterfacePanel,
) -> bpy.types.UILayout:
    header, panel = layout.panel(f"engon.panels.{mod.name}.{interface_panel.name}")
    header.label(text=interface_panel.name)
    return panel


def draw_node_tree(
    layout: bpy.types.UILayout,
    node_tree: bpy.types.NodeTree,
    depth_limit: int = 5,
) -> None:
    def draw_node_and_recurse(
        layout: bpy.types.UILayout,
        node: bpy.types.Node,
        parent_node: bpy.types.Node | None,
        depth: int,
    ) -> None:
        if depth == depth_limit:
            return

        box = layout.box()
        row = box.row()
        row.prop(
            node, "hide", text="", emboss=False, icon='TRIA_RIGHT' if node.hide else 'TRIA_DOWN'
        )
        row.label(text=node.name)
        if parent_node is not None:
            right = row.row()
            right.enabled = False
            right.label(text=f"(from {parent_node.name} node)")

        if not node.hide:
            col = box.column(align=True)
            node.draw_buttons(bpy.context, col)
            draw_node_inputs_filtered(col, node)
        for incoming_node in find_incoming_nodes(node):
            draw_node_and_recurse(layout, incoming_node, node, depth + 1)

    material_output_nodes = find_nodes_in_tree(
        node_tree, lambda x: isinstance(x, bpy.types.ShaderNodeOutputMaterial)
    )

    if len(material_output_nodes) != 1:
        return

    draw_node_and_recurse(layout, material_output_nodes.pop(), None, 0)


def get_node_input_value_from_datablock(
    datablock: bpy.types.ID,
    node_name: str,
    input_name: str,
) -> typing.Any:
    """Returns value of input with 'input_name' from node with 'node_name' in the node tree of 'datablock'"""
    assert hasattr(datablock, "node_tree")
    nodes = find_nodes_by_name(datablock.node_tree, node_name)

    if len(nodes) == 0:
        raise ValueError(f"Node '{node_name}' not found in node tree of '{datablock}'")

    for node in nodes:
        input_socket = get_node_input_socket(node, input_name)
        if input_socket is not None:
            return input_socket.default_value

    raise ValueError(f"Input '{input_name}' not found in node '{node_name}'")


def get_nodegroup_input_value_from_datablock(
    datablock: bpy.types.ID,
    nodegroup_name: str,
    input_name: str,
) -> typing.Any:
    """Returns value of input with 'input_name' from nodegroup with 'nodegroup_name' in the node tree of 'datablock'"""
    assert hasattr(datablock, "node_tree")
    nodegroups = find_nodegroups_by_name(datablock.node_tree, nodegroup_name)

    if len(nodegroups) == 0:
        raise ValueError(f"Nodegroup '{nodegroup_name}' not found in node tree of '{datablock}'")

    for nodegroup in nodegroups:
        input_socket = get_node_input_socket(nodegroup, input_name)
        if input_socket is not None:
            return input_socket.default_value

    raise ValueError(f"Input '{input_name}' not found in nodegroup '{nodegroup_name}'")


def get_node_prop_value_from_datablock(
    datablock: bpy.types.ID,
    node_name: str,
    prop_name: str,
) -> typing.Any:
    """Returns value of a property with 'prop_name' from node with 'node_name' in the node tree of 'datablock'"""
    assert hasattr(datablock, "node_tree")
    nodes = find_nodes_by_name(datablock.node_tree, node_name)

    if len(nodes) == 0:
        raise ValueError(f"Node '{node_name}' not found in node tree of '{datablock}'")

    for node in nodes:
        if hasattr(node, prop_name):
            return getattr(node, prop_name)

    raise ValueError(f"Property '{prop_name}' not found in node '{node_name}'")


def update_node_props_of_datablocks(
    datablocks: typing.Iterable[bpy.types.ID],
    node_name: str,
    prop_name: str,
    value: typing.Any,
    multiple_nodes: bool = False,
) -> None:
    """Update custom properties of a node inside node trees of given datablocks"""
    assert all(hasattr(datablock, "node_tree") for datablock in datablocks)
    for datablock in datablocks:
        nodes = find_nodes_by_name(datablock.node_tree, node_name)
        if not multiple_nodes and len(nodes) > 1:
            raise ValueError(f"Multiple nodes with name '{node_name}' found in node tree")
        for node in nodes:
            if hasattr(node, prop_name):
                setattr(node, prop_name, value)


def update_nodegroup_inputs_of_datablocks(
    datablocks: typing.Iterable[bpy.types.ID],
    nodegroup_name: str,
    input_name: str,
    value: typing.Any,
    multiple_nodegroups: bool = False,
) -> None:
    """Update inputs of a nodegroup inside node trees of given datablocks."""
    assert all(hasattr(datablock, "node_tree") for datablock in datablocks)
    for datablock in datablocks:
        nodegroups = find_nodegroups_by_name(datablock.node_tree, nodegroup_name)
        if not multiple_nodegroups and len(list(nodegroups)) > 1:
            raise ValueError(f"Multiple nodegroups with name '{nodegroup_name}' found in node tree")
        for nodegroup in nodegroups:
            get_node_input_socket(nodegroup, input_name).default_value = value
