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

import bpy
import typing
import logging
import os
import urllib.request
import urllib.parse
import pathlib

from . import asset_pack_panels
from . import feature_utils
from .. import polib
from .. import hatchery
from .. import asset_helpers

logger = logging.getLogger(f"polygoniq.{__name__}")

MODULE_CLASSES = []

# Ideally this would be in frame generator preferences, but we can't store pointers to datablocks there :(
WM_PROP_PQ_FRAME_GEN_IMAGE_SOURCE = "pq_frame_gen_image_source"


@feature_utils.register_feature
class FrameGeneratorPanelMixin(feature_utils.GeonodesAssetFeatureControlPanelMixin):
    feature_name = "frame_generator"
    node_group_name = asset_helpers.SQ_FRAME_GENERATOR_MODIFIER


@polib.log_helpers_bpy.logged_panel
class FrameGeneratorPanel(FrameGeneratorPanelMixin, bpy.types.Panel):
    bl_idname = "VIEW_3D_PT_engon_frame_generator"
    bl_label = "Frame Generator"
    bl_parent_id = asset_pack_panels.AesthetiqPanel.bl_idname
    bl_options = {'DEFAULT_CLOSED'}

    feature_name = "frame_generator"

    def draw_header(self, context: bpy.types.Context) -> None:
        self.layout.label(text="", icon='IMAGE_RGB')

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        layout.operator(FrameImage.bl_idname, text="Frame New Image", icon='SEQ_PREVIEW')


MODULE_CLASSES.append(FrameGeneratorPanel)


@polib.log_helpers_bpy.logged_operator
class FrameGeneratorOpenImage(bpy.types.Operator):
    bl_idname = "engon.open_image_for_frame_generator"
    bl_label = "Open Image"
    bl_description = "Open an image and assign to frame generator modal property, to be framed"
    bl_options = {'REGISTER'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filter_image: bpy.props.BoolProperty(default=True, options={'HIDDEN'})
    filter_folder: bpy.props.BoolProperty(default=True, options={'HIDDEN'})

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context: bpy.types.Context):
        if self.filepath and pathlib.Path(self.filepath).is_file():
            image = bpy.data.images.load(self.filepath)
            context.window_manager.pq_frame_gen_image_source = image  # type: ignore
            logger.info(f"Loaded image '{image.name}' for frame generator.")
        return {'FINISHED'}


MODULE_CLASSES.append(FrameGeneratorOpenImage)


def ensure_pictoral_materials() -> list[bpy.types.Material]:
    """Ensures that all pictoral materials are loaded into Blender.

    Returns a list of the loaded materials.
    """

    material_library_path = asset_helpers.get_asset_pack_library_path(
        "aesthetiq", asset_helpers.SQ_PICTORAL_MATERIALS_LIBRARY_BLEND
    )
    if material_library_path is None:
        raise RuntimeError("Pictoral materials library not found!")
    known_pictorial_materials = [
        mat
        for mat in bpy.data.materials
        if mat.name.startswith(asset_helpers.SQ_PICTORIAL_MATERIAL_PREFIX)
        and mat.library is not None
        and polib.utils_bpy.normalize_path(mat.library.filepath)
        == polib.utils_bpy.normalize_path(material_library_path)
    ]
    with bpy.data.libraries.load(material_library_path, link=True) as (data_from, data_to):
        data_to.materials = [
            name
            for name in data_from.materials
            if name.startswith(asset_helpers.SQ_PICTORIAL_MATERIAL_PREFIX)
            and name not in {mat.name for mat in known_pictorial_materials}
        ]
        logger.info(
            f"Newly loaded pictoral materials {data_to.materials} from {material_library_path}, "
            f"already known {[mat.name for mat in known_pictorial_materials]}."
        )
    return data_to.materials


def _get_material_enum_items(
    _self: bpy.types.Operator, context: bpy.types.Context | None
) -> list[tuple[str, str, str]]:
    mats = [
        (mat.name, mat.name.removeprefix(asset_helpers.SQ_PICTORIAL_MATERIAL_PREFIX), "")
        for mat in bpy.data.materials
        if mat.name.startswith(asset_helpers.SQ_PICTORIAL_MATERIAL_PREFIX)
    ]
    if len(mats) == 0:
        mats = [("", "No pictoral materials found", "")]
    return mats


def _get_default_download_directory() -> str:
    """Get the default directory for saving downloaded images."""
    default_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    if not os.path.exists(default_dir):
        default_dir = os.path.expanduser("~")
    return default_dir


@polib.log_helpers_bpy.logged_operator
class FrameImage(bpy.types.Operator):
    bl_idname = "engon.aesthetiq_generate_picture"
    bl_label = "Frame Image"
    bl_description = "Create an image plane with a frame generator"
    bl_options = {'REGISTER', 'UNDO'}

    source_type: bpy.props.EnumProperty(
        name="Source Type",
        description="Choose between local image or URL",
        items=[
            ('LOCAL', "Local Image", "Use a local Blender image"),
            ('URL', "Image URL", "Use an image from a URL"),
        ],
        default='LOCAL',
    )

    image_url: bpy.props.StringProperty(
        name="Image URL",
        description="URL of the image to use",
        default="",
    )
    image_save_dir: bpy.props.StringProperty(
        name="Save To",
        description="Where to save the downloaded image",
        default=_get_default_download_directory(),
        subtype='DIR_PATH',
    )
    height: bpy.props.FloatProperty(
        name="Height",
        description="Height of the generated picture",
        default=0.6,
        min=0.0,
        subtype='DISTANCE',
    )
    width: bpy.props.FloatProperty(
        name="Width",
        description="Width of the generated picture",
        default=0.4,
        min=0.0,
        subtype='DISTANCE',
    )
    auto_width: bpy.props.BoolProperty(
        name="Auto Width",
        description="Automatically set the width based on the image aspect ratio",
        default=True,
    )

    material_name: bpy.props.EnumProperty(
        name="Material",
        description="Choose a pictoral material",
        items=_get_material_enum_items,
    )

    def _compute_auto_width(self, selected_image: bpy.types.Image) -> float:
        aspect_ratio = selected_image.size[0] / selected_image.size[1]
        return self.height * aspect_ratio

    def _compute_auto_width_from_context(self, context: bpy.types.Context) -> float | None:
        wm = context.window_manager
        selected_image = getattr(wm, WM_PROP_PQ_FRAME_GEN_IMAGE_SOURCE, None)
        if not isinstance(selected_image, bpy.types.Image):
            return None
        return self._compute_auto_width(selected_image)

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        # Only load pictoral materials here, to avoid loading them in draw but having them ready in draw
        ensure_pictoral_materials()
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: bpy.types.Context):
        wm = context.window_manager
        layout = self.layout
        layout.prop(self, "source_type", text="")
        if self.source_type == 'LOCAL':
            # using template_image does not work, as it requires "image_user" which we don't have here
            # using template_ID with new and open buttons also does not work well as it does not update the pointer property properly
            # so we approximate like this
            row = layout.row(align=True)
            row.prop_search(wm, WM_PROP_PQ_FRAME_GEN_IMAGE_SOURCE, bpy.data, "images", text="")
            row.operator(FrameGeneratorOpenImage.bl_idname, text="", icon='FILE_FOLDER')

            if getattr(wm, WM_PROP_PQ_FRAME_GEN_IMAGE_SOURCE, None) is None:
                row = layout.row()
                row.alert = True
                row.label(text="No image selected!")
        elif self.source_type == 'URL':
            layout.prop(self, "image_url")
            layout.prop(self, "image_save_dir")
            if not self.image_url:
                row = layout.row()
                row.alert = True
                row.label(text="No URL provided!")
            if not self.image_save_dir:
                row = layout.row()
                row.alert = True
                row.label(text="No save path provided!")
        else:
            assert False, "Invalid source type"

        layout.prop(self, "material_name")

        layout.prop(self, "height")

        auto_width_text = "Auto Width"
        calculated_width = self._compute_auto_width_from_context(context)
        if calculated_width is not None:
            auto_width_text += f" (calculated: {calculated_width:.3f})"
        layout.prop(self, "auto_width", text=auto_width_text)
        if not self.auto_width:
            layout.prop(self, "width")

    def execute(self, context: bpy.types.Context):
        wm = context.window_manager
        if self.source_type == 'LOCAL':
            selected_image = getattr(wm, WM_PROP_PQ_FRAME_GEN_IMAGE_SOURCE, None)
            if selected_image is None:
                self.report({'ERROR'}, "No image selected.")
                logger.error("No image selected for framing.")
                return {'CANCELLED'}
            selected_image = typing.cast(bpy.types.Image, selected_image)
        elif self.source_type == 'URL':
            if not self.image_url or not self.image_save_dir:
                self.report({'ERROR'}, "Image URL and save path must be provided.")
                logger.error("Image URL or save path not provided.")
                return {'CANCELLED'}
            if not bpy.app.online_access:
                self.report({'ERROR'}, "Allow online access in 'Preferences -> System -> Network'")
                logger.error("Online access for blender is disabled.")
                return {'CANCELLED'}
            try:
                image_filename = pathlib.Path(urllib.parse.urlparse(self.image_url).path).name
                image_save_path = pathlib.Path(self.image_save_dir) / image_filename
                urllib.request.urlretrieve(self.image_url, image_save_path)
                image_name = image_save_path.name
                selected_image = bpy.data.images.load(str(image_save_path))
                selected_image.name = image_name

            except Exception as e:
                self.report(
                    {'ERROR'}, f"Failed to download or load image, see console for details."
                )
                logger.error(f"Failed to download or load image from {self.image_url}", exc_info=e)
                return {'CANCELLED'}
        else:
            self.report({'ERROR'}, "Invalid source type.")
            logger.error("Invalid source type for framing.")
            return {'CANCELLED'}

        if len(selected_image.pixels) == 0:  # type: ignore pixels is a list not a float
            self.report({'ERROR'}, "Selected image is not a valid image.")
            logger.error("Selected image is not a valid image.")
            return {'CANCELLED'}

        # Add frame generator geometry nodes modifier
        frame_generator_library_path = asset_helpers.get_asset_pack_library_path(
            "aesthetiq", asset_helpers.SQ_FRAME_GENERATOR_LIBRARY_BLEND
        )
        if frame_generator_library_path is None:
            self.report({'ERROR'}, "Frame generator geometry nodes not found.")
            logger.error("Frame generator library not found!")
            return {'CANCELLED'}

        plane = hatchery.load.load_object_by_name(
            frame_generator_library_path, asset_helpers.SQ_FRAME_GENERATOR_OBJECT, link=True
        )

        # Move the picture to the correct collection
        collection = polib.asset_pack_bpy.collection_get(
            context,
            "aesthetiq",
            context.scene.collection,
        )
        collection.objects.link(plane)

        bpy.context.view_layer.objects.active = plane
        plane.select_set(True)

        plane.make_local()

        assert plane is not None, "No active object found after spawning frame generator."
        plane.name = f"Framed_{selected_image.name}"
        plane_mesh = plane.data
        assert plane_mesh is not None, "No mesh data found on the frame generator object."
        assert isinstance(plane_mesh, bpy.types.Mesh), "Frame generator object is not a mesh."
        plane_mesh.make_local()
        plane_mesh.name = plane.name
        modifier = plane.modifiers.get(asset_helpers.SQ_FRAME_GENERATOR_MODIFIER)
        assert modifier is not None, "Frame generator modifier not found on the spawned object."
        node_group = modifier.node_group
        assert node_group is not None, "Frame generator modifier has no node group."

        # There is a bug in blender where linked node groups with boolean inputs that you link twice
        # This reload should not be needed, but without it, we are  run into issues where
        # blender does not understand boolean properties on the geometry nodes, and the UI does not show them,
        # and we get a warning like
        # BKE_modifier_set_error: Object: "Framed_kurva.neviem", Modifier: "sq_Frame-Generator",
        # Property type does not match input socket "(Enable)"
        modifier.node_group.library.reload()

        # Set dimensions
        if self.auto_width:
            width = self._compute_auto_width(selected_image)
            assert width is not None, "Could not calculate auto width."
            plane.dimensions = (width, self.height, plane.dimensions.z)
        else:
            plane.dimensions = (self.width, self.height, plane.dimensions.z)
        with bpy.context.temp_override(
            active_object=plane, selected_objects=[plane], selected_editable_objects=[plane]
        ):
            bpy.ops.object.transform_apply()

        # Create a material with the image texture
        mat = bpy.data.materials.get(self.material_name)
        if mat is not None:
            selected_material = mat.copy()
            selected_material.name = plane.name
            if selected_material.node_tree is None:
                self.report({'ERROR'}, "Selected material has no node tree.")
                logger.error("Selected pictoral material has no node tree.")
                return {'CANCELLED'}

            placeholder_nodes = polib.node_utils_bpy.find_nodes_by_name(
                selected_material.node_tree, "sq_Artwork_Placeholder"
            )
            assert (
                len(placeholder_nodes) == 1
            ), f"Pictoral materials are expeceted to have 1 'sq_Artwork_Placeholder' node, found {len(placeholder_nodes)}."

            placeholder_node = placeholder_nodes.pop()

            assert isinstance(
                placeholder_node, bpy.types.ShaderNodeTexImage
            ), "sq_Artwork_Placeholder node is not an image texture node."
            placeholder_node.image = selected_image

            assert (
                plane.material_slots is not None and len(plane.material_slots) > 0
            ), "Frame generator plane has no material slots."
            plane.material_slots[0].material = selected_material

        # tag refresh ui, otherwise the frame generator control panel may not show up
        polib.ui_bpy.tag_areas_redraw(context, {'VIEW_3D'})
        return {'FINISHED'}


MODULE_CLASSES.append(FrameImage)


@polib.log_helpers_bpy.logged_panel
class FrameGeneratorControlPanel(
    FrameGeneratorPanelMixin,
    feature_utils.GeoNodesAssetFeatureSecondaryControlPanelMixin,
    bpy.types.Panel,
):

    bl_idname = "VIEW_3D_PT_engon_frame_generator_control_panel"
    bl_label = "Adjustments"
    bl_parent_id = FrameGeneratorPanel.bl_idname
    bl_options = {'DEFAULT_CLOSED'}

    template = polib.node_utils_bpy.NodeSocketsDrawTemplate(
        asset_helpers.SQ_FRAME_GENERATOR_MODIFIER
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # The poll method is overridden to ensure that the panel appers when appropriate
        # regular use of poll from mixin does not work well here - possibly beause of nested panels
        # or because of multiple mixins
        # poll returns true as expected, but the draw method is not called
        return True

    def draw(self, context: bpy.types.Context):
        if self.conditionally_draw_warning_no_adjustable_active_object(context, self.layout):
            return
        self.draw_active_object_modifiers_node_group_inputs_template(
            self.layout,
            context,
            FrameGeneratorControlPanel.template,
        )


MODULE_CLASSES.append(FrameGeneratorControlPanel)


def register():
    for cls in MODULE_CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.pq_frame_gen_image_source = bpy.props.PointerProperty(  # type: ignore
        name="Image to Frame",
        description="Selected image to be framed",
        type=bpy.types.Image,
    )


def unregister():
    del bpy.types.WindowManager.pq_frame_gen_image_source  # type: ignore
    for cls in reversed(MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
