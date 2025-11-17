# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import typing
import collections
import dataclasses

# Keymap defines a set of keys that are active over a certain space and region in Blender
# For example items of KeymapDefinition("View 3D", "VIEW_3D", "WINDOW") will react to all events
# in the 3D view. For global events a KeymapDefinition("Window", "EMPTY", "WINDOW") can be used.
# The first entry is the name of the keymap in Preferences / Keymap.
KeymapDefinition = collections.namedtuple("KeymapDefinition", ["name", "space_type", "region_type"])


# The name should match the label of the operator with the bl_idname
@dataclasses.dataclass
class KeymapItemDefinition:
    name: str
    bl_idname: str
    key: str
    action: str = 'PRESS'
    ctrl: bool = False
    shift: bool = False
    alt: bool = False
    properties: typing.Dict[str, typing.Any] = dataclasses.field(default_factory=dict)


# Dictionary defining the keymaps to be registered
KeymapDefinitions = typing.Dict[KeymapDefinition, typing.List[KeymapItemDefinition]]
# List of tuples to track registered keymaps and items for un-registration in each addon
AddonKeymaps = typing.List[typing.Tuple[bpy.types.KeyMap, bpy.types.KeyMapItem]]


def draw_settings_ui(
    context: bpy.types.Context, keymap_definitions: KeymapDefinitions, layout: bpy.types.UILayout
) -> None:
    col = layout.column(align=True)

    # keyconfigs.user can be none in background mode
    if context.window_manager.keyconfigs.user is None:
        return

    missing_items = False
    for km_def, km_items_def in keymap_definitions.items():
        km = context.window_manager.keyconfigs.user.keymaps[km_def.name]
        km_items = km.keymap_items
        for km_item_def in km_items_def:
            km_item: bpy.types.KeyMapItem = km_items.get(km_item_def.bl_idname, None)
            if km_item is None:
                row = col.row()
                row.enabled = False
                row.label(text=f"Deleted: {km_item_def.name}")
                missing_items = True
                continue

            assert km_item is not None
            row = col.row(align=True)
            row.prop(km_item, "active", text="", toggle=False)
            row.label(text=km_item.name)
            row = row.row()
            row.prop(km_item, "type", text="", full_event=True)
            if km_item.is_user_modified:
                # This makes the operator's poll method succeed
                row.context_pointer_set("keymap", km)
            row.operator("preferences.keyitem_restore", text="", icon='BACK').item_id = km_item.id
    if missing_items:
        row = col.row()
        row.label(text="You can restore the deleted items in Blender Keymap preferences: ")
        row.operator("screen.userpref_show", icon='PREFERENCES', text="").section = 'KEYMAP'


def register_keymaps(
    addon_keymaps_list: AddonKeymaps, keymaps_definitions: KeymapDefinitions
) -> None:
    addon_keymaps_list.clear()
    wm = bpy.context.window_manager
    # wm.keyconfigs.addon can be None while Blender is running in background mode
    if wm.keyconfigs.addon is None:
        return

    for km_def, km_items_def in keymaps_definitions.items():
        km = wm.keyconfigs.addon.keymaps.new(
            name=km_def.name, space_type=km_def.space_type, region_type=km_def.region_type
        )

        for kmi_def in km_items_def:
            kmi = km.keymap_items.new(
                kmi_def.bl_idname,
                kmi_def.key,
                kmi_def.action,
                ctrl=kmi_def.ctrl,
                shift=kmi_def.shift,
                alt=kmi_def.alt,
            )
            for prop_name, prop_value in kmi_def.properties.items():
                if not hasattr(kmi.properties, prop_name):
                    raise AttributeError(
                        f"Keymap item '{kmi_def.name}' operator '{kmi_def.bl_idname}' has no property '{prop_name}'"
                    )
                setattr(kmi.properties, prop_name, prop_value)

            addon_keymaps_list.append((km, kmi))


def unregister_keymaps(addon_keymaps_list: AddonKeymaps) -> None:
    for km, kmi in addon_keymaps_list:
        km.keymap_items.remove(kmi)

    addon_keymaps_list.clear()
