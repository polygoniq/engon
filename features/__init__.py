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

from . import feature_utils
from . import asset_pack_panels

from . import colorize

from . import light_adjustments

from . import puddles
from . import aquatiq_paint_mask
from . import aquatiq_material_limitation_warning

from . import botaniq_adjustments
from . import botaniq_animations
from . import curve_scatter

from . import traffiq_paint_adjustments
from . import traffiq_wear
from . import traffiq_lights_settings
from . import traffiq_rigs
from . import emergency_lights
from . import license_plates_generator

from . import pictorial_wear
from . import pictorial_adjustments
from . import sculpture_wear

from . import road_generator
from . import vine_generator
from . import river_generator
from . import rain_generator

from . import frame_generator

from . import feature_pie_menu


def register():
    feature_utils.register()
    asset_pack_panels.register()

    colorize.register()
    light_adjustments.register()

    puddles.register()
    aquatiq_paint_mask.register()
    aquatiq_material_limitation_warning.register()

    botaniq_adjustments.register()
    botaniq_animations.register()
    curve_scatter.register()

    traffiq_paint_adjustments.register()
    traffiq_wear.register()
    traffiq_lights_settings.register()
    traffiq_rigs.register()

    pictorial_wear.register()
    pictorial_adjustments.register()
    sculpture_wear.register()

    license_plates_generator.register()
    emergency_lights.register()
    road_generator.register()
    vine_generator.register()
    river_generator.register()
    rain_generator.register()

    frame_generator.register()

    feature_pie_menu.register()


def unregister():
    feature_pie_menu.unregister()

    frame_generator.unregister()
    rain_generator.unregister()
    river_generator.unregister()
    vine_generator.unregister()
    road_generator.unregister()
    emergency_lights.unregister()
    license_plates_generator.unregister()

    sculpture_wear.unregister()
    pictorial_adjustments.unregister()
    pictorial_wear.unregister()

    traffiq_rigs.unregister()
    traffiq_lights_settings.unregister()
    traffiq_wear.unregister()
    traffiq_paint_adjustments.unregister()

    curve_scatter.unregister()
    botaniq_animations.unregister()
    botaniq_adjustments.unregister()

    light_adjustments.unregister()
    colorize.unregister()

    aquatiq_material_limitation_warning.unregister()
    aquatiq_paint_mask.unregister()
    puddles.unregister()

    asset_pack_panels.unregister()
    feature_utils.unregister()
