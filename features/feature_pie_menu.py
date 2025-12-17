# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
from .. import polib
from . import feature_utils
import logging

logger = logging.getLogger(f"polygoniq.{__name__}")


MODULE_CLASSES = []


@polib.log_helpers_bpy.logged_operator
class ENGON_OpenFeaturePanelFromPie(bpy.types.Operator):
    bl_idname = "engon.open_feature_panel_from_pie"
    bl_label = "Open Feature Panel from Pie Menu"
    bl_options = {'REGISTER'}

    panel_bl_idname: bpy.props.StringProperty(name="", default="")

    def execute(self, context: bpy.types.Context) -> set[str]:
        bpy.ops.wm.call_panel(name=self.panel_bl_idname)
        return {'FINISHED'}


MODULE_CLASSES.append(ENGON_OpenFeaturePanelFromPie)


class ENGON_FeaturePieMenu(bpy.types.Menu):
    """Pie menu allowing in-scene control over selection of engon assets.

    The controllable features are displayed based on the current context e. g. if the selection
    contains botaniq asset, botaniq adjustments are displayed, similarly for other asset pack
    features.
    """

    bl_idname = "ENGON_MT_feature_pie_menu"
    bl_label = "Asset Features"
    bl_description = "Quick access to Engon asset feature adjustments"

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        pie_menu_features = feature_utils.get_property_features_panels_with_pie_menu()
        # We draw only features that have adjustable assets in the current context
        drawn_pie_features = [
            feature_cls
            for feature_cls in pie_menu_features
            if feature_cls.has_adjustable_assets(feature_cls.get_possible_assets(context))
        ]
        pie = layout.menu_pie()
        if len(drawn_pie_features) == 0:
            box = pie.box()
            box.label(text="No object with adjustable features selected.")
            box.label(text="Select a engon asset with adjustable features.")
            return

        # Pie menu supports drawing 8 items at maximum, this won't be a frequent use case, so
        # we just break in that case.
        for feature_cls in drawn_pie_features[:7]:
            pie.operator(
                ENGON_OpenFeaturePanelFromPie.bl_idname,
                text=feature_cls.get_feature_name_readable(),
                icon=feature_cls.get_feature_icon(),
            ).panel_bl_idname = feature_cls.bl_idname

        if len(drawn_pie_features) >= 8:
            pie.box().label(text="...and more")


MODULE_CLASSES.append(ENGON_FeaturePieMenu)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
