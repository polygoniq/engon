# copyright (c) 2018- polygoniq xyz s.r.o.

import abc
import bpy
import bpy_extras.view3d_utils
import mathutils
import logging
import typing

from . import draw_2d_bpy
from . import styles

_StyleT = typing.TypeVar("_StyleT", bound=styles.Style)

# Set to True to log detailed UI recalculation trace messages.
LOG_RECALCULATION = False

logger = logging.getLogger(f"polygoniq.{__name__}")
logger.setLevel(logging.DEBUG if LOG_RECALCULATION else logging.INFO)

_trace_depth: int = 0


def _node_desc(node: object) -> str:
    cls = type(node).__name__
    name = getattr(node, '_name', None)
    if name is not None:
        return f'"{name}" ({cls})'
    return f"({cls})"


def _trace_push(node: object) -> None:
    """Log a trace message and increase nesting depth."""
    global _trace_depth
    if LOG_RECALCULATION:
        logger.debug("%s+ %s", "|" * _trace_depth, _node_desc(node))
        _trace_depth += 1


def _trace_pop() -> None:
    """Decrease nesting depth."""
    global _trace_depth
    if LOG_RECALCULATION:
        _trace_depth = max(0, _trace_depth - 1)


def _trace_log(msg: str) -> None:
    """Log a trace message at the current nesting depth."""
    if LOG_RECALCULATION:
        logger.debug("%s  %s", "|" * _trace_depth, msg)


# NOTE on layout calculation and caching:
#
# Layout uses a two-pass, dirty-flag-based system. The dirty flag is managed via two complementary
# mechanisms so that `_precalculate_layout` can skip entire subtrees with a single flag check:
#
#   * Push-up (structural changes): When a node's style, text, or child list changes,
#     `_on_layout_changed()` sets `_dirty = True` and propagates upward to all ancestors via
#     subscribed callbacks, so the root is always aware that something in the tree changed.
#
#   * Push-down (global external changes): At the start of each draw call, the root checks for
#     global state that is out of the tree's control (ui_scale, viewport/region size, camera
#     matrix). If ui_scale changed, the root calls `mark_all_dirty()` to push `_dirty = True`
#     downward to every node in the tree. Viewport and camera changes only set the root itself
#     dirty, since they affect layout only at the root level.
#
# Pass 1 — _precalculate_layout (top-down): Each node checks `_dirty` and returns early if
# clean, avoiding any further work. When dirty it updates its scale, recalculates cached sizes
# (additional, base, max) bottom-up, and returns True so the caller knows a layout pass is needed.
#
# Pass 2 — _recalculate_layout (top-down): Runs only if Pass 1 returned True. Distributes
# available space to children based on precalculated sizes. Individual nodes may skip
# recalculation if their size and position have not changed since the last calculation.


def _get_ui_region_width() -> float:
    """Return the width of the UI region (N-panel) in the current 3D viewport."""
    area = bpy.context.area
    if area is None or area.type != 'VIEW_3D':
        return 0.0
    for region in area.regions:
        if region.type == 'UI':
            return float(region.width)
    return 0.0


class Element(abc.ABC):
    """Base class for all elements that can be drawn in the viewport."""

    def __init__(self, name: str | None = None):
        self._name = name
        self._dirty = True
        self._layout_changed_callbacks: list[typing.Callable[[], None]] = []

    def subscribe_layout_change(self, callback: typing.Callable[[], None]) -> None:
        """Subscribe to layout changes of this element.

        The callback will be called whenever the layout of this element or any of its children changes,
        unless this element is already marked dirty.
        Updating scale won't trigger layout change notifications.
        """
        self._layout_changed_callbacks.append(callback)

    def unsubscribe_layout_change(self, callback: typing.Callable[[], None]) -> None:
        """Unsubscribe from layout changes of this element."""
        self._layout_changed_callbacks.remove(callback)

    def _on_layout_changed(self, mark_self_dirty: bool = True) -> None:
        if self._dirty:
            # Already dirty, no need to propagate further or notify callbacks
            return
        if mark_self_dirty:
            self._dirty = True
        for callback in self._layout_changed_callbacks:
            callback()

    def mark_all_dirty(self) -> None:
        """Mark this element and all descendants as dirty. Does not propagate to parents."""
        self._dirty = True


class Node(typing.Generic[_StyleT], Element):
    """Base class for all elements that can be drawn in the viewport.

    Can be used on its own to render empty styled boxes.
    """

    def __init__(self, style: _StyleT, name: str | None = None):
        super().__init__(name)

        self._style: _StyleT = style
        self._style.subscribe_layout(self._on_layout_changed)

        # Layout cache, recalculated in _precalculate_layout and used in layout calculation
        self._additional_width: float = 0.0
        self._additional_height: float = 0.0
        self._base_width: float = 0.0
        self._base_height: float = 0.0
        self._max_width: float = 0.0
        self._max_height: float = 0.0

        # Bottom left corner of the node in the viewport coordinate system
        self._x = 0
        self._y = 0
        # Size assigned by a parent, includes padding, border, and margin
        self._width = 0.0
        self._height = 0.0

        self._scale: float = 1.0

        # Tag that can be used to mark this node as "Do not render" by parent node.
        # If a parent decides to use this tag, it has to set it before using.
        self.render_tag: bool = True

    @property
    def style(self) -> _StyleT:
        return self._style

    @style.setter
    def style(self, value: _StyleT) -> None:
        self._style.unsubscribe_layout(self._on_layout_changed)
        self._style = value
        self._style.subscribe_layout(self._on_layout_changed)
        self._on_layout_changed()

    @property
    def ui_scale(self) -> float:
        return bpy.context.preferences.system.ui_scale

    def _update_scale(self) -> None:
        """Recompute the cached scale factor from the current ui_scale."""
        self._scale = self.ui_scale if self._style.consider_ui_scale else 1.0

    def _precalculate_additional_sizes(self) -> None:
        self._additional_width = (
            self.style.padding.left
            + self.style.padding.right
            + self.style.margin.left
            + self.style.margin.right
            + 2 * self.style.border_thickness
        ) * self._scale
        self._additional_height = (
            self.style.padding.top
            + self.style.padding.bottom
            + self.style.margin.top
            + self.style.margin.bottom
            + 2 * self.style.border_thickness
        ) * self._scale

    @property
    def additional_width(self) -> float:
        """The additional width added to the node by its style (padding, margin, border)."""
        return self._additional_width

    @property
    def additional_height(self) -> float:
        """The additional height added to the node by its style (padding, margin, border)."""
        return self._additional_height

    def _precalculate_base_sizes(self) -> None:
        if isinstance(self.style.width, styles.SizeMode):
            self._base_width = self.additional_width
        else:
            self._base_width = self.style.width * self._scale + self.additional_width
        if isinstance(self.style.height, styles.SizeMode):
            self._base_height = self.additional_height
        else:
            self._base_height = self.style.height * self._scale + self.additional_height

    @property
    def base_width(self) -> float:
        return self._base_width

    @property
    def base_height(self) -> float:
        return self._base_height

    def _precalculate_max_sizes(self) -> None:
        self._max_width = (
            float("inf") if self.style.width == styles.SizeMode.FULL else self.base_width
        )
        self._max_height = (
            float("inf") if self.style.height == styles.SizeMode.FULL else self.base_height
        )

    @property
    def max_width(self) -> float:
        return self._max_width

    @property
    def max_height(self) -> float:
        return self._max_height

    def _precalculate_layout(self) -> bool:
        """Precalculate any values needed for layout calculation.

        Returns True if the layout needs to be recalculated after precalculation
        (e.g. if any precalculated values changed).
        """
        if not self._dirty:
            _trace_log("not dirty")
            return False

        if self.style.hidden:
            # Nothing will be rendered => we can skip any calculations, but we have to mark
            # the node as clean, so it can be correctly marked dirty again when it becomes visible.
            self._dirty = False
            _trace_log("hidden")
            return False

        # Order of precalculation matters — later steps depend on values calculated in earlier steps,
        # so they must be done in this specific order.
        self._update_scale()
        self._precalculate_additional_sizes()
        self._precalculate_base_sizes()
        self._precalculate_max_sizes()

        _trace_log("recalculated")
        return True

    def _set_position(self, x: int, y: int) -> None:
        """Set the node's absolute position without recalculating layout."""
        self._x = x
        self._y = y

    def _recalculate_layout(
        self, x: int = 0, y: int = 0, width: float = 0.0, height: float = 0.0
    ) -> None:
        """Recalculate the layout of the node based on the given dimensions and the node's style."""
        self._x = x
        self._y = y
        self._width = width
        self._height = height

        self._dirty = False

    def _draw(self) -> None:
        # Draw only if there is something to draw (background or border)
        if self.style.background.alpha > 0.0 or (
            self.style.border_thickness > 0.0 and self.style.border_color.alpha > 0.0
        ):
            s = self._scale
            m = self.style.margin
            cr = self.style.corner_radius
            draw_2d_bpy.draw_rect(
                self._x + m.left * s,
                self._y + m.bottom * s,
                self._width - (m.left + m.right) * s,
                self._height - (m.bottom + m.top) * s,
                (cr[0] * s, cr[1] * s, cr[2] * s, cr[3] * s),
                self.style.border_thickness * s,
                self.style.background,
                self.style.border_color,
            )


class Text(Node[styles.StyleText]):
    """Single-line text element, analogous to an HTML <span>."""

    def __init__(
        self,
        text: str,
        style: styles.StyleText | None = None,
        name: str | None = None,
    ):
        super().__init__(style=style if style is not None else styles.StyleText(), name=name)
        self._text = text

    @property
    def text(self) -> str:
        return self._text

    @text.setter
    def text(self, value: str) -> None:
        if self._text != value:
            self._text = value
            self._on_layout_changed()

    @property
    def _effective_font_size(self) -> float:
        return self.style.font_size * self._scale

    def _precalculate_base_sizes(self) -> None:
        # Width
        if isinstance(self.style.width, styles.SizeMode):
            text_w, _ = draw_2d_bpy.measure_text(
                self.style.font_id, self._effective_font_size, self._text
            )
            self._base_width = text_w + self.additional_width
        else:
            self._base_width = self.style.width * self._scale + self.additional_width

        # Height
        if isinstance(self.style.height, styles.SizeMode):
            # Height is measured independently of the text content to avoid per-glyph differences
            _, text_h = draw_2d_bpy.measure_text(self.style.font_id, self._effective_font_size)
            self._base_height = text_h * self.style.line_height + self.additional_height
        else:
            self._base_height = self.style.height * self._scale + self.additional_height

    def _draw(self) -> None:
        super()._draw()
        s = self._scale
        content_x = (
            self._x
            + (self.style.margin.left + self.style.padding.left + self.style.border_thickness) * s
        )
        content_bottom = (
            self._y
            + (self.style.margin.bottom + self.style.padding.bottom + self.style.border_thickness)
            * s
        )
        content_h = (
            self._height
            - (
                self.style.margin.bottom
                + self.style.margin.top
                + self.style.padding.bottom
                + self.style.padding.top
                + 2 * self.style.border_thickness
            )
            * s
        )
        font_size = self._effective_font_size
        # Center based on the font's cap height (measured from "X") rather than the content-specific
        # height. This avoids per-glyph measurement differences from blf.dimensions and gives a
        # consistent baseline position for all text at the same font size.
        _, text_h = draw_2d_bpy.measure_text(self.style.font_id, font_size)
        content_y = content_bottom + (content_h - text_h) / 2
        draw_2d_bpy.draw_text(
            content_x,
            content_y,
            self._text,
            self.style.font_id,
            font_size,
            self.style.color,
            self.style.outline_color,
        )


class ContainerMixin(abc.ABC):
    """Mixin for elements that can contain children.

    Provides child management and layout change propagation.
    Concrete classes must initialize self._children and implement _on_layout_changed().
    """

    _children: list[Node]

    @property
    def children(self) -> typing.Iterator[Node]:
        return iter(self._children)

    @abc.abstractmethod
    def _on_layout_changed(self) -> None:
        """Called when a child's layout changes or the child list is modified."""
        ...

    def __getitem__(self, index: int) -> Node:
        return self._children[index]

    def __len__(self) -> int:
        return len(self._children)

    def add_child(self, child: Node) -> None:
        self._children.append(child)
        child.subscribe_layout_change(self._on_layout_changed)
        self._on_layout_changed()

    def insert_child(self, index: int, child: Node) -> None:
        self._children.insert(index, child)
        child.subscribe_layout_change(self._on_layout_changed)
        self._on_layout_changed()

    def remove_child(self, child: Node) -> None:
        self._children.remove(child)
        child.unsubscribe_layout_change(self._on_layout_changed)
        self._on_layout_changed()

    def remove_children_range(self, start: int, stop: int) -> None:
        """Remove children in the slice [start:stop]."""
        removed = self._children[start:stop]
        del self._children[start:stop]
        for child in removed:
            child.unsubscribe_layout_change(self._on_layout_changed)
        if len(removed) > 0:
            self._on_layout_changed()

    def reorder_child(self, child: Node, index: int) -> None:
        self._children.remove(child)
        self._children.insert(index, child)
        self._on_layout_changed()

    def extend_children(self, children: list[Node]) -> None:
        for child in children:
            self._children.append(child)
            child.subscribe_layout_change(self._on_layout_changed)
        self._on_layout_changed()

    def clear_children(self) -> None:
        for child in self._children:
            child.unsubscribe_layout_change(self._on_layout_changed)
        self._children.clear()
        self._on_layout_changed()

    def mark_all_children_dirty(self) -> None:
        """Mark all children as dirty. Override to restrict which children are marked."""
        for child in self._children:
            child.mark_all_dirty()

    def draw_tagged_children(self) -> None:
        """Draw children that are tagged with `render_tag = True`."""
        for child in self._children:
            if child.render_tag:
                child._draw()


class Flex(Node[styles.StyleFlex], ContainerMixin):

    def __init__(
        self,
        children: list[Node] | None = None,
        style: styles.StyleFlex | None = None,
        name: str | None = None,
    ):
        super().__init__(style=style if style is not None else styles.StyleFlex(), name=name)
        self._children: list[Node] = []
        if children is not None:
            self.extend_children(children)

        # Layout cache, recalculated in _precalculate_layout and used in layout calculation
        self._children_base_width_cache: float = 0.0
        self._children_base_height_cache: float = 0.0
        self._children_rel_positions: list[tuple[int, int]] = []
        self._visible_children_cache: list[Node] = []

    def mark_all_dirty(self) -> None:
        """Mark this node and all descendants as dirty without propagating to parents."""
        self._dirty = True
        self.mark_all_children_dirty()

    def _main(self, w: float, h: float) -> float:
        """Returns the size along the main axis based on the flex direction."""
        return (
            w if self.style.direction in (styles.Direction.ROW, styles.Direction.ROW_REVERSE) else h
        )

    def _cross(self, w: float, h: float) -> float:
        """Returns the size along the cross axis based on the flex direction."""
        return (
            h if self.style.direction in (styles.Direction.ROW, styles.Direction.ROW_REVERSE) else w
        )

    def _precalculate_visible_children(self) -> None:
        self._visible_children_cache = [child for child in self._children if not child.style.hidden]

    @property
    def _visible_children(self) -> list[Node]:
        """All children that are rendered (i.e. not hidden by style)."""
        return self._visible_children_cache

    @property
    def _total_gap(self) -> float:
        """Sum of all gap space between visible children along the main axis."""
        visible_count = len(self._visible_children)
        if visible_count <= 1:
            return 0.0
        return self.style.gap * self._scale * (visible_count - 1)

    def _precalculate_children_base_sizes(self) -> None:
        # Width
        if len(self._visible_children) == 0:
            self._children_base_width_cache = 0.0
        elif self.style.direction in (styles.Direction.ROW, styles.Direction.ROW_REVERSE):
            self._children_base_width_cache = (
                sum(child.base_width for child in self._visible_children) + self._total_gap
            )
        else:
            self._children_base_width_cache = max(
                child.base_width for child in self._visible_children
            )

        # Height
        if len(self._visible_children) == 0:
            self._children_base_height_cache = 0.0
        elif self.style.direction in (styles.Direction.COLUMN, styles.Direction.COLUMN_REVERSE):
            self._children_base_height_cache = (
                sum(child.base_height for child in self._visible_children) + self._total_gap
            )
        else:
            self._children_base_height_cache = max(
                child.base_height for child in self._visible_children
            )

    @property
    def _children_base_width(self) -> float:
        """The base width of the children along the main axis.

        Calculated based on the flex direction:
        * For ROW/ROW_REVERSE: sum of all children's base widths + total gap
        * For COLUMN/COLUMN_REVERSE: maximum base width among children
        """
        return self._children_base_width_cache

    @property
    def _children_base_height(self) -> float:
        """The base height of the children along the main axis.

        Calculated based on the flex direction:
        * For ROW/ROW_REVERSE: maximum base height among children
        * For COLUMN/COLUMN_REVERSE: sum of all children's base heights + total gap
        """
        return self._children_base_height_cache

    def _precalculate_base_sizes(self) -> None:
        # Width
        if isinstance(self.style.width, styles.SizeMode):
            self._base_width = self._children_base_width + self.additional_width
        else:
            self._base_width = self.style.width * self._scale + self.additional_width

        # Height
        if isinstance(self.style.height, styles.SizeMode):
            self._base_height = self._children_base_height + self.additional_height
        else:
            self._base_height = self.style.height * self._scale + self.additional_height

    def _compute_flex_factors(self, main_available_size: float) -> tuple[float, float]:
        """Returns `(main_children_size, extra_space_per_full_item)` for the current visible children.

        * `main_children_size` is the total size of the children along the main axis including gaps and any extra space added to "FULL" items.
        * `extra_space_per_full_item` is the extra space to add to each "FULL" child.

        Children are never shrunk below their base size — they overflow instead.
        """
        children_available = main_available_size - self._total_gap
        children_with_gaps_size = self._main(self._children_base_width, self._children_base_height)
        children_only_size = children_with_gaps_size - self._total_gap

        # If there is extra space, calculate grow size for "FULL" items
        full_children_count = sum(
            1
            for child in self._visible_children
            if self._main(child.max_width, child.max_height) == float("inf")
        )
        if full_children_count > 0 and children_available > children_only_size:
            extra_space_per_full_item = (
                children_available - children_only_size
            ) / full_children_count
            return main_available_size, extra_space_per_full_item
        return children_with_gaps_size, 0.0

    def _compute_main_axis_offset(
        self, main_available_size: float, main_actual_children_size: float
    ) -> float:
        """Returns the initial main-axis offset for the first child based on `justify_content`.

        `main_actual_children_size` is the total size of the children along the main axis,
        including gaps and any extra space added to "FULL" items.
        """
        if (
            self.style.justify_content == styles.JustifyContent.FLEX_START
            or main_available_size <= main_actual_children_size
        ):  # FLEX_START or overflow case: align to start and let overflow over the end
            return 0.0
        elif self.style.justify_content == styles.JustifyContent.CENTER:
            return (main_available_size - main_actual_children_size) / 2
        else:  # FLEX_END
            return main_available_size - main_actual_children_size

    def _compute_cross_axis_offset(
        self, child: Node, cross_available_size: float
    ) -> tuple[float, float]:
        """Returns `(child_cross_axis_size, child_cross_axis_offset)` based on `align_items`."""
        # Try to fill the available space along the cross axis while respecting the child's max size.
        # Never shrink below base size - overflow instead.
        child_cross_axis_size = max(
            self._cross(child.base_width, child.base_height),
            min(self._cross(child.max_width, child.max_height), cross_available_size),
        )
        if self.style.align_items == styles.AlignItems.FLEX_START:
            child_cross_axis_offset = 0.0
        elif self.style.align_items == styles.AlignItems.CENTER:
            child_cross_axis_offset = (cross_available_size - child_cross_axis_size) / 2
        else:  # FLEX_END
            child_cross_axis_offset = cross_available_size - child_cross_axis_size
        return child_cross_axis_size, child_cross_axis_offset

    def _precalculate_layout(self) -> bool:
        if not self._dirty:
            _trace_log("not dirty")
            return False

        if self.style.hidden:
            # Nothing will be rendered => we can skip any calculations, but we have to mark
            # the node as clean, so it can be correctly marked dirty again when it becomes visible.
            self._dirty = False
            _trace_log("hidden")
            return False

        # Order of precalculation matters — later steps depend on values calculated in earlier steps,
        # so they must be done in this specific order.
        for child in self._children:
            if child._dirty:
                _trace_push(child)
                child._precalculate_layout()
                _trace_pop()

        self._update_scale()
        self._precalculate_visible_children()
        self._precalculate_children_base_sizes()
        self._precalculate_additional_sizes()
        self._precalculate_base_sizes()
        self._precalculate_max_sizes()

        _trace_log("recalculated")
        return True

    def _set_position(self, x: int, y: int) -> None:
        """Set the node's absolute position and recursively update children from stored relative offsets."""
        self._x = x
        self._y = y
        for child, (rel_x, rel_y) in zip(self._visible_children, self._children_rel_positions):
            child._set_position(x + rel_x, y + rel_y)

    def _recalculate_layout(
        self, x: int = 0, y: int = 0, width: float = 0.0, height: float = 0.0
    ) -> None:
        """Recalculate the layout of the node and its children based on the given dimensions and the node's style."""
        if not self._dirty and width == self._width and height == self._height:
            if x == self._x and y == self._y:
                _trace_log("unchanged, skipping recalculation")
                return
            # Only position changed — set children positions directly from stored relative offsets
            self._set_position(x, y)
            _trace_log("position-only update")
            return

        super()._recalculate_layout(x, y, width, height)

        # Calculate the available space for children after accounting for padding
        available_width = self._width - self.additional_width
        available_height = self._height - self.additional_height
        main_available_size = self._main(available_width, available_height)
        cross_available_size = self._cross(available_width, available_height)

        # Calculate grow related values
        main_children_size, extra_space_per_full_item = self._compute_flex_factors(
            main_available_size
        )
        # Compute initial offset along the main axis based on justify_items
        main_axis_offset = self._compute_main_axis_offset(main_available_size, main_children_size)

        # Content-area offsets relative to this node's origin — self._x / self._y are added
        # only at the call site to avoid computing absolute coords and subtracting them back.
        rel_left_x = (
            self.style.margin.left + self.style.padding.left + self.style.border_thickness
        ) * self._scale
        # Top of the content area; vertical placement goes downward in Blender's y-up coordinate system
        rel_top_y = (
            self._height
            - (self.style.margin.top + self.style.padding.top + self.style.border_thickness)
            * self._scale
        )
        scaled_gap = self.style.gap * self._scale
        is_forward = self.style.direction in (styles.Direction.ROW, styles.Direction.COLUMN)
        children = self._visible_children if is_forward else reversed(self._visible_children)
        if len(self._children_rel_positions) != len(self._visible_children):
            self._children_rel_positions = [(0, 0)] * len(self._visible_children)
        for i, child in enumerate(children):
            child_main_axis_size = self._main(child.base_width, child.base_height)
            if self._main(child.max_width, child.max_height) == float("inf"):
                child_main_axis_size += extra_space_per_full_item

            child_cross_axis_size, child_cross_axis_offset = self._compute_cross_axis_offset(
                child, cross_available_size
            )

            _trace_push(child)
            # Set the layout of the child based on the calculated sizes and positions
            if self.style.direction in (styles.Direction.ROW, styles.Direction.ROW_REVERSE):
                rel_x = round(rel_left_x + main_axis_offset)
                # Cross axis is vertical: offset from rel_top_y downward must include the cross axis
                # offset and size as we are setting left bottom corner of the child
                rel_y = round(rel_top_y - child_cross_axis_offset - child_cross_axis_size)
                child._recalculate_layout(
                    x=self._x + rel_x,
                    y=self._y + rel_y,
                    width=child_main_axis_size,
                    height=child_cross_axis_size,
                )
            else:
                rel_x = round(rel_left_x + child_cross_axis_offset)
                # Main axis is vertical: children stack top-to-bottom
                rel_y = round(rel_top_y - main_axis_offset - child_main_axis_size)
                child._recalculate_layout(
                    x=self._x + rel_x,
                    y=self._y + rel_y,
                    width=child_cross_axis_size,
                    height=child_main_axis_size,
                )
            _trace_pop()

            if is_forward:
                self._children_rel_positions[i] = (rel_x, rel_y)
            else:
                self._children_rel_positions[len(self._visible_children) - 1 - i] = (rel_x, rel_y)
            main_axis_offset += child_main_axis_size + scaled_gap

    def _draw(self) -> None:
        super()._draw()
        for child in self._visible_children:
            child._draw()


class RootElement(Element, ContainerMixin):
    """Base class for UI root elements.

    Concrete subclasses must implement _check_external_change() and recalculate_layout().
    """

    def __init__(
        self,
        children: list[Node] | None = None,
        name: str | None = None,
    ):
        super().__init__(name)
        self._children: list[Node] = []
        if children is not None:
            self.extend_children(children)

        self._last_ui_scale: float = 1.0

    def mark_all_dirty(self) -> None:
        """Mark this node and all descendants as dirty without propagating to parents."""
        self._dirty = True
        self.mark_all_children_dirty()

    @abc.abstractmethod
    def _check_external_change(self) -> bool:
        """Return True if an external state (viewport size, camera matrix, ...) has changed."""
        ...

    def _check_ui_scale(self) -> bool:
        """Return True and mark all children dirty if the ui_scale has changed since last check."""
        current_ui_scale = bpy.context.preferences.system.ui_scale
        if current_ui_scale != self._last_ui_scale:
            self._last_ui_scale = current_ui_scale
            self.mark_all_dirty()
            _trace_log("ui scale changed, marking all children dirty")
            return True
        return False

    def _precalculate_dirty_children(self) -> None:
        """Call _precalculate_layout on all non-hidden dirty children."""
        for child in self._children:
            if child._dirty:
                _trace_push(child)
                child._precalculate_layout()
                _trace_pop()

    def _precalculate_layout(self) -> bool:
        self._check_ui_scale()
        external_changed = self._check_external_change()

        if not self._dirty and not external_changed:
            _trace_log("not dirty and no external change")
            return False

        self._precalculate_dirty_children()

        _trace_log("dirty or external change, triggering layout recalculation")
        return True

    @abc.abstractmethod
    def recalculate_layout(self) -> None:
        """Force recalculation of the layout."""
        ...

    def draw(self) -> None:
        _trace_log(f"Drawing {type(self).__name__} - checking if layout needs recalculation")
        _trace_push(self)
        needs_recalc = self._precalculate_layout()
        _trace_pop()
        _trace_log(f"Layout needs recalculation: {needs_recalc}")

        if needs_recalc:
            self.recalculate_layout()
        self.draw_tagged_children()  # Root uses tagged drawing to allow skipping children that are e.g. behind the camera


class RootFixed(RootElement):
    """Top-level container that positions children at fixed viewport anchor points.

    Use when children should be independently positioned relative to the viewport.
    Each child's anchor and offset are read from its style.
    """

    def __init__(
        self,
        children: list[Node] | None = None,
        avoid_ui_region_overlap: bool = False,
        name: str | None = None,
    ):
        super().__init__(children=children, name=name)
        self._avoid_ui_region_overlap = avoid_ui_region_overlap
        self._viewport_width: float = 0.0
        self._viewport_height: float = 0.0

    def _check_external_change(self) -> bool:
        width = float(bpy.context.region.width)
        if self._avoid_ui_region_overlap:
            width = max(width - _get_ui_region_width(), 0.0)
        height = float(bpy.context.region.height)

        if self._viewport_width != width or self._viewport_height != height:
            self._viewport_width = width
            self._viewport_height = height
            return True
        return False

    def _compute_child_position(self, child: Node) -> tuple[int, int, float, float]:
        """Compute (x, y, width, height) for a child based on its anchor and offset."""
        scale = child._scale
        vw = self._viewport_width
        vh = self._viewport_height

        # Resolve child size: inf max size means fill the viewport
        child_w = min(child.max_width, vw)
        child_h = min(child.max_height, vh)

        anchor = child.style.anchor
        offset_x = child.style.offset[0] * scale
        offset_y = child.style.offset[1] * scale

        # Compute horizontal reference and child x
        anchor_col = anchor % 3  # 0=LEFT, 1=CENTER, 2=RIGHT
        if anchor_col == 0:  # LEFT
            x = offset_x
        elif anchor_col == 1:  # CENTER
            x = vw / 2 - child_w / 2 + offset_x
        else:  # RIGHT
            x = vw - child_w + offset_x

        # Compute vertical reference and child y (bottom-left origin, y-up)
        anchor_row = anchor // 3  # 0=TOP, 1=CENTER, 2=BOTTOM
        if anchor_row == 0:  # TOP
            y = vh - child_h + offset_y
        elif anchor_row == 1:  # CENTER
            y = vh / 2 - child_h / 2 + offset_y
        else:  # BOTTOM
            y = offset_y

        return round(x), round(y), child_w, child_h

    def recalculate_layout(self) -> None:
        _trace_log("Recalculating layout")
        for child in self._children:
            if child.style.hidden:
                child.render_tag = False
                continue
            x, y, w, h = self._compute_child_position(child)
            _trace_push(child)
            child._recalculate_layout(x=x, y=y, width=w, height=h)
            child.render_tag = True
            _trace_pop()
        self._dirty = False
        _trace_log("Recalculation done")


class RootProjected(RootElement):
    """Top-level container that positions children at 3D world-space positions projected to screen.

    Each child's `style.world_position` determines where in 3D space it is anchored.
    The 3D position is projected to 2D screen space every draw call. Children whose
    position projects behind the camera (or have no world_position set) are not drawn.

    The child's `style.anchor` controls which point on the child coincides with the
    projected screen position (e.g. CENTER means the child is centered on the point).
    The child's `style.offset` adds additional pixel displacement from the projected point.
    """

    def __init__(
        self,
        children: list[Node] | None = None,
        name: str | None = None,
    ):
        super().__init__(children=children, name=name)
        self._perspective_matrix: mathutils.Matrix | None = None

    def _compute_child_position(self, child: Node) -> tuple[int, int, float, float] | None:
        """Compute (x, y, width, height) for a child based on its world_position projection.

        Returns None if the position is behind the camera or world_position is not set.
        """
        world_pos = child.style.world_position
        if world_pos is None:
            return None

        region = bpy.context.region
        rv3d = bpy.context.region_data
        if region is None or rv3d is None:
            return None

        pos_2d = bpy_extras.view3d_utils.location_3d_to_region_2d(region, rv3d, world_pos)
        if pos_2d is None:
            return None

        scale = child._scale
        px, py = pos_2d.x, pos_2d.y
        child_w = child.base_width
        child_h = child.base_height

        anchor = child.style.anchor
        offset_x = child.style.offset[0] * scale
        offset_y = child.style.offset[1] * scale

        # The projected point sits at the anchor position ON the child
        anchor_col = anchor % 3  # 0=LEFT, 1=CENTER, 2=RIGHT
        if anchor_col == 0:  # LEFT
            x = px + offset_x
        elif anchor_col == 1:  # CENTER
            x = px - child_w / 2 + offset_x
        else:  # RIGHT
            x = px - child_w + offset_x

        anchor_row = anchor // 3  # 0=TOP, 1=CENTER, 2=BOTTOM
        if anchor_row == 0:  # TOP
            y = py - child_h + offset_y
        elif anchor_row == 1:  # CENTER
            y = py - child_h / 2 + offset_y
        else:  # BOTTOM
            y = py + offset_y

        return round(x), round(y), child_w, child_h

    def _check_external_change(self) -> bool:
        """Check if the perspective matrix has changed since the last check."""
        rv3d = bpy.context.region_data
        if rv3d is None:
            return False
        current = rv3d.perspective_matrix.copy()
        if self._perspective_matrix != current:
            self._perspective_matrix = current
            return True
        return False

    def recalculate_layout(self) -> None:
        _trace_log("Recalculating layout")
        for child in self._children:
            if child.style.hidden:
                child.render_tag = False
                continue
            result = self._compute_child_position(child)
            if result is None:
                child.render_tag = False
                continue
            x, y, w, h = result
            _trace_push(child)
            child._recalculate_layout(x=x, y=y, width=w, height=h)
            child.render_tag = True
            _trace_pop()

        _trace_log("Sorting children")
        # Sort children back-to-front so closer elements overdraw farther ones.
        # View-space Z is negative in front of the camera; more negative = farther away.
        # Timsort/Powersort is O(n) for nearly-sorted data, which is the typical case between frames.
        rv3d = bpy.context.region_data
        if rv3d is not None:
            vm = rv3d.view_matrix
            self._children.sort(
                key=lambda child: (
                    (vm @ mathutils.Vector(child.style.world_position)).z
                    if child.style.world_position is not None
                    else float("inf")
                )
            )

        self._dirty = False
        _trace_log("Recalculation done")
