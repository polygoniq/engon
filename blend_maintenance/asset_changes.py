# copyright (c) 2018- polygoniq xyz s.r.o.

import re
import typing


class RegexMapping(typing.NamedTuple):
    pattern: re.Pattern
    replacement: str


class AssetPackMigration(typing.NamedTuple):
    # List of regex expressions that will be iteratively applied to the library blend filenames.
    # So the renames stack up on each other.
    library_changes: typing.List[RegexMapping]
    # Dictionary of datablock types mapped to lists of regex expressions that will be iteratively
    # applied to the datablock names.
    datablock_changes: typing.Dict[str, typing.List[RegexMapping]]


class AssetPackMigrations(typing.NamedTuple):
    # Asset pack name
    pack_name: str
    # Chronological list of migrations in the asset pack
    migrations: typing.List[AssetPackMigration]


# versions in the names reflect the last version of asset pack without given changes
botaniq_6_8_0_unify_bq_prefix = AssetPackMigration(
    [
        RegexMapping(
            re.compile(r"^(?!bq_|Library_Botaniq)([^\\/]+)(\.blend$)"),
            r"bq_\1\2"
        ),
        RegexMapping(
            re.compile("^Library_Botaniq_Materials.blend$"),
            r"bq_Library_Materials.blend"
        )
    ],
    {
        "collections":  [RegexMapping(re.compile(r"^(?!bq_)(.*)"), r"bq_\1")],
        "meshes":       [RegexMapping(re.compile(r"^(?!bq_)(.*)"), r"bq_\1")],
        "objects":      [RegexMapping(re.compile(r"^(?!bq_)(.*)"), r"bq_\1")],
        "images":       [RegexMapping(re.compile(r"^(?!bq_)(.*)"), r"bq_\1")],
        "node_groups":  [RegexMapping(re.compile("^(-bqn---)(.*)(_bqn)$"), r"bq_\2")],
    }
)

_botaniq_6_8_0_rename_vases_to_pots_mappings = {
    r"^bq_Vase_Circular-Simple-Glazed-Ceramics_([AB])_spring-summer-autumn":
        r"bq_Pot_Circular-Simple-Glazed-Ceramics_\1_spring-summer-autumn",
    r"^bq_Vase_Circular-Simple-Wooden-Pedestal_([AB])_spring-summer-autumn":
        r"bq_Pot_Circular-Simple-Wooden-Pedestal_\1_spring-summer-autumn",
    r"^bq_Vase_Circular-Widening-Glazed-Ceramics_([AB])_spring-summer-autumn":
        r"bq_Pot_Circular-Widening-Glazed-Ceramics_\1_spring-summer-autumn",
    r"^bq_Vase_Diamond-Pattern-Glazed-Ceramics_([AB])_spring-summer-autumn":
        r"bq_Pot_Diamond-Pattern-Glazed-Ceramics_\1_spring-summer-autumn",
    r"^bq_Vase_Hemispheric-Steel-Pedestal_([AB])_spring-summer-autumn":
        r"bq_Pot_Hemispheric-Steel-Pedestal_\1_spring-summer-autumn",
    r"^bq_Vase_Weaved-Wicker-Shell_A_spring-summer-autumn":
        r"bq_Pot_Weaved-Wicker-Shell_A_spring-summer-autumn",
}

botaniq_6_8_0_rename_vases_to_pots = AssetPackMigration(
    [
        RegexMapping(re.compile(f"{pattern}.blend$"), f"{replacement}.blend")
        for pattern, replacement
        in _botaniq_6_8_0_rename_vases_to_pots_mappings.items()
    ],
    {
        "collections": [
            RegexMapping(re.compile(pattern), replacement)
            for pattern, replacement
            in _botaniq_6_8_0_rename_vases_to_pots_mappings.items()
        ],
        "meshes": [
            RegexMapping(re.compile(pattern), replacement)
            for pattern, replacement
            in _botaniq_6_8_0_rename_vases_to_pots_mappings.items()
        ],
        "objects": [
            RegexMapping(re.compile(pattern), replacement)
            for pattern, replacement
            in _botaniq_6_8_0_rename_vases_to_pots_mappings.items()
        ],
    }
)

_botaniq_6_8_0_english_names_to_latin_mappings = {
    r"^bq_Flower_Bellflower_([BCEF])_spring-summer": r"bq_Flower_Campanula-scheuchzeri_\1_spring-summer",
    r"^bq_Flower_Common-marigold_A_spring-summer": r"bq_Flower_Calendula-officinalis_A_spring-summer",
    r"^bq_Flower_Cornflower_([BCEF])_spring-summer": r"bq_Flower_Centaurea-cyanus_\1_spring-summer",
    r"^bq_Flower_Crocus-hybridus_([ABC])_spring-summer": r"bq_Flower_Crocus-vernus_\1_spring-summer",
    r"^bq_Flower_Daisy_A_spring-summer": r"bq_Flower_Bellis-perennis_A_spring-summer",
    r"^bq_Flower_Early-dog-violet_([BCEFHI])_spring-summer": r"bq_Flower_Viola-reichenbachiana_\1_spring-summer",
    r"^bq_Flower_Lavender_([BCE])_spring-summer": r"bq_Flower_Lavandula-angustifolia_\1_spring-summer",
    r"^bq_Flower_Purple-hyacinth_A_spring-summer": r"bq_Flower_Hyacinthus-orientalis_A_spring-summer",
    r"^bq_Flower_Rose_([ABC])_spring-summer-autumn": r"bq_Flower_Rosa-gallica_\1_spring-summer-autumn",
    r"^bq_Flower_Sunflower_([ABCDEF])_spring-summer": r"bq_Flower_Helianthus-annuus_\1_spring-summer",
    r"^bq_Flower_Tulip_([BCE])_spring-summer": r"bq_Flower_Tulipa-gesneriana_\1_spring-summer",
    r"^bq_Grass_Basic_([A,D,E,F,G,H])_spring-summer": r"bq_Grass_Lolium-perenne_\1_spring-summer",
    r"^bq_Grass_Basic-dry_([AD])_spring-summer": r"bq_Grass-Dry_Lolium-perenne_\1_spring-summer",
    r"^bq_Grass_Basic-Strands_([ABC])_spring-summer": r"bq_Grass-Strands_Lolium-perenne_\1_spring-summer",
    r"^bq_Grass_Basic-Strands-dry_([ABC])_spring-summer": r"bq_Grass-Strands-Dry_Lolium-perenne_\1_spring-summer",
    r"^bq_Grass_Cut_([AD])_spring-summer": r"bq_Grass-Cut_Lolium-perenne_\1_spring-summer",
    r"^bq_Grass_Cut-grid_([BC])_spring-summer": r"bq_Grass-Cut-Grid_Lolium-perenne_\1_spring-summer",
    r"^bq_Grass_Cut-striped_([AD])_spring-summer": r"bq_Grass-Cut-Striped_Lolium-perenne_\1_spring-summer",
    r"^bq_Grass_Frosted_([AD])_autumn-winter": r"bq_Grass-Frosted_Lolium-perenne_\1_autumn-winter",
    r"^bq_Grass_Frosted-dry_([AD])_autumn-winter": r"bq_Grass-Frosted-Dry_Lolium-perenne_\1_autumn-winter",
    r"^bq_Grass_High_([AB])_spring-summer": r"bq_Grass_Cymbopogon-citratus_\1_spring-summer",
    r"^bq_Grass_Juncus-leopoldii_([ABCDE])_spring-summer-autumn": r"bq_Grass_Juncus-acutus_\1_spring-summer-autumn",
    r"^bq_Grass_Karl-foerster_([BC])_spring-summer": r"bq_Grass_Calamagrostis-acutiflora_\1_spring-summer",
    r"^bq_Grass_Tall_A_spring-summer": r"bq_Grass_Lolium-arundinaceum_A_spring-summer",
    r"^bq_Grass_Wild_([ABC])_spring-summer": r"bq_Grass_Poa-trivialis_\1_spring-summer",
    r"^bq_Ivy_Corner-in_([ABC])_spring-summer-autumn": r"bq_Ivy-Corner-in_Hedera-helix_\1_spring-summer-autumn",
    r"^bq_Ivy_Corner-out_([ABC])_spring-summer-autumn": r"bq_Ivy-Corner-out_Hedera-helix_\1_spring-summer-autumn",
    r"^bq_Ivy_Hanging_([ABC])_spring-summer-autumn": r"bq_Ivy-Hanging_Hedera-helix_\1_spring-summer-autumn",
    r"^bq_Ivy_Loose_([ABC])_spring-summer-autumn": r"bq_Ivy-Loose_Hedera-helix_\1_spring-summer-autumn",
    r"^bq_Ivy_Pot_([ABC])_spring-summer-autumn": r"bq_Ivy-Pot_Hedera-helix_\1_spring-summer-autumn",
    r"^bq_Ivy_Tree_([ABC])_spring-summer-autumn": r"bq_Ivy-Tree_Hedera-helix_\1_spring-summer-autumn",
    r"^bq_Ivy_Wall_([ABC])_spring-summer-autumn": r"bq_Ivy-Wall_Hedera-helix_\1_spring-summer-autumn",
    r"^bq_Ivy_Wall-diagonal_([ABC])_spring-summer-autumn": r"bq_Ivy-Wall-diagonal_Hedera-helix_\1_spring-summer-autumn",
    r"^bq_Ivy_Window-down_([ABC])_spring-summer-autumn": r"bq_Ivy-Window-down_Hedera-helix_\1_spring-summer-autumn",
    r"^bq_Ivy_Window-up_([ABC])_spring-summer-autumn": r"bq_Ivy-Window-up_Hedera-helix_\1_spring-summer-autumn",
    r"^bq_Ivy_Wire_([ABC])_spring-summer-autumn": r"bq_Ivy-Wire_Hedera-helix_\1_spring-summer-autumn",
    r"^bq_Misc_Aplysina-fistularis_([ABCD])_spring-summer-autumn-winter": r"bq_Coral_Aplysina-fistularis_\1_spring-summer-autumn-winter",
    r"^bq_Misc_Dead-leaf_([ABC])_spring-summer-autumn-winter": r"bq_Leaf-Dead_Fagus-sylvatica_\1_spring-summer-autumn-winter",
    r"^bq_Misc_Dead-leaves_A_spring-summer": r"bq_Leaf-Dead-Group_Fagus-sylvatica_A_spring-summer",
    r"^bq_Misc_Leaf-acer_([AB])_autumn": r"bq_Leaf_Acer-saccharum_\1_autumn",
    r"^bq_Misc_Leaf-fagus_([AB])_autumn": r"bq_Leaf_Fagus-sylvatica_\1_autumn",
    r"^bq_Misc_Leaf-quercus_([AB])_autumn": r"bq_Leaf_Quercus-robur_\1_autumn",
    r"^bq_Misc_Lilypad-lily_([AB])_spring-summer": r"bq_Lilypad-Flower_Nymphaea-alba_\1_spring-summer",
    r"^bq_Misc_Lilypad-nymphaea_A_spring-summer": r"bq_Lilypad_Nymphaea-alba_A_spring-summer",
    r"^bq_Misc_Lilypad-nymphaea-blooming_A_spring-summer": r"bq_Lilypad-Blooming_Nymphaea-alba_A_spring-summer",
    r"^bq_Misc_Lilypad-victoria_([BC])_spring-summer": r"bq_Lilypad_Victoria-amazonica_\1_spring-summer",
    r"^bq_Misc_Mushroom-Amanita_([ABC])_spring-summer-autumn-winter": r"bq_Mushroom_Amanita-muscaria_\1_spring-summer-autumn-winter",
    r"^bq_Misc_Mushroom-Boletus_([ABC])_spring-summer-autumn-winter": r"bq_Mushroom_Boletus-edulis_\1_spring-summer-autumn-winter",
    r"^bq_Misc_Mushroom-Russula_([ABC])_spring-summer-autumn-winter": r"bq_Mushroom_Russula-emetica_\1_spring-summer-autumn-winter",
    r"^bq_Misc_Needles_([AB])_spring-summer-autumn": r"bq_Needles_Pinus-ponderosa_\1_spring-summer-autumn",
    r"^bq_Misc_Pinecone_([ABCD])_spring-summer-autumn": r"bq_Pinecone_Pinus-ponderosa_\1_spring-summer-autumn",
    r"^bq_Misc_Pinecone-needle_A_spring-summer-autumn": r"bq_Pinecone-Needle_Pinus-ponderosa_A_spring-summer-autumn",
    r"^bq_Misc_Twig_([AB])_spring-summer-autumn": r"bq_Twig_Picea-abies_\1_spring-summer-autumn",
    r"^bq_Misc_Twig_C_spring-summer-autumn": r"bq_Twig_Tilia-europaea_A_spring-summer-autumn",
    r"^bq_Misc_Twig_D_spring-summer-autumn": r"bq_Twig_Quercus-robur_A_spring-summer-autumn",
    r"^bq_Misc_Twig_E_spring-summer-autumn": r"bq_Twig_Populus-tremuloides_A_spring-summer-autumn",
    r"^bq_Misc_Twig_F_spring-summer-autumn": r"bq_Twig_Populus-tremuloides_B_spring-summer-autumn",
    r"^bq_Misc_Twig_G_spring-summer-autumn": r"bq_Twig_Pinus-ponderosa_A_spring-summer-autumn",
    r"^bq_Plant_Areca_([ABC])_spring-summer-autumn": r"bq_Plant_Dypsis-lutescens_\1_spring-summer-autumn",
    r"^bq_Plant_Aspidistra_A_spring-summer-autumn": r"bq_Plant_Aspidistra-elatior_A_spring-summer-autumn",
    r"^bq_Plant_Basil_([AB])_spring-summer-autumn": r"bq_Plant_Ocimum-basilicum_\1_spring-summer-autumn",
    r"^bq_Plant_Chlorophytum_A_spring-summer-autumn": r"bq_Plant_Chlorophytum-comosum_A_spring-summer-autumn",
    r"^bq_Plant_Coriander_([ABC])_spring-summer-autumn": r"bq_Plant_Coriandrum-sativum_\1_spring-summer-autumn",
    r"^bq_Plant_Dracaena-marginata_A_spring-summer-autumn": r"bq_Plant_Dracaena-reflexa_A_spring-summer-autumn",
    r"^bq_Plant_Dracaena-trifasciata_([ABC])_spring-summer-autumn": r"bq_Plant_Sansevieria-trifasciata_\1_spring-summer-autumn",
    r"^bq_Plant_Fern_([ABCDE])_spring-summer-autumn": r"bq_Plant_Dryopteris-carthusiana_\1_spring-summer-autumn",
    r"^bq_Plant_Fern-single_([ABC])_spring-summer-autumn": r"bq_Plant-Single_Dryopteris-carthusiana_\1_spring-summer-autumn",
    r"^bq_Plant_Ficus_([AB])_spring-summer-autumn": r"bq_Plant_Ficus-elastica_\1_spring-summer-autumn",
    r"^bq_Plant_Hibiscus_([ABCD])_spring-summer-autumn": r"bq_Plant_Hibiscus-rosa-sinensis_\1_spring-summer-autumn",
    r"^bq_Plant_Monstera_A_spring-summer-autumn": r"bq_Plant_Monstera-deliciosa_A_spring-summer-autumn",
    r"^bq_Plant_Monstera-variegata_A_spring-summer-autumn": r"bq_Plant_Monstera-deliciosa-variegata_A_spring-summer-autumn",
    r"^bq_Plant_Pothos_A_spring-summer-autumn": r"bq_Plant_Epipremnum-aureum_A_spring-summer-autumn",
    r"^bq_Plant_Red-Chilli_A_spring-summer-autumn": r"bq_Plant_Capsicum-annuum_A_spring-summer-autumn",
    r"^bq_Plant_Spathiphyllum_A_spring-summer-autumn": r"bq_Plant_Spathiphyllum-wallisii_A_spring-summer-autumn",
    r"^bq_Plant_Tomato-Red-Robin_A_spring-summer-autumn": r"bq_Plant_Solanum-lycopersicum_A_spring-summer-autumn",
    r"^bq_Plant_Zamioculcas_A_spring-summer-autumn": r"bq_Plant_Zamioculcas-zamiifolia_A_spring-summer-autumn",
    r"^bq_Shrub_Buxus-semprevirens_([ABC])_spring-summer-autumn": r"bq_Shrub_Buxus-sempervirens_\1_spring-summer-autumn",
    r"^bq_Shrub_Forsythia_([ABCD])_spring-summer": r"bq_Shrub_Forsythia-intermedia_\1_spring-summer",
    r"^bq_Shrub_Rhododendron_([ABC])_spring-summer": r"bq_Shrub_Rhododendron-ponticum_\1_spring-summer",
    r"^bq_Shrub_Rose_([ABCDEF])_spring-summer-autumn": r"bq_Shrub_Rosa-gallica_\1_spring-summer-autumn",
    r"^bq_Shrub_Sambucus-nigra_([A,B,C])_spring-summer-autumn": r"bq_Shrub_Sambucus-nigra_\1_summer",
    r"^bq_Shrub_Senecio-flacidus_([ABCDEF])_spring-summer": r"bq_Shrub_Senecio-flaccidus_\1_spring-summer",
    r"^bq_Tree_Bamboo_([AB])_spring-summer-autumn": r"bq_Tree_Bambusa-vulgaris_\1_spring-summer-autumn",
    r"^bq_Tree_Cedrus_([A,B])_spring-summer-autumn": r"bq_Tree_Cedrus-brevifolia_\1_spring-summer-autumn",
    r"^bq_Tree_Cedrus_([A,B])_winter": r"bq_Tree_Cedrus-brevifolia_\1_winter",
    r"^bq_Tree_Cedrus_([A,B])_winter": r"bq_Tree_Cedrus-brevifolia_\1_winter",
    r"^bq_Tree_Lemon-Tree_A_spring-summer-autumn": r"bq_Tree_Citrus-medica_A_spring-summer-autumn",
    r"^bq_Tree_Vachellia-tortillis_A_summer": r"bq_Tree_Vachellia-tortilis_A_summer",
    r"^bq_Vine_Ivy_([AD])_spring-summer": r"bq_Vine_Vitis-vinifera_\1_spring-summer",
    r"^bq_Vine_Pothos_([BC])_spring-summer": r"bq_Vine_Epipremnum-aureum_\1_spring-summer",
    r"^bq_Vine_Salix_([BC])_spring-summer": r"bq_Vine_Salix-caprea_\1_spring-summer",
    r"^bq_Vines_Basic_A_spring-summer": r"bq_Vines_Vitis-vinifera_A_spring-summer",
    r"^bq_Weed_Clover_A_spring-summer": r"bq_Weed_Trifolium-repens_A_spring-summer",
    r"^bq_Weed_Dandellion_([A,D])_spring-summer": r"bq_Weed_Taraxacum-officinale_\1_spring-summer",
    r"^bq_Weed_Red-clover_B_spring-summer": r"bq_Weed_Trifolium-pratense_B_spring-summer",
    r"^bq_Weed_Shepherds-purse_([ABC])_spring-summer": r"bq_Weed_Capsella-bursa-pastoris_\1_spring-summer",
    r"^bq_Weed_Tall_A_spring-summer": r"bq_Weed_Paspalum-distichum_A_spring-summer",
    r"^bq_Weed_White-dead-nettle_([BCE])_spring-summer": r"bq_Weed_Lamium-album_\1_spring-summer",
}

botaniq_6_8_0_english_names_to_latin = AssetPackMigration(
    [
        RegexMapping(re.compile(f"{pattern}.blend$"), f"{replacement}.blend")
        for pattern, replacement
        in _botaniq_6_8_0_english_names_to_latin_mappings.items()
    ],
    {
        "collections": [
            RegexMapping(re.compile(pattern), replacement)
            for pattern, replacement
            in _botaniq_6_8_0_english_names_to_latin_mappings.items()
        ],
        "meshes": [
            RegexMapping(re.compile(pattern), replacement)
            for pattern, replacement
            in _botaniq_6_8_0_english_names_to_latin_mappings.items()
        ],
        "objects": [
            RegexMapping(re.compile(pattern), replacement)
            for pattern, replacement
            in _botaniq_6_8_0_english_names_to_latin_mappings.items()
        ],
    }
)

_botaniq_6_8_0_decapitalize_cortaderia_mapping = RegexMapping(
    re.compile(r"^bq_Grass_Cortaderia-Selloana_([ABCDEFHG])_spring-summer"),
    r"bq_Grass_Cortaderia-selloana_\1_spring-summer"
)

botaniq_6_8_0_decapitalize_cortaderia = AssetPackMigration(
    [
        RegexMapping(
            re.compile(r"^bq_Grass_Cortaderia-Selloana_([ABCDEFHG])_spring-summer.blend"),
            r"bq_Grass_Cortaderia-selloana_\1_spring-summer.blend"
        )
    ],
    {
        "collections": [_botaniq_6_8_0_decapitalize_cortaderia_mapping],
        "meshes": [_botaniq_6_8_0_decapitalize_cortaderia_mapping],
        "objects": [_botaniq_6_8_0_decapitalize_cortaderia_mapping]
    }
)

evermotion_am154_1_3_0_am154_prefix = AssetPackMigration(
    [
        RegexMapping(
            re.compile(r"^(AM154-)([^\\/]+)(\.blend)$"),
            r"am154_\2\3"
        ),
        RegexMapping(
            re.compile("^Library_Evermotion-AM154_Materials.blend$"),
            r"am154_Library_Materials.blend"
        )
    ],
    {
        "collections":  [RegexMapping(re.compile("^(AM154-)(.*)"), r"am154_\2")],
        "meshes":       [RegexMapping(re.compile("^(AM154-)(.*)"), r"am154_\2")],
        "objects":      [RegexMapping(re.compile("^(AM154-)(.*)"), r"am154_\2")],
        "materials":    [
            RegexMapping(re.compile("^(bq_)(.*)"), r"am154_\2"),
            RegexMapping(re.compile("(.*)(_bqm)$"), r"am154_\1")
        ],
        "node_groups":  [RegexMapping(re.compile("^(bq_)(.*)"), r"am154_\2")],
    }
)


evermotion_am176_1_2_0_am176_prefix = AssetPackMigration(
    [
        RegexMapping(
            re.compile(r"^(AM176-)([^\\/]+)(\.blend)$"),
            r"am176_\2\3"
        ),
        RegexMapping(
            re.compile("^Library_Evermotion-AM176_Materials.blend$"),
            r"am176_Library_Materials.blend"
        )
    ],
    {
        "collections": [RegexMapping(re.compile("^(AM176-)(.*)"), r"am176_\2")],
        "meshes":      [RegexMapping(re.compile("^(AM176-)(.*)"), r"am176_\2")],
        "objects":     [RegexMapping(re.compile("^(AM176-)(.*)"), r"am176_\2")],
        "materials":   [RegexMapping(re.compile("^(bq_)(.*)"), r"am176_\2")],
        "node_groups": [RegexMapping(re.compile("^(bq_)(.*)"), r"am176_\2")],
    }
)

traffiq_1_7_0_tq_prefix = AssetPackMigration(
    [
        RegexMapping(
            re.compile(r"^(?!tq_|Library_Traffiq)([^\\/]+)(\.blend$)"),
            r"tq_\1\2"
        ),
        RegexMapping(
            re.compile(r"^(Library_Traffiq_)([^\\/]+)(\.blend$)"),
            r"tq_Library_\2\3"
        )
    ],
    {
        "collections":  [RegexMapping(re.compile(r"^(?!tq_)(.*)"), r"tq_\1")],
        "meshes":       [RegexMapping(re.compile(r"^(?!tq_)(.*)"), r"tq_\1")],
        "objects":      [RegexMapping(re.compile(r"^(?!tq_)(.*)"), r"tq_\1")],
        "images":       [RegexMapping(re.compile(r"^(?!tq_)(.*)"), r"tq_\1")],
        "node_groups":  [RegexMapping(re.compile(r"^(.*)(_tqn)$"), r"tq_\1")],
    }
)


_traffiq_2_0_0_remove_percent_from_incline_sign_mapping = RegexMapping(
    re.compile(r"^tq_StreetSign_Warning_Incline-12%$"), r"tq_StreetSign_Warning_Incline-12")

traffiq_2_0_0_remove_percent_from_incline_sign = AssetPackMigration(
    [
        RegexMapping(
            re.compile(r"^tq_StreetSign_Warning_Incline-12%\.blend$"),
            r"tq_StreetSign_Warning_Incline-12.blend"
        )
    ],
    {
        "collections": [_traffiq_2_0_0_remove_percent_from_incline_sign_mapping],
        "meshes": [_traffiq_2_0_0_remove_percent_from_incline_sign_mapping],
        "objects": [_traffiq_2_0_0_remove_percent_from_incline_sign_mapping],
    }
)

ASSET_PACK_MIGRATIONS = [
    AssetPackMigrations(
        pack_name="botaniq",
        migrations=[
            botaniq_6_8_0_unify_bq_prefix,
            botaniq_6_8_0_rename_vases_to_pots,
            botaniq_6_8_0_english_names_to_latin,
            botaniq_6_8_0_decapitalize_cortaderia
        ]
    ),
    AssetPackMigrations(
        pack_name="evermotion_am154",
        migrations=[
            evermotion_am154_1_3_0_am154_prefix
        ]
    ),
    AssetPackMigrations(
        pack_name="evermotion_am176",
        migrations=[
            evermotion_am176_1_2_0_am176_prefix
        ]
    ),
    AssetPackMigrations(
        pack_name="traffiq",
        migrations=[
            traffiq_1_7_0_tq_prefix,
            traffiq_2_0_0_remove_percent_from_incline_sign
        ]
    )
]


MQ4_NODE_TREES_TO_MQ = {
    # category: 0
    "0A_Steel_mqn": "/materialiq/ML_Metal/mq_ML000_STEEL-Smooth",
    "0B_Steel_Rough_mqn": "/materialiq/ML_Metal/mq_ML003_STEEL-Rough",
    "0C_Copper_mqn": "/materialiq/ML_Metal/mq_ML500_COPPER-Smooth",
    "0D_Metal_Dark_mqn": "/materialiq/ML_Metal/mq_ML040_STEEL-Blackened-Smooth",
    "0E_Bronze_mqn": "/materialiq/ML_Metal/mq_ML400_BRONZE-Smooth",
    "0F_Corten_mqn": "/materialiq/ML_Metal/mq_ML015_STEEL-Corten",
    "0G_Steel_Galvanized_mqn": "/materialiq/ML_Metal/mq_ML030_STEEL-Galvanized",
    "0H_Metal_Hammered_mqn": "/materialiq/ML_Metal/mq_ML915_UNSORTED-Hammered",
    "0I_Gold_mqn": "/materialiq/ML_Metal/mq_ML600_PRECIOUS-Gold-18k",
    "0J_Aluminium_mqn": "/materialiq/ML_Metal/mq_ML200_ALUMINUM-Smooth",
    "0K_Steel_Brushed_mqn": "/materialiq/ML_Metal/mq_ML005_STEEL-Brushed-Directional",
    "0L_Steel_Brushed_Radial_mqn": "/materialiq/ML_Metal/mq_ML004_STEEL-Brushed-Radial",
    "0M_Chrome_mqn": "/materialiq/ML_Metal/mq_ML020_STEEL-Chrome-Smooth",
    "0N_Copper_Oxidised_mqn": "/materialiq/ML_Metal/mq_ML510_COPPER-Oxidised",
    "0O_Iron_Wrought_mqn": "/materialiq/ML_Metal/mq_ML111_IRON-Wrought",
    "0P_Metal_Bare_mqn": "/materialiq/ML_Metal/mq_ML010_STEEL-Bare",
    "0Q_Metal_Rusted_mqn": "/materialiq/ML_Metal/mq_ML110_IRON-Rusted",
    "0R_Steel_Corrugated_mqn": "/materialiq/ML_Metal/mq_ML910_UNSORTED-Corrugated",
    "0S_Silver_mqn": "/materialiq/ML_Metal/mq_ML610_PRECIOUS-Silver",
    "0T_Brass_mqn": "/materialiq/ML_Metal/mq_ML300_BRASS-Smooth",
    "0U_Metal_Paint_Peeled_mqn": "/materialiq/ML_Metal/mq_ML710_PAINTED-Peeled",
    "0V_Metal_Painted_mqn": "/materialiq/ML_Metal/mq_ML707_PAINTED-Craters",
    "0W_Aluminium_Foil_mqn": "/materialiq/ML_Metal/mq_ML220_ALUMINUM-Foil",
    "0X_Steel_Scratched_mqn": "/materialiq/ML_Metal/mq_ML002_STEEL-Scratched",
    # category: 1
    "1AA_Concrete_Formwork-Imprint_mqn": "/materialiq/CC_Concrete/mq_CC720_AGED-Bugholes-Dirty",
    "1A_Concrete_Poured_mqn": "/materialiq/CC_Concrete/mq_CC002_COMMON-Smooth-Poured",
    "1BB_Concrete_Old_mqn": "/materialiq/CC_Concrete/mq_CC700_AGED-Smooth",
    "1B_Concrete_Smooth_mqn": "/materialiq/CC_Concrete/mq_CC001_COMMON-Smooth",
    "1CC_Concrete_Cracked_mqn": "/materialiq/CC_Concrete/mq_CC021_COMMON-Rough-Medium-Cracks",
    "1C_Concrete_Rough_mqn": "/materialiq/CC_Concrete/mq_CC340_STRUCTURE-Brutalist-Washed",
    "1D_Concrete_Screed-Spotted_mqn": "/materialiq/CC_Concrete/mq_CC121_CEMENT-Screed-Spotted",
    "1D_Concrete_Screed_mqn": "/materialiq/CC_Concrete/mq_CC120_CEMENT-Screed",
    "1E_Concrete_Spotted_mqn": "/materialiq/CC_Concrete/mq_CC007_COMMON-Spotted",
    "1F_Concrete_WoodenRelief_mqn": "/materialiq/CC_Concrete/mq_CC230_ARCH-Relief-Wood",
    "1F_Concrete_Dirty_mqn": "/materialiq/CC_Concrete/mq_CC200_ARCH-Troweled-Dirty",
    "1H_Concrete_Panels_mqn": "/materialiq/CC_Concrete/mq_CC320_STRUCTURE-Panels",
    "1I_Concrete_Panels_Dirty_mqn": "/materialiq/CC_Concrete/mq_CC322_STRUCTURE-Panels-Aged",
    "1J_Concrete_Floor_Polished_mqn": "/materialiq/CC_Concrete/mq_CC420_FLOOR-Troweled-Smooth",
    "1K_Concrete_Panels_New_mqn": "/materialiq/CC_Concrete/mq_CC321_STRUCTURE-Panels-New",
    "1L_Concrete_Brutalist_mqn": "/materialiq/CC_Concrete/mq_CC341_STRUCTURE-Brutalist-Washed",
    "1M_Concrete_SuperSmooth_mqn": "/materialiq/CC_Concrete/mq_CC202_ARCH-Troweled-Smooth",
    "1N_Concrete_Bugholed_mqn": "/materialiq/CC_Concrete/mq_CC030_COMMON-Bugholes",
    "1OO_Concrete_Medium-Cracks_mqn": "/materialiq/CC_Concrete/mq_CC021_COMMON-Rough-Medium-Cracks",
    "1O_Concrete_BigCracks_mqn": "/materialiq/CC_Concrete/mq_CC201_ARCH-Troweled-Cracked",
    "1P_Concrete_SmallCracks_mqn": "/materialiq/CC_Concrete/mq_CC020_COMMON-Smooth-Small-Cracks",
    "1Q_Concrete_MixedRocks_mqn": "/materialiq/CC_Concrete/mq_CC005_COMMON-Porous-Large",
    "1R_Concrete_Ridged_mqn": "/materialiq/CC_Concrete/mq_CC210_ARCH-Ridged",
    "1S_Concrete_Scratched_mqn": "/materialiq/CC_Concrete/mq_CC400_FLOOR-Scratched",
    "1T_Concrete_Tiny_Rainbow_mqn": "/materialiq/CC_Concrete/mq_CC604_COLORED-Tiny-Rainbow",
    "1U_Concrete_Stracciatella_mqn": "/materialiq/CC_Concrete/mq_CC605_COLORED-Stracciatella",
    "1V_Concrete_Smooth_Bugholes_mqn": "/materialiq/CC_Concrete/mq_CC031_COMMON-Bugholes-Smooth",
    "1WW_Concrete_Brutalist_Washed_mqn": "/materialiq/CC_Concrete/mq_CC342_STRUCTURE-Brutalist-Smaller",
    "1W_Concrete_Floor_Reclaimed_mqn": "/materialiq/CC_Concrete/mq_CC421_FLOOR-Troweled-Reclaimed",
    "1X_Concrete_Old_Worn_mqn": "/materialiq/CC_Concrete/mq_CC701_AGED-Worn",
    "1Y_Concrete_Granular_mqn": "/materialiq/CC_Concrete/mq_CC006_COMMON-Granular",
    "1Z_Concrete_Whitewashed_mqn": "/materialiq/CC_Concrete/mq_CC606_COLORED-Whitewashed",
    # category: 2
    "2DD_Wood_Acacia_mqn": "/materialiq/WD_Wood/mq_WD770_TROPICAL-Acacia",
    "2AA_Wood_Tropical_mqn": "/materialiq/WD_Wood/mq_WD795_TROPICAL-Tropical",
    "2A_Wood_Oak_mqn": "/materialiq/WD_Wood/mq_WD001_DECIDUOUS-Oak-Natural",
    "2BB_Wood_Pine-Resinous_mqn": "/materialiq/WD_Wood/mq_WD346_CONIFEROUS-Pine-Resinous",
    "2B_Wood_Beech_mqn": "/materialiq/WD_Wood/mq_WD040_DECIDUOUS-Beech",
    "2CC_Wood_Obsolete_mqn": "/materialiq/WD_Wood/mq_WD882_VARIOUS-Obsolete",
    "2C_Wood_Rough_mqn": "/materialiq/WD_Wood/mq_WD390_CONIFEROUS-Cedar-Old",
    "2D_Mahogany_mqn": "/materialiq/WD_Wood/mq_WD700_TROPICAL-Mahogany",
    "2E_Wicker_mqn": "/materialiq/WD_Wood/mq_WD790_TROPICAL-Wicker",
    "2FF_Wood_Logs-Square_mqn": "/materialiq/WD_Wood/mq_WD800_VARIOUS-Timber",
    "2F_Fireboard_mqn": "/materialiq/WD_Wood/mq_WD650_ENGINEERED-Fireboard",
    "2G_Wood_Painted-Clean_mqn": "/materialiq/WD_Wood/mq_WD885_VARIOUS-Painted",
    "2H_Wood_Painted-Rough_mqn": "/materialiq/WD_Wood/mq_WD886_VARIOUS-Painted-Rough",
    "2I_Wood_Old-Smooth_mqn": "/materialiq/WD_Wood/mq_WD884_VARIOUS-Old-Smooth",
    "2J_Wood_Charred_mqn": "/materialiq/WD_Wood/mq_WD680_ENGINEERED-Accoya-Charred",
    "2K_Plywood_mqn": "/materialiq/WD_Wood/mq_WD600_ENGINEERED-Plywood",
    "2LL_Wood_Logs-Round_mqn": "/materialiq/WD_Wood/mq_WD801_VARIOUS-Log",
    "2L_Wood_Oak-Dark_mqn": "/materialiq/WD_Wood/mq_WD020_DECIDUOUS-Oak-Dark",
    "2MM_Wood_moss_mqn": "/materialiq/WD_Wood/mq_WD881_VARIOUS-Moss",
    "2M_Wood_Maple_mqn": "/materialiq/WD_Wood/mq_WD180_DECIDUOUS-Maple",
    "2N_Wood_Rough-Chopped_mqn": "/materialiq/WD_Wood/mq_WD810_VARIOUS-Wood-Rough-Chopped",
    "2O_Wood_Aspen-Stained_mqn": "/materialiq/WD_Wood/mq_WD235_DECIDUOUS-Aspen-Stained",
    "2PP_Wood_Pine_mqn": "/materialiq/WD_Wood/mq_WD341_CONIFEROUS-Pine",
    "2P_Wood_Dry-Cracked_mqn": "/materialiq/WD_Wood/mq_WD010_DECIDUOUS-Oak-Dry-Cracked",
    "2Q_Fireboard_Yellow_mqn": "/materialiq/WD_Wood/mq_WD651_ENGINEERED-Fireboard-Yellow",
    "2RR_Wood_Reclaimed_mqn": "/materialiq/WD_Wood/mq_WD421_CONIFEROUS-Larch-Planks",
    "2R_Wood_Raw_mqn": "/materialiq/WD_Wood/mq_WD345_CONIFEROUS-Pine-Raw",
    "2S_Wood_Stripped-Bark_mqn": "/materialiq/WD_Wood/mq_WD631_ENGINEERED-Oak-Stripped",
    "2T_Wood_Teak-Straight_mqn": "/materialiq/WD_Wood/mq_WD720_TROPICAL-Teak-Straight",
    "2U_Wood_Spruce-Knots_mqn": "/materialiq/WD_Wood/mq_WD315_CONIFEROUS-Spruce-Knots",
    "2V_Plywood_Wavy_mqn": "/materialiq/WD_Wood/mq_WD605_ENGINEERED-Plywood-Wavy",
    "2W_Wood_Twisted_mqn": "/materialiq/WD_Wood/mq_WD715_TROPICAL-Twisted",
    "2X_Wood_Old-Dry_mqn": "/materialiq/WD_Wood/mq_WD012_DECIDUOUS-Oak-Dry",
    "2Y_Wood_Cherry_mqn": "/materialiq/WD_Wood/mq_WD265_DECIDUOUS-Cherry",
    "2Z_Wood_Walnut_mqn": "/materialiq/WD_Wood/mq_WD140_DECIDUOUS-Walnut",
    # category: 3
    "3A_Limestone_mqn": "/materialiq/ST_Stone/mq_ST281_PROCESSED-Limestone-Smooth",
    "3B_Basalt_Black_mqn": "/materialiq/ST_Stone/mq_ST009_NATURAL-Basalt-Even",
    "3C_Basalt_Grey_mqn": "/materialiq/ST_Stone/mq_ST010_NATURAL-Basalt-Uneven",
    "3D_Granite_Flamed_mqn": "/materialiq/ST_Stone/mq_ST202_PROCESSED-Granite-Flamed",
    "3E_Granite_mqn": "/materialiq/ST_Stone/mq_ST200_PROCESSED-Granite",
    "3F_Travertine_mqn": "/materialiq/ST_Stone/mq_ST510_EXOTIC-Travertine-Quarry",
    "3G_Granite_Pink_mqn": "/materialiq/ST_Stone/mq_ST204_PROCESSED-Granite-Pink",
    "3H_Granite_CoarseGrained_mqn": "/materialiq/ST_Stone/mq_ST201_PROCESSED-Granite-Coarse",
    "3I_Limestone_Borgos_mqn": "/materialiq/ST_Stone/mq_ST280_PROCESSED-Limestone-Sandblasted",
    "3J_Stone_Porphyritic_mqn": "/materialiq/ST_Stone/mq_ST181_NATURAL-Porphyritic",
    "3K_Marble_Carrara_mqn": "/materialiq/ST_Stone/mq_ST234_PROCESSED-Marble-Carrara",
    "3L_Marble_Breccia_Sarda_mqn": "/materialiq/ST_Stone/mq_ST231_PROCESSED-Marble-Breccia-Sarda",
    "3M_Marble_Marfil_mqn": "/materialiq/ST_Stone/mq_ST236_PROCESSED-Marble-Marfil",
    "3N_Marble_Nero_mqn": "/materialiq/ST_Stone/mq_ST239_PROCESSED-Marble-Nero",
    "3O_Marble_Calacatta_Oro_mqn": "/materialiq/ST_Stone/mq_ST232_PROCESSED-Marble-Calacatta-Oro",
    "3P_Marble_Bianco_Carrara_mqn": "/materialiq/ST_Stone/mq_ST230_PROCESSED-Marble-Bianco-Carrara",
    "3Q_Travertine_Natural_mqn": "/materialiq/ST_Stone/mq_ST500_EXOTIC-Travertine-Natural",
    "3R_Rock_Sandstone_mqn": "/materialiq/ST_Stone/mq_ST060_NATURAL-Sandstone",
    "3S_Rock_Armour_mqn": "/materialiq/ST_Stone/mq_ST180_NATURAL-Armour",
    "3T_Marble_Canyon_Dawn_mqn": "/materialiq/ST_Stone/mq_ST233_PROCESSED-Marble-Canyon-Dawn",
    "3U_Rock_Cliff_mqn": "/materialiq/ST_Stone/mq_ST031_NATURAL-Granite-Cliff",
    "3V_Marble_Volakas_mqn": "/materialiq/ST_Stone/mq_ST238_PROCESSED-Marble-Volakas",
    "3W_Stone_Granite_Brown_mqn": "/materialiq/ST_Stone/mq_ST030_NATURAL-Granite-Brown",
    "3X_Onyx_mqn": "/materialiq/ST_Stone/mq_ST520_EXOTIC-Onyx-Polished",
    "3Y_Rock_Mossy_mqn": "/materialiq/ST_Stone/mq_ST190_NATURAL-Mossy-Rock",
    "3Z_Rock_Slate_mqn": "/materialiq/ST_Stone/mq_ST080_NATURAL-Slate",
    # category: 4
    "4A_Fabric_Even_mqn": "/materialiq/FB_Fabric/mq_FB410_POLYESTER-Fabric-Even",
    "4B_Fabric_Uneven_mqn": "/materialiq/FB_Fabric/mq_FB411_POLYESTER-Fabric-Uneven",
    "4C_Leather_Black_mqn": "/materialiq/FB_Fabric/mq_FB006_LEATHER-Pleather-Grunges",
    "4D_Leather_White_mqn": "/materialiq/FB_Fabric/mq_FB004_LEATHER-Pleather-White",
    "4E_Leather_Brown_mqn": "/materialiq/FB_Fabric/mq_FB001_LEATHER-Cow-Flat-Grain",
    "4F_Leather_Brown_Worn_mqn": "/materialiq/FB_Fabric/mq_FB002_LEATHER-Cow-Damaged",
    "4G_Suede_Brown_mqn": "/materialiq/FB_Fabric/mq_FB008_LEATHER-Suede",
    "4H_Satin_mqn": "/materialiq/FB_Fabric/mq_FB550_SATIN-Classic",
    "4I_Velvet_mqn": "/materialiq/FB_Fabric/mq_FB906_UNSORTED-Velvet-Microfibre",
    "4J_Carpet_Rough_mqn": "/materialiq/FB_Fabric/mq_FB205_CARPET-Office-Rough",
    "4K_Carpet_Wool_mqn": "/materialiq/FB_Fabric/mq_FB205_CARPET-Office-Rough",
    # category: 5
    "5A_Brick_Worn_mqn": "/materialiq/WL_Walls/mq_WL005_BRICK-English-Bond-Worn-Stained",
    "5B_Brick_Classic_mqn": "/materialiq/WL_Walls/mq_WL030_BRICK-Running-Bond-Classic",
    "5CC_Brick_Stained_mqn": "/materialiq/WL_Walls/mq_WL001_BRICK-English-Bond-Stained",
    "5C_Brick_4to1_mqn": "/materialiq/WL_Walls/mq_WL031_BRICK-Running-Bond-Grey",
    "5DD_Plaster_Thin-Layer_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS002_PLASTER-Thin-Layer",
    "5D_Plaster_Smooth_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS200_STUCCO-Basic",
    "5EE_Plaster_Sand-Structure_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS012_PLASTER-Sand-Structure",
    "5E_Plaster_Rough_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS003_PLASTER-Rough",
    "5FF_Plaster_Decorative-Texture_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS006_PLASTER-Decorative",
    "5F_Plaster_Worn_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS009_PLASTER-Worn",
    "5GG_Plaster_Scratched-Structure_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS010_PLASTER-Scratched-Structure",
    "5G_Plaster_Stucco_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS211_STUCCO-Sand-Finish",
    "5HH_Plaster_Lime-Rural_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS022_PLASTER-Lime-Daub",
    "5H_WoodenWool_Board_mqn": "/materialiq/WD_Wood/mq_WD645_ENGINEERED-Wooden-Wool-Board",
    "5II_Plaster_Curvy-Decor_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS005_PLASTER-Curvy-Decor",
    "5I_Stonewall_Random_mqn": "/materialiq/WL_Walls/mq_WL222_STONE-Limestone-Random",
    "5JJ_Plaster_Netted_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS011_PLASTER-Netted",
    "5J_Stonewall_Groutless_mqn": "/materialiq/WL_Walls/mq_WL220_STONE-Limestone-Ashlar-Rough",
    "5KK_Plaster_Deep-Structure-1_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS205_STUCCO-Deep-Structure",
    "5K_Stonewall_Uneven_mqn": "/materialiq/WL_Walls/mq_WL200_STONE-Rubble-Uncoursed",
    "5LL_Concrete_Painted_mqn": "/materialiq/CC_Concrete/mq_CC620_COLORED-Painted",
    "5L_Brick_Worn_Dented_mqn": "/materialiq/WL_Walls/mq_WL020_BRICK-American-Bond-Worn",
    "5MM_Plaster_Mosaic-Marble_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS023_PLASTER-Marble-Mosaic",
    "5M_Stonewall_Muddy_mqn": "/materialiq/WL_Walls/mq_WL221_STONE-Limestone-Random-Mud",
    "5NN_Plaster_Deep-Structure-2_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS206_STUCCO-Deep-Structure",
    "5N_Stonewall_Blocks_Sharp_mqn": "/materialiq/WL_Walls/mq_WL230_STONE-Granite-Rubble-Uncoursed",
    "5OO_Plaster_Deep-Structure-3_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS207_STUCCO-Deep-Structure",
    "5O_Stonewall_SandyBlue_mqn": "/materialiq/WL_Walls/mq_WL210_STONE-Basalt-Ashlar-Regular",
    "5PP_Plaster_Unfinished_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS026_PLASTER-Unfinished",
    "5P_Stonewall_Slate_Groutless_mqn": "/materialiq/WL_Walls/mq_WL240_STONE-Slate-Ashlar-Regular-Dry",
    "5QQ_Plaster_Antique_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS021_PLASTER-Antique-Paint",
    "5Q_Stonewall_Slate_mqn": "/materialiq/WL_Walls/mq_WL242_STONE-Slate-Split-Face-Regular",
    "5RR_Roof_Slate_mqn": "/materialiq/RF_Roof/mq_RF700_SLATE-Cupped",
    "5R_Roof_BarrelTiles_mqn": "/materialiq/RF_Roof/mq_RF205_CERAMIC-Barrel-Tiles",
    "5SS_Roof_Wooden-Shingles_mqn": "/materialiq/RF_Roof/mq_RF800_WOOD-Shingles",
    "5S_Stonewall_Slate_SplitStone_mqn": "/materialiq/WL_Walls/mq_WL241_STONE-Slate-Split-Face-Fine",
    "5TT_Plaster_Old-Layers_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS024_PLASTER-Old-Layers",
    "5T_Stonewall_Travertine_mqn": "/materialiq/WL_Walls/mq_WL250_STONE-Travertine-Rubble-Coursed",
    "5UU_Plaster_Psoriasis_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS210_STUCCO-Psoriasis",
    "5U_Wall_RocksInConcrete_mqn": "/materialiq/CC_Concrete/mq_CC215_ARCH-Washed",
    "5VV_Plaster_Marble-Paint_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS007_PLASTER-Marble-Paint",
    "5V_Roof_STiles_mqn": "/materialiq/RF_Roof/mq_RF200_CERAMIC-STiles",
    "5WW_Plaster_Moldy_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS025_PLASTER-Moldy",
    "5W_Roof_Fibre-cement_mqn": "/materialiq/RF_Roof/mq_RF002_ASPHALT-Fibre-Cement",
    "5XX_Plaster_Crumbs_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS201_STUCCO-Crumbs",
    "5X_Roof_Colored-Tiles_mqn": "/materialiq/RF_Roof/mq_RF001_ASPHALT-Colored-Tiles",
    "5YY_Brindle_Paint_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS008_PLASTER-Brindle-Paint",
    # category: 6
    "6A_Plastic_Glossy_mqn": "/materialiq/MM_Moldable-Materials/mq_MM001_PLASTIC-Glossy",
    "6B_Plastic_Matte_mqn": "/materialiq/MM_Moldable-Materials/mq_MM005_PLASTIC-Matte",
    "6C_Rubber_mqn": "/materialiq/MM_Moldable-Materials/mq_MM101_RUBBER-Basic-Black",
    "6G_Ceramic_Glazed_mqn": "/materialiq/MM_Moldable-Materials/mq_MM305_STONEWARE-Glazed",
    "6H_Clay_mqn": "/materialiq/MM_Moldable-Materials/mq_MM205_EARTHENWARE-Clay",
    # 6I_Polycarbonate_Ribbed_mqm doesn't have its nodegroup..
    "6D_Polycarbonate_mqn": "/materialiq/TR_Transparent/mq_TR600_PLASTIC-Polycarbonate",
    "6J_GFRP_mqn": "/materialiq/MM_Moldable-Materials/mq_MM050_PLASTIC-GFRP",
    # 6E_Acrylic_mqm doesn't have its nodegroup..
    # 6F_ETFE_mqm doesn't have its nodegroup..
    # 6K_BubbleWrap_mqm doesn't have its nodegroup..
    # category: 7
    # 7A_Glass_mqm doesn't have its nodegroup.. "mq_TR000_GLASS_Classic.blend"
    # 7B_Glass_Darkened_mqm doesn't have its nodegroup.. "mq_TR010_GLASS_Dark.blend"
    # 7C_Glass_Frosted_mqm doesn't have its nodegroup..
    # 7D_Mirror_mqm doesn't have its nodegroup..
    # 7E_Glass_Milky_mqm doesn't have its nodegroup.. "mq_TR030_GLASS_Milky.blend"
    # 7F_Glass_Safety_mqm doesn't have its nodegroup.. "mq_TR001_GLASS_Classic-Tempered-Green.blend"
    # 7_Waterial_mqn multiple materials use this node_tree -> we need to distinguish them based on
    #     material name. Namely 7G_Water_Ocean_mqm, 7H_Water_Lake_mqm, 7I_Water_Pond_mqm and
    #     7J_Water_SwimmingPool_mqm uses it.
    "7G_Water_Shoreline_mqn": None,
    # 7K_Water_Frosted_mqm doesn't have its nodegroup.. xxx
    # category: 8
    "8A_Asphalt_Clean_mqn": "/materialiq/GN_Ground/mq_GN001_SURFACE-Asphalt-Clean",
    "8B_Asphalt_New_mqn": "/materialiq/GN_Ground/mq_GN001_SURFACE-Asphalt-Clean",
    "8C_Floor_Studded_mqn": "/materialiq/GN_Ground/mq_GN401_RESERVED-Studded-Floor",
    "8D_Pavement_Permeable_mqn": "/materialiq/GN_Ground/mq_GN195_PAVING-Permeable-Grass",
    "8E_Pavement_Flagstone_mqn": "/materialiq/GN_Ground/mq_GN111_PAVING-Flagstone-Sandstone",
    "8F_WoodenChips_mqn": None,
    "8G_Tartan_mqn": "/materialiq/GN_Ground/mq_GN011_SURFACE-Tartan",
    "8H_RoadMarking_mqn": "/materialiq/GN_Ground/mq_GN090_SURFACE-Road-Marking",
    "8I_Gravel_Large_mqn": "/materialiq/GN_Ground/mq_GN701_GRAVEL-Large",
    "8J_Gravel_Small_mqn": "/materialiq/GN_Ground/mq_GN700_GRAVEL-Small",
    "8K_Pavement_Cobblestone_mqn": "/materialiq/GN_Ground/mq_GN115_PAVING-Cobblestone",
    "8S_Pebbles_Sharp_mqn": "/materialiq/GN_Ground/mq_GN750_GRAVEL-Pebbles-Sharp",
    # category: 9
    "9A_Grass_mqn": "/materialiq/GN_Ground/mq_GN501_GROWTH-Lawn",
    "9B_Sand_Beach_mqn": "/materialiq/GN_Ground/mq_GN650_SOIL-Sand-Beach",
    "9C_Sand_Clean_mqn": "/materialiq/GN_Ground/mq_GN651_SOIL-Sand-Clean",
    "9D_Soil_Rough_mqn": "/materialiq/GN_Ground/mq_GN607_SOIL-Rough",
    "9E_SeaBed_mqn": "/materialiq/GN_Ground/mq_GN630_SOIL-River-Bottom",
    "9F_Soil_Loose_mqn": "/materialiq/GN_Ground/mq_GN606_SOIL-Loose",
    "9G_Soil_Dry_Cracked_mqn": "/materialiq/GN_Ground/mq_GN605_SOIL-Dry-Cracked",
    "9H_Forest_Leafy_mqn": "/materialiq/GN_Ground/mq_GN641_SOIL-Forest-Leafy",
    "9I_Cloverfield_mqn": "/materialiq/GN_Ground/mq_GN502_GROWTH-Grass-Clovers",
    "9J_Moss_mqn": "/materialiq/GN_Ground/mq_GN521_GROWTH-Grass-Mossy",
    "9K_Forest_Needles_mqn": "/materialiq/GN_Ground/mq_GN640_SOIL-Forest",
    "9L_Lawn-and-Leaves_mqn": "/materialiq/GN_Ground/mq_GN503_GROWTH-Grass-Leaves",
    # category: G
    # GA_Generic_White_mqm doesn't have its nodegroup.. "mq_GE010_COLOR-White.blend"
    # GB_Generic_Grey_mqm doesn't have its nodegroup..  "mq_GE006_COLOR-Gray-50.blend"
    # GC_Generic_Black_mqm doesn't have its nodegroup.. "mq_GE002_COLOR-Black.blend"
    # GD_Generic_Red_mqm doesn't have its nodegroup..   "mq_GE011_COLOR-Red.blend"
    # GE_Generic_Green_mqm doesn't have its nodegroup.. "mq_GE019_COLOR-Green.blend"
    # GF_Generic_Blue_mqm doesn't have its nodegroup..  "mq_GE017_COLOR-Blue.blend"
    # GG_Generic_Cyan_mqm doesn't have its nodegroup..  "mq_GE018_COLOR-Cyan.blend"
    # GH_Generic_Magenta_mqm doesn't have its nodegroup.. "mq_GE012_COLOR-Magenta.blend"
    # GI_Generic_Yellow_mqm doesn't have its nodegroup.. "mq_GE014_COLOR-Yellow.blend"
    # GJ_Generic_Brown_mqm doesn't have its nodegroup..  "mq_GE020_COLOR-Brown.blend"
    # GK_Generic_Violet_mqm doesn't have its nodegroup.. "mq_GE016_COLOR-Violet.blend"
    # category: V
    "VA_CarbonFiber_mqn": "/materialiq/FB_Fabric/mq_FB805_FIRM-Carbon-Plain",
    "VB_PhotoVoltaics_mqn": "/materialiq/ML_Metal/mq_ML930_UNSORTED-Solar-Panel",
    "VC_Venetian_Cane_mqn": "/materialiq/WD_Wood/mq_WD792_TROPICAL-Venetian-Cane",
    "VD_Diamond_Plate_mqn": "/materialiq/ML_Metal/mq_ML050_STEEL-Plated-Checker",
    "VE_Expanded_Metal_mqn": "/materialiq/ML_Metal/mq_ML800_ALPHA-Expanded",
    "VF_Metal_Wire_mqn": "/materialiq/ML_Metal/mq_ML810_ALPHA-Wire-Fence",
    "VG_Green_Wall_mqn": "/materialiq/WS_Wall-Surfaces/mq_WS800_VEGETATION-Green-Wall",
    "VH_Rattan_mqn": "/materialiq/WD_Wood/mq_WD791_TROPICAL-Rattan",
    "VI_Metal_Plating_mqn": "/materialiq/ML_Metal/mq_ML921_UNSORTED-Pressed-Brick",
    "VJ_Woven_Bamboo_mqn": "/materialiq/WD_Wood/mq_WD794_TROPICAL-Bamboo-Woven",
    "VK_Steel_Cable_mqn": "/materialiq/ML_Metal/mq_ML060_STEEL-Stainless-Cable",
    "VL_Paper_Crumbled_mqn": "/materialiq/WD_Wood/mq_WD890_VARIOUS-Paper-Crumbled",
    "VM_Wood_Filled-Frame_mqn": "/materialiq/WD_Wood/mq_WD635_ENGINEERED-Wood-Filled-Frame",
    "VN_Snow_mqn": None
}

MQ4_MATERIAL_NAMES_TO_MQ = {
    "6E_Acrylic_mqm": "/materialiq/TR_Transparent/mq_TR610_PLASTIC-Acrylic",
    "6F_ETFE_mqm": "/materialiq/TR_Transparent/mq_TR620_PLASTIC-ETFE-Foil",
    "6I_Polycarbonate_Ribbed_mqm": "/materialiq/TR_Transparent/mq_TR605_PLASTIC-Polycarbonate-Ribbed",
    "6K_BubbleWrap_mqm": "/materialiq/TR_Transparent/mq_TR695_PLASTIC-Bubblewrap",
    "7A_Glass_mqm": "/materialiq/TR_Transparent/mq_TR000_GLASS-Classic",
    "7B_Glass_Darkened_mqm": "/materialiq/TR_Transparent/mq_TR010_GLASS-Dark",
    "7C_Glass_Frosted_mqm": "/materialiq/TR_Transparent/mq_TR031_GLASS-Frosted",
    "7D_Mirror_mqm": "/materialiq/TR_Transparent/mq_TR015_GLASS-Mirror",
    "7E_Glass_Milky_mqm": "/materialiq/TR_Transparent/mq_TR030_GLASS-Milky",
    "7F_Glass_Safety_mqm": "/materialiq/TR_Transparent/mq_TR035_GLASS-Safety",
    "7G_Water_Ocean_mqm": "/materialiq/TR_Transparent/mq_TR900_WATER-Ocean",
    "7H_Water_Lake_mqm": "/materialiq/TR_Transparent/mq_TR905_WATER-Lake",
    "7I_Water_Pond_mqm": "/materialiq/TR_Transparent/mq_TR910_WATER-Pond",
    "7J_Water_SwimmingPool_mqm": "/materialiq/TR_Transparent/mq_TR915_WATER-Swimming-Pool",
    "GA_Generic_White_mqm": "/materialiq/GE_Generic/mq_GE010_COLOR-White",
    "GB_Generic_Grey_mqm": "/materialiq/GE_Generic/mq_GE006_COLOR-Gray-50",
    "GC_Generic_Black_mqm": "/materialiq/GE_Generic/mq_GE002_COLOR-Black",
    "GD_Generic_Red_mqm": "/materialiq/GE_Generic/mq_GE011_COLOR-Red",
    "GE_Generic_Green_mqm": "/materialiq/GE_Generic/mq_GE019_COLOR-Green",
    "GF_Generic_Blue_mqm": "/materialiq/GE_Generic/mq_GE017_COLOR-Blue",
    "GG_Generic_Cyan_mqm": "/materialiq/GE_Generic/mq_GE018_COLOR-Cyan",
    "GH_Generic_Magenta_mqm": "/materialiq/GE_Generic/mq_GE012_COLOR-Magenta",
    "GI_Generic_Yellow_mqm": "/materialiq/GE_Generic/mq_GE014_COLOR-Yellow",
    "GJ_Generic_Brown_mqm": "/materialiq/GE_Generic/mq_GE020_COLOR-Brown",
    "GK_Generic_Violet_mqm": "/materialiq/GE_Generic/mq_GE016_COLOR-Violet",
}
