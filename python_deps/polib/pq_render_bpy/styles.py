# copyright (c) 2018- polygoniq xyz s.r.o.

import copy
import enum
import typing

from .. import color_utils_bpy


class SizeMode(enum.Enum):
    """How a width or height value is resolved during layout.

    * `AUTO`: minimum size to fit the node's content (or to padding/border/margin only if empty).
    * `FULL`: expand to fill all available space the parent can give along that axis.

    A plain `float` may be used instead to specify a fixed unscaled pixel size.
    """

    AUTO = "auto"
    FULL = "full"


class Direction(enum.IntEnum):
    """Main-axis direction for a flex container, analogous to CSS `flex-direction`."""

    ROW = 0
    ROW_REVERSE = 1
    COLUMN = 2
    COLUMN_REVERSE = 3


class JustifyContent(enum.IntEnum):
    """Alignment of children along a flex container's main axis."""

    FLEX_START = 0
    FLEX_END = 1
    CENTER = 2
    # Other options can be added as needed


class AlignItems(enum.IntEnum):
    """Alignment of children along a flex container's cross axis."""

    FLEX_START = 0
    FLEX_END = 1
    CENTER = 2
    # Other options can be added as needed


class Anchor(enum.IntEnum):
    """9-point anchor selecting which point on a node coincides with its reference position.

    Used by `RootFixed` (anchor relative to the viewport) and `RootProjected`
    (anchor relative to a screen-projected world position).
    """

    TOP_LEFT = 0
    TOP_CENTER = 1
    TOP_RIGHT = 2
    CENTER_LEFT = 3
    CENTER = 4
    CENTER_RIGHT = 5
    BOTTOM_LEFT = 6
    BOTTOM_CENTER = 7
    BOTTOM_RIGHT = 8


SizeValue = SizeMode | float
SpacingValue = float | tuple[float, float] | tuple[float, float, float, float]
CornerRadiusValue = float | tuple[float, float, float, float]

# Fully transparent color used as the default for `background`, `border_color` and other
# optional fills.
TRANSPARENT = color_utils_bpy.Color.from_linear(0.0, 0.0, 0.0, 0.0)


class Spacing(typing.NamedTuple):
    """Per-side spacing in CSS order: top, right, bottom, left."""

    top: float
    right: float
    bottom: float
    left: float

    @staticmethod
    def normalize_spacing(value: SpacingValue) -> "Spacing":
        """Normalize a CSS-style spacing shorthand to per-side Spacing.

        * float                  -> all four sides equal
        * (vertical, horizontal) -> top=bottom=vertical, left=right=horizontal
        * (t, r, b, l)           -> top, right, bottom, left
        """
        if not isinstance(value, tuple):
            return Spacing(value, value, value, value)
        if len(value) == 2:
            vertical, horizontal = value
            return Spacing(vertical, horizontal, vertical, horizontal)
        top, right, bottom, left = value
        return Spacing(top, right, bottom, left)


class CornerRadius(typing.NamedTuple):
    """Per-corner radii in CSS order: top-left, top-right, bottom-right, bottom-left."""

    top_left: float
    top_right: float
    bottom_right: float
    bottom_left: float

    @staticmethod
    def normalize_corner_radius(value: CornerRadiusValue) -> "CornerRadius":
        """Normalize a corner radius value to per-corner CornerRadius.

        * float            -> all four corners equal
        * (tl, tr, br, bl) -> top-left, top-right, bottom-right, bottom-left
        """
        if not isinstance(value, tuple):
            return CornerRadius(value, value, value, value)
        return CornerRadius(*value)


class Style:
    """Common visual and layout properties shared by every node.

    All sizes, paddings, margins, border thickness, offsets and corner radii are
    expressed in unscaled pixels and are multiplied by the Blender UI scale at draw
    time when `consider_ui_scale` is true.
    """

    def __init__(
        self,
        width: SizeValue = SizeMode.AUTO,
        height: SizeValue = SizeMode.AUTO,
        padding: SpacingValue = 0.0,
        margin: SpacingValue = 0.0,
        background: color_utils_bpy.Color = TRANSPARENT,
        border_color: color_utils_bpy.Color = TRANSPARENT,
        border_thickness: float = 0.0,
        corner_radius: CornerRadiusValue = 0.0,
        hidden: bool = False,
        consider_ui_scale: bool = True,
        anchor: Anchor = Anchor.TOP_LEFT,
        offset: tuple[float, float] = (0.0, 0.0),
        world_position: tuple[float, float, float] | None = None,
    ):
        """Create a style. See the matching properties for the meaning of each argument."""
        self._layout_callbacks: list[typing.Callable[[bool], None]] = []
        self._render_callbacks: list[typing.Callable[[], None]] = []
        self._width = width
        self._height = height
        self._padding = Spacing.normalize_spacing(padding)
        self._margin = Spacing.normalize_spacing(margin)
        self._background = background
        self._border_color = border_color
        self._border_thickness = border_thickness
        self._corner_radius = CornerRadius.normalize_corner_radius(corner_radius)
        self._hidden = hidden
        self._consider_ui_scale = consider_ui_scale
        self._anchor = anchor
        self._offset = offset
        self._world_position = world_position

    def subscribe_layout(self, callback: typing.Callable[[bool], None]) -> None:
        """Register `callback` to be invoked when a size/position-affecting property changes.

        The callback receives a `mark_self_dirty` flag: `True` when the owning node itself must
        be marked dirty, `False` when only its parent needs to recompute.
        """
        self._layout_callbacks.append(callback)

    def unsubscribe_layout(self, callback: typing.Callable[[bool], None]) -> None:
        """Remove a callback previously registered via `subscribe_layout`."""
        self._layout_callbacks.remove(callback)

    def subscribe_render(self, callback: typing.Callable[[], None]) -> None:
        """Register `callback` to be invoked when a render-only property changes (e.g. colors)."""
        self._render_callbacks.append(callback)

    def unsubscribe_render(self, callback: typing.Callable[[], None]) -> None:
        """Remove a callback previously registered via `subscribe_render`."""
        self._render_callbacks.remove(callback)

    def _notify_layout(self, self_dirty: bool = True) -> None:
        for callback in self._layout_callbacks:
            callback(self_dirty)

    def _notify_render(self) -> None:
        for callback in self._render_callbacks:
            callback()

    @property
    def width(self) -> SizeValue:
        """Node width along the horizontal axis.

        Accepted values:

        * `SizeMode.AUTO`: minimum size to fit the node's content.
        * `SizeMode.FULL`: expand to fill all horizontal space the parent can offer.
        * `float`: fixed unscaled pixel width. The content box is this value;
          padding, border and margin are added on top.
        """
        return self._width

    @width.setter
    def width(self, value: SizeValue) -> None:
        if self._width != value:
            self._width = value
            self._notify_layout()

    @property
    def height(self) -> SizeValue:
        """Node height along the vertical axis.

        Accepted values:

        * `SizeMode.AUTO`: minimum size to fit the node's content.
        * `SizeMode.FULL`: expand to fill all vertical space the parent can offer.
        * `float`: fixed pixel height. The content box is this value;
          padding, border and margin are added on top.
        """
        return self._height

    @height.setter
    def height(self, value: SizeValue) -> None:
        if self._height != value:
            self._height = value
            self._notify_layout()

    @property
    def padding(self) -> Spacing:
        """Inner spacing between the node's border and its content.

        Accepts:

        * `float`: same padding on all four sides.
        * `(vertical, horizontal)`: top/bottom and left/right.
        * `(top, right, bottom, left)`: per-side.

        Reading always returns a `Spacing` instance.
        """
        return self._padding

    @padding.setter
    def padding(self, value: SpacingValue) -> None:
        normalized = Spacing.normalize_spacing(value)
        if self._padding != normalized:
            self._padding = normalized
            self._notify_layout()

    @property
    def margin(self) -> Spacing:
        """Outer spacing between the node's border and its parent/siblings.

        Accepts:

        * `float`: same margin on all four sides.
        * `(vertical, horizontal)`: top/bottom and left/right.
        * `(top, right, bottom, left)`: per-side.

        Reading always returns a `Spacing` instance.
        """
        return self._margin

    @margin.setter
    def margin(self, value: SpacingValue) -> None:
        normalized = Spacing.normalize_spacing(value)
        if self._margin != normalized:
            self._margin = normalized
            self._notify_layout()

    @property
    def background(self) -> color_utils_bpy.Color:
        """Fill color of the node's box."""
        return self._background

    @background.setter
    def background(self, value: color_utils_bpy.Color) -> None:
        if self._background != value:
            self._background = value
            self._notify_render()

    @property
    def border_color(self) -> color_utils_bpy.Color:
        """Border color. The border is only drawn when both alpha and
        `border_thickness` are greater than zero."""
        return self._border_color

    @border_color.setter
    def border_color(self, value: color_utils_bpy.Color) -> None:
        if self._border_color != value:
            self._border_color = value
            self._notify_render()

    @property
    def border_thickness(self) -> float:
        """Border thickness in pixels. `0` disables the border."""
        return self._border_thickness

    @border_thickness.setter
    def border_thickness(self, value: float) -> None:
        if self._border_thickness != value:
            self._border_thickness = value
            self._notify_layout()

    @property
    def corner_radius(self) -> CornerRadius:
        """Per-corner rounding for the background and border, in pixels.

        Accepted values:

        * `float`: same radius on all four corners.
        * `(top_left, top_right, bottom_right, bottom_left)`: per-corner.

        Each radius is clamped at draw time to `min(width, height) / 2`.
        Reading returns a normalized `CornerRadius`.
        """
        return self._corner_radius

    @corner_radius.setter
    def corner_radius(self, value: CornerRadiusValue) -> None:
        normalized = CornerRadius.normalize_corner_radius(value)
        if self._corner_radius != normalized:
            self._corner_radius = normalized
            self._notify_render()

    @property
    def hidden(self) -> bool:
        """When `True` the node is skipped during layout calculations and rendering.

        Hidden flex children are excluded from main-axis size, gap and `justify_content`
        calculations, so toggling visibility re-flows the parent automatically.
        """
        return self._hidden

    @hidden.setter
    def hidden(self, value: bool) -> None:
        if self._hidden != value:
            self._hidden = value
            self._notify_layout()

    @property
    def consider_ui_scale(self) -> bool:
        """When `True` (default) every pixel-valued property is multiplied by the Blender
        UI scale (`preferences.system.ui_scale`) at draw time."""
        return self._consider_ui_scale

    @consider_ui_scale.setter
    def consider_ui_scale(self, value: bool) -> None:
        if self._consider_ui_scale != value:
            self._consider_ui_scale = value
            self._notify_layout()

    @property
    def anchor(self) -> Anchor:
        """Which of the 9 anchor points on the node is pinned to its reference position.

        Used by `RootFixed` (anchor relative to the viewport corners/edges/center) and
        `RootProjected` (anchor relative to the screen projection of `world_position`).
        Ignored by flex children.
        """
        return self._anchor

    @anchor.setter
    def anchor(self, value: Anchor) -> None:
        if self._anchor != value:
            self._anchor = value
            self._notify_layout()

    @property
    def offset(self) -> tuple[float, float]:
        """Additional `(x, y)` pixel displacement applied after `anchor`-based placement.

        Positive `x` moves right, positive `y` moves up (Blender's viewport y-up convention).
        Values are scaled by the UI scale when `consider_ui_scale` is true.
        Used by `RootFixed` and `RootProjected`; ignored by flex children.
        """
        return self._offset

    @offset.setter
    def offset(self, value: tuple[float, float]) -> None:
        if self._offset != value:
            self._offset = value
            self._notify_layout()

    @property
    def world_position(self) -> tuple[float, float, float] | None:
        """3D world-space position used by `RootProjected` to place the node.

        The position is projected to 2D screen coordinates every draw call; the node
        is hidden when the projection fails (e.g. point is behind the camera).
        `None` (the default) means the node is not projected. Ignored by `RootFixed`
        and flex children.
        """
        return self._world_position

    @world_position.setter
    def world_position(self, value: tuple[float, float, float] | None) -> None:
        if self._world_position != value:
            self._world_position = value
            # World position doesn't affect this node's layout, but the parent needs to
            # recompute position of siblings.
            self._notify_layout(self_dirty=False)

    def copy(self) -> typing.Self:
        """Return a shallow copy of this style with all subscribers cleared."""
        new = copy.copy(self)
        new._layout_callbacks = []
        new._render_callbacks = []
        return new


class StyleFlex(Style):
    """Style for a flex container that lays its children out along a main axis.

    Adds CSS-flexbox-like properties (`direction`, `justify_content`,
    `align_items`, `gap`) on top of the common `Style` properties.
    Children with `width`/`height` set to `SizeMode.FULL` grow to share any
    extra main-axis space; no children are ever shrunk below their base size
    (they overflow instead).
    """

    def __init__(
        self,
        width: SizeValue = SizeMode.AUTO,
        height: SizeValue = SizeMode.AUTO,
        padding: SpacingValue = 0.0,
        margin: SpacingValue = 0.0,
        background: color_utils_bpy.Color = TRANSPARENT,
        border_color: color_utils_bpy.Color = TRANSPARENT,
        border_thickness: float = 0.0,
        corner_radius: CornerRadiusValue = 0.0,
        hidden: bool = False,
        consider_ui_scale: bool = True,
        direction: Direction = Direction.ROW,
        justify_content: JustifyContent = JustifyContent.FLEX_START,
        align_items: AlignItems = AlignItems.FLEX_START,
        gap: float = 0.0,
        anchor: Anchor = Anchor.TOP_LEFT,
        offset: tuple[float, float] = (0.0, 0.0),
        world_position: tuple[float, float, float] | None = None,
    ):
        super().__init__(
            width=width,
            height=height,
            padding=padding,
            margin=margin,
            background=background,
            border_color=border_color,
            border_thickness=border_thickness,
            corner_radius=corner_radius,
            hidden=hidden,
            consider_ui_scale=consider_ui_scale,
            anchor=anchor,
            offset=offset,
            world_position=world_position,
        )
        self._direction = direction
        self._justify_content = justify_content
        self._align_items = align_items
        self._gap = gap

    @property
    def direction(self) -> Direction:
        """Which axis children are placed along and in which order.

        * `ROW` / `ROW_REVERSE`: horizontal main axis, vertical cross axis.
        * `COLUMN` / `COLUMN_REVERSE`: vertical main axis, horizontal cross axis.

        `*_REVERSE` variants place children from the opposite end.
        """
        return self._direction

    @direction.setter
    def direction(self, value: Direction) -> None:
        if self._direction != value:
            self._direction = value
            self._notify_layout()

    @property
    def justify_content(self) -> JustifyContent:
        """How leftover main-axis space is distributed when children do not fill the container.

        Has no effect once children overflow; in that case they always align to the start.
        """
        return self._justify_content

    @justify_content.setter
    def justify_content(self, value: JustifyContent) -> None:
        if self._justify_content != value:
            self._justify_content = value
            self._notify_layout()

    @property
    def align_items(self) -> AlignItems:
        """How each child is positioned along the cross axis within the container's content box."""
        return self._align_items

    @align_items.setter
    def align_items(self, value: AlignItems) -> None:
        if self._align_items != value:
            self._align_items = value
            self._notify_layout()

    @property
    def gap(self) -> float:
        """Spacing in pixels inserted between adjacent visible children along the main axis.

        Only applied between children, never before the first or after the last.
        """
        return self._gap

    @gap.setter
    def gap(self, value: float) -> None:
        if self._gap != value:
            self._gap = value
            self._notify_layout()


class StyleText(Style):
    """Style for a text node, adding font and color properties to the common `Style`.

    With `width` / `height` set to `SizeMode.AUTO` the node measures itself from
    the text content and font metrics; setting either to a fixed value or `SizeMode.FULL`
    keeps the text rendered at `font_size` and may clip it.
    """

    def __init__(
        self,
        width: SizeValue = SizeMode.AUTO,
        height: SizeValue = SizeMode.AUTO,
        padding: SpacingValue = 0.0,
        margin: SpacingValue = 0.0,
        background: color_utils_bpy.Color = TRANSPARENT,
        border_color: color_utils_bpy.Color = TRANSPARENT,
        border_thickness: float = 0.0,
        corner_radius: CornerRadiusValue = 0.0,
        hidden: bool = False,
        consider_ui_scale: bool = True,
        font_id: int = 0,
        font_size: float = 15.0,
        color: color_utils_bpy.Color = color_utils_bpy.Color.from_linear(0.0, 0.0, 0.0, 1.0),
        outline_color: color_utils_bpy.Color = TRANSPARENT,
        line_height: float = 1.2,
        anchor: Anchor = Anchor.TOP_LEFT,
        offset: tuple[float, float] = (0.0, 0.0),
        world_position: tuple[float, float, float] | None = None,
    ):
        super().__init__(
            width=width,
            height=height,
            padding=padding,
            margin=margin,
            background=background,
            border_color=border_color,
            border_thickness=border_thickness,
            corner_radius=corner_radius,
            hidden=hidden,
            consider_ui_scale=consider_ui_scale,
            anchor=anchor,
            offset=offset,
            world_position=world_position,
        )
        self._font_id = font_id
        self._font_size = font_size
        self._color = color
        self._outline_color = outline_color
        self._line_height = line_height

    @property
    def font_id(self) -> int:
        """Blender `blf` font id used to render the text. `0` is Blender's built-in default font."""
        return self._font_id

    @font_id.setter
    def font_id(self, value: int) -> None:
        if self._font_id != value:
            self._font_id = value
            self._notify_layout()

    @property
    def font_size(self) -> float:
        """Font size in pixels."""
        return self._font_size

    @font_size.setter
    def font_size(self, value: float) -> None:
        if self._font_size != value:
            self._font_size = value
            self._notify_layout()

    @property
    def color(self) -> color_utils_bpy.Color:
        """Fill color of the glyphs."""
        return self._color

    @color.setter
    def color(self, value: color_utils_bpy.Color) -> None:
        if self._color != value:
            self._color = value
            self._notify_render()

    @property
    def outline_color(self) -> color_utils_bpy.Color:
        """Outline color drawn around each glyph. Skipped when `alpha == 0` (the default)."""
        return self._outline_color

    @outline_color.setter
    def outline_color(self, value: color_utils_bpy.Color) -> None:
        if self._outline_color != value:
            self._outline_color = value
            self._notify_render()

    @property
    def line_height(self) -> float:
        """Multiplier applied to the font's measured height when computing the node's auto height.

        Only affects layout when `Style.height` is `SizeMode.AUTO`.
        """
        return self._line_height

    @line_height.setter
    def line_height(self, value: float) -> None:
        if self._line_height != value:
            self._line_height = value
            self._notify_layout()
