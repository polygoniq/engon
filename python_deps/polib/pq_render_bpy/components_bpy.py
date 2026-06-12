# copyright (c) 2018- polygoniq xyz s.r.o.

import enum
import dataclasses

from . import draw_2d_bpy
from . import styles
from . import ui_bpy
from .. import color_utils_bpy

DEFAULT_INDICATOR_SIZE = 20.0
DEFAULT_INDICATOR_COLOR: color_utils_bpy.Color = color_utils_bpy.Color.from_linear(
    0.0, 1.0, 0.361, 1.0
)  # engon green

ESCAPE_KEY = "ESC"
SHIFT_KEY = "\u21e7"
CTRL_KEY = "CTRL"
ALT_KEY = "ALT"
SPACE_KEY = "\u2423"

_KEY_BORDER_RADIUS = 6.0
_KEY_BORDER_THICKNESS = 2.5
_KEY_PRESSED_TEXT_COLOR: color_utils_bpy.Color = color_utils_bpy.Color.from_linear(
    0.1, 0.1, 0.1, 1.0
)

_DESCRIPTION_GAP = 8.0

_MOUSE_WIDTH_FACTOR = 0.75
_MOUSE_BORDER_THICKNESS = 2.0
_MOUSE_ARROW_THICKNESS = 1.0
_MOUSE_ARROW_SCALE = 0.45
_MOUSE_ARROW_MARGIN_LARGE = 10.0
_MOUSE_ARROW_BARB_HALF_WIDTH = 0.6


class _KeyLabel(ui_bpy.Text):
    """Text label for a key symbol.

    Automatically shrinks the font size if the text is too long to fit inside the key box.
    """

    @property
    def _effective_font_size(self) -> float:
        font_size = self.style.font_size
        if len(self._text) > 2:
            font_size = font_size / (0.475 * len(self._text))
        return font_size * self._scale


class KeySymbol(ui_bpy.Flex):
    """Rounded box with a key label."""

    def __init__(
        self,
        key: str,
        size: float = DEFAULT_INDICATOR_SIZE,
        color: color_utils_bpy.Color = DEFAULT_INDICATOR_COLOR,
        pressed: bool = False,
        pressed_text_color: color_utils_bpy.Color = _KEY_PRESSED_TEXT_COLOR,
        name: str | None = None,
    ):
        self._base_color = color
        self._pressed_text_color = pressed_text_color

        self._label = _KeyLabel(
            key,
            style=styles.StyleText(
                font_size=size - 6,
                color=color,
            ),
        )
        super().__init__(
            name=name,
            style=styles.StyleFlex(
                width=size,
                height=size,
                corner_radius=_KEY_BORDER_RADIUS,
                border_color=color,
                border_thickness=_KEY_BORDER_THICKNESS,
                justify_content=styles.JustifyContent.CENTER,
                align_items=styles.AlignItems.CENTER,
            ),
            children=[self._label],
        )
        self._pressed = False
        if pressed:
            self.pressed = True

    @property
    def key(self) -> str:
        return self._label.text

    @key.setter
    def key(self, value: str) -> None:
        self._label.text = value

    @property
    def pressed(self) -> bool:
        return self._pressed

    @pressed.setter
    def pressed(self, value: bool) -> None:
        if self._pressed != value:
            self._pressed = value
            if value:
                # Fill the box and switch to dark text
                self.style.background = self._base_color
                self._label.style.color = self._pressed_text_color
            else:
                # Set default background and text color
                self.style.background = styles.TRANSPARENT
                self._label.style.color = self._base_color


class MouseButton(enum.IntFlag):
    """Which mouse buttons are shown as pressed."""

    NONE = 0
    LEFT = enum.auto()
    MIDDLE = enum.auto()
    RIGHT = enum.auto()


class MouseArrow(enum.IntFlag):
    """Which directional arrows to display around the mouse icon."""

    NONE = 0
    LEFT = enum.auto()
    RIGHT = enum.auto()
    UP = enum.auto()
    DOWN = enum.auto()


class MouseSymbol(ui_bpy.Node[styles.Style]):
    """Mouse icon with 3 buttons and optional directional arrows."""

    def __init__(
        self,
        buttons: MouseButton = MouseButton.NONE,
        arrows: MouseArrow = MouseArrow.NONE,
        size: float = DEFAULT_INDICATOR_SIZE,
        color: color_utils_bpy.Color = DEFAULT_INDICATOR_COLOR,
        name: str | None = None,
    ):
        self._size = size
        arrow_offset = self._compute_arrow_offset(arrows)
        super().__init__(
            name=name,
            style=styles.Style(
                width=size * _MOUSE_WIDTH_FACTOR + arrow_offset,
                height=size,
                border_thickness=_MOUSE_BORDER_THICKNESS,
            ),
        )
        self._buttons = buttons
        self._arrows = arrows
        self._color = color
        self._arrow_offset = arrow_offset

    def _compute_arrow_offset(self, arrows: MouseArrow) -> float:
        """Extra unscaled horizontal space needed when UP/DOWN arrows are rendered to the left."""
        if MouseArrow.UP in arrows or MouseArrow.DOWN in arrows:
            arrow_half_width = self._size * _MOUSE_ARROW_SCALE * _MOUSE_ARROW_BARB_HALF_WIDTH
            return _MOUSE_ARROW_MARGIN_LARGE + arrow_half_width
        return 0.0

    @property
    def buttons(self) -> MouseButton:
        return self._buttons

    @buttons.setter
    def buttons(self, value: MouseButton) -> None:
        self._buttons = value

    @property
    def arrows(self) -> MouseArrow:
        return self._arrows

    @arrows.setter
    def arrows(self, value: MouseArrow) -> None:
        self._arrows = value
        self._arrow_offset = self._compute_arrow_offset(value)
        self.style.width = self._size * (_MOUSE_WIDTH_FACTOR + self._arrow_offset)

    def _draw(self) -> None:
        s = self._scale
        m = self.style.margin
        cx = self._x + m.left * s
        cy = self._y + m.bottom * s
        cw = self._width - (m.left + m.right) * s
        ch = self._height - (m.bottom + m.top) * s

        # When UP/DOWN arrows are present the style width is wider than the mouse body to reserve
        # space for the arrows on the left. Shift the body right so the arrows fit inside the box.
        body_cx = cx + self._arrow_offset * s
        body_cw = cw - self._arrow_offset * s

        round_radius = self._size * s / 4
        color = self._color

        # Mouse body (bottom half): round bottom corners only
        body_x, body_y, body_w, body_h = body_cx, cy, body_cw, ch / 2
        body_radii = (0.0, 0.0, round_radius, round_radius)

        # Buttons (top half): each 1/3 width.
        # Each button rect has width = (body_cw+2*bt)/3 and they are spaced (body_cw-bt)/3 apart.
        # This makes every shared divider and both outer edges produce exactly one visible
        # border line: adjacent rects overlap by bt so their borders land on the same pixels.
        # Vertically, start bt lower so the button bottom borders overlap the body top border.
        bt = _MOUSE_BORDER_THICKNESS * s
        btn_w = (body_cw + 2 * bt) / 3
        btn_spacing = (body_cw - bt) / 3
        btn_y = cy + ch / 2 - bt
        btn_h = ch / 2 + bt
        left_btn_x = body_cx
        mid_btn_x = body_cx + btn_spacing
        right_btn_x = body_cx + 2 * btn_spacing
        left_btn_radii = (round_radius, 0.0, 0.0, 0.0)
        mid_btn_radii = (0.0, 0.0, 0.0, 0.0)
        right_btn_radii = (0.0, round_radius, 0.0, 0.0)

        # Body outline
        draw_2d_bpy.draw_rect(
            body_x,
            body_y,
            body_w,
            body_h,
            body_radii,
            border_thickness=bt,
            fill_col=styles.TRANSPARENT,
            border_col=color,
        )

        # Buttons
        for b_x, radii, flag in (
            (left_btn_x, left_btn_radii, MouseButton.LEFT),
            (mid_btn_x, mid_btn_radii, MouseButton.MIDDLE),
            (right_btn_x, right_btn_radii, MouseButton.RIGHT),
        ):
            draw_2d_bpy.draw_rect(
                b_x,
                btn_y,
                btn_w,
                btn_h,
                radii,
                border_thickness=bt,
                fill_col=color if flag in self._buttons else styles.TRANSPARENT,
                border_col=color,
            )

        # Directional arrows
        margin_l = _MOUSE_ARROW_MARGIN_LARGE * s
        arrow_size = self._size * s * _MOUSE_ARROW_SCALE
        arrow_thickness = _MOUSE_ARROW_THICKNESS * s
        half_arrow = arrow_size * 0.5
        if MouseArrow.DOWN in self._arrows:
            draw_2d_bpy.draw_arrow(
                body_cx - margin_l,
                cy + ch / 2 + half_arrow,
                arrow_size,
                rotation=90,
                color=color,
                line_thickness=arrow_thickness,
                arrow_length_factor=0.5,
            )
        if MouseArrow.UP in self._arrows:
            draw_2d_bpy.draw_arrow(
                body_cx - margin_l,
                cy + ch / 2 - half_arrow,
                arrow_size,
                rotation=-90,
                color=color,
                line_thickness=arrow_thickness,
                arrow_length_factor=0.5,
            )
        if MouseArrow.LEFT in self._arrows:
            draw_2d_bpy.draw_arrow(
                body_cx + body_cw / 2 - half_arrow,
                cy + ch + margin_l,
                arrow_size,
                rotation=180,
                color=color,
                line_thickness=arrow_thickness,
                arrow_length_factor=0.5,
            )
        if MouseArrow.RIGHT in self._arrows:
            draw_2d_bpy.draw_arrow(
                body_cx + body_cw / 2 + half_arrow,
                cy + ch + margin_l,
                arrow_size,
                color=color,
                line_thickness=arrow_thickness,
                arrow_length_factor=0.5,
            )


@dataclasses.dataclass
class _KeySpec:
    """Lightweight specification for a key symbol inside an InputCombo component."""

    key: str
    pressed: bool = False


@dataclasses.dataclass
class _MouseSpec:
    """Lightweight specification for a mouse symbol inside an InputCombo component."""

    buttons: MouseButton = MouseButton.NONE
    arrows: MouseArrow = MouseArrow.NONE


class InputCombo(ui_bpy.Flex):
    """Combination of mouse and/or key symbols with a single text description.

    Groups multiple input indicators (mouse icons, key boxes) into a single tight row
    followed by a description label. All symbols share the same size and color.
    """

    Mouse = _MouseSpec
    Key = _KeySpec

    def __init__(
        self,
        description: str,
        inputs: list[_MouseSpec | _KeySpec],
        size: float = DEFAULT_INDICATOR_SIZE,
        color: color_utils_bpy.Color = DEFAULT_INDICATOR_COLOR,
        pressed_text_color: color_utils_bpy.Color = _KEY_PRESSED_TEXT_COLOR,
        name: str | None = None,
    ):
        self._symbols: list[KeySymbol | MouseSymbol] = []
        for spec in inputs:
            if isinstance(spec, _MouseSpec):
                self._symbols.append(
                    MouseSymbol(buttons=spec.buttons, arrows=spec.arrows, size=size, color=color)
                )
            elif isinstance(spec, _KeySpec):
                self._symbols.append(
                    KeySymbol(
                        spec.key,
                        pressed=spec.pressed,
                        size=size,
                        color=color,
                        pressed_text_color=pressed_text_color,
                    )
                )

        self._description_text = ui_bpy.Text(
            description,
            style=styles.StyleText(
                font_size=size - 4,
                color=color_utils_bpy.Color.from_linear(1.0, 1.0, 1.0, 1.0),
                outline_color=color_utils_bpy.Color.from_linear(0.0, 0.0, 0.0, 1.0),
            ),
        )
        super().__init__(
            name=name,
            style=styles.StyleFlex(
                align_items=styles.AlignItems.CENTER,
                gap=_DESCRIPTION_GAP,
            ),
            children=[*self._symbols, self._description_text],
        )

    @property
    def symbols(self) -> list[KeySymbol | MouseSymbol]:
        return self._symbols

    @property
    def description(self) -> str:
        return self._description_text.text

    @description.setter
    def description(self, value: str) -> None:
        self._description_text.text = value


class ColorSwatch(ui_bpy.Node[styles.Style]):
    """Simple colored rectangle with a border, used for showing color indicators in the UI.

    Color is taken from the style.background property.
    """

    def _draw(self) -> None:
        # Same as Node._draw, but draw unconditionally and with different draw method
        s = self._scale
        m = self.style.margin
        cr = self.style.corner_radius
        draw_2d_bpy.draw_color_swatch(
            self._x + m.left * s,
            self._y + m.bottom * s,
            self._width - (m.left + m.right) * s,
            self._height - (m.bottom + m.top) * s,
            (cr[0] * s, cr[1] * s, cr[2] * s, cr[3] * s),
            self.style.border_thickness * s,
            self.style.background,
            self.style.border_color,
        )
