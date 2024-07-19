# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import typing
import itertools
import collections
import dataclasses

if "utils_bpy" not in locals():
    from . import utils_bpy
else:
    import importlib

    utils_bpy = importlib.reload(utils_bpy)


# Type that's compatible with both old and new node tree interfaces
if bpy.app.version < (4, 0, 0):
    NodeSocketInterfaceCompat = bpy.types.NodeSocketInterfaceStandard
else:
    NodeSocketInterfaceCompat = bpy.types.NodeTreeInterfaceSocket


def get_node_tree_inputs_map(
    node_tree: bpy.types.NodeTree,
) -> typing.Dict[str, NodeSocketInterfaceCompat]:
    """Returns map of {identifier: input} of given 'node_tree' reassuring compatibility pre and post Blender 4.0"""
    assert isinstance(node_tree, bpy.types.NodeTree)
    if bpy.app.version < (4, 0, 0):
        return {input_.identifier: input_ for input_ in node_tree.inputs}
    else:
        return {
            item.identifier: item
            for item in node_tree.interface.items_tree
            if item.in_out == 'INPUT' and item.item_type == 'SOCKET'
        }


def get_socket_type(socket: NodeSocketInterfaceCompat) -> str:
    """Returns the Blender 4.0 version of socket type from a NodeTree.

    Note 1: This accepts either `bpy.types.NodeSocketInterfaceStandard` or
            `bpy.types.NodeTreeInterfaceSocket` based on Blender version, but basically it is what
            the `.inputs` or `.interface.items_tree` gives you.
    Note 2: NodeTree is different from a NodeGroup!
    """

    # Inspired by a post on the 'bpy' discord by a user named 'Reigen'
    if bpy.app.version < (4, 0, 0):
        assert isinstance(socket, bpy.types.NodeSocketInterfaceStandard)
        socket_type = socket.type
    else:
        assert isinstance(
            socket, bpy.types.NodeTreeInterfaceSocket
        ), "Given socket is not a Node Tree interface! Isn't it a node group?"
        socket_type = socket.bl_socket_idname

    # We remap the values to their newer versions, in 4.0 the values changed
    # from 'key' to the 'value' in MAP
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
    if bpy.app.version >= (4, 0, 0):
        assert new_value is None
        return socket_type
    else:
        return new_value


def find_nodes_in_tree(
    node_tree: typing.Optional[bpy.types.NodeTree],
    filter_: typing.Optional[typing.Callable[[bpy.types.Node], bool]] = None,
    local_only: bool = False,
) -> typing.Set[bpy.types.Node]:
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
    node_names: typing.Set[str],
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


def find_nodes_by_name(node_tree: bpy.types.NodeTree, name: str) -> typing.Set[bpy.types.Node]:
    """Returns set of nodes from 'node_tree' which name without duplicate suffix is 'name'"""
    nodes = find_nodes_in_tree(
        node_tree, lambda x: utils_bpy.remove_object_duplicate_suffix(x.name) == name
    )
    return nodes


def find_nodegroups_by_name(
    node_tree: typing.Optional[bpy.types.NodeTree], name: str, use_node_tree_name: bool = True
) -> typing.Set[bpy.types.NodeGroup]:
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

        name_for_comparing = node.node_tree.name if use_node_tree_name else node.name
        return utils_bpy.remove_object_duplicate_suffix(name_for_comparing) == name

    nodes = find_nodes_in_tree(node_tree, nodegroup_filter)
    return nodes


def find_incoming_nodes(node: bpy.types.Node) -> typing.Set[bpy.types.Node]:
    """Finds and returns all nodes connecting to 'node'"""
    ret: typing.Set[bpy.types.Node] = set()
    for input_ in node.inputs:
        for link in input_.links:
            ret.add(link.from_node)

    return ret


def find_link_connected_to(
    links: typing.Iterable[bpy.types.NodeLink],
    to_node: bpy.types.Node,
    to_socket_name: str,
    skip_reroutes: bool = False,
) -> typing.Optional[bpy.types.NodeLink]:
    """Find the link connected to given target node (to_node) to given socket name (to_socket_name)

    There can be at most 1 such link. In Blender it is not allowed to connect more than one link
    to a socket. It is allowed to connect multiple links *from* one socket, but not *to* one socket.
    """

    ret: typing.List[bpy.types.NodeLink] = []
    for link in links:
        if to_node != link.to_node:
            continue
        if to_socket_name != link.to_socket.name:
            continue

        if skip_reroutes and isinstance(link.from_node, bpy.types.NodeReroute):
            return find_link_connected_to(links, link.from_node, link.from_node.inputs[0].name)

        ret.append(link)

    if len(ret) > 1:
        raise RuntimeError(
            "Found multiple nodes connected to given node and socket. This is not valid!"
        )
    elif len(ret) == 0:
        return None
    return ret[0]


def find_links_connected_from(
    links: typing.Iterable[bpy.types.NodeLink], from_node: bpy.types.Node, from_socket_name: str
) -> typing.Iterable[bpy.types.NodeLink]:
    """Find links connected from given node (from_node) from given socket name (from_socket_name)

    There can be any number of such links.
    """
    for link in links:
        if from_node != link.from_node:
            continue
        if from_socket_name != link.from_socket.name:
            continue

        yield link


def is_node_socket_connected_to(
    links: typing.Iterable[bpy.types.NodeLink],
    from_node: bpy.types.Node,
    from_socket_name: str,
    to_nodes: typing.List[bpy.types.Node],
    to_socket_name: typing.Optional[str],
    recursive: bool = True,
) -> bool:
    for link in find_links_connected_from(links, from_node, from_socket_name):
        if link.to_node in to_nodes and (
            to_socket_name is None or to_socket_name == link.to_socket.name
        ):
            return True
        if recursive and is_node_socket_connected_to(
            links, link.to_node, link.to_socket.name, to_nodes, to_socket_name, True
        ):
            return True

    return False


def get_node_input_socket(
    node: bpy.types.Node, socket_name: str
) -> typing.Optional[bpy.types.NodeSocket]:
    ret = None
    for input_ in node.inputs:
        if input_.name != socket_name:
            continue
        if ret is not None:
            raise RuntimeError("Multiple matches!")
        ret = input_

    return ret


def get_node_output_socket(
    node: bpy.types.Node, socket_name: str
) -> typing.Optional[bpy.types.NodeSocket]:
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
) -> typing.Iterable[typing.Tuple[bpy.types.Object, typing.Iterable[bpy.types.Object]]]:
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
) -> typing.DefaultDict[str, typing.List[bpy.types.ShaderNodeTexImage]]:
    """Returns all image nodes from given nodegroup mapping to filepath"""
    image_nodes = find_nodes_in_tree(
        node_tree, lambda x: isinstance(x, bpy.types.ShaderNodeTexImage)
    )

    channel_nodes_map: typing.DefaultDict[str, typing.List[bpy.types.ShaderNodeTexImage]] = (
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
    socket: bpy.types.NodeSocket | NodeSocketInterfaceCompat,
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

    name: str
    filter_: typing.Callable[[bpy.types.NodeSocket | NodeSocketInterfaceCompat], bool] = (
        lambda _: True
    )
    socket_names_drawn_first: typing.Optional[typing.List[str]] = None

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
                find_nodes_by_name(mat.node_tree, self.name),
                find_nodegroups_by_name(mat.node_tree, self.name),
            )
        )

        if len(nodegroups) == 0:
            layout.label(text=f"No '{self.name}' nodegroup found", icon='INFO')
            return

        for i, group in enumerate(nodegroups):
            if i >= draw_max_first_occurrences:
                break

            inputs = list(filter(is_drawable_node_input, group.inputs))
            self._draw_template(
                inputs, lambda input_: layout.row().prop(input_, "default_value", text=input_.name)
            )

    def draw_from_geonodes_modifier(
        self,
        layout: bpy.types.UILayout,
        mod: bpy.types.NodesModifier,
    ) -> None:
        assert mod.type == 'NODES'
        if mod.node_group is None or mod.node_group.name != self.name:
            layout.label(text=f"No '{self.name}' nodegroup found", icon='INFO')
            return

        inputs = list(
            filter(is_drawable_node_tree_input, get_node_tree_inputs_map(mod.node_group).values())
        )
        self._draw_template(inputs, lambda input_: draw_modifier_input(layout, mod, input_))

    def _draw_template(
        self,
        inputs: typing.List[NodeSocketInterfaceCompat] | typing.List[bpy.types.NodeSocket],
        draw_function: typing.Callable[[NodeSocketInterfaceCompat | bpy.types.NodeSocket], None],
    ) -> None:
        already_drawn = set()
        if self.socket_names_drawn_first is not None:
            socket_name_to_input_map = {input_.name.lower(): input_ for input_ in inputs}
            for name in self.socket_names_drawn_first:
                input_ = socket_name_to_input_map.get(name.lower(), None)
                if input_ is None:
                    continue
                already_drawn.add(input_)
                draw_function(input_)

        for input_ in inputs:
            if input_ not in already_drawn and self.filter_(input_):
                draw_function(input_)


def is_drawable_node_input(input_: bpy.types.NodeSocket) -> bool:
    return (
        hasattr(input_, "default_value")
        and input_.enabled
        and not input_.hide_value
        and not input_.is_linked
    )


def is_drawable_node_tree_input(input_: NodeSocketInterfaceCompat) -> bool:
    return get_socket_type(input_) != 'NodeSocketGeometry' and not input_.hide_value


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


def draw_modifier_input(
    layout: bpy.types.UILayout, mod: bpy.types.NodesModifier, input_: NodeSocketInterfaceCompat
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


def draw_node_tree(
    layout: bpy.types.UILayout,
    node_tree: bpy.types.NodeTree,
    depth_limit: int = 5,
) -> None:
    def draw_node_and_recurse(
        layout: bpy.types.UILayout,
        node: bpy.types.Node,
        parent_node: typing.Optional[bpy.types.Node],
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
