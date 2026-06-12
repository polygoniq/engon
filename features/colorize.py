# copyright (c) 2018- polygoniq xyz s.r.o.

# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

import enum

import bpy
import dataclasses
import typing
from . import feature_utils
from . import asset_pack_panels
from .. import polib
from .. import preferences
from .. import panel

MODULE_CLASSES = []

MAX_COLOR_SLOTS = 10


class OrdinalNames(enum.StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    TERTIARY = "tertiary"
    QUATERNARY = "quaternary"
    # Because EEVEE has an attribute limitation of 8 attributes, and one color requires 2 attributes,
    # we would like to avoid using colors after quaternary where possible
    # We could rework colorize to use single RGBA attribute (encoding RGB + factor) later
    # QUINARY = "quinary"
    # SENARY = "senary"
    # SEPTENARY = "septenary"
    # OCTONARY = "octonary"
    # NONARY = "nonary"
    # DENARY = "denary"


@dataclasses.dataclass
class ColorSlotDefinition:
    """Defines a single color slot in the colorize feature.

    Only the ordinal name (e.g. "primary") and a display label are required;
    all other attributes are derived from the name.
    """

    name: OrdinalNames
    label: str

    @property
    def color_prop(self) -> str:
        return f"pq_{self.name}_color"

    @property
    def factor_prop(self) -> str:
        return f"pq_{self.name}_color_factor"

    @property
    def pref_color(self) -> str:
        return f"{self.name}_color"

    @property
    def pref_factor(self) -> str:
        return f"{self.name}_color_factor"


_DEFAULT_COLOR_SLOTS: list[ColorSlotDefinition] = [
    ColorSlotDefinition(name, name.value.capitalize()) for name in OrdinalNames
]


def _make_prop_update(pref_attr: str, prop_name: str):
    """Return a property update callback that writes pref_attr's value to prop_name."""

    def update(self, context: bpy.types.Context) -> None:
        assets = ColorizePanelMixin.get_multiedit_adjustable_assets(context)
        value = getattr(self, pref_attr)
        polib.custom_props_bpy.update_custom_prop(context, assets, prop_name, value)

    return update


class ColorizePreferences(bpy.types.PropertyGroup):
    pass


# Populate ColorizePreferences with one color + one factor property per ordinal slot.
for _slot in _DEFAULT_COLOR_SLOTS:
    ColorizePreferences.__annotations__[_slot.pref_color] = bpy.props.FloatVectorProperty(
        name=_slot.name.capitalize(),
        subtype='COLOR',
        description=f"Changes {_slot.name} color of assets",
        default=(1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
        step=1,
        size=3,
        update=_make_prop_update(_slot.pref_color, _slot.color_prop),
    )
    ColorizePreferences.__annotations__[_slot.pref_factor] = bpy.props.FloatProperty(
        name=f"{_slot.name.capitalize()} factor",
        description=f"Changes intensity of {_slot.name} colorization effect",
        default=0.0,
        min=0.0,
        max=1.0,
        step=1,
        update=_make_prop_update(_slot.pref_factor, _slot.factor_prop),
    )


MODULE_CLASSES.append(ColorizePreferences)


class ColorizePanelMixin(feature_utils.PropertyAssetFeatureControlPanelMixin, bpy.types.Panel):
    # TODO: this feature is currently selected-asset-packs-only, but in the future it should be moved to engon panel,
    # once all other asset packs implement colorize
    bl_label = "Colorize"
    bl_parent_id = panel.EngonPanel.bl_idname
    feature_name = "colorize"
    bl_options = {'DEFAULT_CLOSED'}

    # Default slots for ordinal color positions. Subclasses override this list to
    # apply asset-pack-specific display labels.
    COLOR_SLOTS: typing.ClassVar[list[ColorSlotDefinition]] = _DEFAULT_COLOR_SLOTS

    # Derived from COLOR_SLOTS so that every property name reachable through this panel is
    # automatically registered as a feature-detection property.
    related_custom_properties: typing.ClassVar[set[str]] = {
        prop for slot in COLOR_SLOTS for prop in (slot.color_prop, slot.factor_prop)
    }

    @classmethod
    def filter_adjustable_assets(
        cls,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> typing.Iterable[bpy.types.ID]:
        return cls.filter_adjustable_assets_simple(possible_assets)

    @classmethod
    def get_feature_icon(cls) -> str:
        return 'MOD_HUE_SATURATION'

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon=self.get_feature_icon())

    def draw_header_preset(self, context: bpy.types.Context) -> None:
        self.layout.operator(
            feature_utils.SelectFeatureCompatibleObjects.bl_idname,
            text="",
            icon='RESTRICT_SELECT_ON',
            emboss=False,
        ).engon_feature_name = type(self).feature_name

    def draw_slot_property(
        self,
        datablock: bpy.types.ID,
        layout: bpy.types.UILayout,
        prop_name: str,
        text: str = "",
    ) -> None:
        """Draw prop_name if present on datablock, or a '-' placeholder."""
        if prop_name in datablock:
            layout.prop(datablock, f'["{prop_name}"]', text=text)
        else:
            layout.label(text="-")

    def draw_properties(
        self,
        datablock: bpy.types.ID,
        layout: bpy.types.UILayout,
        slots: list[ColorSlotDefinition] | None = None,
    ) -> None:
        if slots is None:
            slots = type(self).COLOR_SLOTS
        for slot in slots:
            row = layout.column().row(align=True)
            self.draw_slot_property(datablock, row, slot.color_prop)
            self.draw_slot_property(datablock, row, slot.factor_prop)

    def draw_multiedit(
        self,
        context: bpy.types.Context,
        layout: bpy.types.UILayout,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> None:
        self.draw_multiedit_header(layout)

        adjustable_assets = list(self.filter_adjustable_assets(possible_assets))
        prefs = preferences.prefs_utils.get_preferences(context).colorize_preferences

        for slot in type(self).COLOR_SLOTS:
            if not any(o.get(slot.factor_prop, None) is not None for o in adjustable_assets):
                continue

            active_color_prop = slot.color_prop
            active_factor_prop = slot.factor_prop

            row = layout.row(align=True)
            row.label(text=slot.label, icon='COLOR')
            row.prop(prefs, slot.pref_color, text="")
            self.draw_randomize_property_operator(
                active_color_prop,
                feature_utils.RandomizeColorPropertyOperator,
                row,
            )
            row.prop(prefs, slot.pref_factor, text="Factor", slider=True)
            self.draw_randomize_property_operator(
                active_factor_prop,
                feature_utils.RandomizeFloatPropertyOperator,
                row,
            )

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        possible_assets = self.get_possible_assets(context)

        if self.conditionally_draw_warning_no_adjustable_assets(possible_assets, layout):
            return

        adjustable_assets = list(self.filter_adjustable_assets(possible_assets))
        active_slots = [
            slot
            for slot in type(self).COLOR_SLOTS
            if any(slot.color_prop in obj for obj in adjustable_assets)
        ]

        if len(active_slots) <= 2:
            # Side-by-side table: all slots share one "Selected Assets:" header row.
            row = self.layout.row()
            left_col = row.column(align=True)
            left_col.scale_x = 2.0
            right_col = row.column(align=True)

            row = left_col.row()
            row.enabled = False
            row.label(text="Selected Assets:")

            right_table_header = right_col.row(align=True)
            for slot in active_slots:
                slot_header = right_table_header.column().row(align=True)
                slot_header.enabled = False
                slot_header.label(text=slot.label)
                slot_header.label(text="Factor")

            self.draw_adjustable_assets_property_table_body(
                possible_assets,
                left_col,
                right_col,
                lambda layout, obj: self.draw_properties(obj, layout, active_slots),
            )
        else:
            # Stacked layout: each slot gets its own labelled table.
            for i, slot in enumerate(active_slots):
                if i > 0:
                    layout.separator()
                layout.label(text=f"{slot.label}:", icon='COLOR')
                self.draw_adjustable_assets_property_table(
                    possible_assets,
                    ["Color", "Factor"],
                    layout,
                    lambda layout, obj, s=slot: self.draw_properties(obj, layout, [s]),
                )

        layout.separator()
        self.draw_multiedit(context, layout, possible_assets)


@feature_utils.register_feature
@polib.log_helpers_bpy.logged_panel
class ColorizePanel(ColorizePanelMixin):
    # TODO: This panel is currently registered mainly because of the pie menu use case
    # so we have one registered central panel for all packs supporting colorize. Registering and
    # using the 'ColorizePanelMixin' directly isn't possible, as it causes registration RNA issues.
    bl_idname = "VIEW_3D_PT_engon_feature_colorize_general"
    bl_parent_id = panel.EngonPanel.bl_idname

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # We don't want to display this panel in the engon UI right now as asset packs have their
        # own respective panels and it feels clumsy to have one feature disconnected from others.
        # By this check, we display this panel only inside the pie menu.
        return context.region.type != 'UI'


MODULE_CLASSES.append(ColorizePanel)


@polib.log_helpers_bpy.logged_panel
class AesthetiqColorizePanel(ColorizePanelMixin):
    bl_idname = "VIEW_3D_PT_engon_feature_colorize_aesthetiq"
    bl_parent_id = asset_pack_panels.AesthetiqPanel.bl_idname

    @classmethod
    def filter_adjustable_assets(
        cls,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> typing.Iterable[bpy.types.ID]:
        return filter(
            lambda datablock: polib.custom_props_bpy.has_property(
                datablock,
                "polygoniq_addon",
                lambda v: v == "aesthetiq",
            ),
            super().filter_adjustable_assets(possible_assets),
        )


MODULE_CLASSES.append(AesthetiqColorizePanel)


@polib.log_helpers_bpy.logged_panel
class InterniqColorizePanel(ColorizePanelMixin):
    bl_idname = "VIEW_3D_PT_engon_feature_colorize_interniq"
    bl_parent_id = asset_pack_panels.InterniqPanel.bl_idname

    @classmethod
    def filter_adjustable_assets(
        cls,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> typing.Iterable[bpy.types.ID]:
        return filter(
            lambda datablock: polib.custom_props_bpy.has_property(
                datablock,
                "polygoniq_addon",
                lambda v: v == "interniq",
            ),
            super().filter_adjustable_assets(possible_assets),
        )


MODULE_CLASSES.append(InterniqColorizePanel)


@polib.log_helpers_bpy.logged_panel
class HumaniqColorizePanel(ColorizePanelMixin):
    bl_idname = "VIEW_3D_PT_engon_feature_colorize_humaniq"
    bl_parent_id = asset_pack_panels.HumaniqPanel.bl_idname

    COLOR_SLOTS: typing.ClassVar[list[ColorSlotDefinition]] = [
        ColorSlotDefinition(OrdinalNames.PRIMARY, "Hair"),
        ColorSlotDefinition(OrdinalNames.SECONDARY, "Upper Clothing"),
        ColorSlotDefinition(OrdinalNames.TERTIARY, "Lower Clothing"),
        ColorSlotDefinition(OrdinalNames.QUATERNARY, "Shoes"),
    ]

    @classmethod
    def filter_adjustable_assets(
        cls,
        possible_assets: typing.Iterable[bpy.types.ID],
    ) -> typing.Iterable[bpy.types.ID]:
        return filter(
            lambda datablock: polib.custom_props_bpy.has_property(
                datablock,
                "polygoniq_addon",
                lambda v: v == "humaniq",
            ),
            super().filter_adjustable_assets(possible_assets),
        )


MODULE_CLASSES.append(HumaniqColorizePanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
