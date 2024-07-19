# copyright (c) 2018- polygoniq xyz s.r.o.
# Code is inspired by the 'MeasureIt' addon by Antonio Vazquez that is shipped natively in Blender

import bpy
import bpy_extras
import blf
import dataclasses
import gpu
import gpu_extras.batch
import gpu_extras.presets
import mathutils
import logging
import typing

logger = logging.getLogger(f"polygoniq.{__name__}")


if not bpy.app.background:
    # Blender 4.0 dropped the 3D_ and 2D_ prefixes from the shader names
    SHADER_LINE_BUILTIN = (
        gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        if bpy.app.version >= (4, 0, 0)
        else gpu.shader.from_builtin('3D_POLYLINE_UNIFORM_COLOR')
    )

    SHADER_2D_UNIFORM_COLOR_BUILTIN = (
        gpu.shader.from_builtin('UNIFORM_COLOR')
        if bpy.app.version >= (4, 0, 0)
        else gpu.shader.from_builtin('2D_UNIFORM_COLOR')
    )
else:
    logger.info(f"'{__name__}' module is not available in background mode!")


VIEWPORT_SIZE = (0, 0)
Color = typing.Tuple[float, float, float, float]


def set_context(context: bpy.types.Context) -> None:
    """Sets viewport size from context, to be further used as native bpy uniform in shaders"""
    global VIEWPORT_SIZE
    VIEWPORT_SIZE = (context.region.width, context.region.height)


def line(v1: mathutils.Vector, v2: mathutils.Vector, color: Color, width: float):
    """Draws a line from 'v1' to 'v2' of desired 'color' and 'width'"""
    pos = [v1, v2]
    batch = gpu_extras.batch.batch_for_shader(SHADER_LINE_BUILTIN, 'LINES', {"pos": pos})
    SHADER_LINE_BUILTIN.bind()
    SHADER_LINE_BUILTIN.uniform_float("color", color)
    SHADER_LINE_BUILTIN.uniform_float("lineWidth", width)
    SHADER_LINE_BUILTIN.uniform_float("viewportSize", VIEWPORT_SIZE)
    batch.draw(SHADER_LINE_BUILTIN)


def rectangle(pos: typing.Tuple[float, float], size: typing.Tuple[float, float], color: Color):
    """Draws rectangle starting at 'pos' of width and height from 'size' of desired 'color'"""
    batch = gpu_extras.batch.batch_for_shader(
        SHADER_2D_UNIFORM_COLOR_BUILTIN,
        'TRI_FAN',
        {
            "pos": [
                (pos[0], pos[1]),
                (pos[0] + size[0], pos[1]),
                (pos[0] + size[0], pos[1] + size[1]),
                (pos[0], pos[1] + size[1]),
            ]
        },
    )
    SHADER_2D_UNIFORM_COLOR_BUILTIN.bind()
    SHADER_2D_UNIFORM_COLOR_BUILTIN.uniform_float("color", color)
    batch.draw(SHADER_2D_UNIFORM_COLOR_BUILTIN)


def circle(center: mathutils.Vector, radius: float, color: Color, segments: int):
    gpu_extras.presets.draw_circle_2d(center, color, radius, segments=segments)


@dataclasses.dataclass
class TextStyle:
    """Style of rendered text

    If 'consider_ui_scale' is True, then actual 'font_size' is constructed
    on initialization based on preferences user interface scale
    """

    font_id: int = 0
    font_size: int = 15
    color: Color = (1.0, 1.0, 1.0, 1.0)
    dpi: int = 72
    consider_ui_scale: bool = True

    def __post_init__(self):
        if self.consider_ui_scale:
            self.font_size *= bpy.context.preferences.system.ui_scale


def text(pos: mathutils.Vector, string: str, style: TextStyle) -> None:
    blf.position(style.font_id, pos[0], pos[1], 0)
    if bpy.app.version >= (4, 0, 0):  # dpi argument has been dropped in Blender 4.0
        blf.size(style.font_id, style.font_size)
    else:
        blf.size(style.font_id, style.font_size, style.dpi)
    blf.color(style.font_id, *style.color)
    blf.draw(style.font_id, str(string))


def text_3d(
    world_pos: mathutils.Vector,
    string: str,
    style: TextStyle,
    region: bpy.types.Region,
    rv3d: bpy.types.RegionView3D,
) -> None:
    pos_2d = bpy_extras.view3d_utils.location_3d_to_region_2d(region, rv3d, world_pos)
    text(pos_2d, string, style)


def text_box(
    pos: mathutils.Vector,
    width: int,
    padding: int,
    text_margin: float,
    background: typing.Optional[Color],
    texts: typing.List[typing.Tuple[str, TextStyle]],
) -> None:
    height = sum(t[1].font_size for t in texts) + (len(texts) - 1) * text_margin
    if background is not None:
        rectangle(pos, (width, height + 2 * padding), background)

    x_pos = pos.x + padding
    y_pos = pos.y + height
    for string, style in texts:
        text((x_pos, y_pos), string, style)
        y_pos -= style.font_size + text_margin


def text_box_3d(
    world_pos: mathutils.Vector,
    width: int,
    padding: int,
    text_margin: float,
    background: typing.Optional[Color],
    texts: typing.List[typing.Tuple[str, TextStyle]],
    region: bpy.types.Region,
    rv3d: bpy.types.RegionView3D,
) -> None:
    """Draws text box based on world position aligned to view"""
    pos_2d = bpy_extras.view3d_utils.location_3d_to_region_2d(region, rv3d, world_pos)
    text_box(pos_2d, width, padding, text_margin, background, texts)
