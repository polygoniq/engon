#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import bpy.utils.previews
import typing
import collections
import enum
import logging

try:
    import hatchery
except ImportError:
    from blender_addons import hatchery
logger = logging.getLogger(f"polygoniq.{__name__}")


from . import asset_pack
from . import utils_bpy
from . import rigs_shared_bpy
from . import custom_props_bpy
from . import node_utils_bpy


def get_all_object_ancestors(obj: bpy.types.Object) -> typing.Iterable[bpy.types.Object]:
    """Returns given object's parent, the parent's parent, ..."""

    current = obj.parent
    while current is not None:
        yield current
        current = current.parent


def filter_out_descendants_from_objects(
    objects: typing.Iterable[bpy.types.Object],
) -> typing.Set[bpy.types.Object]:
    """Given a list of objects (i.e. selected objects) this function will return only the
    roots. By roots we mean included objects that have no ancestor that is also contained
    in object.

    Example of use of this is when figuring out which objects to snap to ground. If you have
    a complicated selection of cars, their wheels, etc... you onlt want to snap the parent car
    body, not all objects.
    """

    all_objects = set(objects)

    ret = set()
    for obj in objects:
        ancestors = get_all_object_ancestors(obj)
        if len(all_objects.intersection(ancestors)) == 0:
            # this object has no ancestors that are also contained in objects
            ret.add(obj)

    return ret


def is_polygoniq_object(
    obj: bpy.types.ID,
    addon_name_filter: typing.Optional[typing.Callable[[str], bool]] = None,
    include_editable: bool = True,
    include_linked: bool = True,
) -> bool:
    return custom_props_bpy.has_property(
        obj,
        "polygoniq_addon",
        addon_name_filter,
        include_editable=include_editable,
        include_linked=include_linked,
    )


def has_engon_property_feature(
    obj: bpy.types.ID, feature: str, include_editable: bool = True, include_linked: bool = True
) -> bool:
    if not is_polygoniq_object(obj):
        return False

    # check if obj has at least one of the given properties of the property features
    feature_properties = custom_props_bpy.PROPERTY_FEATURE_PROPERTIES_MAP.get(feature, [])

    for feature_property in feature_properties:
        if custom_props_bpy.has_property(
            obj,
            feature_property,
            include_editable=include_editable,
            include_linked=include_linked,
        ):
            return True
    return False


def find_polygoniq_root_objects(
    objects: typing.Iterable[bpy.types.Object], addon_name: typing.Optional[str] = None
) -> typing.Set[bpy.types.Object]:
    """Finds and returns polygoniq root objects in 'objects'.

    Returned objects are either root or their parent isn't polygoniq object.
    E. g. for 'objects' selected from hierarchy:
    Users_Empty -> Audi_R8 -> [Lights, Wheel1..N -> [Brakes]], this returns Audi_R8.
    """

    traversed_objects = set()
    root_objects = set()
    addon_name_filter = None if addon_name is None else lambda x: x == addon_name

    for obj in objects:
        if obj in traversed_objects:
            continue

        current_obj = obj
        while True:
            if current_obj in traversed_objects:
                break

            if current_obj.parent is None:
                if is_polygoniq_object(current_obj, addon_name_filter):
                    root_objects.add(current_obj)
                break

            if is_polygoniq_object(current_obj, addon_name_filter) and not is_polygoniq_object(
                current_obj.parent, addon_name_filter
            ):
                root_objects.add(current_obj)
                break

            traversed_objects.add(current_obj)
            current_obj = current_obj.parent

    return root_objects


def get_polygoniq_objects(
    objects: typing.Iterable[bpy.types.Object],
    addon_name: typing.Optional[str] = None,
    include_editable: bool = True,
    include_linked: bool = True,
) -> typing.Iterable[bpy.types.Object]:
    """Filters given objects and returns only those that contain the polygoniq_addon property"""
    addon_name_filter = None if addon_name is None else lambda x: x == addon_name
    for obj in objects:
        if is_polygoniq_object(obj, addon_name_filter, include_editable, include_linked):
            yield obj


class TraffiqAssetPart(enum.Enum):
    Body = 'Body'
    Lights = 'Lights'
    Wheel = 'Wheel'
    Brake = 'Brake'


def is_traffiq_asset_part(obj: bpy.types.Object, part: TraffiqAssetPart) -> bool:
    addon_name = obj.get("polygoniq_addon", "")
    if addon_name != "traffiq":
        return False

    obj_name = utils_bpy.remove_object_duplicate_suffix(obj.name)
    if part in {TraffiqAssetPart.Body, TraffiqAssetPart.Lights}:
        splitted_name = obj_name.rsplit("_", 1)
        if len(splitted_name) != 2:
            return False

        _, obj_part_name = splitted_name
        if obj_part_name != part.name:
            return False
        return True

    elif part in {TraffiqAssetPart.Wheel, TraffiqAssetPart.Brake}:
        splitted_name = obj_name.rsplit("_", 3)
        if len(splitted_name) != 4:
            return False

        _, obj_part_name, position, wheel_number = splitted_name
        if obj_part_name != part.name:
            return False
        if position not in {"FL", "FR", "BL", "BR", "F", "B"}:
            return False
        if not wheel_number.isdigit():
            return False
        return True

    return False


DecomposedCarType = typing.Tuple[
    bpy.types.Object,
    bpy.types.Object,
    bpy.types.Object,
    typing.List[bpy.types.Object],
    typing.List[bpy.types.Object],
]


def get_root_object_of_asset(asset: bpy.types.Object) -> typing.Optional[bpy.types.Object]:
    """Returns the root linked object if given a linked asset (instanced collection empty).
    Returns the object itself if given an editable asset. In case there are multiple roots
    or no roots at all it returns None and logs a warning.
    """

    if asset.instance_type == 'COLLECTION':
        # we have to iterate through objects in the collection and return the one
        # that has no parent.

        root_obj = None
        for obj in asset.instance_collection.objects:
            if obj.parent is None:
                if root_obj is not None:
                    logger.warning(
                        f"Found multiple root objects in the given collection instance "
                        f"empty (name='{asset.name}')"
                    )
                    return None

                root_obj = obj

        if root_obj is None:
            logger.warning(
                f"Failed to find the root object of a given collection instance empty "
                f"(name='{asset.name}')"
            )

        return root_obj

    else:
        # given object is editable
        return asset


def get_entire_object_hierarchy(obj: bpy.types.Object) -> typing.Iterable[bpy.types.Object]:
    """List entire hierarchy of an instanced or editable object

    Returns object hierarchy (the object itself and all descendants) in case the object is
    editable. In case the object is instanced it looks through the instance_collection.objects
    and returns all descendants from there.

    Example: If you pass a traffiq car object it will return body, wheels and lights.
    """

    for child in obj.children:
        yield from get_entire_object_hierarchy(child)

    if obj.instance_type == 'COLLECTION' and obj.instance_collection is not None:
        yield from obj.instance_collection.objects
    else:
        yield obj


def decompose_traffiq_vehicle(obj: bpy.types.Object) -> DecomposedCarType:
    if obj is None:
        return None, None, None, [], []

    root_object = get_root_object_of_asset(obj)
    body = None
    lights = None
    wheels = []
    brakes = []

    hierarchy_objects = get_entire_object_hierarchy(obj)
    for hierarchy_obj in hierarchy_objects:
        if is_traffiq_asset_part(hierarchy_obj, TraffiqAssetPart.Body):
            # there should be only one body
            assert body is None
            body = hierarchy_obj
        elif is_traffiq_asset_part(hierarchy_obj, TraffiqAssetPart.Lights):
            # there should be only one lights
            assert lights is None
            lights = hierarchy_obj
        elif is_traffiq_asset_part(hierarchy_obj, TraffiqAssetPart.Wheel):
            wheels.append(hierarchy_obj)
        elif is_traffiq_asset_part(hierarchy_obj, TraffiqAssetPart.Brake):
            brakes.append(hierarchy_obj)

    return root_object, body, lights, wheels, brakes


def find_traffiq_asset_parts(
    obj: bpy.types.Object, part: TraffiqAssetPart
) -> typing.Iterable[bpy.types.Object]:
    """Find all asset parts of a specific type."""

    for hierarchy_obj in get_entire_object_hierarchy(obj):
        if is_traffiq_asset_part(hierarchy_obj, part):
            yield hierarchy_obj


InstancedObjectInfo = typing.Tuple[
    bpy.types.Object, bpy.types.Collection, str, typing.Tuple[float, float, float, float]
]


def find_instanced_collection_objects(
    obj: bpy.types.Object, instanced_collection_objects: typing.Dict[str, InstancedObjectInfo]
) -> None:
    for child in obj.children:
        find_instanced_collection_objects(child, instanced_collection_objects)

    if obj.instance_type == 'COLLECTION':
        if obj.name not in instanced_collection_objects:
            instanced_collection_objects[obj.name] = (
                obj,
                obj.instance_collection,
                obj.parent.name if obj.parent else None,
                obj.color,
            )


def make_selection_editable(
    context: bpy.types.Context,
    delete_base_empty: bool,
    keep_selection: bool = True,
    keep_active: bool = True,
) -> typing.List[str]:
    def apply_botaniq_particle_system_modifiers(obj: bpy.types.Object):
        for child in obj.children:
            apply_botaniq_particle_system_modifiers(child)

        for modifier in obj.modifiers:
            if modifier.type != 'PARTICLE_SYSTEM' or asset_pack.is_pps_name(modifier.name):
                continue

            clear_selection(context)
            obj.select_set(True)
            bpy.ops.object.duplicates_make_real(use_base_parent=True, use_hierarchy=True)
            obj.select_set(False)

            # Remove collection with unused origin objects previously used for particle system
            if modifier.name in bpy.data.collections:
                collection = bpy.data.collections[modifier.name]
                particle_origins = [obj for obj in collection.objects if obj.users == 1]
                bpy.data.batch_remove(particle_origins)
                if len(collection.objects) == 0:
                    bpy.data.collections.remove(collection)

            obj.modifiers.remove(modifier)

    OBJECT_CHILDREN_EMPTY_SIZE = 0.1  # size not too distracting for small objects but still visible

    def set_object_empties_size(obj: bpy.types.Object, size: float) -> None:
        for child in obj.children:
            set_object_empties_size(child, OBJECT_CHILDREN_EMPTY_SIZE)
        if obj.type == 'EMPTY':
            obj.empty_display_size = size

    def copy_polygoniq_custom_props_from_children(obj: bpy.types.Object) -> None:
        """Tries to copy Polygoniq custom properties from children to 'obj'.

        Tries to find child with all polygoniq custom properties
        if such a child exists, values of its properties are copied to 'obj'.
        """
        for child in obj.children:
            copyright = child.get("copyright", None)
            polygoniq_addon = child.get("polygoniq_addon", None)
            polygoniq_blend_path = child.get("polygoniq_addon_blend_path", None)
            if all(prop is not None for prop in [copyright, polygoniq_addon, polygoniq_blend_path]):
                obj["copyright"] = copyright
                obj["polygoniq_addon"] = polygoniq_addon
                obj["polygoniq_addon_blend_path"] = polygoniq_blend_path
                mapr_id = child.get("mapr_asset_id", None)
                mapr_data_id = child.get("mapr_asset_data_id", None)
                if mapr_id is not None:
                    obj["mapr_asset_id"] = mapr_id
                if mapr_data_id is not None:
                    obj["mapr_asset_data_id"] = mapr_data_id
                return

    def get_mesh_to_objects_map(
        obj: bpy.types.Object, result: typing.DefaultDict[str, typing.List[bpy.types.ID]]
    ) -> None:
        for child in obj.children:
            get_mesh_to_objects_map(child, result)

        if obj.type == 'MESH' and obj.data is not None:
            original_mesh_name = utils_bpy.remove_object_duplicate_suffix(obj.data.name)
            result[original_mesh_name].append(obj)

    def get_material_to_slots_map(
        obj: bpy.types.Object, result: typing.DefaultDict[str, typing.List[bpy.types.ID]]
    ) -> None:
        for child in obj.children:
            get_material_to_slots_map(child, result)

        if obj.type == 'MESH':
            for material_slot in obj.material_slots:
                if material_slot.material is None:
                    continue

                original_material_name = utils_bpy.remove_object_duplicate_suffix(
                    material_slot.material.name
                )
                result[original_material_name].append(material_slot)

    def get_armatures_to_objects_map(
        obj: bpy.types.Object, result: typing.DefaultDict[str, typing.List[bpy.types.ID]]
    ) -> None:
        for child in obj.children:
            get_armatures_to_objects_map(child, result)

        if obj.type == 'ARMATURE' and obj.data is not None:
            original_armature_name = utils_bpy.remove_object_duplicate_suffix(obj.data.name)
            result[original_armature_name].append(obj)

    GetNameToUsersMapCallable = typing.Callable[
        [bpy.types.Object, typing.DefaultDict[str, typing.List[bpy.types.ID]]], None
    ]

    def make_datablocks_unique_per_object(
        obj: bpy.types.Object,
        get_data_to_struct_map: GetNameToUsersMapCallable,
        datablock_name: str,
    ) -> typing.Dict[bpy.types.ID, bpy.types.ID]:
        old_new_datablock_map = {}
        datablocks_to_owner_structs: typing.DefaultDict[str, typing.List[bpy.types.ID]] = (
            collections.defaultdict(list)
        )
        get_data_to_struct_map(obj, datablocks_to_owner_structs)

        for owner_structs in datablocks_to_owner_structs.values():
            if len(owner_structs) == 0:
                continue

            first_datablock = getattr(owner_structs[0], datablock_name)
            if first_datablock.library is None and first_datablock.users == len(owner_structs):
                continue

            # data block is linked from library or it is used outside of object 'obj' -> create copy
            datablock_duplicate = first_datablock.copy()
            for owner_struct in owner_structs:
                setattr(owner_struct, datablock_name, datablock_duplicate)
                old_new_datablock_map[first_datablock] = datablock_duplicate
        return old_new_datablock_map

    def try_make_auto_smooth_modifier_local(obj: bpy.types.Object) -> None:
        """Make 'Auto Smooth' geometry nodes modifier local for objects in 'obj' hierarchy."""
        # Blender 4.1.0 changed how auto smooth works, there is a Auto Smooth modifier that replaced
        # auto smooth behavior from object data. We need to make the node group local to the object
        # otherwise it is auto version linked from the source .blend. However the source .blend is
        # never saved thus upon reloading of the scene (saving and opening again), the node group
        # is lost, as it is not available in the source.
        for child in obj.children:
            try_make_auto_smooth_modifier_local(child)

        if bpy.app.version < (4, 1, 0) or obj.type != 'MESH':
            return

        auto_smooth_mod = obj.modifiers.get("Auto Smooth", None)
        if auto_smooth_mod is None:
            return

        if auto_smooth_mod.node_group is not None:
            auto_smooth_mod.node_group.make_local()

    def update_geometry_node_materials(
        obj: bpy.types.Object, old_new_material_map: typing.Dict[bpy.types.ID, bpy.types.ID]
    ):
        """If geometry nodes reference material, use local version instead of linked.

        Linked material is still referenced after asset is converted to local. If we use material
        selection node it will not return the assigned geometry as it is different material.
        """

        for child in obj.children:
            update_geometry_node_materials(child, old_new_material_map)

        for mod in obj.modifiers:
            if not isinstance(mod, bpy.types.NodesModifier):
                continue
            if mod.node_group is None:
                continue

            for input_identifier, input_ in node_utils_bpy.get_node_tree_inputs_map(
                mod.node_group
            ).items():
                if node_utils_bpy.get_socket_type(input_) == 'NodeSocketMaterial':
                    mat = mod[input_.identifier]
                    new_mat = old_new_material_map.get(mat)
                    # We enforce materials referenced in geonodes to be present in object material
                    # slots, but this operator can be used for non-polygoniq assets as well.
                    if new_mat is not None:
                        mod[input_identifier] = new_mat

    selected_objects_names = [obj.name for obj in context.selected_objects]
    prev_active_object_name = context.active_object.name if context.active_object else None

    instanced_collection_objects: typing.Dict[str, InstancedObjectInfo] = {}
    for obj in context.selected_objects:
        find_instanced_collection_objects(obj, instanced_collection_objects)

    for obj_name in selected_objects_names:
        if obj_name in bpy.data.objects:
            apply_botaniq_particle_system_modifiers(bpy.data.objects[obj_name])

    # origin objects from particle systems were removed from scene
    selected_objects_names = [
        obj_name for obj_name in selected_objects_names if obj_name in bpy.data.objects
    ]

    clear_selection(context)
    for instance_object, _, _, _ in instanced_collection_objects.values():
        # Operator duplicates_make_real converts each instance collection to empty (base parent) and its contents,
        # we change the name of the instance collection object (which becomes the empty) so it doesn't clash
        # with the naming of the actual objects (and doesn't increment duplicate suffix).
        # To keep track of what was converted and to not mess up names of objects
        # we use the '[0-9]+bp_' prefix for the base parent
        i = 0
        name = f"{i}bp_" + instance_object.name
        while name in bpy.data.objects:
            i += 1
            name = f"{i}bp_" + instance_object.name

        instance_object.name = name
        instance_object.select_set(True)
        bpy.ops.object.duplicates_make_real(use_base_parent=True, use_hierarchy=True)
        instance_object.select_set(False)

    for obj, instance_collection, parent_name, prev_color in instanced_collection_objects.values():
        assert obj is not None

        for child in obj.children:
            set_object_empties_size(child, obj.empty_display_size)
            child.color = prev_color
            # Create mapr_asset_id and mapr_data_asset_id custom properties on the child if they
            # don't exist already. Otherwise the properties would not get copied because we use
            # only_existing=True with copy_custom_props.
            if child.get("mapr_asset_id", None) is None:
                child["mapr_asset_id"] = ""

            if child.get("mapr_asset_data_id", None) is None:
                child["mapr_asset_data_id"] = ""

            # Copy custom property values from each instanced obj to all children recursively
            # only if the property exists on the target object
            hatchery.utils.copy_custom_props(obj, child, only_existing=True, recursive=True)

        # reorder the hierarchy in following way (car example):
        # base_parent_CAR -> [CAR, base_parent_CAR_Lights, WHEEL1..N -> [CAR_Lights]] to CAR -> [CAR_Lights, WHEEL1..N]
        if parent_name is not None and parent_name in bpy.data.objects:
            parent = bpy.data.objects[parent_name]
            for child in obj.children:
                # after setting parent object here, child.parent_type is always set to 'OBJECT'
                child.parent = parent
                child_source_name = utils_bpy.remove_object_duplicate_suffix(child.name)
                if (
                    child_source_name in instance_collection.objects
                    and instance_collection.objects[child_source_name].parent is not None
                ):
                    # set parent_type from source blend, for example our _Lights need to have parent_type = 'BONE'
                    child.parent_type = instance_collection.objects[child_source_name].parent_type
                    child.matrix_local = instance_collection.objects[child_source_name].matrix_local
            bpy.data.objects.remove(obj)
            continue

        if delete_base_empty:
            if len(obj.children) > 1:
                # instanced collection contained multiple top-level objects, keep base empty as container
                splitted_name = obj.name.split("_", 1)
                if len(splitted_name) == 2 and splitted_name[0].endswith("bp"):
                    obj.name = splitted_name[1]
                # empty parent newly created in duplicates_make_real does not have polygoniq custom properties
                copy_polygoniq_custom_props_from_children(obj)

            else:
                # remove the parent from children which were not reparented above
                # if they were reparented they are no longer in obj.children and we can
                # safely delete the base parent
                for child in obj.children:
                    child_matrix = child.matrix_world.copy()
                    child.parent = None
                    # Original child_matrix took account also for transforms of the parent, apply
                    # the original matrix, otherwise child's pos/rot/scale would change after parent
                    # was removed
                    child.matrix_world = child_matrix
                bpy.data.objects.remove(obj)

    selected_objects = []
    for obj_name in selected_objects_names:
        if obj_name not in bpy.data.objects:
            logger.error(f"Previously selected object: {obj_name} is no longer in bpy.data")
            continue

        obj = bpy.data.objects[obj_name]
        # Create copy of meshes shared with other objects or linked from library
        make_datablocks_unique_per_object(obj, get_mesh_to_objects_map, "data")
        # Create copy of materials shared with other objects or linked from library
        old_new_material_map = make_datablocks_unique_per_object(
            obj, get_material_to_slots_map, "material"
        )
        # Create copy of armature data shared with other objects or linked from library
        make_datablocks_unique_per_object(obj, get_armatures_to_objects_map, "data")
        # Make auto smooth modifier local to the object, so objects don't disappear when the modifier
        # is missing.
        try_make_auto_smooth_modifier_local(obj)
        # When converted to editable geometry node setups still reference linked version of materials
        # in some cases (iq lights) we read the material on the object which is the local version
        update_geometry_node_materials(obj, old_new_material_map)
        # Blender operator duplicates_make_real doesn't append animation data with drivers.
        # Thus we have to create those drivers dynamically based on bone names.
        if rigs_shared_bpy.is_object_rigged(obj):
            # set object as active to be able to go into POSE mode
            context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode='POSE')
            driver_creator = rigs_shared_bpy.RigDrivers(obj)
            driver_creator.create_all_drivers()
            bpy.ops.object.mode_set(mode='OBJECT')

        if keep_selection:
            selected_objects.append(obj_name)
            obj.select_set(True)

    if keep_active and prev_active_object_name is not None:
        if prev_active_object_name in bpy.data.objects:
            context.view_layer.objects.active = bpy.data.objects[prev_active_object_name]

    return selected_objects


HierarchyNameComparator = typing.Callable[
    [bpy.types.Object, typing.Optional[bpy.types.Object]], bool
]


def find_object_in_hierarchy(
    root_obj: bpy.types.Object,
    name_comparator: HierarchyNameComparator,
) -> typing.Optional[bpy.types.Object]:
    # We don't use get_hierarchy function, because here we can return the desired
    # object before going through the whole hierarchy
    def search_hierarchy(parent_obj: bpy.types.Object) -> typing.Optional[bpy.types.Object]:
        if name_comparator(parent_obj, root_obj):
            return parent_obj

        for obj in parent_obj.children:
            candidate = search_hierarchy(obj)
            if candidate is not None:
                return candidate

        return None

    return search_hierarchy(root_obj)


def get_root_objects_with_matched_child(
    objects: typing.Iterable[bpy.types.Object], comparator: HierarchyNameComparator
) -> typing.Iterable[typing.Tuple[bpy.types.Object, bpy.types.Object]]:
    """Searches hierarchies of objects and returns objects that satisfy the 'comparator', and their root objects"""
    for root_obj in find_polygoniq_root_objects(objects):
        searched_obj = find_object_in_hierarchy(root_obj, comparator)
        if searched_obj is not None:
            yield (root_obj, searched_obj)


def get_hierarchy(root: bpy.types.ID) -> typing.List[bpy.types.ID]:
    """Gathers children of 'root' recursively"""

    assert hasattr(root, "children")
    ret = [root]
    for child in root.children:
        ret.extend(get_hierarchy(child))

    return ret


def collection_get(
    context: bpy.types.Context, name: str, parent: typing.Optional[bpy.types.Collection] = None
) -> bpy.types.Collection:
    scene_collections = get_hierarchy(context.scene.collection)
    for coll in scene_collections:
        if utils_bpy.remove_object_duplicate_suffix(coll.name) == name:
            return coll

    coll = bpy.data.collections.new(name)
    if parent is None:
        context.scene.collection.children.link(coll)
    else:
        parent.children.link(coll)

    if hasattr(coll, "color_tag"):  # coloring is only supported if this attribute is present
        coll_color = asset_pack.ASSET_PACK_COLLECTION_COLOR_MAP.get(name, None)
        if coll_color is not None:
            coll.color_tag = coll_color
        elif (
            parent is not None
        ):  # color direct descendants by their parent color - e.g. botaniq/weed
            parent_name = utils_bpy.remove_object_duplicate_suffix(parent.name)
            parent_color = asset_pack.ASSET_PACK_COLLECTION_COLOR_MAP.get(parent_name, None)
            if parent_color is not None:
                coll.color_tag = parent_color
    return coll


def collection_add_object(collection: bpy.types.Collection, obj: bpy.types.Object) -> None:
    """Unlinks 'obj' from all collections and links it into 'collection'"""

    for coll in obj.users_collection:
        coll.objects.unlink(obj)

    collection.objects.link(obj)


def copy_object_hierarchy(root_obj: bpy.types.Object) -> bpy.types.Object:
    """Copies 'root_obj' and its hierarchy while preserving parenting, returns the root copy"""

    def copy_hierarchy(obj: bpy.types.Object, parent: bpy.types.Object) -> None:
        obj_copy = obj.copy()
        obj_copy.parent = parent
        for child in obj.children:
            copy_hierarchy(child, obj_copy)

    root_obj_copy = root_obj.copy()
    for obj in root_obj.children:
        copy_hierarchy(obj, root_obj_copy)

    return root_obj_copy


def collection_link_hierarchy(collection: bpy.types.Collection, root_obj: bpy.types.Object) -> None:
    """Links 'root_obj' and its hierarachy to 'collection' and unlinks it from all other collections"""

    for obj in get_hierarchy(root_obj):
        for coll in obj.users_collection:
            coll.objects.unlink(obj)
        collection.objects.link(obj)


def collection_unlink_hierarchy(
    collection: bpy.types.Collection, root_obj: bpy.types.Object
) -> None:
    """Unlinks 'root_obj' and it's hierarchy from 'collection'"""

    for obj in get_hierarchy(root_obj):
        collection.objects.unlink(obj)


def find_layer_collection(
    view_layer_root: bpy.types.LayerCollection, target: bpy.types.Collection
) -> typing.Optional[bpy.types.LayerCollection]:
    """Finds corresponding LayerCollection from 'view_layer_coll' hierarchy
    which contains 'target' collection.
    """

    if view_layer_root.collection == target:
        return view_layer_root

    for layer_child in view_layer_root.children:
        found_layer_collection = find_layer_collection(layer_child, target)
        if found_layer_collection is not None:
            return found_layer_collection

    return None


def clear_selection(context: bpy.types.Context) -> None:
    for obj in context.selected_objects:
        obj.select_set(False)


def append_modifiers_from_library(
    modifier_container_name: str, library_path: str, target_objs: typing.Iterable[bpy.types.Object]
) -> None:
    """Add all modifiers from object with given name in given .blend library to 'target_objects'.

    It doesn't copy complex and readonly properties, e.g. properties that are driven by FCurve.
    """
    if modifier_container_name not in bpy.data.objects:
        with bpy.data.libraries.load(library_path) as (data_from, data_to):
            assert modifier_container_name in data_from.objects
            data_to.objects = [modifier_container_name]

    assert modifier_container_name in bpy.data.objects
    modifier_container = bpy.data.objects[modifier_container_name]

    for obj in target_objs:
        for src_modifier in modifier_container.modifiers:
            assert src_modifier.name not in obj.modifiers
            dest_modifier = obj.modifiers.new(src_modifier.name, src_modifier.type)

            # collect names of writable properties
            properties = [p.identifier for p in src_modifier.bl_rna.properties if not p.is_readonly]

            # copy those properties
            for prop in properties:
                setattr(dest_modifier, prop, getattr(src_modifier, prop))
