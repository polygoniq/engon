# copyright (c) 2018- polygoniq xyz s.r.o.

import math
import mathutils
import blf
import gpu
import gpu.matrix
import gpu_extras.batch

from .. import color_utils_bpy

rect_data_struct = """
struct RectData {
    vec4 rect;
    vec4 radii;
    vec4 fill_color;
    vec4 border_color;
    float border_thickness;
};
"""

rect_vertex_shader = """
void main() {
    // rect.xy = bottom-left pos, rect.zw = size
    vec2 pos_scaled = pos * rect_data.rect.zw;

    // Move the quad geometry to the requested bottom-left position
    vec2 pos_final = pos_scaled + rect_data.rect.xy;

    // Transform for Blender's 2D Viewport
    gl_Position = ModelViewProjectionMatrix * vec4(pos_final, 0.0, 1.0);

    // Pass normalized UVs to the fragment shader
    frag_uv = pos; // (0 to 1)

    // Offset to center so the SDF in the fragment shader can treat origin as center
    pixel_coords = pos_scaled - rect_data.rect.zw * 0.5;
}
"""

fragment_shader_helpers = """
// Per-corner SDF for a rounded rectangle (Inigo Quilez technique).
// p: pixel coordinate offset from rect center
// b: half-width, half-height (size / 2.0)
// r: per-corner radii (top-left, top-right, bottom-right, bottom-left)
float sdRoundedBox(vec2 p, vec2 b, vec4 r) {
    // Select radius based on which quadrant the pixel is in
    r.xy = (p.y > 0.0) ? r.xy : r.wz;
    r.x  = (p.x < 0.0) ? r.x  : r.y;
    vec2 q = abs(p) - b + r.x;
    return min(max(q.x, q.y), 0.0) + length(max(q, 0.0)) - r.x;
}
"""

rect_fragment_shader = fragment_shader_helpers + """
void main() {
    // rect.zw = size
    vec2 half_dim = rect_data.rect.zw * 0.5;

    // Calculate Distance to the true boundary of the rounded rectangle
    // Distance > 0 = outside, < 0 = inside, 0.0 = exactly on the edge
    float d = sdRoundedBox(pixel_coords, half_dim, rect_data.radii);

    // We use smoothstep to define a fuzzy transition area.
    // This creates smooth edges regardless of the thickness or radius.
    float antialias_fuzz = 2;
    // Expand shape by half the fuzz range to prevent edge clipping on circles
    float alpha = 1.0 - smoothstep(0.0, antialias_fuzz, d + antialias_fuzz / 2);

    // If pixel is completely outside the alpha range, kill it early
    if (alpha <= 0.01) { discard; }

    // Check how close we are to the boundary from the inside
    float border_dist = abs(d);

    // Determine how much 'border' influence should be present (0 to 1)
    float border_mask = 1.0 - smoothstep(rect_data.border_thickness - antialias_fuzz, rect_data.border_thickness, border_dist);

    vec4 final_color = mix(rect_data.fill_color, rect_data.border_color, border_mask);
    // Apply the distance-based alpha for the main smooth boundary
    fragColor = vec4(final_color.rgb, final_color.a * alpha);
}
"""

color_swatch_fragment_shader = fragment_shader_helpers + """
    vec4 checkered_color(vec2 coord) {
        float check_size = 5.0; // Size of each check in pixels
        float check_x = floor(coord.x / check_size);
        float check_y = floor(coord.y / check_size);
        // Linear values converted from sRGB UI-picked grays (160, 100 out of 255)
        if (mod(check_x + check_y, 2.0) < 1.0) {
            return vec4(0.352, 0.352, 0.352, 1.0); // Light gray
        } else {
            return vec4(0.127, 0.127, 0.127, 1.0); // Dark gray
        }
    }

    void main() {
        // rect.zw = size
        vec2 half_dim = rect_data.rect.zw * 0.5;

        // Calculate Distance to the true boundary of the rounded rectangle
        // Distance > 0 = outside, < 0 = inside, 0.0 = exactly on the edge
        float d = sdRoundedBox(pixel_coords, half_dim, rect_data.radii);

        // We use smoothstep to define a fuzzy transition area.
        // This creates smooth edges regardless of the thickness or radius.
        float antialias_fuzz = 2;
        // Expand shape by half the fuzz range to prevent edge clipping on circles
        float alpha = 1.0 - smoothstep(0.0, antialias_fuzz, d + antialias_fuzz / 2);

        // If pixel is completely outside the alpha range, kill it early
        if (alpha <= 0.01) { discard; }

        // Check how close we are to the boundary from the inside
        float border_dist = abs(d);

        // Determine how much 'border' influence should be present (0 to 1)
        float border_mask = 1.0 - smoothstep(rect_data.border_thickness - antialias_fuzz, rect_data.border_thickness, border_dist);

        // Fill for the left half is always fully opaque, there is checkered pattern visible on the right half when fill alpha is low
        vec4 fill_color = vec4(rect_data.fill_color.rgb, pixel_coords.x < 0.0 ? 1.0 : rect_data.fill_color.a);
        fill_color  = mix(checkered_color(pixel_coords), fill_color, fill_color.a);

        vec4 final_color = mix(fill_color, rect_data.border_color, border_mask);
        // Apply the distance-based alpha for the main smooth boundary
        fragColor = vec4(final_color.rgb, alpha);
    }
"""


_rect_shader = None
_rect_batch = None
_rect_ubo = None  # TODO: Ideally, we would use a separate UBO for each rectangle which updates only when the rectangle changes


def _ensure_rect_gpu_resources() -> None:
    global _rect_shader, _rect_batch, _rect_ubo
    if _rect_shader is not None:
        return

    vert_iface = gpu.types.GPUStageInterfaceInfo("sdf_rect_iface")
    vert_iface.smooth('VEC2', "frag_uv")
    vert_iface.smooth('VEC2', "pixel_coords")

    shader_info = gpu.types.GPUShaderCreateInfo()
    shader_info.push_constant('MAT4', "ModelViewProjectionMatrix")
    shader_info.typedef_source(rect_data_struct)
    shader_info.uniform_buf(0, "RectData", "rect_data")
    shader_info.vertex_in(0, 'VEC2', "pos")
    shader_info.vertex_out(vert_iface)
    shader_info.fragment_out(0, 'VEC4', "fragColor")
    shader_info.vertex_source(rect_vertex_shader)
    shader_info.fragment_source(rect_fragment_shader)

    _rect_shader = gpu.shader.create_from_info(shader_info)

    rect_ubo_buffer = gpu.types.Buffer('FLOAT', 20)  # 4x vec4 + 1 float + padding
    _rect_ubo = gpu.types.GPUUniformBuf(rect_ubo_buffer)

    coords = [(0, 0), (1, 0), (1, 1), (0, 1)]
    indices = [(0, 1, 2), (0, 2, 3)]
    _rect_batch = gpu_extras.batch.batch_for_shader(
        _rect_shader, 'TRIS', {"pos": coords}, indices=indices
    )


_arrow_shader = None
_arrow_batches: dict[tuple, gpu.types.GPUBatch] = {}


def _ensure_arrow_gpu_resources() -> None:
    global _arrow_shader
    if _arrow_shader is not None:
        return
    _arrow_shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')


_color_swatch_shader = None
_color_swatch_batch = None
_color_swatch_ubo = None


def _ensure_color_swatch_gpu_resources() -> None:
    global _color_swatch_shader, _color_swatch_batch, _color_swatch_ubo
    if _color_swatch_shader is not None:
        return

    # Color swatch is basically a rect shader but with a custom fill
    vert_iface = gpu.types.GPUStageInterfaceInfo("sdf_color_swatch_iface")
    vert_iface.smooth('VEC2', "frag_uv")
    vert_iface.smooth('VEC2', "pixel_coords")

    shader_info = gpu.types.GPUShaderCreateInfo()
    shader_info.push_constant('MAT4', "ModelViewProjectionMatrix")
    shader_info.typedef_source(rect_data_struct)
    shader_info.uniform_buf(0, "RectData", "rect_data")
    shader_info.vertex_in(0, 'VEC2', "pos")
    shader_info.vertex_out(vert_iface)
    shader_info.fragment_out(0, 'VEC4', "fragColor")
    shader_info.vertex_source(rect_vertex_shader)
    shader_info.fragment_source(color_swatch_fragment_shader)

    _color_swatch_shader = gpu.shader.create_from_info(shader_info)

    color_swatch_ubo_buffer = gpu.types.Buffer('FLOAT', 20)  # 4x vec4 + 1 float + padding
    _color_swatch_ubo = gpu.types.GPUUniformBuf(color_swatch_ubo_buffer)

    coords = [(0, 0), (1, 0), (1, 1), (0, 1)]
    indices = [(0, 1, 2), (0, 2, 3)]
    _color_swatch_batch = gpu_extras.batch.batch_for_shader(
        _color_swatch_shader, 'TRIS', {"pos": coords}, indices=indices
    )


def draw_rect(
    x: float,
    y: float,
    width: float,
    height: float,
    radius: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
    border_thickness: float = 0.0,
    fill_col: color_utils_bpy.Color = color_utils_bpy.Color.from_linear(0.0, 0.0, 0.0, 1.0),
    border_col: color_utils_bpy.Color = color_utils_bpy.Color.from_linear(0.0, 0.0, 0.0, 1.0),
) -> None:
    """Draw a rectangle with optional rounded corners and border.

    `radius` is a tuple of 4 floats for per-corner radii in order
    (top-left, top-right, bottom-right, bottom-left).
    """
    _ensure_rect_gpu_resources()
    assert (
        _rect_shader is not None and _rect_batch is not None and _rect_ubo is not None
    ), "GPU resources failed to initialize"

    original_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    _rect_shader.bind()

    max_r = min(width, height) / 2.0
    clamped = tuple(min(float(r), max_r) for r in radius)

    new_buffer_data = gpu.types.Buffer(
        'FLOAT',
        20,
        (
            # vec4 rect
            x,
            y,
            width,
            height,
            # vec4 radii
            *clamped,
            # vec4 fill_color
            *fill_col.linear,
            # vec4 border_color
            *border_col.linear,
            # float border_thickness
            border_thickness,
            # padding to align to vec4
            0.0,
            0.0,
            0.0,
        ),
    )
    _rect_ubo.update(new_buffer_data)
    _rect_shader.uniform_block("rect_data", _rect_ubo)

    _rect_batch.draw(_rect_shader)
    gpu.state.blend_set(original_blend)


def draw_circle(
    x: float,
    y: float,
    radius: float,
    border_thickness: float = 0.0,
    fill_col: color_utils_bpy.Color = color_utils_bpy.Color.from_linear(0.0, 0.0, 0.0, 1.0),
    border_col: color_utils_bpy.Color = color_utils_bpy.Color.from_linear(0.0, 0.0, 0.0, 1.0),
) -> None:
    diameter = radius * 2
    draw_rect(
        x,
        y,
        diameter,
        diameter,
        (radius, radius, radius, radius),
        border_thickness,
        fill_col,
        border_col,
    )


def _get_arrow_base_verts(
    draw_stem: bool,
    stem_length_factor: float,
    arrow_length_factor: float,
) -> tuple[tuple[float, float], ...]:
    """Return normalized arrow vertices (in 0-1 space, centered at 0.5) for the given shape."""
    arrow_length = max(0.0, min(1.0, 1.0 - arrow_length_factor))
    if draw_stem:
        return (
            (max(0.0, min(1.0, 1.0 - stem_length_factor)), 0.5),
            (1.0, 0.5),
            (arrow_length, 0.8),
            (1.0, 0.5),
            (arrow_length, 0.2),
        )
    return (
        (arrow_length, 0.8),
        (1.0, 0.5),
        (arrow_length, 0.2),
    )


def draw_arrow(
    x: float,
    y: float,
    size: float,
    rotation: float = 0.0,
    color: color_utils_bpy.Color = color_utils_bpy.Color.from_linear(1.0, 1.0, 1.0, 1.0),
    line_thickness: float = 1.0,
    draw_stem: bool = True,
    stem_length_factor: float = 0.75,
    arrow_length_factor: float = 0.4,
) -> None:
    """Draw a 2D arrow at (x, y) with the given size and rotation (in degrees).

    Rotation: 0=right, 90=down, 180=left, -90=up (screen coordinates).
    The base arrow shape is cached per unique (draw_stem, stem_length_factor, arrow_length_factor)
    combination to avoid creating a new batch every frame.
    """
    _ensure_arrow_gpu_resources()
    assert _arrow_shader is not None, "GPU resources failed to initialize"

    cache_key = (draw_stem, stem_length_factor, arrow_length_factor)
    batch = _arrow_batches.get(cache_key)
    if batch is None:
        base_verts = _get_arrow_base_verts(draw_stem, stem_length_factor, arrow_length_factor)
        # Pre-center to [-1, 1] range so the draw loop only needs rotate + scale + translate
        centered = tuple(((vx - 0.5) * 2, (vy - 0.5) * 2) for vx, vy in base_verts)
        batch = gpu_extras.batch.batch_for_shader(_arrow_shader, 'LINE_STRIP', {"pos": centered})
        _arrow_batches[cache_key] = batch

    original_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')

    _arrow_shader.bind()
    # Set uniforms for `POLYLINE_UNIFORM_COLOR` shader
    _arrow_shader.uniform_float("color", color.srgb)
    _arrow_shader.uniform_float("lineWidth", line_thickness)
    _arrow_shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])

    # Push custom transform matrix on top of ModelViewProjectionMatrix
    rotation_rad = math.radians(rotation)
    cos_r = math.cos(rotation_rad)
    sin_r = math.sin(rotation_rad)
    with gpu.matrix.push_pop():
        gpu.matrix.multiply_matrix(
            mathutils.Matrix(
                (
                    (cos_r * size, -sin_r * size, 0.0, x),
                    (sin_r * size, cos_r * size, 0.0, y),
                    (0.0, 0.0, 1.0, 0.0),
                    (0.0, 0.0, 0.0, 1.0),
                )
            )
        )
        batch.draw(_arrow_shader)

    gpu.state.blend_set(original_blend)


def draw_color_swatch(
    x: float,
    y: float,
    width: float,
    height: float,
    radius: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
    border_thickness: float = 0.0,
    fill_col: color_utils_bpy.Color = color_utils_bpy.Color.from_linear(0.0, 0.0, 0.0, 1.0),
    border_col: color_utils_bpy.Color = color_utils_bpy.Color.from_linear(0.0, 0.0, 0.0, 1.0),
) -> None:
    """Draw a color swatch rectangle with optional rounded corners and border.

    `radius` is a tuple of 4 floats for per-corner radii in order
    (top-left, top-right, bottom-right, bottom-left).
    """
    _ensure_color_swatch_gpu_resources()
    assert (
        _color_swatch_shader is not None
        and _color_swatch_batch is not None
        and _color_swatch_ubo is not None
    ), "GPU resources failed to initialize"

    original_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')
    _color_swatch_shader.bind()

    max_r = min(width, height) / 2.0
    clamped = tuple(min(float(r), max_r) for r in radius)

    new_buffer_data = gpu.types.Buffer(
        'FLOAT',
        20,
        (
            # vec4 rect
            x,
            y,
            width,
            height,
            # vec4 radii
            *clamped,
            # vec4 fill_color
            *fill_col.linear,
            # vec4 border_color
            *border_col.linear,
            # float border_thickness
            border_thickness,
            # padding to align to vec4
            0.0,
            0.0,
            0.0,
        ),
    )
    _color_swatch_ubo.update(new_buffer_data)
    _color_swatch_shader.uniform_block("rect_data", _color_swatch_ubo)

    _color_swatch_batch.draw(_color_swatch_shader)
    gpu.state.blend_set(original_blend)


def measure_text(font_id: int, font_size: float, text: str = "X") -> tuple[float, float]:
    """Return (width, height) of `text` rendered at `font_size` with `font_id`.

    We use a default text of "X" to get the content independent line height.
    """
    blf.size(font_id, font_size)
    return blf.dimensions(font_id, text)


def draw_text(
    x: float,
    y: float,
    text: str,
    font_id: int,
    font_size: float,
    color: color_utils_bpy.Color,
    outline_color: color_utils_bpy.Color = color_utils_bpy.Color.from_linear(0.0, 0.0, 0.0, 0.0),
) -> None:
    blf.position(font_id, x, y, 0)
    blf.size(font_id, font_size)
    blf.color(font_id, *color.srgb)
    if outline_color.alpha > 0.0:
        blf.enable(font_id, blf.SHADOW)
        blf.shadow(font_id, 6, *outline_color.srgb)
        blf.shadow_offset(font_id, 0, 0)
    blf.draw(font_id, text)
    if outline_color.alpha > 0.0:
        blf.disable(font_id, blf.SHADOW)
