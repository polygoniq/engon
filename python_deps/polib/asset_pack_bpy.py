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


if "linalg_bpy" not in locals():
    from . import linalg_bpy
    from . import utils_bpy
    from . import rigs_shared_bpy
else:
    import importlib

    linalg_bpy = importlib.reload(linalg_bpy)
    utils_bpy = importlib.reload(utils_bpy)
    rigs_shared_bpy = importlib.reload(rigs_shared_bpy)


CustomAttributeValueType = typing.Union[
    str,
    int,
    float,
    typing.Tuple[int, ...],
    typing.Tuple[float, ...],
    typing.List[int],
    typing.List[float],
]


# Maps asset pack names to blender Collection color_tags
ASSET_PACK_COLLECTION_COLOR_MAP = {
    "botaniq": 'COLOR_04',  # green
    "traffiq": 'COLOR_02',  # orange
    "aquatiq": 'COLOR_05',  # blue
}


PARTICLE_SYSTEM_TOKEN = "pps"
PREVIEW_NOT_FOUND = "No-Asset-Found"


BOTANIQ_SEASONS = {"spring", "summer", "autumn", "winter"}


# order matters, assets often have multiple seasons, color is set according to the first
# matched season
BOTANIQ_SEASONS_WITH_COLOR_CHANNEL = (
    ("summer", 1.0),
    ("spring", 0.75),
    ("winter", 0.5),
    ("autumn", 0.25),
)

BOTANIQ_ANIMATED_CATEGORIES = {
    "coniferous",
    "deciduous",
    "shrubs",
    "flowers",
    "grass",
    "ivy",
    "plants",
    "sapling",
    "tropical",
    "vine",
    "weed",
}


class CustomPropertyNames:
    # traffiq specific custom property names
    TQ_DIRT = "tq_dirt"
    TQ_SCRATCHES = "tq_scratches"
    TQ_BUMPS = "tq_bumps"
    TQ_PRIMARY_COLOR = "tq_primary_color"
    TQ_FLAKES_AMOUNT = "tq_flakes_amount"
    TQ_CLEARCOAT = "tq_clearcoat"
    TQ_LIGHTS = "tq_main_lights"
    # botaniq specific custom property names
    BQ_BRIGHTNESS = "bq_brightness"
    BQ_RANDOM_PER_BRANCH = "bq_random_per_branch"
    BQ_RANDOM_PER_LEAF = "bq_random_per_leaf"
    BQ_SEASON_OFFSET = "bq_season_offset"


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
    obj: bpy.types.Object,
    addon_name_filter: typing.Optional[typing.Callable[[str], bool]] = None,
    include_editable: bool = True,
    include_linked: bool = True,
) -> bool:
    if include_editable and obj.instance_type == 'NONE' and obj.get("polygoniq_addon", None):
        # only non-'EMPTY' objects can be considered editable
        return addon_name_filter is None or addon_name_filter(obj.get("polygoniq_addon", None))

    elif include_linked and obj.instance_collection is not None:
        # the object is linked and the custom properties are in the linked collection
        # in most cases there will be exactly one linked object but we want to play it
        # safe and will check all of them. if any linked object is a polygoniq object
        # we assume the whole instance collection is
        for linked_obj in obj.instance_collection.objects:
            if is_polygoniq_object(linked_obj, addon_name_filter):
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

    if obj.instance_type == 'COLLECTION':
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


def is_pps(name: str) -> bool:
    split = name.split("_")
    if len(split) < 3:
        return False

    return split[1] == PARTICLE_SYSTEM_TOKEN


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
            if modifier.type != 'PARTICLE_SYSTEM' or is_pps(modifier.name):
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

    InstancedObjectInfo = typing.Tuple[
        bpy.types.Object, bpy.types.Collection, str, typing.Tuple[float, float, float, float]
    ]

    def find_instanced_collection_objects(
        obj: bpy.types.Object, instanced_collection_objects: typing.Dict[str, InstancedObjectInfo]
    ):
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
    ):
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
        make_datablocks_unique_per_object(obj, get_material_to_slots_map, "material")
        # Create copy of armature data shared with other objects or linked from library
        make_datablocks_unique_per_object(obj, get_armatures_to_objects_map, "data")

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
        coll_color = ASSET_PACK_COLLECTION_COLOR_MAP.get(name, None)
        if coll_color is not None:
            coll.color_tag = coll_color
        elif (
            parent is not None
        ):  # color direct descendants by their parent color - e.g. botaniq/weed
            parent_name = utils_bpy.remove_object_duplicate_suffix(parent.name)
            parent_color = ASSET_PACK_COLLECTION_COLOR_MAP.get(parent_name, None)
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


def update_custom_prop(
    context: bpy.types.Context,
    objs: typing.Iterable[bpy.types.Object],
    prop_name: str,
    value: CustomAttributeValueType,
    update_tag_refresh: typing.Set[str] = {'OBJECT'},
) -> None:
    """Update custom properties of given objects and force 3D view to redraw

    When we set values of custom properties from code, affected objects don't get updated in 3D View
    automatically. We need to call obj.update_tag() and then refresh 3D view areas manually.

    'update_tag_refresh' set of enums {'OBJECT', 'DATA', 'TIME'}, updating DATA is really slow
    as it forces Blender to recompute the whole mesh, we should use 'OBJECT' wherever it's enough.
    """
    for obj in objs:
        if prop_name in obj:
            obj[prop_name] = value
            obj.update_tag(refresh=update_tag_refresh)

    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()
