# copyright (c) 2018- polygoniq xyz s.r.o.

from . import country_locations

# Definition of tags that can be manually added to the asset in grumpy_cat. Each tag maps to a
# dictionary where more details can be specified. Including a description that is used as a tooltip.
# Keep in mind that in addition to these, assets can have tags not on this list!
TAGS = {
    "Bathroom": {"description": ""},
    "Bedroom": {"description": ""},
    "Cafe": {"description": ""},
    "Decoration": {"description": ""},
    "Dining": {"description": ""},
    "Electronics": {"description": ""},
    "Enterprise": {"description": ""},
    "Entertainment": {"description": ""},
    "Textiles": {"description": ""},
    "Furniture": {"description": ""},
    "Hallway": {"description": ""},
    "Indoor": {"description": ""},
    "Kids": {"description": ""},
    "Kitchen": {"description": ""},
    "Library": {"description": ""},
    "Lights": {"description": ""},
    "Living room": {"description": ""},
    "Lobby": {"description": ""},
    "Music": {"description": ""},
    "Office": {"description": ""},
    "Outdoor": {"description": ""},
    "Park": {"description": ""},
    "Playground": {"description": ""},
    "Restaurant": {"description": ""},
    "Rigged": {"description": "Asset that has a rig for animation"},
    "Utilities": {"description": ""},
    "Sanitary": {"description": ""},
    "Spring": {"description": ""},
    "Summer": {"description": ""},
    "Autumn": {"description": ""},
    "Winter": {"description": ""},
    "Drawable": {"description": "Asset that can be drawn using pen tools"},
    "Photoscan": {"description": "Assets created using photogrammetry"},
}


# Which numeric parameters can be added to assets in grumpy_cat. Each maps to a dictionary with more
# info about each parameter. Keep in mind that in addition to these, assets can have parameters not
# on this list!
NUMERIC_PARAMETERS = {
    "model_year": {
        "description": "When was this man-made object made",
        "type": "int",
    },
    "price_usd": {
        "description": "Price in USD for which this man-made object was typically sold in $model_year year",
        "search_weight": 0.0,
        "unit": "$",
    },
    "width": {
        "description": "Width of the asset in meters",
        "unit": "m",
    },
    "height": {
        "description": "Height of the asset in meters",
        "unit": "m",
    },
    "depth": {
        "description": "Depth of the asset in meters",
        "unit": "m",
    },
    "image_count": {
        "description": "Number of images used in the asset",
        "type": "int",
    },
    "material_count": {
        "description": "Number of materials used in the asset",
        "type": "int",
    },
    "object_count": {
        "description": "Number of objects used in the asset",
        "type": "int",
    },
    "triangle_count": {
        "description": "Number of triangles used in the asset before applying modifiers",
        "type": "int",
    },
    "triangle_count_applied": {
        "description": "Number of triangles used in the asset after applying modifiers",
        "type": "int",
    },
}

# Order matters! From least to most permissive.
LICENSE_TYPES = ["Editorial", "Royalty Free", "Public Domain / CC0"]
# Which text parameters can be added to assets in grumpy_cat. Each maps to a dictionary with more
# info about each parameter. Keep in mind that in addition to these, assets can have parameters not
# on this list!
TEXT_PARAMETERS = {
    "license": {
        "description": "What license applies to this asset",
        "is_required": True,
        "choices": LICENSE_TYPES,
        "search_weight": 0.0,
    },
    "mapr_asset_id": {
        "description": "UUID of the asset in the MAPR index, internal use only",
        "is_required": True,
        "search_weight": 0.0,
        "show_filter": False,
    },
    # This is used for transferring the asset id from the recipe to the deserialized .blend file
    "mapr_asset_data_id": {
        "description": "UUID of the asset data in the MAPR index, internal use only",
        "search_weight": 0.0,
        "show_filter": False,
    },
    "bpy.data.version": {
        "description": "Which version of the .blend format was used for this asset",
        "show_filter": False,
        "search_weight": 0.0,
    },
    "copyright": {
        "description": "Who holds the copyright of this asset",
        "show_filter": False,
        "search_weight": 0.0,
    },
    "polygoniq_addon": {
        "description": "Which asset pack is this asset from, internal use only",
        "show_filter": False,
        "search_weight": 0.0,
    },
    "bq_animation_type": {
        "choices": [
            "Wind-Tree",
            "Wind-Low-Vegetation",
            "Wind-Low-Vegetation-Plants",
            "Wind-Palm",
            "Wind-Simple",
        ],
        "description": "Animation type that is the most suitable for this asset",
        "show_filter": False,
        "search_weight": 0.0,
    },
    "brand": {"description": "What is the brand of the man-made object"},
    "model": {
        "description": "What does the manufacturer call this man-made object in marketing materials"
    },
    "country_of_origin": {
        "description": "Where is this man-made object usually made",
        "choices": sorted(
            country_locations.COUNTRY_COORDINATES.keys(),
            key=lambda country: country.lower(),
        ),
    },
    "furniture_style": {
        "choices": [
            "Art-Deco",
            "Boho",
            "Contemporary",
            "Industrial",
            "Maximalist",
            "Mid-Century",
            "Minimalist",
            "Modern",
            "Postmodern",
            "Traditional",
            "Transitional",
            "Vintage/Old",
        ],
        "description": "Most fitting style for this piece of furniture or room",
    },
    "species": {"description": "Scientific (usually Latin) taxonomy name for the species"},
    "species_en": {"description": "English common name for the species", "search_weight": 1.0},
    "class": {"description": "Scientific (usually Latin) taxonomy class name for the species"},
    "class_en": {
        "description": "English common name for class of the species",
        "search_weight": 1.0,
    },
    "order": {"description": "Scientific (usually Latin) taxonomy order name for the species"},
    "order_en": {
        "description": "English common name for order of the species",
        "search_weight": 1.0,
    },
    "family": {"description": "Scientific (usually Latin) taxonomy family name for the species"},
    "family_en": {
        "description": "English common name for family of the species",
        "search_weight": 1.0,
    },
    "genus": {"description": "Scientific (usually Latin) taxonomy genus name for the species"},
    "genus_en": {
        "description": "English common name for genus of the species",
        "search_weight": 1.0,
    },
    "varietas": {
        "description": "Scientific (usually Latin) taxonomy varietas (variant) name for the asset",
        "search_weight": 1.0,
    },
    "varietas_en": {
        "description": "English common name for varietas of the asset",
        "search_weight": 1.0,
    },
    "forma": {
        "description": "Scientific (usually Latin) taxonomy forma name for the asset",
        "search_weight": 1.0,
    },
    "forma_en": {
        "description": "English common name for forma of the asset",
        "search_weight": 1.0,
    },
    "cultivar": {
        "description": "Name for cultivated variety of the asset",
        "search_weight": 1.0,
    },
    "conservation_status": {
        "choices": [
            "? - Not evaluated (NE)",
            "X - Data deficient (DD)",
            "0 - Least concern (LC)",
            "1 - Near threatened (NT)",
            "2 - Vulnerable (VU)",
            "3 - Endangered (EN)",
            "4 - Critically endangered (CE)",
            "5 - Extinct in the wild (EW)",
            "6 - Extinct (EX)",
        ],
        "description": "Conservation status of the species according to the IUCN",
        "search_weight": 0.0,
    },
    "model_detail": {
        "choices": [
            "Low-poly",
            "Mid-poly",
            "High-poly",
        ],
        "description": "Polygonal resolution of model",
        "search_weight": 0.0,
    },
    "st_original": {
        "description": "Path to the original source file and optionally the object name in the source 3DShaker asset pack",
        "show_filter": False,
        "search_weight": 0.0,
    },
    "interior_detail": {
        "choices": [
            "Low",
            "High",
        ],
        "description": "Interior detail level",
        "search_weight": 0.0,
    },
    "author": {
        "description": "Who created this asset. Optional and relevant only for internal use",
        "show_filter": False,
        "search_weight": 0.0,
    },
    "native_observations": {
        "description": "List of lat/long coordinates where the asset is naturally occurring",
        "search_weight": 0.0,
    },
    "all_observations": {
        "description": "List of lat/long coordinates where the asset is occurring",
        "search_weight": 0.0,
    },
    "location_of_origin": {
        "description": "List of lat/long coordinates based on 'country_of_origin' parameter",
        "search_weight": 0.0,
    },
}


class VectorType:
    FLOAT = 'FLOAT'
    INT = 'INT'
    COLOR = 'COLOR'


# Which vector parameters can be added to assets in grumpy_cat. Each maps to a dictionary with more
# info about each parameter. Keep in mind that in addition to these, assets can have parameters not
# on this list! The type is used to determine how the vector should be shown and manipulated in the
# interfaces - possible values are VectorType.FLOAT (default), INT or COLOR.
# TODO: Currently only vec3 is supported. We are not able to define sizes of vectors for display
# in the UI dynamically, so we hardcode the size of the vector in the UI. For different sizes
# different unique properties with switching between them would be required.
VECTOR_PARAMETERS = {
    "introduced_in": {
        "description": "Version of asset pack this asset was introduced in",
        "search_weight": 0.0,
        "type": VectorType.INT,
        "is_required": True,
    },
    "viewport_color": {
        "description": "",
        "search_weight": 0.0,
        "type": VectorType.COLOR,
    },
}

LOCATION_PARAMETERS = {
    "native_observations": {
        "description": "List of lat/long coordinates where the asset is naturally occurring.",
        "search_weight": 0.0,
    },
    "all_observations": {
        "description": "List of lat/long coordinates where the asset is naturally occurring, "
        "or was artificially introduced.",
        "search_weight": 0.0,
    },
}


# Mapping of parameter name to unit. If the parameter is not specified here it is considered unitless.
PARAMETER_UNITS = {
    param: info.get("unit")
    for param, info in NUMERIC_PARAMETERS.items()
    if info.get("unit", None) is not None
}

# Mapping of "group_name": ["child", "parameter", "names"]. If the parameter is not specified here
# it is considered ungrouped and should be drawn outside of any groups.
# TODO: Unify the num: type prefixing  here and in parameter_meta ideally use classes for
# parameters, so the unique name is ensured in the class and the caller can specify only
# the name.
PARAMETER_GROUPING = {
    "dimensions": [
        "num:width",
        "num:height",
        "num:depth",
    ],
    "taxonomy": [
        "text:class",
        "text:order",
        "text:family",
        "text:genus",
        "text:species",
        "text:varietas",
        "text:forma",
        "text:cultivar",
    ],
    "taxonomy_en": [
        "text:class_en",
        "text:order_en",
        "text:family_en",
        "text:genus_en",
        "text:species_en",
        "text:varietas_en",
        "text:forma_en",
        # this is an intentional duplicate of the cultivar in (latin) `taxonomy` group
        # as cultivars don't have another 'common' name
        "text:cultivar",
    ],
    "observations": [
        "loc:native_observations",
        "loc:all_observations",
    ],
    "manufacturing": [
        "text:brand",
        "text:country_of_origin",
        "loc:location_of_origin",
        "text:model",
        "num:model_year",
        "num:price_usd",
    ],
    "material": [
        "text:blend_method",
        "text:shadow_method",
        "text:displacement_method",
        "num:metallic",
        "num:roughness",
        "vec:viewport_color",
    ],
    "data_count": [
        "num:triangle_count",
        "num:triangle_count_applied",
        "num:object_count",
        "num:material_count",
        "num:image_count",
    ],
}


def format_parameter_name(param_name: str) -> str:
    """Formats given parameter to human readable form by removing underscores and titling it."""
    return param_name.replace("_", " ").title()


def format_group_name(group_name: str) -> str:
    """Formats given group name to human readable form by removing underscores and titling it."""
    return group_name.replace("_", " ").title()
