# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import os
import pathlib
import typing
import logging
import shutil
import enum
import functools
import OpenImageIO
from .. import mapr
from .. import polib
import hashlib


logger = logging.getLogger(f"polygoniq.{__name__}")

tile_manager = polib.preview_manager_bpy.PreviewManager()


class MapTileVariant(enum.StrEnum):
    """Enum for the two variants of map tiles."""

    SELECTED = "selected"
    UNSELECTED = "unselected"

    @classmethod
    def from_bool(cls, selected: bool) -> 'MapTileVariant':
        return cls.SELECTED if selected else cls.UNSELECTED


def get_tile_filename(selected: MapTileVariant, y: int, x: int) -> str:
    """Returns the filename of the tile for the given selection state and coordinates."""
    return f"{selected}_y{y}x{x}"


@functools.cache
def _get_current_map_tiles_hash() -> str:
    """Compute a hash based on the contents of selected.png and unselected.png."""
    hash_md5 = hashlib.md5()
    base_dir = pathlib.Path(__file__).parent / "map-tiles"
    for variant in MapTileVariant:
        file_path = base_dir / f"{variant}.png"
        if not file_path.exists():
            continue
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                hash_md5.update(chunk)
    return hash_md5.hexdigest()[:6]  # shorten for directory names


def _get_root_tiles_dir() -> pathlib.Path:
    """Get the blender-specific directory where versions of the tiles are stored."""

    return pathlib.Path(polib.utils_bpy.get_user_data_resource_path("engon")) / "map_tiles"


def _get_current_tiles_dir() -> pathlib.Path:
    """Get the blender-specific directory for the current version of the tiles."""
    return pathlib.Path(_get_root_tiles_dir()) / _get_current_map_tiles_hash()


def _ensure_and_empty_current_tiles_dir() -> pathlib.Path:
    """Get the blender-specific directory for the current version of the tiles.

    If the directory exists, it will be emptied (removed and recreated).
    """
    logger.info("Ensuring that the current tiles directory exists and is empty.")
    shutil.rmtree(_get_current_tiles_dir(), ignore_errors=True)
    try:
        os.makedirs(_get_current_tiles_dir())
    except FileExistsError:
        logger.exception(
            "Tiles directory already exists right after removing it. "
            "This can happen when running multiple Blender instances. "
            "Tiles may not be created correctly."
        )

    return _get_current_tiles_dir()


def _create_tiles(tiles_dir: pathlib.Path) -> None:
    """Split shipped map into tiles and save them in the given directory.

    Assumes existence of map-tiles/selected.png and map-tiles/unselected.png in engon.
    """

    tiles_x = mapr.filters.LocationParameterFilter.map_projection.max_x
    tiles_y = mapr.filters.LocationParameterFilter.map_projection.max_y

    for variant in MapTileVariant:
        path = pathlib.Path(__file__).parent / "map-tiles" / f"{variant}.png"
        if not path.exists():
            logger.error(
                f"Map tiles image not found: {path}. Map filter will contain no map icons."
            )
            return

        img = OpenImageIO.ImageBuf(str(path))
        if img.has_error:
            logger.error(
                f"Error opening image: {path} - {img.geterror()}. Map filter will contain no map icons."
            )
            return

        spec = img.spec()
        width, height = spec.width, spec.height

        if width % tiles_x != 0 or height % tiles_y != 0:
            logger.error(
                f"Image size {width}x{height} is not divisible by tile grid {tiles_x}x{tiles_y}. "
                f"Map tiles cannot be created correctly. Map filter will contain no map icons."
            )
            return

        tile_width = width // tiles_x
        tile_height = height // tiles_y

        if tile_width != 32 or tile_height != 32:
            logger.warning(
                f"Map tiles are not 32x32 pixels, but {tile_width}x{tile_height}. "
                f"This may cause issues with the map filter rendering."
            )

        tile_num = 0
        for y in range(tiles_y):
            for x in range(tiles_x):
                xmin = x * tile_width
                ymin = y * tile_height
                xmax = min(xmin + tile_width, width)
                ymax = min(ymin + tile_height, height)

                roi = OpenImageIO.ROI(xmin, xmax, ymin, ymax, 0, 1)
                tile = OpenImageIO.ImageBufAlgo.cut(img, roi)

                tile_filename = os.path.join(tiles_dir, f"{get_tile_filename(variant, y, x)}.png")
                try:
                    tile.write(tile_filename)
                except OSError:
                    logger.exception(
                        f"Error writing tile {tile_filename}. "
                        "This can happen when running multiple Blender instances. "
                        "Tiles may not be created correctly."
                    )
                tile_num += 1

        logger.info(f"{tile_num} map tiles of {variant} variant written to {tiles_dir}")


def _verify_tiles(tiles_dir: pathlib.Path) -> bool:
    """Verify that the tiles directory and the tile files are present."""

    if not tiles_dir.exists():
        return False

    for variant in MapTileVariant:
        for y in range(mapr.filters.LocationParameterFilter.map_projection.max_y):
            for x in range(mapr.filters.LocationParameterFilter.map_projection.max_x):
                tile_filename = get_tile_filename(variant, y, x) + ".png"
                tile_path = tiles_dir / tile_filename
                if not tile_path.exists():
                    return False
    return True


def ensure_tiles_ready() -> None:
    """Ensure that the tiles directory exists and contains the correct tiles. Removes old versions.

    If background mode is enabled, this function does nothing, as tiles are not needed.
    """

    if bpy.app.background:
        logger.info("Running in background mode, not ensuring tiles.")
        return

    tiles_dir = _get_current_tiles_dir()
    if not _verify_tiles(tiles_dir):
        logger.info(
            "Tiles directory does not exist or does not contain valid tiles, recreating tiles."
        )
        # remove the directory where all versions of the tiles are stored
        shutil.rmtree(_get_root_tiles_dir(), ignore_errors=True)
        # create the directory for only the current version of the tiles
        tiles_dir = _ensure_and_empty_current_tiles_dir()
        _create_tiles(tiles_dir)
    else:
        logger.info("Tiles directory contains valid tiles, no need to recreate.")


def _draw_map(
    layout: bpy.types.UILayout,
    property_owner: bpy.types.PropertyGroup | None,
    prop_name: str | None,
    selected_coords: list[list[bool]] | None,
    max_x: int,
    max_y: int,
    crop: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> None:
    top, bottom, left, right = crop
    interactive_mode = property_owner is not None and prop_name is not None
    static_mode = selected_coords is not None

    if not (interactive_mode ^ static_mode):
        raise ValueError("Either property_owner and prop_name or selected_coords must be provided.")

    layout.use_property_decorate = False

    map_tile_scale_x = 0.88
    map_tile_scale_y = 0.88

    row = layout.row(align=True)
    row.alignment = 'CENTER'
    row.scale_y = map_tile_scale_y
    row.scale_x = map_tile_scale_x
    for x in range(left, max_x - right):
        col = row.column(align=True)
        col.emboss = 'NONE'

        for y in range(top, max_y - bottom):
            if interactive_mode:
                selected = getattr(property_owner, prop_name)[y][x]
                col.prop(
                    property_owner,
                    prop_name,
                    index=y * max_x + x,
                    icon_only=True,
                    icon_value=tile_manager.get_icon_id(
                        get_tile_filename(MapTileVariant.from_bool(selected), y, x)
                    ),
                    text="",
                    toggle=True,
                )
            elif static_mode:
                selected = selected_coords[y][x]
                col.label(
                    icon_value=tile_manager.get_icon_id(
                        get_tile_filename(MapTileVariant.from_bool(selected), y, x)
                    ),
                )


def draw_map_interactive(
    layout: bpy.types.UILayout,
    property_owner: bpy.types.PropertyGroup,
    prop_name: str,
    max_x: int,
    max_y: int,
    crop: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> None:
    """Draws an interactive tiled max_x * max_y map in the given layout.

    The map controls a boolean vector property with the given name.
    """
    assert (
        getattr(property_owner, prop_name) != None
    ), f"Property owner must have a {prop_name} property."

    _draw_map(
        layout,
        property_owner,
        prop_name,
        None,
        max_x,
        max_y,
        crop=crop,
    )


def draw_map_static(
    layout: bpy.types.UILayout,
    selected_coords: list[list[bool]],
    max_x: int,
    max_y: int,
    crop: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> None:
    """Draws a static tiled max_x * max_y map in the given layout, with given tiles preselected."""

    col = layout.column(align=True)
    _draw_map(
        col,
        None,
        None,
        selected_coords,
        max_x,
        max_y,
        crop=crop,
    )


def register():
    ensure_tiles_ready()
    tile_manager.add_preview_path(str(_get_current_tiles_dir()))


def unregister():
    global tile_manager
    del tile_manager
