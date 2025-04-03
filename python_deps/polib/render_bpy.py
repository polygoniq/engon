# copyright (c) 2018- polygoniq xyz s.r.o.
# Code is inspired by the 'MeasureIt' addon by Antonio Vazquez that is shipped natively in Blender
# Parts of code for drawing rounded box and mouse are adjusted from the 'ScreenCastKeys' addon
# by nutti


# TODO: This whole module is super unoptimized, we should batch things for UI and ideally
# only draw should happen in these callbacks, style and things that can be computed when setup
# should be done once.

import bpy
import bpy_extras.view3d_utils
import blf
import dataclasses
import gpu
import gpu_extras.batch
import gpu_extras.presets
import mathutils
import math
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
# Default size of a key or mouse indicator in px
DEFAULT_INDICATOR_SIZE = 20.0
# Default color of the key or mouse indicator, currently a 'engon' color
DEFAULT_INDICATOR_COLOR = (0, 1.0, 162.0 / 255.0, 1.0)
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


def arrow(
    pos: typing.Tuple[float, float],
    color: Color,
    size: float,
    rotation: float = 0.0,
    line_thickness: float = 1.0,
    draw_stem: bool = True,
    stem_length_factor: float = 0.75,
    arrow_length_factor: float = 0.4,
):
    rotation = math.radians(rotation)
    arrow_length = max(0.0, min(1.0, 1.0 - arrow_length_factor))
    if draw_stem:
        verts = [
            (max(0.0, min(1.0, 1.0 - stem_length_factor)), 0.5),
            (1.0, 0.5),
            (arrow_length, 0.8),
            (1.0, 0.5),
            (arrow_length, 0.2),
        ]
    else:
        verts = [
            (arrow_length, 0.8),
            (1.0, 0.5),
            (arrow_length, 0.2),
        ]

    rotated_verts = []
    for vert in verts:
        x = (vert[0] - 0.5) * 2
        y = (vert[1] - 0.5) * 2
        x_rot = x * math.cos(rotation) - y * math.sin(rotation)
        y_rot = x * math.sin(rotation) + y * math.cos(rotation)
        rotated_verts.append((x_rot, y_rot))

    # We modify the given scale to be similar to the key size
    verts = [(v[0] * size + pos[0], v[1] * size + pos[1]) for v in rotated_verts]

    original_blend = gpu.state.blend_get()
    batch = gpu_extras.batch.batch_for_shader(
        SHADER_2D_UNIFORM_COLOR_BUILTIN,
        'LINE_STRIP',
        {"pos": verts},
    )
    gpu.state.line_width_set(line_thickness)

    SHADER_2D_UNIFORM_COLOR_BUILTIN.bind()
    SHADER_2D_UNIFORM_COLOR_BUILTIN.uniform_float("color", color)
    batch.draw(SHADER_2D_UNIFORM_COLOR_BUILTIN)

    gpu.state.blend_set(original_blend)


def mouse_symbol(
    x: float,
    y: float,
    w: float,
    h: float,
    left_pressed: bool = False,
    middle_pressed: bool = False,
    right_pressed: bool = False,
    indicate_left: bool = False,
    indicate_right: bool = False,
    indicate_up: bool = False,
    indicate_down: bool = False,
    round_radius: float = 5.0,
    color: Color = (1.0, 1.0, 1.0, 1.0),
    fill: bool = False,
    line_thickness: float = 1.0,
):
    """Draws mouse symbol using rounded rectangles.

    Optionally arrows can be drawn to indicate the direction of the mouse movement.
    Optionally the mouse buttons can be filled to indicate they are pressed.
    """
    # Code is adjusted from the ScreenCastKeys addon by nutti.
    mouse_body = [x, y, w, h / 2]
    left_mouse_button = [x, y + h / 2, w / 3, h / 2]
    middle_mouse_button = [x + w / 3, y + h / 2, w / 3, h / 2]
    right_mouse_button = [x + 2 * w / 3, y + h / 2, w / 3, h / 2]

    # Mouse body.
    if fill:
        rounded_rectangle(
            mouse_body[0],
            mouse_body[1],
            mouse_body[2],
            mouse_body[3],
            round_radius,
            fill=True,
            color=color,
            round_corner=(True, True, False, False),
            line_thickness=line_thickness,
        )
    rounded_rectangle(
        mouse_body[0],
        mouse_body[1],
        mouse_body[2],
        mouse_body[3],
        round_radius,
        fill=False,
        color=color,
        round_corner=(True, True, False, False),
        line_thickness=line_thickness,
    )

    # Left button.
    if fill:
        rounded_rectangle(
            left_mouse_button[0],
            left_mouse_button[1],
            left_mouse_button[2],
            left_mouse_button[3],
            round_radius / 2,
            fill=True,
            color=color,
            round_corner=(False, False, False, True),
            line_thickness=line_thickness,
        )
    rounded_rectangle(
        left_mouse_button[0],
        left_mouse_button[1],
        left_mouse_button[2],
        left_mouse_button[3],
        round_radius / 2,
        fill=False,
        color=color,
        round_corner=(False, False, False, True),
        line_thickness=line_thickness,
    )
    if left_pressed:
        rounded_rectangle(
            left_mouse_button[0],
            left_mouse_button[1],
            left_mouse_button[2],
            left_mouse_button[3],
            round_radius / 2,
            fill=True,
            color=color,
            round_corner=(False, False, False, True),
            line_thickness=line_thickness,
        )

    # Middle button.
    if fill:
        rounded_rectangle(
            middle_mouse_button[0],
            middle_mouse_button[1],
            middle_mouse_button[2],
            middle_mouse_button[3],
            round_radius / 2,
            fill=True,
            color=color,
            round_corner=(False, False, False, False),
            line_thickness=line_thickness,
        )
    rounded_rectangle(
        middle_mouse_button[0],
        middle_mouse_button[1],
        middle_mouse_button[2],
        middle_mouse_button[3],
        round_radius / 2,
        fill=False,
        color=color,
        round_corner=(False, False, False, False),
        line_thickness=line_thickness,
    )
    if middle_pressed:
        rounded_rectangle(
            middle_mouse_button[0],
            middle_mouse_button[1],
            middle_mouse_button[2],
            middle_mouse_button[3],
            round_radius / 2,
            fill=True,
            color=color,
            round_corner=(False, False, False, False),
            line_thickness=line_thickness,
        )

    # Right button.
    if fill:
        rounded_rectangle(
            right_mouse_button[0],
            right_mouse_button[1],
            right_mouse_button[2],
            right_mouse_button[3],
            round_radius / 2,
            fill=True,
            color=color,
            round_corner=(False, False, True, False),
            line_thickness=line_thickness,
        )
    rounded_rectangle(
        right_mouse_button[0],
        right_mouse_button[1],
        right_mouse_button[2],
        right_mouse_button[3],
        round_radius / 2,
        fill=False,
        color=color,
        round_corner=(False, False, True, False),
        line_thickness=line_thickness,
    )
    if right_pressed:
        rounded_rectangle(
            right_mouse_button[0],
            right_mouse_button[1],
            right_mouse_button[2],
            right_mouse_button[3],
            round_radius / 2,
            fill=True,
            color=color,
            round_corner=(False, False, True, False),
            line_thickness=line_thickness,
        )

    ui_scale = bpy.context.preferences.system.ui_scale
    margin_5 = 5 * ui_scale
    margin_10 = 10 * ui_scale
    arrows_scale = 0.45
    if indicate_down:
        arrow(
            (x - margin_10, y + h / 2 + margin_5),
            color,
            DEFAULT_INDICATOR_SIZE * ui_scale * arrows_scale,
            rotation=90,
            arrow_length_factor=0.5,
        )
    if indicate_up:
        arrow(
            (x - margin_10, y + h / 2 - margin_5),
            color,
            DEFAULT_INDICATOR_SIZE * ui_scale * arrows_scale,
            rotation=-90,
            arrow_length_factor=0.5,
        )
    if indicate_left:
        arrow(
            (x + margin_5, y + h + margin_10),
            color,
            DEFAULT_INDICATOR_SIZE * ui_scale * arrows_scale,
            rotation=180,
            arrow_length_factor=0.5,
        )
    if indicate_right:
        arrow(
            (x + w - margin_5, y + h + margin_10),
            color,
            DEFAULT_INDICATOR_SIZE * ui_scale * arrows_scale,
            arrow_length_factor=0.5,
        )


def rounded_rectangle(
    x: float,
    y: float,
    w: float,
    h: float,
    round_radius: float,
    fill: bool = False,
    color: typing.Optional[Color] = None,
    round_corner: typing.Optional[typing.Tuple[bool, bool, bool, bool]] = None,
    line_thickness: float = 1.0,
):
    if color is None:
        color = (1.0, 1.0, 1.0, 1.0)

    if round_corner is None:
        round_corner = (True, True, True, True)

    num_verts = 16
    n = int(num_verts / 4) + 1
    dangle = math.pi * 2 / num_verts

    radius = [round_radius if rc else 0 for rc in round_corner]

    x_origin = [
        x + radius[0],
        x + w - radius[1],
        x + w - radius[2],
        x + radius[3],
    ]
    y_origin = [
        y + radius[0],
        y + radius[1],
        y + h - radius[2],
        y + h - radius[3],
    ]
    angle_start = [
        math.pi * 1.0,
        math.pi * 1.5,
        math.pi * 0.0,
        math.pi * 0.5,
    ]

    original_state = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')

    verts = []
    for x0, y0, angle, r in zip(x_origin, y_origin, angle_start, radius):
        for _ in range(n):
            x = x0 + r * math.cos(angle)
            y = y0 + r * math.sin(angle)
            if not fill:
                verts.append((x, y, 0))
            else:
                verts.append((x, y, 0))
            angle += dangle

    # repeat the first vertex to close the box
    verts.append(verts[0])

    shader = SHADER_2D_UNIFORM_COLOR_BUILTIN
    batch = gpu_extras.batch.batch_for_shader(
        shader,
        'TRI_FAN' if fill else 'LINE_STRIP',
        {"pos": verts},
    )
    original_width = gpu.state.line_width_get()
    gpu.state.line_width_set(line_thickness)

    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)

    gpu.state.blend_set(original_state)
    gpu.state.line_width_set(original_width)


def circle(center: mathutils.Vector, radius: float, color: Color, segments: int):
    gpu_extras.presets.draw_circle_2d(center, color, radius, segments=segments)


@dataclasses.dataclass
class TextStyle:
    """Style of rendered text

    If 'consider_ui_scale' is True, then actual 'font_size' is constructed
    on initialization based on preferences user interface scale
    """

    font_id: int = 0
    font_size: float = 15.0
    color: Color = (1.0, 1.0, 1.0, 1.0)
    dpi: int = 72
    consider_ui_scale: bool = True

    def __post_init__(self):
        if self.consider_ui_scale:
            self.font_size *= bpy.context.preferences.system.ui_scale


def text(pos: mathutils.Vector, string: str, style: TextStyle) -> None:
    blf.position(style.font_id, pos[0], pos[1], 0)
    _set_text_size(style)
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
    padding: float,
    text_margin: float,
    background: typing.Optional[Color],
    texts: typing.List[typing.Tuple[str, TextStyle]],
) -> None:
    height = sum(t[1].font_size for t in texts) + (len(texts) - 1) * text_margin
    width = _calculate_lines_width(texts) + 2 * padding
    if background is not None:
        rectangle(pos, (width, height + 2 * padding), background)

    x_pos = pos.x + padding
    y_pos = pos.y + height
    for string, style in texts:
        text((x_pos, y_pos), string, style)
        y_pos -= style.font_size + text_margin


def key_symbol(
    x: float,
    y: float,
    key: str,
    pressed: bool = False,
) -> None:
    """Draws a key symbol on (x, y) position on the screen. Considers Blender's ui scale."""
    ui_scale = bpy.context.preferences.system.ui_scale
    style = TextStyle(
        font_size=DEFAULT_INDICATOR_SIZE - 6,
        color=DEFAULT_INDICATOR_COLOR,
    )
    # Adjust font sized based on the length of the key (e. g. ESC, Shift, CTRL, F12)
    if len(key) > 2:
        style.font_size = style.font_size / (0.475 * len(key))

    text_width, text_height = get_text_size(key, style)
    size = DEFAULT_INDICATOR_SIZE * ui_scale
    # Draw outline rounded rectangle to indicate the key to press, if pressed draw filled rectangle
    rounded_rectangle(
        x,
        y,
        size,
        size,
        4.0 * ui_scale,
        line_thickness=2.0,
        fill=pressed,
        color=DEFAULT_INDICATOR_COLOR,
    )
    if pressed:
        # If pressed change the color to black, as we draw on the filled background.
        style.color = (0.1, 0.1, 0.1, 1.0)

    # Text aligned to the middle of the key
    text(
        mathutils.Vector((x + (size - text_width) * 0.5, y + (size - text_height) * 0.5)),
        key,
        style,
    )


def key_info(
    x: float,
    y: float,
    key: str,
    description: str,
    pressed: bool = False,
) -> None:
    """Draws a key symbol with a description on (x, y) position on the screen.

    Blender's ui scale is considered for all elements. If 'pressed' is True then the key
    will be drawn as filled with a black color text.
    """
    key_symbol(x, y, key, pressed)

    ui_scale = bpy.context.preferences.system.ui_scale
    style = TextStyle(font_size=DEFAULT_INDICATOR_SIZE - 4)
    _, text_height = get_text_size(description, style)
    text(
        mathutils.Vector(
            (
                x + (DEFAULT_INDICATOR_SIZE + 5) * ui_scale,
                y + (DEFAULT_INDICATOR_SIZE * ui_scale - text_height) * 0.5,
            )
        ),
        description,
        style,
    )


def mouse_info(
    x: float,
    y: float,
    description: str,
    left_click: bool = False,
    middle_click: bool = False,
    right_click: bool = False,
    indicate_left: bool = False,
    indicate_right: bool = False,
    indicate_up: bool = False,
    indicate_down: bool = False,
) -> None:
    """Draws a mouse symbol with a text description on (x, y) position on the screen.

    'left_click', 'middle_click', 'right_click' arguments can be used to indicate the mouse buttons
    pressed - making them filled.
    'indicate_left', 'indicate_right', 'indicate_up', 'indicate_down' arguments can be used to
    display arrows that indicate the direction of the mouse movement.

    Blender's ui scale is considered for all elements.
    """
    ui_scale = bpy.context.preferences.system.ui_scale
    mouse_width = DEFAULT_INDICATOR_SIZE * 0.75
    mouse_symbol(
        x,
        y,
        mouse_width * ui_scale,
        DEFAULT_INDICATOR_SIZE * ui_scale,
        left_click,
        middle_click,
        right_click,
        indicate_left,
        indicate_right,
        indicate_up,
        indicate_down,
        round_radius=DEFAULT_INDICATOR_SIZE * ui_scale / 4,
        color=DEFAULT_INDICATOR_COLOR,
    )

    style = TextStyle(font_size=DEFAULT_INDICATOR_SIZE - 4)
    _, text_height = get_text_size(description, style)
    text(
        mathutils.Vector(
            (
                x + (mouse_width + 5) * ui_scale,
                y + (DEFAULT_INDICATOR_SIZE * ui_scale - text_height) * 0.5,
            )
        ),
        description,
        style,
    )


def text_box_3d(
    world_pos: mathutils.Vector,
    padding: int,
    text_margin: float,
    background: typing.Optional[Color],
    texts: typing.List[typing.Tuple[str, TextStyle]],
    region: bpy.types.Region,
    rv3d: bpy.types.RegionView3D,
) -> None:
    """Draws text box based on world position aligned to view"""
    pos_2d = bpy_extras.view3d_utils.location_3d_to_region_2d(region, rv3d, world_pos)
    if pos_2d is not None:  # Do not draw if the position is behind the camera
        text_box(pos_2d, padding, text_margin, background, texts)


def get_text_size(string: str, style: TextStyle) -> typing.Tuple[float, float]:
    """Returns size of the text in pixels"""
    _set_text_size(style)
    return blf.dimensions(style.font_id, string)


def _calculate_lines_width(lines: typing.List[typing.Tuple[str, TextStyle]]) -> float:
    max_width = 0
    for string, style in lines:
        width, _ = get_text_size(string, style)
        max_width = max(max_width, width)
    return max_width


def _set_text_size(style: TextStyle) -> None:
    if bpy.app.version >= (4, 0, 0):  # dpi argument has been dropped in Blender 4.0
        blf.size(style.font_id, style.font_size)
    else:
        blf.size(style.font_id, style.font_size, style.dpi)
